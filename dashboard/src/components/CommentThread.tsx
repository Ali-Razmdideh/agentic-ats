"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

interface CommentRow {
  id: number;
  body: string;
  created_at: string;
  author_email: string | null;
}

export default function CommentThread({
  runId,
  candidateId,
  comments,
  currentUserEmail,
}: {
  runId: number;
  candidateId: number;
  comments: CommentRow[];
  currentUserEmail: string;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit() {
    if (!draft.trim()) return;
    startTransition(async () => {
      const fd = new FormData();
      fd.set("run_id", String(runId));
      fd.set("candidate_id", String(candidateId));
      fd.set("body", draft.trim());
      const res = await fetch("/api/comments", { method: "POST", body: fd });
      if (res.ok) {
        setDraft("");
        setError(null);
        router.refresh();
      } else {
        setError("Failed to post comment.");
      }
    });
  }

  return (
    <div className="space-y-4">
      {comments.length === 0 ? (
        <p className="text-sm italic text-slate-500">No comments yet.</p>
      ) : (
        <ul className="space-y-3">
          {comments.map((c) => {
            const isMine = c.author_email === currentUserEmail;
            const initials = (c.author_email || "?")
              .split("@")[0]!
              .slice(0, 2)
              .toUpperCase();
            return (
              <li key={c.id} className="flex gap-3">
                <span
                  className={`mt-0.5 inline-flex h-8 w-8 flex-none items-center justify-center rounded-full text-xs font-semibold text-white ${isMine ? "bg-slate-900" : "bg-indigo-500"}`}
                >
                  {initials}
                </span>
                <div className="flex-1 rounded-md border border-slate-200 bg-white p-3">
                  <div className="flex items-baseline justify-between gap-3 text-xs text-slate-500">
                    <span className="font-medium text-slate-800">
                      {c.author_email || "—"}
                      {isMine && (
                        <span className="ml-1 text-[10px] uppercase tracking-wide text-slate-400">
                          you
                        </span>
                      )}
                    </span>
                    <time>{new Date(c.created_at).toLocaleString()}</time>
                  </div>
                  <p className="mt-1.5 whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
                    {c.body}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <div>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`Comment as ${currentUserEmail}…`}
          rows={3}
          className="block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
        />
        {error && (
          <p className="mt-1 text-xs text-red-700">{error}</p>
        )}
        <div className="mt-2 text-right">
          <button
            type="button"
            disabled={pending || !draft.trim()}
            onClick={submit}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            Post comment
          </button>
        </div>
      </div>
    </div>
  );
}
