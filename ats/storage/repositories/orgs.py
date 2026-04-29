"""Org repository — NOT org-scoped (it manages tenants themselves)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ats.storage.models import Org


class OrgRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_slug(self, slug: str) -> Org | None:
        res = await self._session.execute(select(Org).where(Org.slug == slug))
        return res.scalar_one_or_none()

    async def get_by_id(self, org_id: int) -> Org | None:
        res = await self._session.execute(select(Org).where(Org.id == org_id))
        return res.scalar_one_or_none()

    async def create(self, slug: str, name: str) -> Org:
        org = Org(slug=slug, name=name)
        self._session.add(org)
        await self._session.flush()
        return org

    async def get_or_create(self, slug: str, name: str) -> Org:
        existing = await self.get_by_slug(slug)
        if existing is not None:
            return existing
        return await self.create(slug, name)
