// Server-sent events for live run progress. Replaces the 2.5s
// polling RunStatusPoller did against /api/runs/:id/status.
//
// The handler keeps a single connection open per browser tab, polls
// Postgres every POLL_MS, and pushes an `update` event when any of
// (status, scored_count, audit_event_count) changes. When the run
// reaches a terminal status it emits one final `done` event and
// closes the stream so the client can stop reconnecting.
//
// Why server-side polling rather than LISTEN/NOTIFY: the worker
// already writes audit rows + scores rows to Postgres, so we just
// detect changes by comparing snapshots. LISTEN/NOTIFY would push
// near-instant updates but needs a dedicated long-lived connection
// per listener and orchestrator-side NOTIFY emits — bigger surface
// area for a marginal latency win at this scale. Keep that as a
// follow-up if the page ever feels laggy.

import { requireUserAndOrg } from "@/lib/auth";
import { pool } from "@/lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const POLL_MS = 1000;
const HEARTBEAT_MS = 15_000; // empty `: ping` keepalives so proxies don't time out
const MAX_DURATION_MS = 30 * 60 * 1000; // hard cap, even for stuck runs
const TERMINAL = new Set([
  "ok",
  "completed",
  "failed",
  "cancelled",
  "blocked_by_bias",
  "budget_exceeded",
]);

interface Snapshot {
  status: string;
  scored: number;
  events: number;
  finished_at: string | null;
}

async function snapshot(orgId: number, runId: number): Promise<Snapshot | null> {
  const r = await pool.query<Snapshot & { exists: boolean }>(
    `SELECT
        runs.status,
        runs.finished_at,
        (SELECT COUNT(*)::int FROM scores
           WHERE org_id = $1 AND run_id = $2) AS scored,
        (SELECT COUNT(*)::int FROM audits
           WHERE org_id = $1 AND run_id = $2) AS events
       FROM runs
      WHERE org_id = $1 AND id = $2`,
    [orgId, runId],
  );
  return r.rows[0] ?? null;
}

function sseFrame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

export async function GET(
  req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const { org } = await requireUserAndOrg();
  const { id } = await ctx.params;
  const runId = Number(id);
  if (!Number.isFinite(runId)) {
    return new Response("invalid id", { status: 400 });
  }

  const enc = new TextEncoder();
  const startedAt = Date.now();

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      let lastKey = "";
      let closed = false;

      const onAbort = () => {
        if (closed) return;
        closed = true;
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      };
      // Close the loop when the browser disconnects.
      req.signal.addEventListener("abort", onAbort);

      function safeEnqueue(s: string): boolean {
        if (closed) return false;
        try {
          controller.enqueue(enc.encode(s));
          return true;
        } catch {
          closed = true;
          return false;
        }
      }

      // Initial event so the client knows we're alive immediately.
      safeEnqueue(sseFrame("hello", { runId }));

      let lastHeartbeatAt = Date.now();
      while (!closed) {
        if (Date.now() - startedAt > MAX_DURATION_MS) {
          safeEnqueue(sseFrame("done", { reason: "max_duration" }));
          break;
        }
        let snap: Snapshot | null;
        try {
          snap = await snapshot(org.id, runId);
        } catch (err) {
          // eslint-disable-next-line no-console
          console.error("sse snapshot failed", err);
          await new Promise((r) => setTimeout(r, POLL_MS));
          continue;
        }
        if (!snap) {
          // Run was deleted or doesn't belong to org.
          safeEnqueue(sseFrame("done", { reason: "not_found" }));
          break;
        }
        const key = `${snap.status}|${snap.scored}|${snap.events}|${
          snap.finished_at ?? ""
        }`;
        if (key !== lastKey) {
          lastKey = key;
          if (!safeEnqueue(sseFrame("update", snap))) break;
        } else if (Date.now() - lastHeartbeatAt > HEARTBEAT_MS) {
          // Empty comment line keeps the connection alive through
          // proxies that drop idle TCP after ~30-60s.
          if (!safeEnqueue(": ping\n\n")) break;
          lastHeartbeatAt = Date.now();
        }
        if (TERMINAL.has(snap.status)) {
          safeEnqueue(sseFrame("done", { status: snap.status }));
          break;
        }
        await new Promise((r) => setTimeout(r, POLL_MS));
      }
      onAbort();
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      // Disable nginx-style buffering when proxied.
      "X-Accel-Buffering": "no",
    },
  });
}
