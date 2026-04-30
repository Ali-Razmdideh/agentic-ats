import type { RunStatus } from "@/lib/types";

const COLORS: Record<RunStatus, string> = {
  queued: "bg-slate-100 text-slate-700",
  running: "bg-blue-100 text-blue-800",
  completed: "bg-emerald-100 text-emerald-800",
  ok: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
  cancelled: "bg-slate-100 text-slate-700",
  blocked_by_bias: "bg-amber-100 text-amber-800",
  budget_exceeded: "bg-red-100 text-red-800",
};

export default function StatusBadge({ status }: { status: RunStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        COLORS[status] ?? "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200"
      }`}
    >
      {status}
    </span>
  );
}
