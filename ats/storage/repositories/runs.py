"""Run repository — org-scoped, plus worker-queue helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ats.storage.models import Run, RunStatus
from ats.storage.repositories.base import OrgScopedRepository


class RunRepository(OrgScopedRepository[Run]):
    Model = Run
    __leak_test__ = True

    async def create(
        self,
        jd_path: str,
        jd_hash: str,
        jd_blob_key: str | None = None,
        created_by_user_id: int | None = None,
        status: RunStatus = RunStatus.running,
        queued_inputs: dict[str, Any] | None = None,
    ) -> int:
        run = Run(
            org_id=self._org_id,
            jd_path=jd_path,
            jd_hash=jd_hash,
            jd_blob_key=jd_blob_key,
            status=status,
            created_by_user_id=created_by_user_id,
            queued_inputs=queued_inputs,
        )
        self._session.add(run)
        await self._session.flush()
        return int(run.id)

    async def finish(self, run_id: int, status: RunStatus | str) -> None:
        s = RunStatus(status) if isinstance(status, str) else status
        await self._session.execute(
            update(Run)
            .where(Run.id == run_id, Run.org_id == self._org_id)
            .values(finished_at=datetime.now(timezone.utc), status=s)
        )

    async def update_usage(self, run_id: int, usage: dict[str, Any]) -> None:
        await self._session.execute(
            update(Run)
            .where(Run.id == run_id, Run.org_id == self._org_id)
            .values(usage=usage)
        )

    async def get(self, run_id: int) -> dict[str, Any] | None:
        res = await self._session.execute(
            self._scope(select(Run)).where(Run.id == run_id)
        )
        run = res.scalar_one_or_none()
        if run is None:
            return None
        return {
            "id": run.id,
            "org_id": run.org_id,
            "jd_path": run.jd_path,
            "jd_hash": run.jd_hash,
            "jd_blob_key": run.jd_blob_key,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "status": run.status.value,
            "usage": run.usage,
            "created_by_user_id": run.created_by_user_id,
            "queued_inputs": run.queued_inputs,
        }

    async def list_for_org(self, limit: int = 50) -> list[dict[str, Any]]:
        res = await self._session.execute(
            self._scope(select(Run)).order_by(Run.id.desc()).limit(limit)
        )
        return [
            {
                "id": r.id,
                "status": r.status.value,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "jd_path": r.jd_path,
                "created_by_user_id": r.created_by_user_id,
            }
            for r in res.scalars()
        ]


async def claim_next_queued_run(
    session: AsyncSession, worker_id: str
) -> dict[str, Any] | None:
    """Claim the oldest queued run via FOR UPDATE SKIP LOCKED.

    Not tenant-scoped: the worker is a system-level process that processes
    runs from every org. Returns ``None`` when the queue is empty.
    """
    sql = text(
        """
        UPDATE runs
        SET status = 'running',
            worker_id = :wid,
            claimed_at = now()
        WHERE id = (
            SELECT id FROM runs
            WHERE status = 'queued'
            ORDER BY started_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING id, org_id, queued_inputs;
        """
    )
    res = await session.execute(sql, {"wid": worker_id})
    row = res.mappings().first()
    if row is None:
        return None
    return {
        "id": int(row["id"]),
        "org_id": int(row["org_id"]),
        "queued_inputs": row["queued_inputs"],
    }


async def mark_run_status(
    session: AsyncSession, run_id: int, status: RunStatus
) -> None:
    """Update run status outside of any tenant scope (worker uses this)."""
    await session.execute(
        update(Run)
        .where(Run.id == run_id)
        .values(status=status, finished_at=datetime.now(timezone.utc))
    )
