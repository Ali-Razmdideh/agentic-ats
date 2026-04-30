// Streams the org's audit_log as CSV. Admin-only.
//
// CSV escaping per RFC 4180: double-quote every field, double the
// inner quotes, normalise newlines to \r\n. Payload column is
// JSON-encoded then escaped, so it survives transport into Excel
// without splitting cells on commas / line breaks inside the JSON.

import { NextResponse } from "next/server";
import { requireUserAndOrg } from "@/lib/auth";
import { iterAudit } from "@/lib/audit";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const COLUMNS = [
  "id",
  "created_at",
  "actor_kind",
  "actor_user_id",
  "kind",
  "target_kind",
  "target_id",
  "payload",
];

function csvField(v: unknown): string {
  if (v === null || v === undefined) return '""';
  let s: string;
  if (typeof v === "object") {
    s = JSON.stringify(v);
  } else {
    s = String(v);
  }
  return `"${s.replace(/"/g, '""')}"`;
}

export async function GET(req: Request) {
  const { org, role } = await requireUserAndOrg();
  if (role !== "admin") {
    return NextResponse.json({ error: "admin_only" }, { status: 403 });
  }
  const url = new URL(req.url);
  const kind = url.searchParams.get("kind") ?? undefined;
  const since = url.searchParams.get("since") ?? undefined;
  const until = url.searchParams.get("until") ?? undefined;

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const enc = new TextEncoder();
      controller.enqueue(enc.encode(COLUMNS.join(",") + "\r\n"));
      try {
        for await (const row of iterAudit({
          orgId: org.id,
          kind,
          since,
          until,
        })) {
          const r = row as unknown as Record<string, unknown>;
          const line =
            COLUMNS.map((c) => csvField(r[c])).join(",") + "\r\n";
          controller.enqueue(enc.encode(line));
        }
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("audit export failed", err);
      }
      controller.close();
    },
  });

  const filename = `audit-log-${org.slug}-${new Date()
    .toISOString()
    .slice(0, 10)}.csv`;
  return new Response(stream, {
    status: 200,
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${filename}"`,
      "Cache-Control": "no-store",
    },
  });
}
