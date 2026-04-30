// HMAC chain helpers — must produce IDENTICAL bytes to the Python
// implementation in ats/storage/audit_chain.py for any given record.
//
// Canonical JSON contract:
//   - Object keys sorted lexicographically (UTF-16 code-unit order;
//     same as Python's sort_keys for ASCII keys).
//   - No whitespace. Numbers / strings / null / booleans serialised
//     with the standard JS JSON rules. Arrays preserve order.
//   - UTF-8 encoded on the wire.
// Hash input layout:
//   HMAC-SHA256(secret, prev_hash || canonical_json(record_view))

import { createHmac } from "crypto";

export const ZERO_HASH = Buffer.alloc(32);

let CACHED_KEY: Buffer | null = null;

function resolveKey(): Buffer {
  if (CACHED_KEY) return CACHED_KEY;
  const raw = (process.env.ATS_AUDIT_HMAC_KEY ?? "").trim();
  if (raw) {
    try {
      CACHED_KEY = Buffer.from(raw, "hex");
    } catch (e) {
      throw new Error(`ATS_AUDIT_HMAC_KEY must be hex-encoded: ${e}`);
    }
  } else {
    // Dev fallback. Production should set the env var.
    CACHED_KEY = Buffer.alloc(32);
  }
  return CACHED_KEY;
}

export function resetKeyCache(): void {
  CACHED_KEY = null;
}

export function nowIso(): string {
  // toISOString already produces millisecond precision + 'Z' suffix —
  // matches what Python emits via isoformat(timespec='milliseconds').
  return new Date().toISOString();
}

export function canonicalJson(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "number" || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) {
    return "[" + value.map(canonicalJson).join(",") + "]";
  }
  if (typeof value === "object") {
    const keys = Object.keys(value as Record<string, unknown>).sort();
    return (
      "{" +
      keys
        .map(
          (k) =>
            JSON.stringify(k) +
            ":" +
            canonicalJson((value as Record<string, unknown>)[k]),
        )
        .join(",") +
      "}"
    );
  }
  // undefined or unknown — coerce to null to match Python behaviour
  // for json.dumps which would raise; we choose stable null instead.
  return "null";
}

export interface AuditRecordView {
  actor_kind: string;
  actor_user_id: number | null;
  created_at: string;
  kind: string;
  org_id: number;
  payload: Record<string, unknown>;
  target_id: number | null;
  target_kind: string | null;
}

export function recordView(args: {
  org_id: number;
  actor_user_id: number | null;
  actor_kind: string;
  kind: string;
  target_kind: string | null;
  target_id: number | null;
  payload: Record<string, unknown>;
  created_at: string;
}): AuditRecordView {
  // Field order here is informational; canonicalJson sorts keys.
  return {
    actor_kind: args.actor_kind,
    actor_user_id: args.actor_user_id,
    created_at: args.created_at,
    kind: args.kind,
    org_id: args.org_id,
    payload: args.payload,
    target_id: args.target_id,
    target_kind: args.target_kind,
  };
}

export function computeHash(
  prevHash: Buffer,
  view: AuditRecordView,
): Buffer {
  const h = createHmac("sha256", resolveKey());
  h.update(prevHash);
  h.update(canonicalJson(view), "utf8");
  return h.digest();
}
