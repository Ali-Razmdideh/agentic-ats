from __future__ import annotations

import json
import logging
from typing import Any

from claude_agent_sdk import tool
from sqlalchemy.exc import SQLAlchemyError

from ats.storage import current_uow

log = logging.getLogger("ats.tools.db_tools")

_MAX_AUDIT_BYTES = 1_000_000

_KIND_ALLOWLIST = {"jd_parsed", "dedup", "outreach", "bias", "run_error"}
_KIND_PREFIXES = ("red_flags:", "interview_qs:", "enricher:")


def _kind_is_allowed(kind: str) -> bool:
    if kind in _KIND_ALLOWLIST:
        return True
    return any(kind.startswith(p) for p in _KIND_PREFIXES)


@tool(
    "save_audit",
    "Persist an audit payload (e.g. bias report, dedup map) under a kind label for a run.",
    {"run_id": int, "kind": str, "payload_json": str},
)
async def save_audit(args: dict[str, Any]) -> dict[str, Any]:
    raw = str(args.get("payload_json") or "")
    if len(raw.encode("utf-8")) > _MAX_AUDIT_BYTES:
        return {
            "content": [{"type": "text", "text": "ERROR: payload exceeds 1 MB cap"}],
            "isError": True,
        }
    kind = str(args["kind"])
    if not _kind_is_allowed(kind):
        return {
            "content": [{"type": "text", "text": f"ERROR: kind {kind!r} not allowed"}],
            "isError": True,
        }
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {
            "content": [
                {"type": "text", "text": f"ERROR: payload_json invalid: {exc}"}
            ],
            "isError": True,
        }
    try:
        async with current_uow() as repos:
            await repos.audits.write(int(args["run_id"]), kind, payload)
    except SQLAlchemyError as exc:
        # Most likely cause: run_id from a different org (composite FK
        # rejects it). Surface as a tool error rather than crashing the
        # orchestrator's MCP loop.
        log.warning("save_audit failed", extra={"err": str(exc), "kind": kind})
        return {
            "content": [{"type": "text", "text": f"ERROR: save_audit failed: {exc}"}],
            "isError": True,
        }
    return {"content": [{"type": "text", "text": "ok"}]}


@tool(
    "get_run_scores",
    "Return all candidate scores for a run as JSON.",
    {"run_id": int},
)
async def get_run_scores(args: dict[str, Any]) -> dict[str, Any]:
    async with current_uow() as repos:
        rows = await repos.scores.list_for_run(int(args["run_id"]))
    return {"content": [{"type": "text", "text": json.dumps(rows)}]}


@tool(
    "get_candidate",
    "Return a candidate record (with parsed JSON) by id.",
    {"candidate_id": int},
)
async def get_candidate(args: dict[str, Any]) -> dict[str, Any]:
    async with current_uow() as repos:
        rec = await repos.candidates.get(int(args["candidate_id"]))
    return {"content": [{"type": "text", "text": json.dumps(rec)}]}
