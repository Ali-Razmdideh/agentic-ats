"""Test fixtures + tenant-leak collection guard.

Requires Docker. Tests that depend on the ``pg_*`` fixtures skip cleanly
if testcontainers cannot start a container (e.g. CI without Docker).
"""

from __future__ import annotations

from typing import Iterator

import pytest
import pytest_asyncio

try:
    from testcontainers.postgres import (  # type: ignore[import-not-found]  # noqa: E501
        PostgresContainer,
    )

    _TC_AVAILABLE = True
except Exception:  # pragma: no cover
    PostgresContainer = None  # type: ignore[assignment]
    _TC_AVAILABLE = False

from ats.config import Settings
from ats.storage.db import make_engine, make_sessionmaker
from ats.storage.models import Base
from ats.storage.repositories.base import OrgScopedRepository

# --------------------------- Postgres container ----------------------------


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    if not _TC_AVAILABLE:
        pytest.skip("testcontainers not installed; skipping Postgres tests")
    try:
        container = PostgresContainer("postgres:16")
        container.start()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Could not start Postgres container: {exc}")

    raw = container.get_connection_url()
    url = raw.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
        "postgresql://", "postgresql+asyncpg://"
    )
    try:
        yield url
    finally:
        container.stop()


@pytest.fixture(scope="session")
def pg_settings(pg_url: str) -> Settings:
    return Settings(pg_dsn=pg_url, pg_pool_size=2, pg_pool_max_over=2)


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def pg_engine(pg_settings: Settings):  # type: ignore[no-untyped-def]
    engine = make_engine(pg_settings)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS citext")
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def pg_sessionmaker(pg_engine):  # type: ignore[no-untyped-def]
    """Truncate all tables before yielding the sessionmaker.

    Per-test isolation: every test starts with empty tables and reset
    identity sequences. Cheaper than recreating the schema.
    """
    from sqlalchemy import text

    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE audits, shortlists, scores, candidates, "
                "runs, memberships, users, orgs RESTART IDENTITY CASCADE"
            )
        )
    yield make_sessionmaker(pg_engine)


# ----------------- Collection-time tenant-leak opt-in guard ----------------


def _all_subclasses(cls: type) -> set[type]:
    out: set[type] = set()
    stack = [cls]
    while stack:
        c = stack.pop()
        for s in c.__subclasses__():
            if s not in out:
                out.add(s)
                stack.append(s)
    return out


def pytest_collection_finish(session: pytest.Session) -> None:
    import ats.storage.repositories  # noqa: F401

    missing = [
        cls.__name__
        for cls in _all_subclasses(OrgScopedRepository)
        if not getattr(cls, "__leak_test__", False)
    ]
    if missing:
        raise pytest.UsageError(
            "OrgScopedRepository subclasses missing __leak_test__ = True: "
            + ", ".join(missing)
        )
