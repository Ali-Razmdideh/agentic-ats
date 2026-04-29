"""Repository CRUD + tenant-leak tests against a real Postgres."""

from __future__ import annotations

import pytest

from ats.storage.models import Org, Role, RunStatus
from ats.storage.uow import _build_bundle, uow

pytestmark = pytest.mark.asyncio


async def _seed_org(sm, slug: str) -> int:  # type: ignore[no-untyped-def]  # noqa: E501
    async with sm() as s:
        org = Org(slug=slug, name=slug.title())
        s.add(org)
        await s.commit()
        return int(org.id)


async def test_runs_basic_lifecycle(pg_sessionmaker) -> None:  # type: ignore[no-untyped-def]  # noqa: E501
    org_id = await _seed_org(pg_sessionmaker, "acme")
    async with uow(pg_sessionmaker, org_id) as repos:
        run_id = await repos.runs.create("/tmp/jd.txt", "h", jd_blob_key="k")
    async with uow(pg_sessionmaker, org_id) as repos:
        await repos.runs.update_usage(run_id, {"tokens": 10})
        await repos.runs.finish(run_id, RunStatus.ok)
    async with uow(pg_sessionmaker, org_id) as repos:
        rec = await repos.runs.get(run_id)
    assert rec is not None
    assert rec["status"] == "ok"
    assert rec["usage"] == {"tokens": 10}


async def test_candidate_dedupe_per_org(pg_sessionmaker) -> None:  # type: ignore[no-untyped-def]  # noqa: E501
    org_id = await _seed_org(pg_sessionmaker, "acme")
    async with uow(pg_sessionmaker, org_id) as repos:
        a = await repos.candidates.upsert("h1", "k1", {"contact": {"name": "A"}})
        b = await repos.candidates.upsert("h1", "k2", {"contact": {"name": "A"}})
    assert a == b


async def test_candidate_same_hash_across_orgs_is_independent(  # type: ignore[no-untyped-def]  # noqa: E501
    pg_sessionmaker,
) -> None:
    a_id = await _seed_org(pg_sessionmaker, "acme")
    b_id = await _seed_org(pg_sessionmaker, "globex")
    async with uow(pg_sessionmaker, a_id) as repos:
        ca = await repos.candidates.upsert(
            "shared_hash", "ka", {"contact": {"name": "A"}}
        )
    async with uow(pg_sessionmaker, b_id) as repos:
        cb = await repos.candidates.upsert(
            "shared_hash", "kb", {"contact": {"name": "B"}}
        )
    assert ca != cb


async def test_score_and_shortlist_round_trip(pg_sessionmaker) -> None:  # type: ignore[no-untyped-def]  # noqa: E501
    org_id = await _seed_org(pg_sessionmaker, "acme")
    async with uow(pg_sessionmaker, org_id) as repos:
        run_id = await repos.runs.create("/jd", "h")
        cid = await repos.candidates.upsert(
            "h1", "k", {"contact": {"name": "X", "email": "x@e.com"}}
        )
        await repos.scores.write(run_id, cid, 0.8, "good", {"v": ["Python"]})
        await repos.shortlists.write(run_id, [(cid, "shortlist")])
    async with uow(pg_sessionmaker, org_id) as repos:
        rows = await repos.scores.list_for_run(run_id)
    assert len(rows) == 1
    assert rows[0]["score"] == 0.8
    assert rows[0]["name"] == "X"


async def test_audit_lifecycle(pg_sessionmaker) -> None:  # type: ignore[no-untyped-def]  # noqa: E501
    org_id = await _seed_org(pg_sessionmaker, "acme")
    async with uow(pg_sessionmaker, org_id) as repos:
        run_id = await repos.runs.create("/jd", "h")
        await repos.audits.write(run_id, "bias", {"status": "pass"})
        await repos.audits.write(run_id, "dedup", {"groups": []})
    async with uow(pg_sessionmaker, org_id) as repos:
        events = await repos.audits.list_for_run(run_id)
    kinds = [e["kind"] for e in events]
    assert "bias" in kinds and "dedup" in kinds


async def test_membership_role(pg_sessionmaker) -> None:  # type: ignore[no-untyped-def]  # noqa: E501
    org_id = await _seed_org(pg_sessionmaker, "acme")
    async with pg_sessionmaker() as session:
        bundle = _build_bundle(session, org_id=org_id)
        user = await bundle.users.create("alice@example.com", "Alice")
        await bundle.memberships.add(org_id, user.id, Role.admin)
        await session.commit()
        m = await bundle.memberships.get(org_id, user.id)
        assert m is not None and m.role == Role.admin


# ----------------------------- Tenant leak ---------------------------------


async def test_tenant_leak_isolation(pg_sessionmaker) -> None:  # type: ignore[no-untyped-def]  # noqa: E501
    """The non-negotiable: org A cannot see org B's data through any repo."""
    a_id = await _seed_org(pg_sessionmaker, "acme")
    b_id = await _seed_org(pg_sessionmaker, "globex")

    # Seed parallel rows in both orgs.
    async with uow(pg_sessionmaker, a_id) as repos:
        run_a = await repos.runs.create("/a/jd", "ha")
        cand_a = await repos.candidates.upsert(
            "shared_hash", "ka", {"contact": {"name": "A"}}
        )
        await repos.scores.write(run_a, cand_a, 0.9, "a-score")
        await repos.shortlists.write(run_a, [(cand_a, "shortlist")])
        await repos.audits.write(run_a, "bias", {"side": "a"})
    async with uow(pg_sessionmaker, b_id) as repos:
        run_b = await repos.runs.create("/b/jd", "hb")
        cand_b = await repos.candidates.upsert(
            "shared_hash", "kb", {"contact": {"name": "B"}}
        )
        await repos.scores.write(run_b, cand_b, 0.1, "b-score")
        await repos.shortlists.write(run_b, [(cand_b, "shortlist")])
        await repos.audits.write(run_b, "bias", {"side": "b"})

    # Reading via A's repo must NEVER surface B's rows.
    async with uow(pg_sessionmaker, a_id) as repos:
        assert await repos.runs.get(run_b) is None
        assert await repos.candidates.get(cand_b) is None
        a_scores = await repos.scores.list_for_run(run_a)
        assert all(r["candidate_id"] == cand_a for r in a_scores)
        b_scores_via_a = await repos.scores.list_for_run(run_b)
        assert b_scores_via_a == []
        a_audits = await repos.audits.list_for_run(run_a)
        assert all(e["payload"].get("side") == "a" for e in a_audits)
        b_audits_via_a = await repos.audits.list_for_run(run_b)
        assert b_audits_via_a == []
