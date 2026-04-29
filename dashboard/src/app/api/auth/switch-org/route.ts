import { NextResponse } from "next/server";
import { getCurrentUser, listMembershipsWithOrg } from "@/lib/auth";
import { setActiveOrgCookie } from "@/lib/session";
import { SwitchOrgInput } from "@/lib/schema";

export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const form = await req.formData();
  const parsed = SwitchOrgInput.safeParse({ slug: form.get("slug") });
  if (!parsed.success) {
    return NextResponse.json({ error: "validation" }, { status: 400 });
  }
  const memberships = await listMembershipsWithOrg(user.id);
  const target = memberships.find((m) => m.org.slug === parsed.data.slug);
  if (!target) {
    return NextResponse.json({ error: "not_a_member" }, { status: 403 });
  }
  await setActiveOrgCookie(target.org.slug);
  return NextResponse.redirect(new URL("/runs", req.url), 303);
}
