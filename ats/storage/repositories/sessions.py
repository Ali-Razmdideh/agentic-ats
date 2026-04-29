"""Session repository — NOT org-scoped (sessions belong to a user, not an org)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ats.storage.models import Session


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        session_id: str,
        user_id: int,
        ttl: timedelta,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> Session:
        s = Session(
            id=session_id,
            user_id=user_id,
            expires_at=datetime.now(timezone.utc) + ttl,
            user_agent=user_agent,
            ip=ip,
        )
        self._session.add(s)
        await self._session.flush()
        return s

    async def get_active(self, session_id: str) -> Session | None:
        res = await self._session.execute(
            select(Session).where(
                Session.id == session_id,
                Session.revoked_at.is_(None),
                Session.expires_at > datetime.now(timezone.utc),
            )
        )
        return res.scalar_one_or_none()

    async def touch(self, session_id: str) -> None:
        await self._session.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(last_seen_at=datetime.now(timezone.utc))
        )

    async def revoke(self, session_id: str) -> None:
        await self._session.execute(
            update(Session)
            .where(Session.id == session_id, Session.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
