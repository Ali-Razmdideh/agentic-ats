"use client";

import { useState } from "react";

interface VerifyResult {
  status: "ok" | "broken" | "pre_chain_only";
  total: number;
  chained: number;
  pre_chain: number;
  first_break: { id: number; expected: string; actual: string } | null;
}

export default function AuditVerifyButton() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function verify() {
    setLoading(true);
    setErr(null);
    setResult(null);
    try {
      const res = await fetch("/api/audit/verify", { cache: "no-store" });
      if (!res.ok) {
        setErr(`HTTP ${res.status}`);
        return;
      }
      setResult((await res.json()) as VerifyResult);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <button
        type="button"
        onClick={verify}
        disabled={loading}
        className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
      >
        {loading ? "Verifying…" : "Verify chain"}
      </button>
      {err && (
        <p className="text-xs text-red-700 dark:text-red-300">Error: {err}</p>
      )}
      {result && <Result r={result} />}
    </div>
  );
}

function Result({ r }: { r: VerifyResult }) {
  const cls =
    r.status === "ok"
      ? "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-100"
      : r.status === "broken"
        ? "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950/40 dark:text-red-100"
        : "border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200";
  return (
    <div className={`rounded-md border px-3 py-2 text-xs ${cls}`}>
      {r.status === "ok" && (
        <p>
          <strong>Chain intact.</strong> {r.chained} of {r.total} rows verified.
          {r.pre_chain > 0 && ` ${r.pre_chain} pre-chain (legacy) rows skipped.`}
        </p>
      )}
      {r.status === "broken" && r.first_break && (
        <p className="font-mono">
          <strong>Chain broken at row #{r.first_break.id}.</strong>
          <br />
          expected: {r.first_break.expected.slice(0, 16)}…
          <br />
          actual: {r.first_break.actual.slice(0, 16)}…
        </p>
      )}
      {r.status === "pre_chain_only" && (
        <p>
          All {r.total} rows pre-date the chain (sub-project #5 v1). New
          writes will start a fresh chain from the next event onward.
        </p>
      )}
    </div>
  );
}
