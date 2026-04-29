"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function RunStatusPoller({ runId }: { runId: number }) {
  const router = useRouter();
  useEffect(() => {
    let cancelled = false;
    async function tick() {
      while (!cancelled) {
        await new Promise((r) => setTimeout(r, 2500));
        if (cancelled) return;
        try {
          const res = await fetch(`/api/runs/${runId}/status`, {
            cache: "no-store",
          });
          if (!res.ok) continue;
          const j = (await res.json()) as { status: string };
          const done = !["queued", "running"].includes(j.status);
          if (done) {
            router.refresh();
            return;
          } else {
            router.refresh();
          }
        } catch {
          // swallow; try again
        }
      }
    }
    tick();
    return () => {
      cancelled = true;
    };
  }, [runId, router]);
  return (
    <div className="flex items-center gap-2 rounded-md border border-blue-200 bg-blue-50 p-2 text-sm text-blue-900">
      <span className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />
      Worker is processing this run — page refreshes automatically.
    </div>
  );
}
