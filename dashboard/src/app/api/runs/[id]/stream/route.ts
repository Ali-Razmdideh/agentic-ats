// Server-sent events for live run progress. Replaces the earlier
// 2.5s client polling: one persistent connection per browser tab,
// driven by Postgres LISTEN/NOTIFY (see lib/run-events.ts) plus a
// 5s safety poll for missed notifications.
//
// Event protocol:
//   event: hello   data: { runId }                    once on connect
//   event: update  data: { status, scored, events,    on every change
//                          finished_at }
//   event: done    data: { status?, reason? }         terminal status
//
// Diff is computed server-side so a quiet run produces no events.

import { requireUserAndOrg } from "@/lib/auth";
import { pool } from "@/lib/db";
import { subscribeToRun } from "@/lib/run-events";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const SAFETY_POLL_MS = 5000;
const HEARTBEAT_MS = 15_000;
const MAX_DURATION_MS = 30 * 60 * 1000;
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
  const r = await pool.query<Snapshot>(
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
      let closed = false;
      let lastKey = "";
      let lastSentAt = Date.now();
      let unsubscribe: () => void = () => {};

      // Coordinates wakeups from either the NOTIFY bus, the safety
      // poll, or the heartbeat timer.
      let wake: () => void = () => {};
      function nextWake(timeoutMs: number): Promise<"event" | "timeout" | "abort"> {
        return new Promise((resolve) => {
          const t = setTimeout(() => {
            wake = () => {};
            resolve("timeout");
          }, timeoutMs);
          wake = () => {
            clearTimeout(t);
            wake = () => {};
            resolve("event");
          };
          req.signal.addEventListener(
            "abort",
            () => {
              clearTimeout(t);
              resolve("abort");
            },
            { once: true },
          );
        });
      }

      function teardown(): void {
        if (closed) return;
        closed = true;
        unsubscribe();
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      }
      req.signal.addEventListener("abort", teardown);

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

      async function emitIfChanged(): Promise<{ done: boolean }> {
        let snap: Snapshot | null;
        try {
          snap = await snapshot(org.id, runId);
        } catch (err) {
          // eslint-disable-next-line no-console
          console.error("[sse] snapshot failed", err);
          return { done: false };
        }
        if (!snap) {
          safeEnqueue(sseFrame("done", { reason: "not_found" }));
          return { done: true };
        }
        const key = `${snap.status}|${snap.scored}|${snap.events}|${
          snap.finished_at ?? ""
        }`;
        if (key !== lastKey) {
          lastKey = key;
          if (!safeEnqueue(sseFrame("update", snap))) return { done: true };
          lastSentAt = Date.now();
        }
        if (TERMINAL.has(snap.status)) {
          safeEnqueue(sseFrame("done", { status: snap.status }));
          return { done: true };
        }
        return { done: false };
      }

      // Subscribe to NOTIFY before sending hello so we don't miss
      // events that fire during the first snapshot.
      unsubscribe = await subscribeToRun(runId, () => wake());

      safeEnqueue(sseFrame("hello", { runId }));

      // Initial snapshot.
      if ((await emitIfChanged()).done) {
        teardown();
        return;
      }

      while (!closed) {
        if (Date.now() - startedAt > MAX_DURATION_MS) {
          safeEnqueue(sseFrame("done", { reason: "max_duration" }));
          break;
        }
        const idle = Date.now() - lastSentAt;
        const heartbeatIn = Math.max(0, HEARTBEAT_MS - idle);
        const wait = Math.min(SAFETY_POLL_MS, heartbeatIn || HEARTBEAT_MS);
        const reason = await nextWake(wait);
        if (reason === "abort") break;
        if (reason === "timeout" && Date.now() - lastSentAt >= HEARTBEAT_MS) {
          // Empty SSE comment line keeps the connection alive through
          // proxies that drop idle TCP after ~30-60s.
          if (!safeEnqueue(": ping\n\n")) break;
          lastSentAt = Date.now();
        }
        const result = await emitIfChanged();
        if (result.done) break;
      }
      teardown();
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
