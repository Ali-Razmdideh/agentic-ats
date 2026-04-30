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

from ats.agents import build_agents
from ats.agents.definitions import NEEDED, OPTIONAL, RECOMMENDED
from ats.agents.schemas import (
    BiasReport,
    DedupReport,
    EnrichmentResult,
    InterviewResult,
    JDParsed,
    LinkedInEnrichmentResult,
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
from ats.storage import (
    BlobStore,
    BlobStoreProtocol,
    hash_file,
    hash_text,
    iter_resumes,
    make_engine,
    make_sessionmaker,
    read_text_file,
    run_context,
    uow,
)
from ats.storage.models import RunStatus
from ats.tools import db_tools, pdf_tools, skills_index

log = logging.getLogger("ats.orchestrator")

_GH_HANDLE_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$")

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


async def _resolve_org_id(  # type: ignore[no-untyped-def]
    sessionmaker, slug: str
) -> int:
    """Look up the org by slug; ``ats init`` (Alembic) seeds 'system'."""
    from ats.storage.uow import _build_bundle  # local import to avoid cycle

    async with sessionmaker() as session:
        bundle = _build_bundle(session, org_id=0)
        org = await bundle.orgs.get_by_slug(slug)
        if org is None:
            raise RuntimeError(
                f"Org '{slug}' not found. Run `ats init` to create it, or "
                f"pass --org with an existing slug."
            )
        return int(org.id)


async def run_pipeline(
    settings: Settings,
    jd_path: Path,
    resumes_dir: Path,
    top_n: int = 5,
    skip_optional: bool = False,
    *,
    client_factory: ClientFactory | None = None,
    org_slug: str | None = None,
    blob_store: BlobStoreProtocol | None = None,
    sessionmaker_override: Any = None,
    org_id_override: int | None = None,
    existing_run_id: int | None = None,
) -> dict[str, Any]:
    """Run the full screening pipeline.

    The CLI (`ats screen`) creates a new run row. The worker passes
    ``org_id_override`` + ``existing_run_id`` so the queued row created at
    upload time gets reused — no double-counting.
    """
    engine = None
    if sessionmaker_override is not None:
        sessionmaker = sessionmaker_override
    else:
        engine = make_engine(settings)
        sessionmaker = make_sessionmaker(engine)

    blobs: BlobStoreProtocol = blob_store or BlobStore(settings)

    if org_id_override is not None:
        org_id = org_id_override
    else:
        slug = org_slug or settings.default_org_slug
        org_id = await _resolve_org_id(sessionmaker, slug)

    jd_text = read_text_file(jd_path)
    jd_hash_value = hash_text(jd_text)

    # Worker path: the JD is already in MinIO from the upload step, so we
    # skip the put_jd round-trip. CLI path: upload now (content-addressed,
    # so re-runs are a no-op anyway).
    jd_blob_key: str | None = None
    if existing_run_id is None:
        jd_blob_key = await blobs.put_jd(org_id, jd_text.encode("utf-8"), jd_path.name)

    async with run_context(sessionmaker, org_id):
        if existing_run_id is not None:
            run_id = existing_run_id
        else:
            async with uow(sessionmaker, org_id) as repos:
                run_id = await repos.runs.create(
                    jd_path=str(jd_path),
                    jd_hash=jd_hash_value,
                    jd_blob_key=jd_blob_key,
                )
        log.info(
            "run start",
            extra={"run_id": run_id, "jd_path": str(jd_path), "org_id": org_id},
        )
        async with uow(sessionmaker, org_id) as repos:
            from ats.storage.models import ActorKind

            await repos.audit_log.append(
                kind="run.started",
                payload={
                    "jd_path": str(jd_path),
                    "skip_optional": skip_optional,
                    "top_n": top_n,
                },
                actor_user_id=None,
                actor_kind=ActorKind.worker,
                target_kind="run",
                target_id=run_id,
            )

        options = _build_options(settings)
        enabled = (
            set(NEEDED) | set(RECOMMENDED) | (set() if skip_optional else set(OPTIONAL))
        )

        summary: dict[str, Any] = {"run_id": run_id, "candidates": [], "audits": {}}
        usage = Usage()

        factory = client_factory or _default_client_factory
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
            _check_budget()
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
            _check_budget()
            return model

        try:
            async with factory(options) as client:
                jd_model = await call(client, "jd_analyzer", jd_text)
                assert isinstance(jd_model, JDParsed)
                async with uow(sessionmaker, org_id) as repos:
                    await repos.audits.write(
                        run_id, "jd_parsed", _to_jsonable(jd_model)
                    )

                # Per-resume parse + blob upload + db upsert.
                parsed_candidates: list[dict[str, Any]] = []
                for resume_path in iter_resumes(resumes_dir):
                    file_hash_value = hash_file(resume_path)
                    parsed_model = await call(
                        client,
                        "parser",
                        json.dumps({"path": str(resume_path)}),
                    )
                    assert isinstance(parsed_model, ParsedResume)
                    parsed = _to_jsonable(parsed_model)

                    blob_key = await blobs.put_resume(
                        org_id, resume_path.read_bytes(), resume_path.name
                    )

                    async with uow(sessionmaker, org_id) as repos:
                        cand_id = await repos.candidates.upsert(
                            file_hash=file_hash_value,
                            file_blob_key=blob_key,
                            parsed=parsed,
                            source_filename=resume_path.name,
                        )
                    parsed_candidates.append(
                        {
                            "id": cand_id,
                            "path": str(resume_path),
                            "parsed": parsed,
                        }
                    )

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
                    async with uow(sessionmaker, org_id) as repos:
                        await repos.audits.write(run_id, "dedup", dedup)
                    duplicates = {
                        dup_id
                        for grp in dedup_model.groups
                        for dup_id in grp.duplicate_ids
                    }
                    parsed_candidates = [
                        c for c in parsed_candidates if c["id"] not in duplicates
                    ]
                    summary["audits"]["dedup"] = dedup

                async def process_candidate(
                    cand: dict[str, Any],
                ) -> dict[str, Any]:
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
                    score_value = match_model.score
                    rationale = match_model.rationale

                    if "verifier" in enabled:
                        resume_text = pdf_tools.extract_text_from_path(
                            Path(cand["path"])
                        )
                        v_model = await call(
                            client,
                            "verifier",
                            json.dumps({"resume_text": resume_text, "match": match}),
                            candidate_id=cid,
                        )
                        assert isinstance(v_model, VerifierResult)
                        verified = _to_jsonable(v_model)
                        score_value = v_model.adjusted_score or score_value

                    async with uow(sessionmaker, org_id) as repos:
                        await repos.scores.write(
                            run_id, cid, score_value, rationale, verified
                        )

                    cand_summary: dict[str, Any] = {
                        "candidate_id": cid,
                        "score": score_value,
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
                        async with uow(sessionmaker, org_id) as repos:
                            await repos.audits.write(run_id, f"red_flags:{cid}", rf)
                        cand_summary["red_flags"] = rf

                    if "summarizer" in enabled:
                        s_model = await call(
                            client,
                            "summarizer",
                            json.dumps(
                                {
                                    "parsed_resume": cand["parsed"],
                                    "match": match,
                                }
                            ),
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
                        async with uow(sessionmaker, org_id) as repos:
                            await repos.audits.write(run_id, f"interview_qs:{cid}", qs)
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
                                    extra={
                                        "candidate_id": cid,
                                        "handle": handle,
                                    },
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
                                async with uow(sessionmaker, org_id) as repos:
                                    await repos.audits.write(
                                        run_id, f"enricher:{cid}", enr
                                    )
                                cand_summary["enrichment"] = enr

                    if "linkedin_enricher" in enabled:
                        # Match the canonical /in/ profile URLs only —
                        # /company/, /pub/, /jobs/ etc. aren't person
                        # pages. Anti-SSRF: re-validate the URL host so
                        # a crafted resume with linkedin.com.evil.tld in
                        # the link text doesn't slip past WebFetch.
                        li_urls = [
                            link
                            for link in cand["parsed"].get("links", [])
                            if "linkedin.com/in/" in link
                        ]
                        if li_urls:
                            url = li_urls[0]
                            host = url.split("/")[2] if "://" in url else ""
                            if host in {"linkedin.com", "www.linkedin.com"}:
                                li_model = await call(
                                    client,
                                    "linkedin_enricher",
                                    json.dumps({"linkedin_url": url}),
                                    candidate_id=cid,
                                )
                                assert isinstance(
                                    li_model, LinkedInEnrichmentResult
                                )
                                li = _to_jsonable(li_model)
                                async with uow(sessionmaker, org_id) as repos:
                                    await repos.audits.write(
                                        run_id, f"linkedin_enricher:{cid}", li
                                    )
                                cand_summary["linkedin"] = li
                            else:
                                log.warning(
                                    "linkedin_enricher: rejecting non-canonical host",
                                    extra={"candidate_id": cid, "host": host},
                                )

                    return cand_summary

                results = await asyncio.gather(
                    *(process_candidate(c) for c in parsed_candidates)
                )
                summary["candidates"] = results

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
                        async with uow(sessionmaker, org_id) as repos:
                            await repos.runs.update_usage(run_id, usage.to_dict())
                            await repos.runs.finish(run_id, RunStatus.blocked_by_bias)
                        summary["status"] = "blocked_by_bias"
                        return summary

                rank_model = await call(
                    client,
                    "ranker",
                    json.dumps({"run_id": run_id, "top_n": top_n}),
                )
                assert isinstance(rank_model, Ranking)
                ranked: list[tuple[int, str]] = [
                    (r.candidate_id, r.decision) for r in rank_model.ranked
                ]
                async with uow(sessionmaker, org_id) as repos:
                    await repos.shortlists.write(run_id, ranked)
                summary["ranking"] = _to_jsonable(rank_model)

                if "outreach" in enabled:
                    drafts: list[dict[str, Any]] = []

                    async def draft_for(
                        cid: int, decision: str
                    ) -> dict[str, Any] | None:
                        if decision != "shortlist":
                            return None
                        async with uow(sessionmaker, org_id) as repos:
                            cand_rec = await repos.candidates.get(cid)
                        if not cand_rec:
                            return None
                        o_model = await call(
                            client,
                            "outreach",
                            json.dumps(
                                {
                                    "decision": decision,
                                    "candidate_name": cand_rec.get("name")
                                    or "Candidate",
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
                    async with uow(sessionmaker, org_id) as repos:
                        await repos.audits.write(run_id, "outreach", {"drafts": drafts})
                    summary["outreach"] = drafts

            async with uow(sessionmaker, org_id) as repos:
                from ats.storage.models import ActorKind

                await repos.runs.update_usage(run_id, usage.to_dict())
                await repos.runs.finish(run_id, RunStatus.ok)
                await repos.audit_log.append(
                    kind="run.completed",
                    payload={
                        "candidates": len(summary.get("candidates", [])),
                        "usage": usage.to_dict(),
                    },
                    actor_user_id=None,
                    actor_kind=ActorKind.worker,
                    target_kind="run",
                    target_id=run_id,
                )
            summary["status"] = "ok"
            summary["usage"] = usage.to_dict()
            return summary
        except BudgetExceeded as exc:
            async with uow(sessionmaker, org_id) as repos:
                from ats.storage.models import ActorKind

                await repos.runs.update_usage(run_id, usage.to_dict())
                await repos.runs.finish(run_id, RunStatus.budget_exceeded)
                await repos.audit_log.append(
                    kind="run.budget_exceeded",
                    payload={"usage": usage.to_dict(), "message": str(exc)[:500]},
                    actor_user_id=None,
                    actor_kind=ActorKind.worker,
                    target_kind="run",
                    target_id=run_id,
                )
            summary["status"] = "budget_exceeded"
            summary["error"] = str(exc)
            return summary
        except Exception as exc:
            # Catch-all: any unhandled agent failure (timeouts past retries,
            # CoercionFailedError on a load-bearing agent, etc.) used to leave
            # the run stuck in `status='running'` forever. Now mark it failed
            # and persist the error message so the dashboard can surface it.
            log.exception(
                "run failed",
                extra={"run_id": run_id, "agent_error": type(exc).__name__},
            )
            try:
                async with uow(sessionmaker, org_id) as repos:
                    from ats.storage.models import ActorKind

                    await repos.runs.update_usage(run_id, usage.to_dict())
                    await repos.runs.finish(run_id, RunStatus.failed)
                    await repos.audits.write(
                        run_id,
                        "run_error",
                        {
                            "error_type": type(exc).__name__,
                            "message": str(exc)[:2000],
                        },
                    )
                    await repos.audit_log.append(
                        kind="run.failed",
                        payload={
                            "error_type": type(exc).__name__,
                            "message": str(exc)[:2000],
                        },
                        actor_user_id=None,
                        actor_kind=ActorKind.worker,
                        target_kind="run",
                        target_id=run_id,
                    )
            except Exception:  # pragma: no cover - last-resort safety
                log.exception("failed to persist run failure", extra={"run_id": run_id})
            summary["status"] = "failed"
            summary["error"] = str(exc)
            return summary
        finally:
            if engine is not None:
                await engine.dispose()
