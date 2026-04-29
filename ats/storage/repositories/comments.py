"""Candidate-comment repository — org-scoped append-only thread."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ats.storage.models import CandidateComment
from ats.storage.repositories.base import OrgScopedRepository


class CandidateCommentRepository(OrgScopedRepository[CandidateComment]):
    Model = CandidateComment
    __leak_test__ = True

    async def add(
        self,
        run_id: int,
        candidate_id: int,
        author_user_id: int,
        body: str,
    ) -> int:
        c = CandidateComment(
            org_id=self._org_id,
            run_id=run_id,
            candidate_id=candidate_id,
            author_user_id=author_user_id,
            body=body,
        )
        self._session.add(c)
        await self._session.flush()
        return int(c.id)

    async def list_for_candidate(
        self, run_id: int, candidate_id: int
    ) -> list[dict[str, Any]]:
        res = await self._session.execute(
            self._scope(select(CandidateComment))
            .where(
                CandidateComment.run_id == run_id,
                CandidateComment.candidate_id == candidate_id,
            )
            .order_by(CandidateComment.created_at)
        )
        return [
            {
                "id": c.id,
                "author_user_id": c.author_user_id,
                "body": c.body,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in res.scalars()
        ]
