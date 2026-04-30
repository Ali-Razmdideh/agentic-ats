// Job description card — renders the jd_analyzer audit payload as a
// structured view (role, seniority, must-haves, nice-to-haves,
// responsibilities, min years) plus a download link to the raw JD blob
// in MinIO.

import type { ReactNode } from "react";
import JdDownloadLink from "./JdDownloadLink";

interface Props {
  jdParsedPayload: unknown;
  jdPath: string;
  jdBlobKey: string | null;
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

function Chip({
  children,
  tone = "slate",
}: {
  children: ReactNode;
  tone?: "slate" | "rose" | "indigo" | "blue" | "emerald";
}) {
  const tones: Record<string, string> = {
    slate: "bg-slate-100 text-slate-700 border-slate-200",
    rose: "bg-rose-50 text-rose-800 border-rose-200",
    indigo: "bg-indigo-50 text-indigo-800 border-indigo-200",
    blue: "bg-blue-50 text-blue-800 border-blue-200",
    emerald: "bg-emerald-50 text-emerald-800 border-emerald-200",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export default function RunJobDescription({
  jdParsedPayload,
  jdPath,
  jdBlobKey,
}: Props) {
  const p = asObject(jdParsedPayload);

  // If jd_analyzer hasn't run yet, fall back to a thin card with just
  // the JD path + download link so reviewers aren't staring at nothing
  // during the early seconds of a run.
  const hasParse = Object.keys(p).length > 0;

  const role = asString(p.role_family) || "—";
  const seniority = asString(p.seniority) || "—";
  const minYears = typeof p.min_years === "number" ? p.min_years : null;
  const mustHave = asArray(p.must_have)
    .map((s) => asString(s))
    .filter(Boolean);
  const niceToHave = asArray(p.nice_to_have)
    .map((s) => asString(s))
    .filter(Boolean);
  const responsibilities = asArray(p.responsibilities)
    .map((s) => asString(s))
    .filter(Boolean);

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Job description
          </h2>
          <p className="mt-0.5 font-mono text-xs text-slate-500">{jdPath}</p>
        </div>
        {jdBlobKey && <JdDownloadLink blobKey={jdBlobKey} />}
      </div>

      {!hasParse ? (
        <p className="rounded-md border border-dashed border-slate-300 bg-slate-50 p-4 text-sm italic text-slate-500">
          JD analysis pending — the jd_analyzer agent hasn't completed yet.
        </p>
      ) : (
        <div className="space-y-5">
          {/* Headline: role + seniority + min years */}
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-xl font-semibold text-slate-900">{role}</h3>
            <Chip tone="indigo">{seniority}</Chip>
            {minYears != null && (
              <Chip tone="slate">{minYears}+ yrs experience</Chip>
            )}
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            {/* Must-haves */}
            <Block
              title="Must-have requirements"
              count={mustHave.length}
              tone="rose"
              icon="●"
            >
              {mustHave.length === 0 ? (
                <p className="text-sm italic text-slate-500">
                  No must-haves identified.
                </p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {mustHave.map((s, i) => (
                    <Chip key={`mh-${s}-${i}`} tone="rose">
                      {s}
                    </Chip>
                  ))}
                </div>
              )}
            </Block>

            {/* Nice-to-haves */}
            <Block
              title="Nice to have"
              count={niceToHave.length}
              tone="blue"
              icon="○"
            >
              {niceToHave.length === 0 ? (
                <p className="text-sm italic text-slate-500">
                  None listed.
                </p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {niceToHave.map((s, i) => (
                    <Chip key={`nh-${s}-${i}`} tone="blue">
                      {s}
                    </Chip>
                  ))}
                </div>
              )}
            </Block>
          </div>

          {/* Responsibilities */}
          {responsibilities.length > 0 && (
            <Block
              title="Responsibilities"
              count={responsibilities.length}
              tone="emerald"
              icon="→"
            >
              <ul className="space-y-1.5 text-sm text-slate-800">
                {responsibilities.map((r, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="mt-1 h-1.5 w-1.5 flex-none rounded-full bg-emerald-500" />
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </Block>
          )}
        </div>
      )}
    </section>
  );
}

function Block({
  title,
  count,
  tone,
  icon,
  children,
}: {
  title: string;
  count: number;
  tone: "rose" | "blue" | "emerald" | "slate";
  icon: string;
  children: ReactNode;
}) {
  const headerTone: Record<string, string> = {
    rose: "text-rose-700",
    blue: "text-blue-700",
    emerald: "text-emerald-700",
    slate: "text-slate-700",
  };
  return (
    <div>
      <h4
        className={`mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide ${headerTone[tone]}`}
      >
        <span>{icon}</span>
        {title}
        {count > 0 && (
          <span className="rounded-full bg-slate-100 px-1.5 font-mono text-[10px] text-slate-600">
            {count}
          </span>
        )}
      </h4>
      {children}
    </div>
  );
}
