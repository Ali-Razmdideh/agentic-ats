// Top-of-page summary for a candidate: score gauge, overall verdict,
// pros / cons distilled from agent outputs.
//
// Inputs:
//   - score row (matcher + verifier merged)
//   - red_flags audit payload (Gap[] / Overlap[] / inconsistencies[])
//   - enricher audit payload (GitHub stats; pros if strong, hidden otherwise)
//   - reviewer decision (overrides the auto-derived verdict)

import type {
  Decision,
  DecisionKind,
  ScoreRow,
  VerifierPayload,
} from "@/lib/types";

interface Props {
  score: ScoreRow | undefined;
  redFlagsPayload: unknown;
  enrichmentPayload: unknown;
  decision: Decision | null;
}

function asObject(x: unknown): Record<string, unknown> {
  return x && typeof x === "object" && !Array.isArray(x)
    ? (x as Record<string, unknown>)
    : {};
}

function asArray(x: unknown): unknown[] {
  return Array.isArray(x) ? x : [];
}

function asString(x: unknown, fallback = ""): string {
  return typeof x === "string" ? x : fallback;
}

function asNumber(x: unknown, fallback = 0): number {
  return typeof x === "number" && Number.isFinite(x) ? x : fallback;
}

interface Verdict {
  label: string;
  description: string;
  tone: "emerald" | "amber" | "red" | "slate" | "indigo";
  reviewer: boolean;
}

function deriveVerdict(
  score: number | undefined,
  decision: DecisionKind | null,
): Verdict {
  // Reviewer's manual call wins.
  if (decision === "shortlist") {
    return {
      label: "Shortlisted",
      description: "Reviewer has shortlisted this candidate.",
      tone: "emerald",
      reviewer: true,
    };
  }
  if (decision === "reject") {
    return {
      label: "Rejected",
      description: "Reviewer has rejected this candidate.",
      tone: "red",
      reviewer: true,
    };
  }
  if (decision === "hold") {
    return {
      label: "On hold",
      description: "Reviewer is keeping this candidate pending more info.",
      tone: "amber",
      reviewer: true,
    };
  }

  // Otherwise derive from the auto score.
  if (score == null) {
    return {
      label: "Pending",
      description: "Scoring hasn't completed for this candidate yet.",
      tone: "slate",
      reviewer: false,
    };
  }
  if (score >= 0.7) {
    return {
      label: "Strong fit",
      description: "High match against the JD's must-have requirements.",
      tone: "emerald",
      reviewer: false,
    };
  }
  if (score >= 0.4) {
    return {
      label: "Mixed fit",
      description: "Partial match — some must-haves missing or unverified.",
      tone: "amber",
      reviewer: false,
    };
  }
  return {
    label: "Weak fit",
    description: "Most JD must-haves not met by this resume.",
    tone: "red",
    reviewer: false,
  };
}

const TONE_CSS: Record<Verdict["tone"], { ring: string; text: string; bg: string; border: string }> = {
  emerald: {
    ring: "ring-emerald-500",
    text: "text-emerald-700",
    bg: "bg-emerald-50",
    border: "border-emerald-200",
  },
  amber: {
    ring: "ring-amber-500",
    text: "text-amber-700",
    bg: "bg-amber-50",
    border: "border-amber-200",
  },
  red: {
    ring: "ring-red-500",
    text: "text-red-700",
    bg: "bg-red-50",
    border: "border-red-200",
  },
  slate: {
    ring: "ring-slate-400",
    text: "text-slate-600",
    bg: "bg-slate-50",
    border: "border-slate-200",
  },
  indigo: {
    ring: "ring-indigo-500",
    text: "text-indigo-700",
    bg: "bg-indigo-50",
    border: "border-indigo-200",
  },
};

interface Bullet {
  text: string;
  detail?: string;
}

function buildPros(
  verified: VerifierPayload | null | undefined,
  enrichment: unknown,
): Bullet[] {
  const out: Bullet[] = [];
  for (const skill of asArray(verified?.verified ?? [])
    .map((s) => asString(s))
    .filter(Boolean)) {
    out.push({ text: `Verified skill: ${skill}` });
  }

  const e = asObject(enrichment);
  const repos = asNumber(e.public_repos);
  const followers = asNumber(e.followers);
  if (repos >= 5) {
    out.push({
      text: `Active GitHub presence (${repos} public repos)`,
    });
  }
  if (followers >= 25) {
    out.push({
      text: `Notable GitHub following (${followers} followers)`,
    });
  }
  const langs = asArray(e.top_languages)
    .map((l) => asString(l))
    .filter(Boolean);
  if (langs.length > 0) {
    out.push({ text: `Top languages: ${langs.slice(0, 5).join(", ")}` });
  }
  return out;
}

function buildCons(
  verified: VerifierPayload | null | undefined,
  redFlags: unknown,
): Bullet[] {
  const out: Bullet[] = [];

  for (const skill of asArray(verified?.hallucinated ?? [])
    .map((s) => asString(s))
    .filter(Boolean)) {
    out.push({
      text: `Unverified claim: ${skill}`,
      detail: "Skill mentioned but not substantiated in the resume body.",
    });
  }

  const rf = asObject(redFlags);
  const gaps = asArray(rf.gaps).map(asObject);
  for (const g of gaps) {
    const months = asNumber(g.months);
    if (months <= 0) continue;
    out.push({
      text: `Employment gap (${months} months)`,
      detail: `${asString(g.before) || "?"} → ${asString(g.after) || "?"}`,
    });
  }
  const overlaps = asArray(rf.overlaps).map(asObject);
  for (const o of overlaps) {
    const months = asNumber(o.months);
    if (months <= 0) continue;
    out.push({
      text: `Overlapping roles (${months} months)`,
      detail: `${asString(o.a) || "?"} ↔ ${asString(o.b) || "?"}`,
    });
  }
  for (const inc of asArray(rf.inconsistencies)
    .map((s) => asString(s))
    .filter(Boolean)) {
    out.push({ text: inc });
  }
  return out;
}

function ScoreGauge({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(1, score));
  const tone = pct >= 0.7 ? "emerald" : pct >= 0.4 ? "amber" : "red";
  const fillCss =
    tone === "emerald"
      ? "bg-emerald-500"
      : tone === "amber"
        ? "bg-amber-500"
        : "bg-red-500";
  return (
    <div className="flex flex-col items-center justify-center gap-2">
      <div className="relative">
        <span className="text-5xl font-semibold tabular-nums text-slate-900 dark:text-slate-50">
          {score.toFixed(2)}
        </span>
        <span className="ml-1 text-sm text-slate-500 dark:text-slate-400">/ 1.00</span>
      </div>
      <div className="w-40">
        <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
          <div
            className={`h-full rounded-full ${fillCss}`}
            style={{ width: `${pct * 100}%` }}
          />
        </div>
        <div className="mt-1 flex justify-between text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
          <span>0</span>
          <span>0.4</span>
          <span>0.7</span>
          <span>1</span>
        </div>
      </div>
    </div>
  );
}

export default function CandidateSummary({
  score,
  redFlagsPayload,
  enrichmentPayload,
  decision,
}: Props) {
  const verdict = deriveVerdict(score?.score, decision?.decision ?? null);
  const tone = TONE_CSS[verdict.tone];
  const pros = buildPros(score?.verified ?? null, enrichmentPayload);
  const cons = buildCons(score?.verified ?? null, redFlagsPayload);

  return (
    <section
      className={`rounded-xl border ${tone.border} ${tone.bg} p-5 shadow-sm`}
    >
      <div className="grid grid-cols-1 gap-6 md:grid-cols-[auto_1fr]">
        {/* Left: score + verdict */}
        <div className="flex flex-col items-center justify-center gap-3 border-b border-slate-200 dark:border-slate-800 pb-4 md:border-b-0 md:border-r md:pb-0 md:pr-6">
          {score ? (
            <ScoreGauge score={score.score} />
          ) : (
            <p className="text-sm italic text-slate-500 dark:text-slate-400">Not scored yet</p>
          )}
          <div
            className={`inline-flex items-center rounded-full bg-white dark:bg-slate-900 px-3 py-1 text-sm font-semibold ring-2 ring-inset ${tone.ring} ${tone.text}`}
          >
            {verdict.label}
            {verdict.reviewer && (
              <span className="ml-1.5 text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
                reviewer
              </span>
            )}
          </div>
          <p className="max-w-xs text-center text-xs text-slate-600 dark:text-slate-300">
            {verdict.description}
          </p>
        </div>

        {/* Right: pros / cons */}
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <Column
            title="Pros"
            items={pros}
            emptyText="No verified strengths surfaced yet."
            tone="emerald"
            icon="✓"
          />
          <Column
            title="Cons"
            items={cons}
            emptyText="No concerns flagged."
            tone="red"
            icon="✕"
          />
        </div>
      </div>

      {score?.rationale && (
        <div className="mt-5 rounded-md border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2 text-sm leading-relaxed text-slate-700 dark:text-slate-200">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Match rationale
          </p>
          {score.rationale}
        </div>
      )}
    </section>
  );
}

function Column({
  title,
  items,
  emptyText,
  tone,
  icon,
}: {
  title: string;
  items: Bullet[];
  emptyText: string;
  tone: "emerald" | "red";
  icon: string;
}) {
  const iconCss =
    tone === "emerald"
      ? "bg-emerald-100 text-emerald-700"
      : "bg-red-100 text-red-700";
  return (
    <div>
      <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-200">
        <span
          className={`inline-flex h-5 w-5 items-center justify-center rounded-full ${iconCss}`}
        >
          {icon}
        </span>
        {title} ({items.length})
      </h3>
      {items.length === 0 ? (
        <p className="text-xs italic text-slate-500 dark:text-slate-400">{emptyText}</p>
      ) : (
        <ul className="space-y-1.5 text-sm text-slate-800 dark:text-slate-100">
          {items.map((b, i) => (
            <li key={i} className="flex gap-2">
              <span
                className={`mt-1 h-1.5 w-1.5 flex-none rounded-full ${tone === "emerald" ? "bg-emerald-500" : "bg-red-500"}`}
              />
              <span className="flex-1">
                {b.text}
                {b.detail && (
                  <span className="block text-xs text-slate-500 dark:text-slate-400">
                    {b.detail}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
