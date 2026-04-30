"""Append-only audit log repository — HMAC-chained compliance trail.

Each new row's ``hash`` is HMAC-SHA256(secret, prev_hash || canonical_json(view))
where ``view`` is the alphabetised dict from
``ats.storage.audit_chain.record_view``. The first row in an org has
prev_hash = ``ZERO_HASH`` (32 zero bytes).

Concurrency: ``append`` takes a Postgres advisory transaction lock keyed
on ``org_id`` so two concurrent writers can't both observe the same
``prev_hash`` (which would let one of their hashes silently drop out of
the chain). The lock is released on transaction commit/rollback.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ats.storage.audit_chain import (
    ZERO_HASH,
    compute_hash,
    now_iso,
    record_view,
)
from ats.storage.models import ActorKind, AuditLog
from ats.storage.repositories.base import OrgScopedRepository


async def _latest_chain_hash(
    session: AsyncSession, org_id: int
) -> bytes:
    """Read the most-recent non-NULL ``hash`` for the org.

    Pre-chain (NULL hash) rows are skipped so the chain starts cleanly
    on the first chained write even if the table already had v1 rows.
    """
    res = await session.execute(
        text(
            """
            SELECT hash FROM audit_log
             WHERE org_id = :org_id AND hash IS NOT NULL
             ORDER BY id DESC LIMIT 1
            """
        ),
        {"org_id": org_id},
    )
    row = res.first()
    if row is None or row[0] is None:
        return ZERO_HASH
    return bytes(row[0])


async def _acquire_org_lock(session: AsyncSession, org_id: int) -> None:
    """Per-org transaction-scoped advisory lock.

    pg_advisory_xact_lock(int8) released automatically at COMMIT/ROLLBACK.
    No conflict with other orgs (different keys) and tiny overhead.
    """
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:k)"),
        {"k": int(org_id)},
    )


class AuditLogRepository(OrgScopedRepository[AuditLog]):
    Model = AuditLog
    __leak_test__ = True

    async def append(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        actor_user_id: int | None,
        actor_kind: ActorKind,
        target_kind: str | None = None,
        target_id: int | None = None,
    ) -> int:
        await _acquire_org_lock(self._session, self._org_id)
        prev = await _latest_chain_hash(self._session, self._org_id)
        created_at = now_iso()
        view = record_view(
            org_id=self._org_id,
            actor_user_id=actor_user_id,
            actor_kind=actor_kind.value,
            kind=kind,
            target_kind=target_kind,
            target_id=target_id,
            payload=payload,
            created_at=created_at,
        )
        h = compute_hash(prev, view)

        row = AuditLog(
            org_id=self._org_id,
            actor_user_id=actor_user_id,
            actor_kind=actor_kind,
            kind=kind,
            target_kind=target_kind,
            target_id=target_id,
            payload=payload,
            prev_hash=prev,
            hash=h,
        )
        # Force created_at so the chain hash matches what's stored.
        # Server default would tick a different microsecond.
        from datetime import datetime as _dt

        row.created_at = _dt.fromisoformat(created_at.replace("Z", "+00:00"))
        self._session.add(row)
        await self._session.flush()
        return int(row.id)

    async def list_for_org(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        kind: str | None = None,
        actor_user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        stmt = self._scope(select(AuditLog)).order_by(AuditLog.id.desc())
        if kind:
            stmt = stmt.where(AuditLog.kind == kind)
        if actor_user_id is not None:
            stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
        stmt = stmt.limit(limit).offset(offset)
        res = await self._session.execute(stmt)
        return [
            {
                "id": r.id,
                "org_id": r.org_id,
                "actor_user_id": r.actor_user_id,
                "actor_kind": r.actor_kind.value,
                "kind": r.kind,
                "target_kind": r.target_kind,
                "target_id": r.target_id,
                "payload": r.payload,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "hash": r.hash.hex() if r.hash else None,
                "prev_hash": r.prev_hash.hex() if r.prev_hash else None,
            }
            for r in res.scalars()
        ]


async def log_event_unscoped(
    session: AsyncSession,
    *,
    org_id: int,
    kind: str,
    payload: dict[str, Any],
    actor_user_id: int | None,
    actor_kind: ActorKind,
    target_kind: str | None = None,
    target_id: int | None = None,
) -> int:
    """Append from outside a tenant-scoped uow. Same chain semantics."""
    await _acquire_org_lock(session, org_id)
    prev = await _latest_chain_hash(session, org_id)
    created_at = now_iso()
    view = record_view(
        org_id=org_id,
        actor_user_id=actor_user_id,
        actor_kind=actor_kind.value,
        kind=kind,
        target_kind=target_kind,
        target_id=target_id,
        payload=payload,
        created_at=created_at,
    )
    h = compute_hash(prev, view)

    from datetime import datetime as _dt

    row = AuditLog(
        org_id=org_id,
        actor_user_id=actor_user_id,
        actor_kind=actor_kind,
        kind=kind,
        target_kind=target_kind,
        target_id=target_id,
        payload=payload,
        prev_hash=prev,
        hash=h,
    )
    row.created_at = _dt.fromisoformat(created_at.replace("Z", "+00:00"))
    session.add(row)
    await session.flush()
    return int(row.id)


# ---------- Verification ---------------------------------------------------


async def verify_chain(
    session: AsyncSession, org_id: int
) -> dict[str, Any]:
    """Walk the org's audit_log in id-order, recompute each hash, report.

    Returns a dict with:
      - status: "ok" | "broken" | "pre_chain_only"
      - total: total rows for the org
      - chained: rows that have non-NULL hash (post-#5b)
      - pre_chain: rows with NULL hash (legacy from #5 v1)
      - first_break: { id, expected, actual } when status="broken"
    """
    res = await session.execute(
        text(
            """
            SELECT id, actor_kind, actor_user_id, created_at, kind, org_id,
                   payload, target_id, target_kind, prev_hash, hash
              FROM audit_log
             WHERE org_id = :org_id
             ORDER BY id ASC
            """
        ),
        {"org_id": org_id},
    )
    rows = res.mappings().all()

    total = len(rows)
    pre_chain = sum(1 for r in rows if r["hash"] is None)
    chained = total - pre_chain
    if chained == 0:
        return {
            "status": "pre_chain_only",
            "total": total,
            "chained": 0,
            "pre_chain": pre_chain,
            "first_break": None,
        }

    expected_prev = ZERO_HASH
    for r in rows:
        if r["hash"] is None:
            # legacy row, skip and reset chain root for the next chained row
            continue
        # Build the same view the writer hashed.
        created_at = r["created_at"]
        if hasattr(created_at, "isoformat"):
            created_iso = (
                created_at.isoformat(timespec="milliseconds").replace(
                    "+00:00", "Z"
                )
            )
        else:
            created_iso = str(created_at)
        view = record_view(
            org_id=r["org_id"],
            actor_user_id=r["actor_user_id"],
            actor_kind=str(r["actor_kind"]),
            kind=r["kind"],
            target_kind=r["target_kind"],
            target_id=r["target_id"],
            payload=r["payload"],
            created_at=created_iso,
        )
        actual = compute_hash(expected_prev, view)
        stored = bytes(r["hash"])
        if actual != stored:
            return {
                "status": "broken",
                "total": total,
                "chained": chained,
                "pre_chain": pre_chain,
                "first_break": {
                    "id": int(r["id"]),
                    "expected": actual.hex(),
                    "actual": stored.hex(),
                },
            }
        expected_prev = stored

    return {
        "status": "ok",
        "total": total,
        "chained": chained,
        "pre_chain": pre_chain,
        "first_break": None,
    }
