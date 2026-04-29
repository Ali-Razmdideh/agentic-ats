"""Score repository — org-scoped via composite FK to runs+candidates."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ats.storage.models import Candidate, Score
from ats.storage.repositories.base import OrgScopedRepository


class ScoreRepository(OrgScopedRepository[Score]):
    Model = Score
    __leak_test__ = True

    async def write(
        self,
        run_id: int,
        candidate_id: int,
        score: float,
        rationale: str,
        verified: dict[str, Any] | None = None,
    ) -> None:
        stmt = pg_insert(Score).values(
            run_id=run_id,
            candidate_id=candidate_id,
            org_id=self._org_id,
            score=score,
            rationale=rationale,
            verified=verified,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Score.run_id, Score.candidate_id],
            set_={
                "score": stmt.excluded.score,
                "rationale": stmt.excluded.rationale,
                "verified": stmt.excluded.verified,
            },
        )
        await self._session.execute(stmt)

    async def list_for_run(self, run_id: int) -> list[dict[str, Any]]:
        res = await self._session.execute(
            select(
                Score.candidate_id,
                Score.score,
                Score.rationale,
                Candidate.name,
                Candidate.email,
            )
            .join(
                Candidate,
                (Candidate.id == Score.candidate_id)
                & (Candidate.org_id == Score.org_id),
            )
            .where(Score.run_id == run_id, Score.org_id == self._org_id)
            .order_by(Score.score.desc())
        )
        return [dict(r._mapping) for r in res.all()]
