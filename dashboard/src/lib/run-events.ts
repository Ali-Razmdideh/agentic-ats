// Single-process Postgres LISTEN client + in-memory fan-out for the
// `run_progress` channel. Triggers in the database (see
// ats/cli.py:_init_async) emit NOTIFY 'run_progress', '<run_id>' after
// every mutation to runs / audits / scores / shortlists; this module
// keeps one long-lived pg.Client subscribed and re-emits each
// notification on a Node EventEmitter so SSE handlers can subscribe
// without each one opening its own pg connection.
//
// Safety:
// - The listener client is separate from the Pool (LISTEN holds the
//   connection; pool checkouts must come back).
// - On end / error we drop the singleton and let the next subscriber
//   reconnect. Callers should still implement a slow polling fallback
//   in case a notification is lost during a reconnect window.

import { Client } from "pg";
import { EventEmitter } from "events";

const CHANNEL = "run_progress";

class RunProgressBus extends EventEmitter {}
const bus: RunProgressBus = new RunProgressBus();
// Many SSE handlers may subscribe; bump the default 10-listener cap
// so Node doesn't warn under load.
bus.setMaxListeners(0);

let listener: Client | null = null;
let initPromise: Promise<void> | null = null;

async function ensureListener(): Promise<void> {
  if (listener) return;
  if (initPromise) return initPromise;
  initPromise = (async () => {
    const c = new Client({
      connectionString:
        process.env.DATABASE_URL ?? "postgresql://ats:ats@localhost:5432/ats",
    });
    c.on("notification", (msg) => {
      if (msg.channel !== CHANNEL || !msg.payload) return;
      bus.emit(`run:${msg.payload}`, msg.payload);
    });
    function teardown(): void {
      if (listener === c) listener = null;
      initPromise = null;
    }
    c.on("error", (err) => {
      // eslint-disable-next-line no-console
      console.error("[run-events] listener error", err);
      teardown();
    });
    c.on("end", teardown);
    await c.connect();
    await c.query(`LISTEN ${CHANNEL}`);
    listener = c;
  })();
  try {
    await initPromise;
  } catch (err) {
    initPromise = null;
    throw err;
  }
}

/**
 * Subscribe to NOTIFY events for a specific run id. Returns an
 * unsubscribe function. The handler is fired with no args; the SSE
 * layer re-snapshots the run state on each tick anyway, so the
 * notification just acts as a "wake up" signal.
 *
 * If the listener can't be established (pg outage, etc.) the promise
 * resolves with a no-op unsubscribe and the caller's fallback polling
 * keeps working.
 */
export async function subscribeToRun(
  runId: number,
  handler: () => void,
): Promise<() => void> {
  try {
    await ensureListener();
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error("[run-events] subscribe failed; falling back to poll only", err);
    return () => {};
  }
  const evt = `run:${runId}`;
  bus.on(evt, handler);
  return () => bus.off(evt, handler);
}
