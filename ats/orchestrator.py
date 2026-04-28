"""Pipeline orchestrator — drives the 13 ATS subagents."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Callable

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, create_sdk_mcp_server
from pydantic import BaseModel

from ats import db, storage
from ats.agents import build_agents
from ats.agents.definitions import NEEDED, OPTIONAL, RECOMMENDED
from ats.agents.schemas import (
    BiasReport,
    DedupReport,
    EnrichmentResult,
    InterviewResult,
    JDParsed,
    MatchResult,
    OutreachDraft,
    ParsedResume,
    Ranking,
    RedFlagsResult,
    SummarizerResult,
    VerifierResult,
)
from ats.config import Settings
from ats.cost import BudgetExceeded, Usage
from ats.invoke import invoke_agent
from ats.tools import db_tools, pdf_tools, skills_index

log = logging.getLogger("ats.orchestrator")

# GitHub usernames: alphanumeric + hyphen, max 39 chars, can't start/end
# with hyphen. Anything else is rejected before being passed to the
# enricher agent, which prevents SSRF via crafted URLs in resume links.
_GH_HANDLE_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$")

# Type alias for the test seam: a factory that yields a SDK client given options.
ClientFactory = Callable[[ClaudeAgentOptions], Any]


def _build_options(settings: Settings) -> ClaudeAgentOptions:
    server = create_sdk_mcp_server(
        name="ats",
        version="0.1.0",
        tools=[
            pdf_tools.read_resume,
            skills_index.normalize_skills,
            skills_index.list_canonical_skills,
            db_tools.save_audit,
            db_tools.get_run_scores,
            db_tools.get_candidate,
        ],
    )
    return ClaudeAgentOptions(
        mcp_servers={"ats": server},
        agents=build_agents(settings),
        permission_mode="acceptEdits",
        system_prompt=(
            "You are the ATS pipeline coordinator. For every user request, "
            "dispatch the named subagent via the Agent tool and relay its "
            "JSON response VERBATIM. Never paraphrase, summarize, or add prose."
        ),
        allowed_tools=[
            "mcp__ats__read_resume",
            "mcp__ats__normalize_skills",
            "mcp__ats__list_canonical_skills",
            "mcp__ats__save_audit",
            "mcp__ats__get_run_scores",
            "mcp__ats__get_candidate",
            "WebFetch",
        ],
    )


def _default_client_factory(options: ClaudeAgentOptions) -> Any:
    return ClaudeSDKClient(options=options)


def _to_jsonable(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


async def run_pipeline(
    settings: Settings,
    jd_path: Path,
    resumes_dir: Path,
    top_n: int = 5,
    skip_optional: bool = False,
    *,
    client_factory: ClientFactory | None = None,
) -> dict[str, Any]:
    db.init_db(settings.db_path)
    jd_text = storage.read_text_file(jd_path)
    jd_hash = storage.hash_text(jd_text)
    run_id = db.create_run(settings.db_path, str(jd_path), jd_hash)
    log.info("run start", extra={"run_id": run_id, "jd_path": str(jd_path)})

    options = _build_options(settings)
    enabled = (
        set(NEEDED) | set(RECOMMENDED) | (set() if skip_optional else set(OPTIONAL))
    )

    summary: dict[str, Any] = {"run_id": run_id, "candidates": [], "audits": {}}
    usage = Usage()

    factory = client_factory or _default_client_factory

    # The Claude Agent SDK's ClaudeSDKClient multiplexes one
    # request/response channel per process; concurrent ``query()`` calls on
    # the same client would interleave their replies. We hold a single Lock
    # for every invocation so they serialize. Per-candidate fan-out via
    # ``asyncio.gather`` still helps for I/O-bound steps that don't go
    # through the LLM, but each LLM call is atomic.
    client_lock = asyncio.Lock()

    def _check_budget() -> None:
        if settings.max_cost_usd and usage.cost_usd > settings.max_cost_usd:
            raise BudgetExceeded(
                f"cost {usage.cost_usd:.2f} > cap {settings.max_cost_usd:.2f}"
            )

    async def call(
        client: Any,
        agent: str,
        payload: str,
        candidate_id: int | None = None,
    ) -> BaseModel:
        _check_budget()  # pre-flight: don't start expensive call over budget
        model = await invoke_agent(
            client,
            agent,
            payload,
            timeout_s=settings.agent_timeout_s,
            max_retries=settings.agent_max_retries,
            run_id=run_id,
            candidate_id=candidate_id,
            client_lock=client_lock,
            usage=usage,
        )
        _check_budget()  # post-flight: stop the next one if we just busted
        return model

    try:
        async with factory(options) as client:
            # 1. JD analysis (cached across all candidates)
            jd_model = await call(client, "jd_analyzer", jd_text)
            assert isinstance(jd_model, JDParsed)
            db.write_audit(
                settings.db_path, run_id, "jd_parsed", _to_jsonable(jd_model)
            )

            # 2. Per-resume parsing — sequential (small fan-in, parser is cheap)
            parsed_candidates: list[dict[str, Any]] = []
            for resume_path in storage.iter_resumes(resumes_dir):
                file_hash = storage.hash_file(resume_path)
                parsed_model = await call(
                    client,
                    "parser",
                    json.dumps({"path": str(resume_path)}),
                )
                assert isinstance(parsed_model, ParsedResume)
                parsed = _to_jsonable(parsed_model)
                cand_id = db.upsert_candidate(
                    settings.db_path, str(resume_path), file_hash, parsed
                )
                parsed_candidates.append(
                    {"id": cand_id, "path": str(resume_path), "parsed": parsed}
                )

            # 3. Deduper
            if "deduper" in enabled and len(parsed_candidates) > 1:
                dedup_model = await call(
                    client,
                    "deduper",
                    json.dumps(
                        [
                            {"id": c["id"], "parsed": c["parsed"]}
                            for c in parsed_candidates
                        ]
                    ),
                )
                assert isinstance(dedup_model, DedupReport)
                dedup = _to_jsonable(dedup_model)
                db.write_audit(settings.db_path, run_id, "dedup", dedup)
                duplicates = {
                    dup_id for grp in dedup_model.groups for dup_id in grp.duplicate_ids
                }
                parsed_candidates = [
                    c for c in parsed_candidates if c["id"] not in duplicates
                ]
                summary["audits"]["dedup"] = dedup

            # 4. Per-candidate work — parallel, bounded by Semaphore.
            async def process_candidate(cand: dict[str, Any]) -> dict[str, Any]:
                cid = cand["id"]
                jd_payload = _to_jsonable(jd_model)
                match_model = await call(
                    client,
                    "matcher",
                    json.dumps({"jd": jd_payload, "resume": cand["parsed"]}),
                    candidate_id=cid,
                )
                assert isinstance(match_model, MatchResult)
                match = _to_jsonable(match_model)

                verified: dict[str, Any] | None = None
                score = match_model.score
                rationale = match_model.rationale

                if "verifier" in enabled:
                    resume_text = pdf_tools.extract_text_from_path(Path(cand["path"]))
                    v_model = await call(
                        client,
                        "verifier",
                        json.dumps({"resume_text": resume_text, "match": match}),
                        candidate_id=cid,
                    )
                    assert isinstance(v_model, VerifierResult)
                    verified = _to_jsonable(v_model)
                    score = v_model.adjusted_score or score

                db.write_score(
                    settings.db_path, run_id, cid, score, rationale, verified
                )

                cand_summary: dict[str, Any] = {
                    "candidate_id": cid,
                    "score": score,
                    "match": match,
                    "verified": verified,
                }

                if "red_flags" in enabled:
                    rf_model = await call(
                        client,
                        "red_flags",
                        json.dumps(cand["parsed"].get("experience", [])),
                        candidate_id=cid,
                    )
                    assert isinstance(rf_model, RedFlagsResult)
                    rf = _to_jsonable(rf_model)
                    db.write_audit(settings.db_path, run_id, f"red_flags:{cid}", rf)
                    cand_summary["red_flags"] = rf

                if "summarizer" in enabled:
                    s_model = await call(
                        client,
                        "summarizer",
                        json.dumps({"parsed_resume": cand["parsed"], "match": match}),
                        candidate_id=cid,
                    )
                    assert isinstance(s_model, SummarizerResult)
                    cand_summary["brief"] = s_model.brief

                if "interview_qs" in enabled:
                    q_model = await call(
                        client,
                        "interview_qs",
                        json.dumps(
                            {
                                "jd": jd_payload,
                                "parsed_resume": cand["parsed"],
                                "match": match,
                            }
                        ),
                        candidate_id=cid,
                    )
                    assert isinstance(q_model, InterviewResult)
                    qs = _to_jsonable(q_model)
                    db.write_audit(settings.db_path, run_id, f"interview_qs:{cid}", qs)
                    cand_summary["interview_qs"] = qs.get("questions", [])

                if "enricher" in enabled:
                    handles = [
                        link
                        for link in cand["parsed"].get("links", [])
                        if "github.com/" in link
                    ]
                    if handles:
                        handle = handles[0].rstrip("/").split("/")[-1]
                        if not _GH_HANDLE_RE.match(handle):
                            log.warning(
                                "enricher: rejecting non-handle link",
                                extra={"candidate_id": cid, "handle": handle},
                            )
                        else:
                            e_model = await call(
                                client,
                                "enricher",
                                json.dumps({"github_handle": handle}),
                                candidate_id=cid,
                            )
                            assert isinstance(e_model, EnrichmentResult)
                            enr = _to_jsonable(e_model)
                            db.write_audit(
                                settings.db_path, run_id, f"enricher:{cid}", enr
                            )
                            cand_summary["enrichment"] = enr

                return cand_summary

            results = await asyncio.gather(
                *(process_candidate(c) for c in parsed_candidates)
            )
            summary["candidates"] = results

            # 5. Bias audit gate
            if "bias_auditor" in enabled and parsed_candidates:
                bias_model = await call(
                    client,
                    "bias_auditor",
                    json.dumps(
                        {
                            "run_id": run_id,
                            "block_threshold": settings.bias_block_threshold,
                        }
                    ),
                )
                assert isinstance(bias_model, BiasReport)
                bias = _to_jsonable(bias_model)
                summary["audits"]["bias"] = bias
                if bias_model.status == "block":
                    db.update_run_usage(settings.db_path, run_id, usage.to_dict())
                    db.finish_run(settings.db_path, run_id, "blocked_by_bias")
                    summary["status"] = "blocked_by_bias"
                    return summary

            # 6. Rank + shortlist
            rank_model = await call(
                client,
                "ranker",
                json.dumps({"run_id": run_id, "top_n": top_n}),
            )
            assert isinstance(rank_model, Ranking)
            ranked: list[tuple[int, str]] = [
                (r.candidate_id, r.decision) for r in rank_model.ranked
            ]
            db.write_shortlist(settings.db_path, run_id, ranked)
            summary["ranking"] = _to_jsonable(rank_model)

            # 7. Outreach drafts for shortlisted
            if "outreach" in enabled:
                drafts: list[dict[str, Any]] = []

                async def draft_for(cid: int, decision: str) -> dict[str, Any] | None:
                    if decision != "shortlist":
                        return None
                    cand_rec = db.get_candidate(settings.db_path, cid)
                    if not cand_rec:
                        return None
                    o_model = await call(
                        client,
                        "outreach",
                        json.dumps(
                            {
                                "decision": decision,
                                "candidate_name": cand_rec.get("name") or "Candidate",
                                "role": jd_model.role_family or "the role",
                                "tone": "warm",
                            }
                        ),
                        candidate_id=cid,
                    )
                    assert isinstance(o_model, OutreachDraft)
                    return {"candidate_id": cid, **_to_jsonable(o_model)}

                produced = await asyncio.gather(
                    *(draft_for(cid, d) for cid, d in ranked)
                )
                drafts = [d for d in produced if d is not None]
                db.write_audit(settings.db_path, run_id, "outreach", {"drafts": drafts})
                summary["outreach"] = drafts

        db.update_run_usage(settings.db_path, run_id, usage.to_dict())
        db.finish_run(settings.db_path, run_id, "ok")
        summary["status"] = "ok"
        summary["usage"] = usage.to_dict()
        return summary
    except BudgetExceeded as exc:
        db.update_run_usage(settings.db_path, run_id, usage.to_dict())
        db.finish_run(settings.db_path, run_id, "budget_exceeded")
        summary["status"] = "budget_exceeded"
        summary["error"] = str(exc)
        return summary
