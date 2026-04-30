"use client";

// SSE client for the run-detail page. Replaces the previous 2.5s
// polling loop with a single persistent connection to
// /api/runs/:id/stream, which itself does the polling + diffing
// server-side and only pushes when something actually changed.
//
// On every `update` event we call router.refresh() so the server-
// rendered page picks up the new audit rows / scores. On the final
// `done` event we close the stream so the browser doesn't keep
// reconnecting via EventSource's default retry behaviour.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function RunStatusPoller({ runId }: { runId: number }) {
  const router = useRouter();
  useEffect(() => {
    let es: EventSource | null = null;
    let closed = false;

    function close() {
      closed = true;
      if (es) {
        es.close();
        es = null;
      }
    }

    function open() {
      if (closed) return;
      es = new EventSource(`/api/runs/${runId}/stream`);
      es.addEventListener("update", () => {
        // Server says state changed — re-render the RSC tree.
        router.refresh();
      });
      es.addEventListener("done", () => {
        // One last refresh so the final state is visible, then close.
        router.refresh();
        close();
      });
      es.onerror = () => {
        // EventSource auto-retries by default. We keep that behaviour
        // while the run is in-flight; only `done` causes us to bail.
      };
    }

    open();
    return close;
  }, [runId, router]);

  return (
    <div className="flex items-center gap-2 rounded-md border border-blue-200 dark:border-blue-900 bg-blue-50 dark:bg-blue-950/40 p-2 text-sm text-blue-900 dark:text-blue-100">
      <span className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />
      Worker is processing this run — page updates live.
    </div>
  );
}
