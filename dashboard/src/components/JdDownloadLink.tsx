"use client";

import { useState } from "react";

export default function JdDownloadLink({ blobKey }: { blobKey: string }) {
  const [loading, setLoading] = useState(false);
  return (
    <button
      type="button"
      disabled={loading}
      onClick={async () => {
        setLoading(true);
        try {
          const res = await fetch(
            `/api/resumes/url?key=${encodeURIComponent(blobKey)}`,
          );
          if (!res.ok) throw new Error("url");
          const j = (await res.json()) as { url: string };
          window.open(j.url, "_blank", "noopener,noreferrer");
        } catch {
          alert("Failed to mint download URL.");
        } finally {
          setLoading(false);
        }
      }}
      className="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-xs hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
    >
      {loading ? "Generating…" : "Download original JD"}
    </button>
  );
}
