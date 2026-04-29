import { createHash } from "crypto";
import { NextResponse } from "next/server";
import { requireUserAndOrg } from "@/lib/auth";
import { putJd, putResume } from "@/lib/blob";
import { createQueuedRun } from "@/lib/repo";
import { RunUploadInput } from "@/lib/schema";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const { user, org } = await requireUserAndOrg();
  const form = await req.formData();

  const parsed = RunUploadInput.safeParse({
    top_n: form.get("top_n") ?? 5,
    skip_optional: form.get("skip_optional") ?? false,
  });
  if (!parsed.success) {
    return NextResponse.redirect(
      new URL("/runs/new?error=validation", req.url),
      303,
    );
  }

  const jd = form.get("jd");
  const resumes = form.getAll("resumes").filter((f) => f instanceof File) as File[];
  if (!(jd instanceof File) || resumes.length === 0) {
    return NextResponse.redirect(
      new URL("/runs/new?error=missing+files", req.url),
      303,
    );
  }

  const jdBytes = Buffer.from(await jd.arrayBuffer());
  const jdKey = await putJd(org.id, jdBytes, jd.name || "jd.txt");
  const jdHash = createHash("sha256").update(jdBytes).digest("hex");

  const resumeKeys: string[] = [];
  for (const r of resumes) {
    const bytes = Buffer.from(await r.arrayBuffer());
    const key = await putResume(org.id, bytes, r.name || "resume");
    resumeKeys.push(key);
  }

  const runId = await createQueuedRun(
    org.id,
    user.id,
    jd.name || "jd.txt",
    jdHash,
    jdKey,
    resumeKeys,
    parsed.data.top_n,
    parsed.data.skip_optional,
  );

  return NextResponse.redirect(new URL(`/runs/${runId}`, req.url), 303);
}
