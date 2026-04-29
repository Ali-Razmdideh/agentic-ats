"""Unit-of-work + ContextVar wiring.

Two entry points:

- ``uow(sessionmaker, org_id)`` — explicit async context manager that opens
  one ``AsyncSession`` and exposes a ``RepositoryBundle``. Commits on clean
  exit, rolls back on exception. The orchestrator and CLI use this directly.

- ``current_uow()`` — reads the active sessionmaker + org from a ``ContextVar``
  set by ``run_context()``. MCP tool handlers (``ats/tools/db_tools.py``) use
  this so they don't need every caller to thread a session through.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ats.storage.repositories import (
    AuditRepository,
    CandidateCommentRepository,
    CandidateRepository,
    DecisionRepository,
    MembershipRepository,
    OrgRepository,
    RunRepository,
    ScoreRepository,
    SessionRepository,
    ShortlistRepository,
    UserRepository,
)


@dataclass
class RepositoryBundle:
    session: AsyncSession
    org_id: int
    runs: RunRepository
    candidates: CandidateRepository
    scores: ScoreRepository
    shortlists: ShortlistRepository
    audits: AuditRepository
    decisions: DecisionRepository
    comments: CandidateCommentRepository
    orgs: OrgRepository
    users: UserRepository
    memberships: MembershipRepository
    sessions: SessionRepository


def _build_bundle(session: AsyncSession, org_id: int) -> RepositoryBundle:
    return RepositoryBundle(
        session=session,
        org_id=org_id,
        runs=RunRepository(session, org_id),
        candidates=CandidateRepository(session, org_id),
        scores=ScoreRepository(session, org_id),
        shortlists=ShortlistRepository(session, org_id),
        audits=AuditRepository(session, org_id),
        decisions=DecisionRepository(session, org_id),
        comments=CandidateCommentRepository(session, org_id),
        orgs=OrgRepository(session),
        users=UserRepository(session),
        memberships=MembershipRepository(session),
        sessions=SessionRepository(session),
    )


@asynccontextmanager
async def uow(
    sessionmaker: async_sessionmaker[AsyncSession],
    org_id: int,
) -> AsyncIterator[RepositoryBundle]:
    async with sessionmaker() as session:
        try:
            yield _build_bundle(session, org_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@dataclass
class _RunCtx:
    sessionmaker: async_sessionmaker[AsyncSession]
    org_id: int


_current: ContextVar[_RunCtx | None] = ContextVar("ats_run_ctx", default=None)


@asynccontextmanager
async def run_context(
    sessionmaker: async_sessionmaker[AsyncSession],
    org_id: int,
) -> AsyncIterator[None]:
    """Set the ambient sessionmaker + org for the duration of a run.

    MCP tool handlers can then call ``current_uow()`` to open a fresh
    short session against the right tenant without being passed one.
    """
    token = _current.set(_RunCtx(sessionmaker=sessionmaker, org_id=org_id))
    try:
        yield
    finally:
        _current.reset(token)


@asynccontextmanager
async def current_uow() -> AsyncIterator[RepositoryBundle]:
    ctx = _current.get()
    if ctx is None:
        raise RuntimeError(
            "current_uow() called outside run_context(); orchestrator must "
            "establish a run context before tool handlers run"
        )
    async with uow(ctx.sessionmaker, ctx.org_id) as repos:
        yield repos
