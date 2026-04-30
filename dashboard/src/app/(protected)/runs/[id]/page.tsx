import Link from "next/link";
import { notFound } from "next/navigation";
import { requireUserAndOrg } from "@/lib/auth";
import { pool } from "@/lib/db";
import {
  getRun,
  listAuditEventsForRun,
  listAuditsForRun,
  listDecisionsForRun,
  listScoresForRun,
} from "@/lib/repo";
import StatusBadge from "@/components/StatusBadge";
import RunStatusPoller from "@/components/RunStatusPoller";
import PipelineProgress from "@/components/PipelineProgress";
import RunJobDescription from "@/components/RunJobDescription";
import type { Decision } from "@/lib/types";

async function hasShortlistRows(orgId: number, runId: number): Promise<boolean> {
  const r = await pool.query<{ exists: boolean }>(
    `SELECT EXISTS (
        SELECT 1 FROM shortlists WHERE org_id = $1 AND run_id = $2
     ) AS exists`,
    [orgId, runId],
  );
  return r.rows[0]?.exists === true;
}

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

  const [scores, audits, decisions, events, shortlistsExist] = await Promise.all([
    listScoresForRun(org.id, runId),
    listAuditsForRun(org.id, runId),
    listDecisionsForRun(org.id, runId),
    listAuditEventsForRun(org.id, runId, 50),
    hasShortlistRows(org.id, runId),
  ]);
  const decisionByCandidate = new Map<number, Decision>(
    decisions.map((d) => [d.candidate_id, d]),
  );

  const isPending = run.status === "queued" || run.status === "running";

  const bias = audits.find((a) => a.kind === "bias");
  const jdParsed = audits.find((a) => a.kind === "jd_parsed")?.payload;
  const runError = audits.find((a) => a.kind === "run_error")?.payload as
    | { error_type?: string; message?: string }
    | undefined;

  const expectedCandidates = run.queued_inputs?.resume_blob_keys?.length ?? scores.length;
  const skipOptional = run.queued_inputs?.skip_optional ?? false;

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between">
        <h1 className="text-2xl font-semibold">Run #{run.id}</h1>
        <div className="flex flex-col items-end gap-1">
          <StatusBadge status={run.status} />
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Started {new Date(run.started_at).toLocaleString()}
          </p>
        </div>
      </div>

      {isPending && <RunStatusPoller runId={run.id} />}

      {runError && (
        <section className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 p-4">
          <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-red-800 dark:text-red-200">
            <span>⨯</span>
            Run failed
          </h2>
          <p className="text-sm text-red-900 dark:text-red-100">
            {runError.error_type && (
              <span className="font-mono text-xs text-red-700 dark:text-red-300">
                {runError.error_type}:{" "}
              </span>
            )}
            {runError.message || "Unknown error."}
          </p>
          <p className="mt-2 text-xs text-red-700 dark:text-red-300">
            The orchestrator hit an unrecoverable error and stopped. Re-upload
            and try again; if it keeps happening, check{" "}
            <code className="rounded bg-white dark:bg-slate-900 px-1 py-0.5">
              docker compose logs worker
            </code>
            .
          </p>
        </section>
      )}

      <RunJobDescription
        jdParsedPayload={jdParsed}
        jdPath={run.jd_path}
        jdBlobKey={run.jd_blob_key}
      />

      <PipelineProgress
        status={run.status}
        expectedCandidates={expectedCandidates}
        skipOptional={skipOptional}
        scores={scores}
        audits={audits}
        events={events}
        hasShortlists={shortlistsExist}
      />

      {bias && (
        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Bias audit
          </h2>
          <pre className="max-h-60 overflow-auto rounded bg-slate-50 dark:bg-slate-950 p-3 text-xs">
            {JSON.stringify(bias.payload, null, 2)}
          </pre>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Candidates
        </h2>
        {scores.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 text-center text-sm text-slate-500 dark:text-slate-400">
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
                  className="flex items-center justify-between rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 hover:border-slate-400 dark:hover:border-slate-500"
                >
                  <div>
                    <p className="font-medium">
                      {s.name || `Candidate #${s.candidate_id}`}
                    </p>
                    <p className="text-sm text-slate-500 dark:text-slate-400">{s.email || "—"}</p>
                    {s.rationale && (
                      <p className="mt-1 line-clamp-2 max-w-2xl text-sm text-slate-600 dark:text-slate-300">
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
                            ? "bg-emerald-100 dark:bg-emerald-900/50 text-emerald-800 dark:text-emerald-200"
                            : d.decision === "reject"
                              ? "bg-red-100 dark:bg-red-900/50 text-red-800 dark:text-red-200"
                              : "bg-amber-100 dark:bg-amber-900/50 text-amber-800 dark:text-amber-200"
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
