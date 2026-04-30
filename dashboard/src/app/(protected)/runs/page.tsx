import Link from "next/link";
import { requireUserAndOrg } from "@/lib/auth";
import { listRuns } from "@/lib/repo";
import StatusBadge from "@/components/StatusBadge";

export const dynamic = "force-dynamic";

export default async function RunsPage() {
  const { org } = await requireUserAndOrg();
  const runs = await listRuns(org.id, 50);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Runs</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            All screening runs in <span className="font-medium">{org.name}</span>.
          </p>
        </div>
        <Link
          href="/runs/new"
          className="rounded-md bg-slate-900 dark:bg-slate-100 dark:text-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:hover:bg-slate-700"
        >
          New run
        </Link>
      </div>
      <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 dark:bg-slate-950 text-left text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            <tr>
              <th className="px-4 py-2">#</th>
              <th className="px-4 py-2">Started</th>
              <th className="px-4 py-2">JD</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Finished</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {runs.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-4 py-12 text-center text-sm text-slate-500 dark:text-slate-400"
                >
                  No runs yet. Click &ldquo;New run&rdquo; to upload a JD and resumes.
                </td>
              </tr>
            )}
            {runs.map((r) => (
              <tr key={r.id} className="hover:bg-slate-50 dark:hover:bg-slate-800">
                <td className="px-4 py-2 font-medium">
                  <Link className="text-slate-900 dark:text-slate-50 underline" href={`/runs/${r.id}`}>
                    {r.id}
                  </Link>
                </td>
                <td className="px-4 py-2 text-slate-600 dark:text-slate-300">
                  {new Date(r.started_at).toLocaleString()}
                </td>
                <td className="px-4 py-2 text-slate-600 dark:text-slate-300">
                  {r.jd_path.split("/").pop()}
                </td>
                <td className="px-4 py-2">
                  <StatusBadge status={r.status} />
                </td>
                <td className="px-4 py-2 text-slate-500 dark:text-slate-400">
                  {r.finished_at ? new Date(r.finished_at).toLocaleString() : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
