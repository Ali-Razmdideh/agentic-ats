import { NextResponse } from "next/server";
import { clearSessionCookie, getSessionCookie, revokeSession } from "@/lib/session";

export async function POST(req: Request) {
  const sid = await getSessionCookie();
  if (sid) await revokeSession(sid);
  await clearSessionCookie();
  return NextResponse.redirect(new URL("/login", req.url), 303);
}
