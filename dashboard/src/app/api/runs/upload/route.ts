import { createHash } from "crypto";
import { NextResponse } from "next/server";
import { requireUserAndOrg } from "@/lib/auth";
import { putJd, putResume } from "@/lib/blob";
import { createQueuedRun } from "@/lib/repo";
import { RunUploadInput } from "@/lib/schema";

export const runtime = "nodejs";
export const maxDuration = 300; // up to 5 min for large multi-resume uploads

/** Build a 303 redirect with a relative Location header.
 *
 * NextResponse.redirect() needs an absolute URL, and `new URL(path, req.url)`
 * resolves against `req.url` — which inside a container with
 * HOSTNAME=0.0.0.0 can come back as ``http://0.0.0.0:3000/...``. The
 * browser then follows the Location to ``0.0.0.0`` and displays an
 * "empty page" error because that address isn't routable client-side.
 * A relative Location is resolved by the browser against the URL
 * it actually requested, so it always lands back on the right host.
 */
function relativeRedirect(path: string): Response {
  return new Response(null, {
    status: 303,
    headers: { Location: path },
  });
}

export async function POST(req: Request) {
  const { user, org } = await requireUserAndOrg();
  const form = await req.formData();

  const parsed = RunUploadInput.safeParse({
    top_n: form.get("top_n") ?? 5,
    skip_optional: form.get("skip_optional") ?? false,
  });
  if (!parsed.success) {
    return relativeRedirect("/runs/new?error=validation");
  }

  const jd = form.get("jd");
  const resumes = form
    .getAll("resumes")
    .filter((f) => f instanceof File) as File[];
  if (!(jd instanceof File) || resumes.length === 0) {
    return relativeRedirect("/runs/new?error=missing+files");
  }

  // Read every uploaded file into memory in parallel; multipart form
  // parsing has already buffered them, so this is just promise plumbing.
  const [jdBytes, resumeBuffers] = await Promise.all([
    jd.arrayBuffer().then((b) => Buffer.from(b)),
    Promise.all(
      resumes.map((r) =>
        r.arrayBuffer().then((b) => ({ name: r.name || "resume", buf: Buffer.from(b) })),
      ),
    ),
  ]);
  const jdHash = createHash("sha256").update(jdBytes).digest("hex");

  // Upload JD + every resume to MinIO in parallel. Was sequential — at
  // ~250–500ms per blob, four resumes turned a 0.5s round-trip into 2–3s,
  // long enough that the browser's wait-for-redirect timer fired before
  // Next responded with the 303.
  const [jdKey, ...resumeKeys] = await Promise.all([
    putJd(org.id, jdBytes, jd.name || "jd.txt"),
    ...resumeBuffers.map((rb) => putResume(org.id, rb.buf, rb.name)),
  ]);

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

  return relativeRedirect(`/runs/${runId}`);
}

// Type the unused import as referenced so eslint/tsc don't complain;
// kept for future where we might want to call NextResponse for non-redirect
// branches.
void NextResponse;
