import { NextResponse } from "next/server";
import { requireUserAndOrg } from "@/lib/auth";
import { getRun } from "@/lib/repo";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const runId = Number(id);
  if (!Number.isFinite(runId)) {
    return NextResponse.json({ error: "bad_id" }, { status: 400 });
  }
  const { org } = await requireUserAndOrg();
  const run = await getRun(org.id, runId);
  if (!run) return NextResponse.json({ error: "not_found" }, { status: 404 });
  return NextResponse.json({
    id: run.id,
    status: run.status,
    started_at: run.started_at,
    finished_at: run.finished_at,
  });
}
