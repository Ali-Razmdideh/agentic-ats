import { NextResponse } from "next/server";
import { requireUserAndOrg } from "@/lib/auth";
import { upsertDecision } from "@/lib/repo";
import { DecisionInput } from "@/lib/schema";

export async function POST(req: Request) {
  const { user, org } = await requireUserAndOrg();
  const form = await req.formData();
  const parsed = DecisionInput.safeParse({
    run_id: form.get("run_id"),
    candidate_id: form.get("candidate_id"),
    decision: form.get("decision"),
    notes: form.get("notes"),
  });
  if (!parsed.success) {
    return NextResponse.json(
      { error: "validation", details: parsed.error.flatten() },
      { status: 400 },
    );
  }
  try {
    await upsertDecision(
      org.id,
      parsed.data.run_id,
      parsed.data.candidate_id,
      parsed.data.decision,
      parsed.data.notes ?? null,
      user.id,
    );
  } catch (e) {
    if ((e as Error).message === "CROSS_TENANT") {
      return NextResponse.json({ error: "forbidden" }, { status: 403 });
    }
    throw e;
  }
  return NextResponse.json({ ok: true });
}
