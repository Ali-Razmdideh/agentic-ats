"""Run repository — org-scoped."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

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
    ) -> int:
        run = Run(
            org_id=self._org_id,
            jd_path=jd_path,
            jd_hash=jd_hash,
            jd_blob_key=jd_blob_key,
            status=RunStatus.running,
            created_by_user_id=created_by_user_id,
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
        }
