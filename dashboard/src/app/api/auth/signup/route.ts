import { signup } from "@/lib/auth";
import { SignupInput } from "@/lib/schema";
import { appendAudit } from "@/lib/audit";
import { relativeRedirect } from "@/lib/redirect";

export async function POST(req: Request) {
  const form = await req.formData();
  const parsed = SignupInput.safeParse({
    email: form.get("email"),
    password: form.get("password"),
    display_name: form.get("display_name") || null,
  });
  if (!parsed.success) {
    return relativeRedirect("/signup?error=validation");
  }
  try {
    const { user, org } = await signup(
      parsed.data.email,
      parsed.data.password,
      parsed.data.display_name,
    );
    await appendAudit({
      orgId: org.id,
      actorUserId: user.id,
      actorKind: "user",
      kind: "auth.signup",
      payload: { email: user.email, org_slug: org.slug },
    });
  } catch (e) {
    const code = (e as Error).message === "EMAIL_TAKEN" ? "taken" : "unknown";
    return relativeRedirect(`/signup?error=${code}`);
  }
  return relativeRedirect("/login?signed_up=1");
}
