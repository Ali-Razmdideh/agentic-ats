"""Audit repository — org-scoped, append-only event log per run."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ats.storage.models import Audit
from ats.storage.repositories.base import OrgScopedRepository


class AuditRepository(OrgScopedRepository[Audit]):
    Model = Audit
    __leak_test__ = True

    async def write(self, run_id: int, kind: str, payload: dict[str, Any]) -> None:
        a = Audit(org_id=self._org_id, run_id=run_id, kind=kind, payload=payload)
        self._session.add(a)

    async def list_for_run(self, run_id: int) -> list[dict[str, Any]]:
        res = await self._session.execute(
            self._scope(select(Audit)).where(Audit.run_id == run_id).order_by(Audit.id)
        )
        return [{"kind": a.kind, "payload": a.payload} for a in res.scalars()]
