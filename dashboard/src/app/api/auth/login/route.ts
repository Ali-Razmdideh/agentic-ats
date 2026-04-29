import { NextResponse } from "next/server";
import { login, startSessionFor } from "@/lib/auth";
import { LoginInput } from "@/lib/schema";

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
  return NextResponse.redirect(new URL("/runs", req.url), 303);
}
