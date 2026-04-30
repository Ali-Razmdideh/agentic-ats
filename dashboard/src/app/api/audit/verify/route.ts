// Walks the org's audit_log in id-order, recomputes each row's HMAC
// chain hash, and reports the first break (or "ok"). Admin-only.
//
// Same canonical-JSON contract as lib/audit-chain.ts and the Python
// helper — a successful verification here proves no row's content
// (or order) was modified since insertion AND that the writers
// (worker + dashboard) agreed on the canonical form.

import { NextResponse } from "next/server";
import { requireUserAndOrg } from "@/lib/auth";
import { pool } from "@/lib/db";
import {
  ZERO_HASH,
  computeHash,
  recordView,
} from "@/lib/audit-chain";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface ChainRow {
  id: number;
  org_id: number;
  actor_user_id: number | null;
  actor_kind: string;
  kind: string;
  target_kind: string | null;
  target_id: number | null;
  payload: Record<string, unknown>;
  created_at: Date;
  prev_hash: Buffer | null;
  hash: Buffer | null;
}

function toIsoMs(d: Date): string {
  // Match Python's isoformat(timespec='milliseconds') + 'Z' suffix.
  return d.toISOString();
}

export async function GET() {
  const { org, role } = await requireUserAndOrg();
  if (role !== "admin") {
    return NextResponse.json({ error: "admin_only" }, { status: 403 });
  }
  const res = await pool.query<ChainRow>(
    `SELECT id, org_id, actor_user_id, actor_kind, kind, target_kind, target_id,
            payload, created_at, prev_hash, hash
       FROM audit_log
      WHERE org_id = $1
      ORDER BY id ASC`,
    [org.id],
  );
  const rows = res.rows;
  const total = rows.length;
  const preChain = rows.filter((r) => r.hash == null).length;
  const chained = total - preChain;
  if (chained === 0) {
    return NextResponse.json({
      status: "pre_chain_only",
      total,
      chained: 0,
      pre_chain: preChain,
      first_break: null,
    });
  }

  let expectedPrev: Buffer = ZERO_HASH;
  for (const r of rows) {
    if (r.hash == null) continue; // legacy row, skip
    const view = recordView({
      org_id: r.org_id,
      actor_user_id: r.actor_user_id,
      actor_kind: r.actor_kind,
      kind: r.kind,
      target_kind: r.target_kind,
      target_id: r.target_id,
      payload: r.payload,
      created_at: toIsoMs(new Date(r.created_at)),
    });
    const expected = computeHash(expectedPrev, view);
    const stored = Buffer.from(r.hash);
    if (!expected.equals(stored)) {
      return NextResponse.json({
        status: "broken",
        total,
        chained,
        pre_chain: preChain,
        first_break: {
          id: r.id,
          expected: expected.toString("hex"),
          actual: stored.toString("hex"),
        },
      });
    }
    expectedPrev = stored;
  }

  return NextResponse.json({
    status: "ok",
    total,
    chained,
    pre_chain: preChain,
    first_break: null,
  });
}
