"""Shortlist repository — org-scoped via composite FK to runs+candidates."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy.dialects.postgresql import insert as pg_insert

from ats.storage.models import Shortlist
from ats.storage.repositories.base import OrgScopedRepository


class ShortlistRepository(OrgScopedRepository[Shortlist]):
    Model = Shortlist
    __leak_test__ = True

    async def write(self, run_id: int, ranked: Sequence[tuple[int, str]]) -> None:
        for rank, (candidate_id, decision) in enumerate(ranked, start=1):
            stmt = pg_insert(Shortlist).values(
                run_id=run_id,
                candidate_id=candidate_id,
                org_id=self._org_id,
                rank=rank,
                decision=decision,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[Shortlist.run_id, Shortlist.candidate_id],
                set_={"rank": stmt.excluded.rank, "decision": stmt.excluded.decision},
            )
            await self._session.execute(stmt)
