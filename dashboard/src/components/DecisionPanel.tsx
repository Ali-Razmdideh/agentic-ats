"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import type { DecisionKind } from "@/lib/types";

const OPTIONS: Array<{ value: DecisionKind; label: string; cls: string }> = [
  {
    value: "shortlist",
    label: "Shortlist",
    cls: "bg-emerald-100 text-emerald-800 hover:bg-emerald-200",
  },
  {
    value: "hold",
    label: "Hold",
    cls: "bg-amber-100 text-amber-800 hover:bg-amber-200",
  },
  {
    value: "reject",
    label: "Reject",
    cls: "bg-red-100 text-red-800 hover:bg-red-200",
  },
];

export default function DecisionPanel({
  runId,
  candidateId,
  currentDecision,
  currentNotes,
}: {
  runId: number;
  candidateId: number;
  currentDecision: DecisionKind | null;
  currentNotes: string;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [decision, setDecision] = useState<DecisionKind | null>(
    currentDecision,
  );
  const [notes, setNotes] = useState(currentNotes);
  const [saved, setSaved] = useState<string | null>(null);

  function submit(value: DecisionKind, n: string) {
    startTransition(async () => {
      const fd = new FormData();
      fd.set("run_id", String(runId));
      fd.set("candidate_id", String(candidateId));
      fd.set("decision", value);
      fd.set("notes", n);
      const res = await fetch("/api/decisions", { method: "POST", body: fd });
      if (res.ok) {
        setDecision(value);
        setSaved("Saved.");
        setTimeout(() => setSaved(null), 1500);
        router.refresh();
      } else {
        setSaved("Save failed.");
      }
    });
  }

  return (
    <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Decision
        </h2>
        {saved && <span className="text-xs text-slate-500 dark:text-slate-400">{saved}</span>}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {OPTIONS.map((o) => (
          <button
            key={o.value}
            type="button"
            disabled={pending}
            onClick={() => submit(o.value, notes)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${
              decision === o.value
                ? `${o.cls} ring-2 ring-offset-1 ring-slate-900`
                : o.cls
            } disabled:opacity-50`}
          >
            {o.label}
          </button>
        ))}
      </div>
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Notes (optional)…"
        rows={3}
        className="mt-3 block w-full rounded-md border border-slate-300 dark:border-slate-700 px-3 py-2 text-sm focus:border-slate-900 dark:focus:border-slate-100 focus:outline-none focus:ring-1 focus:ring-slate-900 dark:focus:ring-slate-100"
      />
      <div className="mt-2 text-right">
        <button
          type="button"
          disabled={pending || decision === null}
          onClick={() => decision && submit(decision, notes)}
          className="rounded-md bg-slate-900 dark:bg-slate-100 dark:text-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 dark:hover:bg-slate-700 disabled:opacity-50"
        >
          Save notes
        </button>
      </div>
    </section>
  );
}
