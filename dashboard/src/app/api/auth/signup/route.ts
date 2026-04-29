import { NextResponse } from "next/server";
import { signup } from "@/lib/auth";
import { SignupInput } from "@/lib/schema";

export async function POST(req: Request) {
  const form = await req.formData();
  const parsed = SignupInput.safeParse({
    email: form.get("email"),
    password: form.get("password"),
    display_name: form.get("display_name") || null,
  });
  if (!parsed.success) {
    return NextResponse.redirect(
      new URL("/signup?error=validation", req.url),
      303,
    );
  }
  try {
    await signup(
      parsed.data.email,
      parsed.data.password,
      parsed.data.display_name,
    );
  } catch (e) {
    const code =
      (e as Error).message === "EMAIL_TAKEN" ? "taken" : "unknown";
    return NextResponse.redirect(
      new URL(`/signup?error=${code}`, req.url),
      303,
    );
  }
  return NextResponse.redirect(
    new URL("/login?signed_up=1", req.url),
    303,
  );
}
