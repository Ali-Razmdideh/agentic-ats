"""Decision repository — org-scoped reviewer accept/reject/hold per candidate."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ats.storage.models import Decision, DecisionKind
from ats.storage.repositories.base import OrgScopedRepository


class DecisionRepository(OrgScopedRepository[Decision]):
    Model = Decision
    __leak_test__ = True

    async def upsert(
        self,
        run_id: int,
        candidate_id: int,
        decision: DecisionKind | str,
        decided_by_user_id: int,
        notes: str | None = None,
    ) -> None:
        kind = (
            decision if isinstance(decision, DecisionKind) else DecisionKind(decision)
        )
        stmt = pg_insert(Decision).values(
            run_id=run_id,
            candidate_id=candidate_id,
            org_id=self._org_id,
            decision=kind,
            notes=notes,
            decided_by_user_id=decided_by_user_id,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Decision.run_id, Decision.candidate_id],
            set_={
                "decision": stmt.excluded.decision,
                "notes": stmt.excluded.notes,
                "decided_by_user_id": stmt.excluded.decided_by_user_id,
            },
        )
        await self._session.execute(stmt)

    async def get(self, run_id: int, candidate_id: int) -> dict[str, Any] | None:
        res = await self._session.execute(
            self._scope(select(Decision)).where(
                Decision.run_id == run_id,
                Decision.candidate_id == candidate_id,
            )
        )
        d = res.scalar_one_or_none()
        if d is None:
            return None
        return {
            "run_id": d.run_id,
            "candidate_id": d.candidate_id,
            "decision": d.decision.value,
            "notes": d.notes,
            "decided_by_user_id": d.decided_by_user_id,
            "decided_at": d.decided_at.isoformat() if d.decided_at else None,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        }

    async def list_for_run(self, run_id: int) -> list[dict[str, Any]]:
        res = await self._session.execute(
            self._scope(select(Decision)).where(Decision.run_id == run_id)
        )
        return [
            {
                "candidate_id": d.candidate_id,
                "decision": d.decision.value,
                "notes": d.notes,
                "decided_by_user_id": d.decided_by_user_id,
            }
            for d in res.scalars()
        ]
