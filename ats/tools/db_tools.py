from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from ats import db
from ats.config import get_settings


def _db_path() -> Path:
    return get_settings().db_path


_MAX_AUDIT_BYTES = 1_000_000  # 1 MB hard cap on a single audit payload

# Allow only these kinds (or prefixes ending in ":") to land in the audits
# table. Prevents an agent from polluting the table with arbitrary keys.
_KIND_ALLOWLIST = {"jd_parsed", "dedup", "outreach", "bias"}
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
    db.write_audit(_db_path(), int(args["run_id"]), kind, payload)
    return {"content": [{"type": "text", "text": "ok"}]}


@tool(
    "get_run_scores",
    "Return all candidate scores for a run as JSON.",
    {"run_id": int},
)
async def get_run_scores(args: dict[str, Any]) -> dict[str, Any]:
    rows = db.get_run_scores(_db_path(), int(args["run_id"]))
    return {"content": [{"type": "text", "text": json.dumps(rows)}]}


@tool(
    "get_candidate",
    "Return a candidate record (with parsed JSON) by id.",
    {"candidate_id": int},
)
async def get_candidate(args: dict[str, Any]) -> dict[str, Any]:
    rec = db.get_candidate(_db_path(), int(args["candidate_id"]))
    return {"content": [{"type": "text", "text": json.dumps(rec)}]}
