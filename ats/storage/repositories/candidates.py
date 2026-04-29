"""Candidate repository — org-scoped, with per-org file_hash dedupe."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ats.storage.models import Candidate
from ats.storage.repositories.base import OrgScopedRepository


class CandidateRepository(OrgScopedRepository[Candidate]):
    Model = Candidate
    __leak_test__ = True

    async def upsert(
        self,
        file_hash: str,
        file_blob_key: str,
        parsed: dict[str, Any],
        source_filename: str | None = None,
    ) -> int:
        """Insert-or-fetch by ``(org_id, file_hash)``.

        Race-safe under concurrent writes: uses ``ON CONFLICT DO NOTHING``
        on the per-org unique constraint and falls back to a SELECT if the
        insert was a no-op.
        """
        contact = (parsed.get("contact") or {}) if isinstance(parsed, dict) else {}
        stmt = (
            pg_insert(Candidate)
            .values(
                org_id=self._org_id,
                file_hash=file_hash,
                file_blob_key=file_blob_key,
                source_filename=source_filename,
                name=contact.get("name"),
                email=contact.get("email"),
                phone=contact.get("phone"),
                parsed=parsed,
            )
            .on_conflict_do_nothing(constraint="uq_candidates_org_file_hash")
            .returning(Candidate.id)
        )
        res = await self._session.execute(stmt)
        new_id = res.scalar_one_or_none()
        if new_id is not None:
            return int(new_id)
        # Conflict path: row already exists for this (org_id, file_hash).
        existing = await self._session.execute(
            self._scope(select(Candidate.id)).where(Candidate.file_hash == file_hash)
        )
        return int(existing.scalar_one())

    async def get(self, candidate_id: int) -> dict[str, Any] | None:
        res = await self._session.execute(
            self._scope(select(Candidate)).where(Candidate.id == candidate_id)
        )
        c = res.scalar_one_or_none()
        if c is None:
            return None
        return {
            "id": c.id,
            "org_id": c.org_id,
            "file_hash": c.file_hash,
            "file_blob_key": c.file_blob_key,
            "source_filename": c.source_filename,
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
            "parsed": c.parsed,
        }
