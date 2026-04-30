import { requireUserAndOrg } from "@/lib/auth";

export default async function NewRunPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  await requireUserAndOrg();
  const sp = await searchParams;
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">New run</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Upload a job description and one or more resumes. The worker picks
          up queued runs every few seconds.
        </p>
      </div>
      {sp.error && (
        <div className="rounded border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 p-2 text-sm text-red-800 dark:text-red-200">
          {sp.error}
        </div>
      )}
      <form
        action="/api/runs/upload"
        method="post"
        encType="multipart/form-data"
        className="space-y-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6"
      >
        <label className="block">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Job description (.txt or .md)
          </span>
          <input
            name="jd"
            type="file"
            accept=".txt,.md,text/plain,text/markdown"
            required
            className="mt-1 block w-full text-sm"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Resumes (.pdf, .docx, .txt — pick multiple)
          </span>
          <input
            name="resumes"
            type="file"
            accept=".pdf,.docx,.txt,.md"
            multiple
            required
            className="mt-1 block w-full text-sm"
          />
        </label>
        <div className="grid grid-cols-2 gap-4">
          <label className="block">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
              Shortlist size
            </span>
            <input
              name="top_n"
              type="number"
              defaultValue={5}
              min={1}
              max={50}
              className="mt-1 block w-full rounded-md border border-slate-300 dark:border-slate-700 px-3 py-2 text-sm"
            />
          </label>
          <label className="flex items-center gap-2 pt-6 text-sm">
            <input
              name="skip_optional"
              type="checkbox"
              className="h-4 w-4 rounded border-slate-300 dark:border-slate-700"
            />
            Skip optional agents (faster + cheaper)
          </label>
        </div>
        <button
          type="submit"
          className="rounded-md bg-slate-900 dark:bg-slate-100 dark:text-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:hover:bg-slate-700"
        >
          Queue run
        </button>
      </form>
    </div>
  );
}
