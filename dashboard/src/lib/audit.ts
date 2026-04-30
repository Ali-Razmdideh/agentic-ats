// Append-only compliance log. Mirrors the Python AuditLogRepository so
// dashboard-originated events land in the same table the worker writes
// to. Keep payloads small + redaction-safe (no passwords, no resume body).
//
// Each append computes an HMAC chain hash; both Python and this helper
// must produce identical bytes for a given record. See lib/audit-chain.ts
// + ats/storage/audit_chain.py.

import { pool, withClient } from "@/lib/db";
import {
  ZERO_HASH,
  computeHash,
  nowIso,
  recordView,
} from "@/lib/audit-chain";

export type ActorKind = "user" | "worker" | "system";

export interface AuditEntry {
  id: number;
  org_id: number;
  actor_user_id: number | null;
  actor_kind: ActorKind;
  kind: string;
  target_kind: string | null;
  target_id: number | null;
  payload: Record<string, unknown>;
  created_at: string;
}

interface AppendInput {
  orgId: number;
  actorUserId: number | null;
  actorKind: ActorKind;
  kind: string;
  payload: Record<string, unknown>;
  targetKind?: string | null;
  targetId?: number | null;
}

/** Append an audit event with HMAC chain hash. Failures are logged +
 *  swallowed: a logging outage must NEVER block a reviewer action. */
export async function appendAudit(input: AppendInput): Promise<void> {
  try {
    await withClient(async (client) => {
      await client.query("BEGIN");
      try {
        // Per-org transaction-scoped advisory lock; same key the Python
        // worker uses, so cross-language writers serialize.
        await client.query("SELECT pg_advisory_xact_lock($1)", [input.orgId]);

        const prevRes = await client.query<{ hash: Buffer | null }>(
          `SELECT hash FROM audit_log
             WHERE org_id = $1 AND hash IS NOT NULL
             ORDER BY id DESC LIMIT 1`,
          [input.orgId],
        );
        const prev =
          prevRes.rows[0]?.hash != null
            ? Buffer.from(prevRes.rows[0]!.hash!)
            : ZERO_HASH;
        const createdAt = nowIso();
        const view = recordView({
          org_id: input.orgId,
          actor_user_id: input.actorUserId,
          actor_kind: input.actorKind,
          kind: input.kind,
          target_kind: input.targetKind ?? null,
          target_id: input.targetId ?? null,
          payload: input.payload,
          created_at: createdAt,
        });
        const hash = computeHash(prev, view);

        await client.query(
          `INSERT INTO audit_log
             (org_id, actor_user_id, actor_kind, kind, target_kind, target_id,
              payload, created_at, prev_hash, hash)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
          [
            input.orgId,
            input.actorUserId,
            input.actorKind,
            input.kind,
            input.targetKind ?? null,
            input.targetId ?? null,
            input.payload,
            createdAt,
            prev,
            hash,
          ],
        );
        await client.query("COMMIT");
      } catch (e) {
        await client.query("ROLLBACK");
        throw e;
      }
    });
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error("audit_log append failed", { kind: input.kind, err });
  }
}

interface ListInput {
  orgId: number;
  limit?: number;
  offset?: number;
  kind?: string;
  actorUserId?: number;
  since?: string;
  until?: string;
}

export async function listAudit(input: ListInput): Promise<AuditEntry[]> {
  const where: string[] = ["org_id = $1"];
  const params: unknown[] = [input.orgId];
  if (input.kind) {
    params.push(input.kind);
    where.push(`kind = $${params.length}`);
  }
  if (input.actorUserId != null) {
    params.push(input.actorUserId);
    where.push(`actor_user_id = $${params.length}`);
  }
  if (input.since) {
    params.push(input.since);
    where.push(`created_at >= $${params.length}`);
  }
  if (input.until) {
    params.push(input.until);
    where.push(`created_at < $${params.length}`);
  }
  params.push(input.limit ?? 100);
  const limitIdx = params.length;
  params.push(input.offset ?? 0);
  const offsetIdx = params.length;

  const sql = `
    SELECT id, org_id, actor_user_id, actor_kind, kind, target_kind, target_id,
           payload, created_at
      FROM audit_log
     WHERE ${where.join(" AND ")}
     ORDER BY id DESC
     LIMIT $${limitIdx} OFFSET $${offsetIdx}
  `;
  const res = await pool.query<AuditEntry>(sql, params);
  return res.rows;
}

export async function countAudit(input: Omit<ListInput, "limit" | "offset">): Promise<number> {
  const where: string[] = ["org_id = $1"];
  const params: unknown[] = [input.orgId];
  if (input.kind) {
    params.push(input.kind);
    where.push(`kind = $${params.length}`);
  }
  if (input.actorUserId != null) {
    params.push(input.actorUserId);
    where.push(`actor_user_id = $${params.length}`);
  }
  if (input.since) {
    params.push(input.since);
    where.push(`created_at >= $${params.length}`);
  }
  if (input.until) {
    params.push(input.until);
    where.push(`created_at < $${params.length}`);
  }
  const res = await pool.query<{ n: string }>(
    `SELECT COUNT(*)::text AS n FROM audit_log WHERE ${where.join(" AND ")}`,
    params,
  );
  return Number(res.rows[0]?.n ?? 0);
}

/** Streaming iterator for CSV export. */
export async function* iterAudit(input: ListInput): AsyncGenerator<AuditEntry> {
  const pageSize = 500;
  let offset = input.offset ?? 0;
  while (true) {
    const page = await listAudit({ ...input, limit: pageSize, offset });
    for (const row of page) yield row;
    if (page.length < pageSize) return;
    offset += pageSize;
  }
}
