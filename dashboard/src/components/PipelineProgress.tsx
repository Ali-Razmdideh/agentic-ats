// Server component. Renders a checklist of orchestrator stages + a
// recent-events log so reviewers can see live progress while a run is
// in `running`/`queued`. The run-detail page's RunStatusPoller calls
// router.refresh() every 2.5s, which re-renders this with fresh data.

import type { AuditEvent, AuditEntry, ScoreRow } from "@/lib/types";

type StageState = "done" | "in_progress" | "pending" | "skipped";

interface Stage {
  id: string;
  label: string;
  state: StageState;
  detail?: string;
}

interface Props {
  status: string;
  expectedCandidates: number;
  skipOptional: boolean;
  scores: ScoreRow[];
  audits: AuditEntry[];
  events: AuditEvent[];
  hasShortlists: boolean;
}

function countByPrefix(audits: AuditEntry[], prefix: string): number {
  return audits.filter((a) => a.kind.startsWith(prefix)).length;
}

function hasKind(audits: AuditEntry[], kind: string): boolean {
  return audits.some((a) => a.kind === kind);
}

function buildStages(p: Omit<Props, "events">): Stage[] {
  const total = Math.max(p.expectedCandidates, 1);
  const scoredCount = p.scores.length;
  const redFlagsCount = countByPrefix(p.audits, "red_flags:");
  const interviewQsCount = countByPrefix(p.audits, "interview_qs:");
  const enricherCount = countByPrefix(p.audits, "enricher:");
  const dedupPresent = hasKind(p.audits, "dedup");
  const isFinished =
    p.status === "ok" ||
    p.status === "completed" ||
    p.status === "failed" ||
    p.status === "cancelled" ||
    p.status === "blocked_by_bias" ||
    p.status === "budget_exceeded";

  function stageOf(done: number, expected: number): StageState {
    if (done >= expected && expected > 0) return "done";
    if (done > 0) return "in_progress";
    return isFinished ? "skipped" : "pending";
  }

  function flag(present: boolean): StageState {
    if (present) return "done";
    return isFinished ? "skipped" : "pending";
  }

  // Resume parsing isn't audited per-resume — we only know it finished
  // once *something* downstream ran. If dedup ran, all parsers ran (dedup
  // sees every parsed_resume). If a score landed, that resume was parsed.
  // For mid-flight runs without those signals, show "in progress" so it
  // doesn't read as 0/4 when parsers are clearly busy.
  let parseState: StageState;
  let parseDetail: string;
  if (dedupPresent || scoredCount >= total) {
    parseState = "done";
    parseDetail = `${total} / ${total}`;
  } else if (scoredCount > 0) {
    parseState = "in_progress";
    parseDetail = `${scoredCount} / ${total}`;
  } else if (isFinished) {
    parseState = "skipped";
    parseDetail = `0 / ${total}`;
  } else {
    parseState = "in_progress";
    parseDetail = `… / ${total}`;
  }

  const stages: Stage[] = [
    {
      id: "jd",
      label: "JD analysis",
      state: flag(hasKind(p.audits, "jd_parsed")),
    },
    {
      id: "parse",
      label: "Resume parsing",
      state: parseState,
      detail: parseDetail,
    },
    {
      id: "dedup",
      label: "Deduplication",
      state: flag(dedupPresent),
    },
    {
      id: "score",
      label: "Scoring (matcher + verifier)",
      state: stageOf(scoredCount, total),
      detail: `${Math.min(scoredCount, total)} / ${total}`,
    },
  ];

  if (!p.skipOptional) {
    stages.push(
      {
        id: "red_flags",
        label: "Red flags",
        state: stageOf(redFlagsCount, total),
        detail: `${redFlagsCount} / ${total}`,
      },
      {
        id: "interview_qs",
        label: "Interview questions",
        state: stageOf(interviewQsCount, total),
        detail: `${interviewQsCount} / ${total}`,
      },
      {
        id: "enricher",
        label: "GitHub enrichment",
        state:
          enricherCount > 0
            ? isFinished
              ? "done"
              : "in_progress"
            : isFinished
              ? "skipped"
              : "pending",
        detail: enricherCount > 0 ? `${enricherCount} / ${total}` : undefined,
      },
    );
  }

  stages.push(
    { id: "bias", label: "Bias audit", state: flag(hasKind(p.audits, "bias")) },
    { id: "ranker", label: "Ranking", state: flag(p.hasShortlists) },
    {
      id: "outreach",
      label: "Outreach drafts",
      state: flag(hasKind(p.audits, "outreach")),
    },
  );

  return stages;
}

const STATE_STYLES: Record<StageState, { dot: string; label: string }> = {
  done: { dot: "bg-emerald-500", label: "text-slate-700" },
  in_progress: { dot: "bg-blue-500 animate-pulse", label: "text-slate-700" },
  pending: { dot: "bg-slate-300", label: "text-slate-400" },
  skipped: { dot: "bg-slate-200", label: "text-slate-400 line-through" },
};

const KIND_LABEL: Record<string, string> = {
  jd_parsed: "JD analyzed",
  dedup: "Deduplication",
  bias: "Bias audit",
  outreach: "Outreach drafts",
  run_error: "Run failed",
};

function prettyKind(kind: string): string {
  if (KIND_LABEL[kind]) return KIND_LABEL[kind]!;
  if (kind.startsWith("red_flags:")) {
    return `Red flags · candidate #${kind.split(":")[1]}`;
  }
  if (kind.startsWith("interview_qs:")) {
    return `Interview Qs · candidate #${kind.split(":")[1]}`;
  }
  if (kind.startsWith("enricher:")) {
    return `GitHub enrichment · candidate #${kind.split(":")[1]}`;
  }
  return kind;
}

export default function PipelineProgress(props: Props) {
  const stages = buildStages(props);
  const counted = stages.filter((s) => s.state === "done").length;
  return (
    <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Pipeline progress
        </h2>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {counted} / {stages.length} stages complete
          {props.skipOptional ? " · optional agents skipped" : ""}
        </p>
      </div>
      <ol className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {stages.map((s) => {
          const css = STATE_STYLES[s.state];
          return (
            <li
              key={s.id}
              className="flex items-center gap-3 rounded-md bg-slate-50 dark:bg-slate-950 px-3 py-2 text-sm"
            >
              <span className={`h-2 w-2 rounded-full ${css.dot}`} />
              <span className={`flex-1 ${css.label}`}>{s.label}</span>
              {s.detail && (
                <span className="font-mono text-xs text-slate-500 dark:text-slate-400">
                  {s.detail}
                </span>
              )}
            </li>
          );
        })}
      </ol>

      {props.events.length > 0 && (
        <details className="mt-4 text-xs" open={props.events.length <= 8}>
          <summary className="cursor-pointer font-medium text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-50">
            Recent agent events ({props.events.length})
          </summary>
          <ul className="mt-2 max-h-64 space-y-1 overflow-y-auto rounded bg-slate-50 dark:bg-slate-950 p-2 font-mono text-[11px] text-slate-700 dark:text-slate-200">
            {props.events.map((e) => (
              <li key={e.id} className="flex justify-between gap-3">
                <span className="text-slate-500 dark:text-slate-400">
                  {new Date(e.created_at).toLocaleTimeString()}
                </span>
                <span className="flex-1 truncate">{prettyKind(e.kind)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
