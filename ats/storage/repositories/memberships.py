"""Membership repository — joins users and orgs with a role."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ats.storage.models import Membership, Role


class MembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, org_id: int, user_id: int, role: Role) -> Membership:
        m = Membership(org_id=org_id, user_id=user_id, role=role)
        self._session.add(m)
        await self._session.flush()
        return m

    async def get(self, org_id: int, user_id: int) -> Membership | None:
        res = await self._session.execute(
            select(Membership).where(
                Membership.org_id == org_id, Membership.user_id == user_id
            )
        )
        return res.scalar_one_or_none()

    async def list_for_user(self, user_id: int) -> list[Membership]:
        res = await self._session.execute(
            select(Membership).where(Membership.user_id == user_id)
        )
        return list(res.scalars())
