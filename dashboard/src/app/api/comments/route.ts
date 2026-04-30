import { NextResponse } from "next/server";
import { requireUserAndOrg } from "@/lib/auth";
import { addComment } from "@/lib/repo";
import { CommentInput } from "@/lib/schema";
import { appendAudit } from "@/lib/audit";

export async function POST(req: Request) {
  const { user, org } = await requireUserAndOrg();
  const form = await req.formData();
  const parsed = CommentInput.safeParse({
    run_id: form.get("run_id"),
    candidate_id: form.get("candidate_id"),
    body: form.get("body"),
  });
  if (!parsed.success) {
    return NextResponse.json({ error: "validation" }, { status: 400 });
  }
  let id: number;
  try {
    id = await addComment(
      org.id,
      parsed.data.run_id,
      parsed.data.candidate_id,
      user.id,
      parsed.data.body,
    );
  } catch (e) {
    if ((e as Error).message === "CROSS_TENANT") {
      return NextResponse.json({ error: "forbidden" }, { status: 403 });
    }
    throw e;
  }
  await appendAudit({
    orgId: org.id,
    actorUserId: user.id,
    actorKind: "user",
    kind: "comment.added",
    payload: {
      run_id: parsed.data.run_id,
      candidate_id: parsed.data.candidate_id,
      comment_id: id,
      body_preview: parsed.data.body.slice(0, 200),
    },
    targetKind: "candidate",
    targetId: parsed.data.candidate_id,
  });
  return NextResponse.json({ ok: true, id });
}
