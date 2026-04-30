// Admin-only compliance log viewer. Shows the most recent audit_log
// entries for the active org with filters for kind / actor and a date
// range, plus a "Download CSV" link that hits /api/audit/export with
// the same query parameters.

import Link from "next/link";
import { redirect } from "next/navigation";
import { requireUserAndOrg } from "@/lib/auth";
import { countAudit, listAudit } from "@/lib/audit";
import AuditVerifyButton from "@/components/AuditVerifyButton";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 50;

interface SearchParams {
  kind?: string;
  since?: string;
  until?: string;
  page?: string;
}

const KIND_OPTIONS = [
  { value: "", label: "All kinds" },
  { value: "auth.login", label: "auth.login" },
  { value: "auth.logout", label: "auth.logout" },
  { value: "auth.signup", label: "auth.signup" },
  { value: "run.submitted", label: "run.submitted" },
  { value: "run.started", label: "run.started" },
  { value: "run.completed", label: "run.completed" },
  { value: "run.failed", label: "run.failed" },
  { value: "run.budget_exceeded", label: "run.budget_exceeded" },
  { value: "decision.set", label: "decision.set" },
  { value: "comment.added", label: "comment.added" },
];

export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const { org, role } = await requireUserAndOrg();
  if (role !== "admin") {
    redirect("/runs?error=admin_only");
  }
  const sp = await searchParams;
  const page = Math.max(1, Number(sp.page) || 1);
  const offset = (page - 1) * PAGE_SIZE;
  const filter = {
    orgId: org.id,
    kind: sp.kind || undefined,
    since: sp.since || undefined,
    until: sp.until || undefined,
  };
  const [entries, total] = await Promise.all([
    listAudit({ ...filter, limit: PAGE_SIZE, offset }),
    countAudit(filter),
  ]);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // Build the export URL preserving filters.
  const exportParams = new URLSearchParams();
  if (filter.kind) exportParams.set("kind", filter.kind);
  if (filter.since) exportParams.set("since", filter.since);
  if (filter.until) exportParams.set("until", filter.until);
  const exportHref = `/api/audit/export?${exportParams.toString()}`;

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Compliance log</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Append-only record of reviewer + worker actions in {org.name}.{" "}
            {total.toLocaleString()} total events.
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <a
            href={exportHref}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            Download CSV
          </a>
          <AuditVerifyButton />
        </div>
      </div>

      <form
        method="get"
        className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
      >
        <label className="flex flex-col text-xs">
          <span className="font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Kind
          </span>
          <select
            name="kind"
            defaultValue={sp.kind ?? ""}
            className="mt-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
          >
            {KIND_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col text-xs">
          <span className="font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Since (UTC)
          </span>
          <input
            name="since"
            type="datetime-local"
            defaultValue={sp.since ?? ""}
            className="mt-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </label>
        <label className="flex flex-col text-xs">
          <span className="font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Until (UTC)
          </span>
          <input
            name="until"
            type="datetime-local"
            defaultValue={sp.until ?? ""}
            className="mt-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </label>
        <button
          type="submit"
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200"
        >
          Apply
        </button>
      </form>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
            <tr>
              <th className="px-3 py-2 font-semibold">When</th>
              <th className="px-3 py-2 font-semibold">Actor</th>
              <th className="px-3 py-2 font-semibold">Kind</th>
              <th className="px-3 py-2 font-semibold">Target</th>
              <th className="px-3 py-2 font-semibold">Payload</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white dark:divide-slate-800 dark:bg-slate-900">
            {entries.length === 0 ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-3 py-6 text-center text-sm italic text-slate-500 dark:text-slate-400"
                >
                  No events match the current filters.
                </td>
              </tr>
            ) : (
              entries.map((e) => (
                <tr key={e.id} className="align-top">
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-slate-700 dark:text-slate-200">
                    {new Date(e.created_at).toISOString().replace("T", " ").slice(0, 19)}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    <span className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                      {e.actor_kind}
                    </span>
                    {e.actor_user_id && (
                      <span className="ml-1 text-slate-500 dark:text-slate-400">
                        user #{e.actor_user_id}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-slate-900 dark:text-slate-50">
                    {e.kind}
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-600 dark:text-slate-300">
                    {e.target_kind ? (
                      <>
                        <span className="font-mono">{e.target_kind}</span>
                        {e.target_id != null && (
                          <span className="ml-1">#{e.target_id}</span>
                        )}
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <details>
                      <summary className="cursor-pointer text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-50">
                        View
                      </summary>
                      <pre className="mt-1 max-h-40 overflow-auto rounded bg-slate-50 p-2 font-mono text-[10px] text-slate-700 dark:bg-slate-950 dark:text-slate-200">
                        {JSON.stringify(e.payload, null, 2)}
                      </pre>
                    </details>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Pagination page={page} totalPages={totalPages} sp={sp} />
    </div>
  );
}

function Pagination({
  page,
  totalPages,
  sp,
}: {
  page: number;
  totalPages: number;
  sp: SearchParams;
}) {
  if (totalPages <= 1) return null;
  function href(target: number): string {
    const q = new URLSearchParams();
    if (sp.kind) q.set("kind", sp.kind);
    if (sp.since) q.set("since", sp.since);
    if (sp.until) q.set("until", sp.until);
    q.set("page", String(target));
    return `/settings/audit?${q.toString()}`;
  }
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-slate-500 dark:text-slate-400">
        Page {page} of {totalPages}
      </span>
      <div className="flex gap-2">
        {page > 1 && (
          <Link
            href={href(page - 1)}
            className="rounded-md border border-slate-300 px-2 py-1 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            ← Newer
          </Link>
        )}
        {page < totalPages && (
          <Link
            href={href(page + 1)}
            className="rounded-md border border-slate-300 px-2 py-1 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            Older →
          </Link>
        )}
      </div>
    </div>
  );
}
