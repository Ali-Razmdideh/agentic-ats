import Link from "next/link";
import { notFound } from "next/navigation";
import { requireUserAndOrg } from "@/lib/auth";
import {
  getRun,
  listAuditsForRun,
  listDecisionsForRun,
  listScoresForRun,
} from "@/lib/repo";
import StatusBadge from "@/components/StatusBadge";
import RunStatusPoller from "@/components/RunStatusPoller";
import type { Decision } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const runId = Number(id);
  if (!Number.isFinite(runId)) notFound();

  const { org } = await requireUserAndOrg();
  const run = await getRun(org.id, runId);
  if (!run) notFound();

  const [scores, audits, decisions] = await Promise.all([
    listScoresForRun(org.id, runId),
    listAuditsForRun(org.id, runId),
    listDecisionsForRun(org.id, runId),
  ]);
  const decisionByCandidate = new Map<number, Decision>(
    decisions.map((d) => [d.candidate_id, d]),
  );

  const isPending = run.status === "queued" || run.status === "running";

  const bias = audits.find((a) => a.kind === "bias");

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Run #{run.id}</h1>
          <p className="text-sm text-slate-500">
            JD: <span className="font-mono">{run.jd_path}</span>
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <StatusBadge status={run.status} />
          <p className="text-xs text-slate-500">
            Started {new Date(run.started_at).toLocaleString()}
          </p>
        </div>
      </div>

      {isPending && <RunStatusPoller runId={run.id} />}

      {bias && (
        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Bias audit
          </h2>
          <pre className="max-h-60 overflow-auto rounded bg-slate-50 p-3 text-xs">
            {JSON.stringify(bias.payload, null, 2)}
          </pre>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Candidates
        </h2>
        {scores.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
            {isPending
              ? "Worker is processing this run; results will appear here when scoring completes."
              : "No scored candidates for this run."}
          </div>
        ) : (
          <div className="grid gap-3">
            {scores.map((s) => {
              const d = decisionByCandidate.get(s.candidate_id);
              return (
                <Link
                  key={s.candidate_id}
                  href={`/runs/${run.id}/candidates/${s.candidate_id}`}
                  className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4 hover:border-slate-400"
                >
                  <div>
                    <p className="font-medium">
                      {s.name || `Candidate #${s.candidate_id}`}
                    </p>
                    <p className="text-sm text-slate-500">{s.email || "—"}</p>
                    {s.rationale && (
                      <p className="mt-1 line-clamp-2 max-w-2xl text-sm text-slate-600">
                        {s.rationale}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span className="text-2xl font-semibold tabular-nums">
                      {s.score.toFixed(2)}
                    </span>
                    {d && (
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          d.decision === "shortlist"
                            ? "bg-emerald-100 text-emerald-800"
                            : d.decision === "reject"
                              ? "bg-red-100 text-red-800"
                              : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {d.decision}
                      </span>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
