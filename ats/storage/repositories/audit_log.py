"""Append-only audit log repository — compliance trail.

Distinct from ``audits`` (which holds per-agent outputs). The audit log
records reviewer + worker actions for legal/compliance review. Org-scoped
like every other writeable repo, but the worker writes events without an
``actor_user_id`` (system events), so ``log_event_unscoped`` is exposed
on the module too for callers outside a normal ``uow`` boundary.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ats.storage.models import ActorKind, AuditLog
from ats.storage.repositories.base import OrgScopedRepository


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
        row = AuditLog(
            org_id=self._org_id,
            actor_user_id=actor_user_id,
            actor_kind=actor_kind,
            kind=kind,
            target_kind=target_kind,
            target_id=target_id,
            payload=payload,
        )
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
    """Append an audit event without going through a tenant-scoped uow.

    The worker uses this to log run lifecycle events; it knows the run's
    org_id from the row it just claimed and doesn't always have a
    full RepositoryBundle in scope.
    """
    row = AuditLog(
        org_id=org_id,
        actor_user_id=actor_user_id,
        actor_kind=actor_kind,
        kind=kind,
        target_kind=target_kind,
        target_id=target_id,
        payload=payload,
    )
    session.add(row)
    await session.flush()
    return int(row.id)
