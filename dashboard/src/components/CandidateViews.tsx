// Server components for rich candidate-detail visualizations.
// All four agent payloads (parsed resume, red flags, interview Qs,
// enrichment) come in as `unknown` JSONB from Postgres; we shape them
// safely at render time without depending on any chart library.

import type { ReactNode } from "react";

// ---------- shared helpers -------------------------------------------------

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

function Chip({
  children,
  tone = "slate",
}: {
  children: ReactNode;
  tone?: "slate" | "emerald" | "amber" | "red" | "indigo" | "blue";
}) {
  const tones: Record<string, string> = {
    slate: "bg-slate-100 text-slate-700 border-slate-200",
    emerald: "bg-emerald-50 text-emerald-800 border-emerald-200",
    amber: "bg-amber-50 text-amber-800 border-amber-200",
    red: "bg-red-50 text-red-800 border-red-200",
    indigo: "bg-indigo-50 text-indigo-800 border-indigo-200",
    blue: "bg-blue-50 text-blue-800 border-blue-200",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

function Bar({
  value,
  max,
  tone = "slate",
}: {
  value: number;
  max: number;
  tone?: "slate" | "emerald" | "amber" | "red" | "blue";
}) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  const tones: Record<string, string> = {
    slate: "bg-slate-500",
    emerald: "bg-emerald-500",
    amber: "bg-amber-500",
    red: "bg-red-500",
    blue: "bg-blue-500",
  };
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
      <div
        className={`h-full rounded-full ${tones[tone]}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

// ---------- parsed resume --------------------------------------------------

export function ParsedResumeView({ parsed }: { parsed: unknown }) {
  const p = asObject(parsed);
  const contact = asObject(p.contact);
  const summary = asString(p.summary);
  const skills = asArray(p.skills).map((s) => asString(s)).filter(Boolean);
  const experience = asArray(p.experience).map(asObject);
  const education = asArray(p.education).map(asObject);
  const links = asArray(p.links).map((l) => asString(l)).filter(Boolean);

  return (
    <div className="space-y-6">
      {/* Contact card */}
      <div className="grid grid-cols-1 gap-3 rounded-md bg-slate-50 p-3 text-sm sm:grid-cols-4">
        <Field label="Name" value={asString(contact.name) || "—"} />
        <Field label="Email" value={asString(contact.email) || "—"} mono />
        <Field label="Phone" value={asString(contact.phone) || "—"} mono />
        <Field label="Location" value={asString(contact.location) || "—"} />
      </div>

      {summary && (
        <p className="rounded-md border-l-4 border-slate-300 bg-slate-50/50 px-3 py-2 text-sm leading-relaxed text-slate-700">
          {summary}
        </p>
      )}

      {/* Skills */}
      {skills.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Skills ({skills.length})
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {skills.map((s, i) => (
              <Chip key={`${s}-${i}`} tone="indigo">
                {s}
              </Chip>
            ))}
          </div>
        </div>
      )}

      {/* Experience timeline */}
      {experience.length > 0 && (
        <div>
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Experience ({experience.length})
          </h3>
          <ol className="relative space-y-4 border-l-2 border-slate-200 pl-5">
            {experience.map((e, i) => {
              const start = asString(e.start);
              const end = asString(e.end) || "Present";
              const bullets = asArray(e.bullets)
                .map((b) => asString(b))
                .filter(Boolean);
              return (
                <li key={i} className="relative">
                  <span className="absolute -left-[27px] top-1 h-3 w-3 rounded-full border-2 border-white bg-slate-400" />
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <p className="text-sm font-semibold text-slate-900">
                      {asString(e.title) || "—"}{" "}
                      <span className="font-normal text-slate-500">
                        @ {asString(e.company) || "—"}
                      </span>
                    </p>
                    <p className="font-mono text-xs text-slate-500">
                      {start || "?"} – {end}
                    </p>
                  </div>
                  {bullets.length > 0 && (
                    <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-slate-700">
                      {bullets.map((b, j) => (
                        <li key={j}>{b}</li>
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ol>
        </div>
      )}

      {/* Education */}
      {education.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Education ({education.length})
          </h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {education.map((ed, i) => (
              <div
                key={i}
                className="rounded-md border border-slate-200 bg-white p-3 text-sm"
              >
                <p className="font-medium text-slate-900">
                  {asString(ed.school) || "—"}
                </p>
                <p className="text-slate-600">
                  {asString(ed.degree)}
                  {ed.field ? ` · ${asString(ed.field)}` : ""}
                </p>
                {ed.year_end != null && (
                  <p className="text-xs text-slate-500">{asNumber(ed.year_end)}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Links */}
      {links.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Links
          </h3>
          <div className="flex flex-wrap gap-2 text-sm">
            {links.map((l, i) => (
              <LinkChip key={`${l}-${i}`} url={l} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Maps a URL to a friendly label / icon by looking at its domain. Used in
// the "Links" section of the parsed-resume view so chips read "LinkedIn"
// instead of `https://linkedin.com/in/...`. Falls back to the bare host.
function describeLink(url: string): {
  label: string;
  icon: string;
  href: string;
  tone: "blue" | "slate" | "indigo" | "emerald" | "amber";
} {
  let href = url.trim();
  if (
    !href.startsWith("http://") &&
    !href.startsWith("https://") &&
    !href.startsWith("mailto:") &&
    !href.startsWith("tel:")
  ) {
    // bare-host or "linkedin.com/foo" — make it a real link
    href = `https://${href}`;
  }
  let host = "";
  try {
    host = new URL(href).hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return { label: url, icon: "↗", href, tone: "slate" };
  }
  if (host === "linkedin.com" || host.endsWith(".linkedin.com")) {
    return { label: "LinkedIn", icon: "in", href, tone: "blue" };
  }
  if (host === "github.com") {
    return { label: "GitHub", icon: "GH", href, tone: "slate" };
  }
  if (host.endsWith("stackoverflow.com")) {
    return { label: "Stack Overflow", icon: "SO", href, tone: "amber" };
  }
  if (host.endsWith("twitter.com") || host === "x.com") {
    return { label: "X", icon: "𝕏", href, tone: "slate" };
  }
  if (host.endsWith("kaggle.com")) {
    return { label: "Kaggle", icon: "K", href, tone: "blue" };
  }
  if (host.endsWith("medium.com")) {
    return { label: "Medium", icon: "M", href, tone: "slate" };
  }
  if (host === "wa.me" || host.endsWith("whatsapp.com")) {
    return { label: "WhatsApp", icon: "WA", href, tone: "emerald" };
  }
  if (host === "t.me" || host.endsWith("telegram.org")) {
    return { label: "Telegram", icon: "TG", href, tone: "blue" };
  }
  if (href.startsWith("mailto:")) {
    return { label: href.slice(7), icon: "✉", href, tone: "slate" };
  }
  return { label: host, icon: "↗", href, tone: "slate" };
}

function LinkChip({ url }: { url: string }) {
  const { label, icon, href, tone } = describeLink(url);
  const tones: Record<string, string> = {
    slate: "bg-slate-50 border-slate-200 text-slate-700 hover:bg-white",
    blue: "bg-blue-50 border-blue-200 text-blue-800 hover:bg-white",
    indigo: "bg-indigo-50 border-indigo-200 text-indigo-800 hover:bg-white",
    emerald: "bg-emerald-50 border-emerald-200 text-emerald-800 hover:bg-white",
    amber: "bg-amber-50 border-amber-200 text-amber-800 hover:bg-white",
  };
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={href}
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs ${tones[tone]}`}
    >
      <span className="font-mono text-[10px] font-bold opacity-70">{icon}</span>
      <span>{label}</span>
    </a>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
      <p
        className={`text-sm text-slate-900 ${mono ? "font-mono break-all" : ""}`}
      >
        {value}
      </p>
    </div>
  );
}

// ---------- red flags ------------------------------------------------------

export function RedFlagsView({ payload }: { payload: unknown }) {
  const p = asObject(payload);
  const gaps = asArray(p.gaps).map(asObject);
  const overlaps = asArray(p.overlaps).map(asObject);
  const inconsistencies = asArray(p.inconsistencies)
    .map((x) => asString(x))
    .filter(Boolean);

  if (
    gaps.length === 0 &&
    overlaps.length === 0 &&
    inconsistencies.length === 0
  ) {
    return (
      <p className="text-sm italic text-slate-500">No red flags detected.</p>
    );
  }

  const maxMonths = Math.max(
    1,
    ...gaps.map((g) => asNumber(g.months)),
    ...overlaps.map((o) => asNumber(o.months)),
  );

  return (
    <div className="space-y-5">
      {gaps.length > 0 && (
        <FlagBlock
          title={`Employment gaps (${gaps.length})`}
          tone="red"
          icon="⏳"
        >
          <ul className="space-y-2">
            {gaps.map((g, i) => {
              const months = asNumber(g.months);
              return (
                <li key={i} className="text-sm">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-slate-700">
                      <span className="font-mono text-slate-500">
                        {asString(g.before) || "?"}
                      </span>{" "}
                      →{" "}
                      <span className="font-mono text-slate-500">
                        {asString(g.after) || "?"}
                      </span>
                    </span>
                    <span className="font-mono text-xs text-red-700">
                      {months} mo
                    </span>
                  </div>
                  <Bar value={months} max={maxMonths} tone="red" />
                </li>
              );
            })}
          </ul>
        </FlagBlock>
      )}

      {overlaps.length > 0 && (
        <FlagBlock
          title={`Overlapping roles (${overlaps.length})`}
          tone="amber"
          icon="⤫"
        >
          <ul className="space-y-2">
            {overlaps.map((o, i) => {
              const months = asNumber(o.months);
              return (
                <li key={i} className="text-sm">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-slate-700">
                      <span className="font-mono text-slate-500">
                        {asString(o.a) || "?"}
                      </span>{" "}
                      ↔{" "}
                      <span className="font-mono text-slate-500">
                        {asString(o.b) || "?"}
                      </span>
                    </span>
                    <span className="font-mono text-xs text-amber-700">
                      {months} mo
                    </span>
                  </div>
                  <Bar value={months} max={maxMonths} tone="amber" />
                </li>
              );
            })}
          </ul>
        </FlagBlock>
      )}

      {inconsistencies.length > 0 && (
        <FlagBlock
          title={`Inconsistencies (${inconsistencies.length})`}
          tone="amber"
          icon="!"
        >
          <ul className="space-y-1.5 text-sm text-slate-700">
            {inconsistencies.map((s, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-amber-600">•</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </FlagBlock>
      )}
    </div>
  );
}

function FlagBlock({
  title,
  tone,
  icon,
  children,
}: {
  title: string;
  tone: "red" | "amber";
  icon: string;
  children: ReactNode;
}) {
  const cls =
    tone === "red"
      ? "border-red-200 bg-red-50/40"
      : "border-amber-200 bg-amber-50/40";
  return (
    <div className={`rounded-md border ${cls} p-3`}>
      <h4 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-700">
        <span>{icon}</span>
        {title}
      </h4>
      {children}
    </div>
  );
}

// ---------- interview questions -------------------------------------------

export function InterviewQuestionsView({ payload }: { payload: unknown }) {
  const p = asObject(payload);
  const questions = asArray(p.questions).map(asObject);

  if (questions.length === 0) {
    return (
      <p className="text-sm italic text-slate-500">No questions generated.</p>
    );
  }

  return (
    <ol className="space-y-3">
      {questions.map((q, i) => {
        const text = asString(q.q);
        const skill = asString(q.skill);
        const probes = asArray(q.probes)
          .map((x) => asString(x))
          .filter(Boolean);
        return (
          <li
            key={i}
            className="rounded-md border border-slate-200 bg-white p-3"
          >
            <div className="flex items-start gap-3">
              <span className="mt-0.5 inline-flex h-6 w-6 flex-none items-center justify-center rounded-full bg-slate-900 text-xs font-semibold text-white">
                {i + 1}
              </span>
              <div className="flex-1 space-y-2">
                <p className="text-sm font-medium leading-snug text-slate-900">
                  {text || "—"}
                </p>
                {skill && <Chip tone="indigo">{skill}</Chip>}
                {probes.length > 0 && (
                  <details className="group">
                    <summary className="cursor-pointer text-xs text-slate-500 hover:text-slate-700">
                      <span className="group-open:hidden">
                        Show {probes.length} probe{probes.length === 1 ? "" : "s"}
                      </span>
                      <span className="hidden group-open:inline">
                        Hide probes
                      </span>
                    </summary>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                      {probes.map((pr, j) => (
                        <li key={j}>{pr}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

// ---------- enrichment -----------------------------------------------------

const LANG_TONES: Record<string, "indigo" | "amber" | "emerald" | "blue" | "slate"> = {
  python: "blue",
  javascript: "amber",
  typescript: "blue",
  go: "blue",
  rust: "amber",
  java: "red" as never,
  ruby: "red" as never,
};

export function EnrichmentView({ payload }: { payload: unknown }) {
  const p = asObject(payload);
  const error = asString(p.error);
  if (error) {
    return (
      <p className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
        Enrichment error: {error}
      </p>
    );
  }
  const repos = asNumber(p.public_repos);
  const followers = asNumber(p.followers);
  const langs = asArray(p.top_languages)
    .map((x) => asString(x))
    .filter(Boolean);
  const notable = asArray(p.notable_repos).map(asObject);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Public repos" value={repos} />
        <Stat label="Followers" value={followers} />
        <Stat label="Top langs" value={langs.length} />
        <Stat label="Notable" value={notable.length} />
      </div>

      {langs.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Top languages
          </p>
          <div className="flex flex-wrap gap-1.5">
            {langs.map((l, i) => {
              const tone = LANG_TONES[l.toLowerCase()] ?? "slate";
              return (
                <Chip key={`${l}-${i}`} tone={tone}>
                  {l}
                </Chip>
              );
            })}
          </div>
        </div>
      )}

      {notable.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Notable repos ({notable.length})
          </p>
          <div className="overflow-x-auto rounded-md border border-slate-200">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2 font-semibold">Repo</th>
                  <th className="px-3 py-2 font-semibold">Language</th>
                  <th className="px-3 py-2 text-right font-semibold">Stars</th>
                  <th className="px-3 py-2 text-right font-semibold">Forks</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {notable.map((r, i) => {
                  const name = asString(r.name) || asString(r.full_name) || "—";
                  const url = asString(r.url) || asString(r.html_url);
                  const lang = asString(r.language);
                  const stars = asNumber(r.stars ?? r.stargazers_count);
                  const forks = asNumber(r.forks ?? r.forks_count);
                  return (
                    <tr key={`${name}-${i}`}>
                      <td className="px-3 py-2 font-mono text-xs text-slate-900">
                        {url ? (
                          <a
                            href={url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="hover:underline"
                          >
                            {name}
                          </a>
                        ) : (
                          name
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-700">
                        {lang ? <Chip tone="slate">{lang}</Chip> : "—"}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-xs tabular-nums text-slate-700">
                        ★ {stars}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-xs tabular-nums text-slate-700">
                        ⑂ {forks}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-3 py-2">
      <p className="text-[11px] uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="text-2xl font-semibold tabular-nums text-slate-900">
        {value.toLocaleString()}
      </p>
    </div>
  );
}
