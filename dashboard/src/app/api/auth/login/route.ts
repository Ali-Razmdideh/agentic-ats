import { NextResponse } from "next/server";
import {
  listMembershipsWithOrg,
  login,
  startSessionFor,
} from "@/lib/auth";
import { LoginInput } from "@/lib/schema";
import { setActiveOrgCookie } from "@/lib/session";
import { appendAudit } from "@/lib/audit";

export async function POST(req: Request) {
  const form = await req.formData();
  const parsed = LoginInput.safeParse({
    email: form.get("email"),
    password: form.get("password"),
  });
  if (!parsed.success) {
    return NextResponse.redirect(
      new URL("/login?error=validation", req.url),
      303,
    );
  }
  const user = await login(parsed.data.email, parsed.data.password);
  if (!user) {
    return NextResponse.redirect(new URL("/login?error=invalid", req.url), 303);
  }
  await startSessionFor(
    user.id,
    req.headers.get("user-agent"),
    req.headers.get("x-forwarded-for"),
  );
  // Pin an active org so the dashboard's first request has a non-empty
  // cookie. Server components cannot write cookies in Next 15.
  const memberships = await listMembershipsWithOrg(user.id);
  if (memberships.length > 0) {
    await setActiveOrgCookie(memberships[0]!.org.slug);
    await appendAudit({
      orgId: memberships[0]!.org.id,
      actorUserId: user.id,
      actorKind: "user",
      kind: "auth.login",
      payload: { email: user.email },
    });
  }
  return NextResponse.redirect(new URL("/runs", req.url), 303);
}
