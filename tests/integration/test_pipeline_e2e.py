"""End-to-end pipeline tests with a fake LLM transport (no network)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from ats import db
from ats.config import Settings
from ats.orchestrator import run_pipeline
from tests.integration.fakes import make_factory

# --------------------------- canned agent handlers ---------------------------


def _jd_handler(_payload: str) -> dict[str, Any]:
    return {
        "role_family": "Applied AI Engineer",
        "seniority": "senior",
        "must_have": ["Python", "TypeScript", "Claude Code"],
        "nice_to_have": ["AWS", "Postgres"],
        "responsibilities": ["Ship features"],
        "min_years": 2,
    }


# alice / bob / carol parsed shapes keyed by file basename
_PARSED: dict[str, dict[str, Any]] = {
    "alice.txt": {
        "contact": {
            "name": "Alice",
            "email": "alice@example.com",
            "phone": "1",
            "location": "SF",
        },
        "skills": ["Python", "TypeScript", "Claude Code"],
        "experience": [],
        "education": [],
        "links": [],
    },
    "bob.txt": {
        "contact": {
            "name": "Bob",
            "email": "bob@example.com",
            "phone": "2",
            "location": "NY",
        },
        "skills": ["React"],
        "experience": [],
        "education": [],
        "links": [],
    },
    "carol.txt": {
        "contact": {
            "name": "Carol",
            "email": "carol@example.com",
            "phone": "3",
            "location": "LDN",
        },
        "skills": ["Python", "Go"],
        "experience": [],
        "education": [],
        "links": [],
    },
}


def _parser_handler(payload: str) -> dict[str, Any]:
    raw = json.loads(_extract_payload(payload))
    name = Path(raw["path"]).name
    return _PARSED.get(name, _PARSED["alice.txt"])


def _matcher_handler(payload: str) -> dict[str, Any]:
    inner = json.loads(_extract_payload(payload))
    skills = set(inner["resume"]["skills"])
    must = set(inner["jd"]["must_have"])
    score = round(len(skills & must) / max(1, len(must)), 2)
    return {
        "score": score,
        "must_have_hits": [{"skill": s, "evidence": s} for s in skills & must],
        "must_have_misses": list(must - skills),
        "nice_to_have_hits": [],
        "years_experience": 5.0,
        "rationale": f"matched {len(skills & must)}/{len(must)}",
    }


def _verifier_handler(payload: str) -> dict[str, Any]:
    inner = json.loads(_extract_payload(payload))
    match = inner["match"]
    return {
        "verified": [h["skill"] for h in match.get("must_have_hits", [])],
        "hallucinated": [],
        "adjusted_score": match.get("score", 0.0),
    }


def _ranker_handler(_payload: str) -> dict[str, Any]:
    # Read scores via DB tool — but here we just rank candidates 1..N.
    # In the e2e tests, the orchestrator already wrote scores; the
    # ranker is simulated to just shortlist top 2.
    return {
        "ranked": [
            {"candidate_id": 1, "rank": 1, "decision": "shortlist"},
            {"candidate_id": 3, "rank": 2, "decision": "shortlist"},
            {"candidate_id": 2, "rank": 3, "decision": "reject"},
        ],
        "threshold": 0.5,
        "notes": "fake",
    }


def _bias_pass(_payload: str) -> dict[str, Any]:
    return {"status": "pass", "findings": [], "recommendation": "ok"}


def _bias_block(_payload: str) -> dict[str, Any]:
    return {
        "status": "block",
        "findings": [
            {
                "cohort": "demographic-A",
                "metric": "mean_score",
                "gap": 0.4,
                "note": "synthetic test",
            }
        ],
        "recommendation": "review prompts",
    }


def _bias_list_shape(_payload: str) -> list[dict[str, Any]]:
    """Real-world failure shape: agent returned a JSON array, not an object."""
    return [
        {
            "cohort": "demographic-A",
            "metric": "mean_score",
            "gap": 0.05,
            "note": "minor",
        }
    ]


def _dedup_none(_payload: str) -> dict[str, Any]:
    return {"groups": []}


def _dedup_match(payload: str) -> dict[str, Any]:
    arr = json.loads(_extract_payload(payload))
    if len(arr) < 2:
        return {"groups": []}
    return {
        "groups": [
            {
                "canonical_id": arr[0]["id"],
                "duplicate_ids": [arr[1]["id"]],
                "reason": "same email",
            }
        ]
    }


# regex to pull "INPUT:\n..." section out of the dispatcher prompt.
_INPUT_RE = re.compile(r"INPUT:\n(.*)\Z", re.DOTALL)


def _extract_payload(prompt: str) -> str:
    m = _INPUT_RE.search(prompt)
    return m.group(1) if m else prompt


# ------------------------------- fixtures ------------------------------------


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "ats.db",
        inbox_dir=tmp_path / "inbox",
        agent_timeout_s=5,
        agent_max_retries=0,
    )


@pytest.fixture
def jd_file(tmp_path: Path) -> Path:
    p = tmp_path / "jd.txt"
    p.write_text("Applied AI Engineer JD")
    return p


@pytest.fixture
def resumes_dir(tmp_path: Path) -> Path:
    d = tmp_path / "resumes"
    d.mkdir()
    for name in ("alice.txt", "bob.txt", "carol.txt"):
        # Use .txt so the verifier's extract_text_from_path round-trips
        # cleanly without requiring a real PDF.
        (d / name).write_text(f"resume body for {name}")
    return d


# -------------------------------- tests --------------------------------------


@pytest.mark.asyncio
async def test_happy_path_skip_optional(
    settings: Settings, jd_file: Path, resumes_dir: Path
) -> None:
    handlers = {
        "jd_analyzer": _jd_handler,
        "parser": _parser_handler,
        "matcher": _matcher_handler,
        "verifier": _verifier_handler,
        "ranker": _ranker_handler,
        "bias_auditor": _bias_pass,
        "deduper": _dedup_none,
    }
    summary = await run_pipeline(
        settings,
        jd_file,
        resumes_dir,
        top_n=2,
        skip_optional=True,
        client_factory=make_factory(handlers),
    )
    assert summary["status"] == "ok"
    assert len(summary["candidates"]) == 3
    assert summary["audits"]["bias"]["status"] == "pass"

    # DB row finalised
    run_row = db.get_run(settings.db_path, summary["run_id"])
    assert run_row is not None
    assert run_row["status"] == "ok"


@pytest.mark.asyncio
async def test_bias_blocks_shortlist(
    settings: Settings, jd_file: Path, resumes_dir: Path
) -> None:
    handlers = {
        "jd_analyzer": _jd_handler,
        "parser": _parser_handler,
        "matcher": _matcher_handler,
        "verifier": _verifier_handler,
        "ranker": _ranker_handler,
        "bias_auditor": _bias_block,
        "deduper": _dedup_none,
    }
    summary = await run_pipeline(
        settings,
        jd_file,
        resumes_dir,
        top_n=2,
        skip_optional=True,
        client_factory=make_factory(handlers),
    )
    assert summary["status"] == "blocked_by_bias"
    # Ranker never wrote shortlist rows
    with db.connect(settings.db_path) as c:
        rows = c.execute(
            "SELECT COUNT(*) AS n FROM shortlists WHERE run_id=?",
            (summary["run_id"],),
        ).fetchone()
    assert rows["n"] == 0


@pytest.mark.asyncio
async def test_bias_list_shape_is_coerced(
    settings: Settings, jd_file: Path, resumes_dir: Path
) -> None:
    """Real bug we hit twice: agent returned a list. Schema must coerce it."""
    handlers = {
        "jd_analyzer": _jd_handler,
        "parser": _parser_handler,
        "matcher": _matcher_handler,
        "verifier": _verifier_handler,
        "ranker": _ranker_handler,
        "bias_auditor": _bias_list_shape,
        "deduper": _dedup_none,
    }
    summary = await run_pipeline(
        settings,
        jd_file,
        resumes_dir,
        top_n=2,
        skip_optional=True,
        client_factory=make_factory(handlers),
    )
    # Coercion: list under findings, default status=pass → run completes.
    assert summary["status"] == "ok"
    assert summary["audits"]["bias"]["status"] == "pass"
    assert len(summary["audits"]["bias"]["findings"]) == 1


@pytest.mark.asyncio
async def test_dedup_drops_duplicate(
    settings: Settings, jd_file: Path, resumes_dir: Path
) -> None:
    handlers = {
        "jd_analyzer": _jd_handler,
        "parser": _parser_handler,
        "matcher": _matcher_handler,
        "verifier": _verifier_handler,
        "ranker": _ranker_handler,
        "bias_auditor": _bias_pass,
        "deduper": _dedup_match,
    }
    summary = await run_pipeline(
        settings,
        jd_file,
        resumes_dir,
        top_n=2,
        skip_optional=True,
        client_factory=make_factory(handlers),
    )
    # 3 resumes - 1 duplicate = 2 processed candidates
    assert len(summary["candidates"]) == 2
    assert "dedup" in summary["audits"]
