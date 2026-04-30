"""HMAC chain helpers for audit_log (sub-project #5b).

Canonical JSON contract — both Python and the TypeScript dashboard MUST
produce the SAME bytes for a given record, or hashes won't match across
languages. The contract:

- Object keys are sorted lexicographically (UTF-16 code-unit order, the
  default of both ``sorted()`` in Python and ``Array.prototype.sort()``
  in JavaScript for ASCII keys, which is all we use).
- No whitespace anywhere.
- Strings escaped per JSON spec, encoded as UTF-8 on the wire.
- Numbers serialized normally (integers without trailing ``.0``).
- ``null`` for nulls.
- Arrays preserve order.

Hash input layout:

    HMAC-SHA256(secret, prev_hash || canonical_json(record_view))

where ``record_view`` is the dict ``{actor_kind, actor_user_id, created_at,
kind, org_id, payload, target_id, target_kind}`` (id and prev_hash/hash
intentionally excluded — id is opaque, prev_hash is in the input bytes
already).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any

ZERO_HASH = bytes(32)

# Cache the resolved key bytes between calls. Resolved lazily so unit
# tests can monkeypatch the env without restarting.
_KEY: bytes | None = None


def _resolve_key() -> bytes:
    """Read ATS_AUDIT_HMAC_KEY (hex). Falls back to a dev-only constant
    so demo deployments work without configuration; production should
    override via env."""
    global _KEY
    if _KEY is not None:
        return _KEY
    raw = os.environ.get("ATS_AUDIT_HMAC_KEY", "").strip()
    if raw:
        try:
            _KEY = bytes.fromhex(raw)
        except ValueError as exc:  # pragma: no cover
            raise RuntimeError(
                f"ATS_AUDIT_HMAC_KEY must be hex-encoded: {exc}"
            ) from exc
    else:
        # Dev fallback. CHANGE THIS in production via env.
        _KEY = b"\x00" * 32
    return _KEY


def reset_key_cache() -> None:
    """Tests use this after monkey-patching the env."""
    global _KEY
    _KEY = None


def now_iso() -> str:
    """ISO-8601 with millisecond precision, UTC, trailing 'Z'.

    Both Python and JS render this exact format (``new Date().toISOString()``
    matches), so the same datetime hashes identically across languages.
    """
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def canonical_json(value: Any) -> bytes:
    """Sorted-keys, no-whitespace JSON in UTF-8 — matches the TS helper.

    Uses ``json.dumps`` with sort_keys=True; Python's default sort of
    string keys is lexicographic over Unicode code points, matching JS's
    default ``Array.sort()`` for ASCII. Our keys are all ASCII.
    """
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def record_view(
    *,
    org_id: int,
    actor_user_id: int | None,
    actor_kind: str,
    kind: str,
    target_kind: str | None,
    target_id: int | None,
    payload: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    """Build the dict that gets hashed. Stable shape regardless of writer.

    Keys are alphabetised by ``canonical_json`` so the order here is
    informational; we still pass an ordered dict to make the reading
    clearer.
    """
    return {
        "actor_kind": actor_kind,
        "actor_user_id": actor_user_id,
        "created_at": created_at,
        "kind": kind,
        "org_id": org_id,
        "payload": payload,
        "target_id": target_id,
        "target_kind": target_kind,
    }


def compute_hash(prev_hash: bytes, view: dict[str, Any]) -> bytes:
    return hmac.new(
        _resolve_key(),
        prev_hash + canonical_json(view),
        hashlib.sha256,
    ).digest()
