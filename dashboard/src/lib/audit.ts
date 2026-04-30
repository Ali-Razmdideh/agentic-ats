// Append-only compliance log. Mirrors the Python AuditLogRepository so
// dashboard-originated events land in the same table the worker writes
// to. Keep payloads small + redaction-safe (no passwords, no resume body).

import { pool } from "@/lib/db";

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

/** Append an audit event. Failures are logged + swallowed: a logging
 *  outage must NEVER block a reviewer action. */
export async function appendAudit(input: AppendInput): Promise<void> {
  try {
    await pool.query(
      `INSERT INTO audit_log
         (org_id, actor_user_id, actor_kind, kind, target_kind, target_id, payload)
       VALUES ($1, $2, $3, $4, $5, $6, $7)`,
      [
        input.orgId,
        input.actorUserId,
        input.actorKind,
        input.kind,
        input.targetKind ?? null,
        input.targetId ?? null,
        input.payload,
      ],
    );
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
