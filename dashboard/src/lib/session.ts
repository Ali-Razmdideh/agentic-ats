// Server-side sessions backed by the `sessions` table.
// Cookie holds a 32-byte hex token; the row carries the user.

import { randomBytes } from "crypto";
import { cookies } from "next/headers";
import { pool } from "@/lib/db";
import type { User } from "@/lib/types";

export const SESSION_COOKIE = process.env.SESSION_COOKIE_NAME ?? "ats_session";
export const ACTIVE_ORG_COOKIE = "ats_active_org";
const TTL_DAYS = 30;

export function newSessionId(): string {
  return randomBytes(32).toString("hex");
}

/** Returns a parseable single IP literal or null. ``x-forwarded-for`` can
 * be a comma-separated chain (`client, proxy1, proxy2`), garbage from an
 * untrusted client, or absent. We take the leftmost entry, validate it
 * fits a simple IPv4/IPv6 shape, and fall back to NULL on anything else
 * so the ``::inet`` cast cannot raise on login.
 */
function normaliseIp(raw: string | null): string | null {
  if (!raw) return null;
  const first = raw.split(",")[0]?.trim() ?? "";
  if (!first) return null;
  const ipv4 = /^\d{1,3}(?:\.\d{1,3}){3}$/;
  const ipv6 = /^[0-9a-fA-F:]+$/;
  if (ipv4.test(first) || (ipv6.test(first) && first.includes(":"))) {
    return first;
  }
  return null;
}

export async function createSession(
  userId: number,
  userAgent: string | null,
  ip: string | null,
): Promise<string> {
  const id = newSessionId();
  const expires = new Date(Date.now() + TTL_DAYS * 86400 * 1000);
  await pool.query(
    `INSERT INTO sessions (id, user_id, expires_at, user_agent, ip)
     VALUES ($1, $2, $3, $4, $5::inet)`,
    [id, userId, expires, userAgent, normaliseIp(ip)],
  );
  return id;
}

export async function revokeSession(sessionId: string): Promise<void> {
  await pool.query(
    `UPDATE sessions SET revoked_at = now()
     WHERE id = $1 AND revoked_at IS NULL`,
    [sessionId],
  );
}

export async function getUserBySession(
  sessionId: string,
): Promise<User | null> {
  const res = await pool.query(
    `SELECT u.id, u.email, u.display_name
       FROM sessions s JOIN users u ON u.id = s.user_id
      WHERE s.id = $1 AND s.revoked_at IS NULL AND s.expires_at > now()`,
    [sessionId],
  );
  if (res.rows.length === 0) return null;
  await pool.query(`UPDATE sessions SET last_seen_at = now() WHERE id = $1`, [
    sessionId,
  ]);
  return res.rows[0] as User;
}

export async function setSessionCookie(sessionId: string): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE, sessionId, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: TTL_DAYS * 86400,
  });
}

export async function clearSessionCookie(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.delete(SESSION_COOKIE);
  cookieStore.delete(ACTIVE_ORG_COOKIE);
}

export async function getSessionCookie(): Promise<string | null> {
  const cookieStore = await cookies();
  return cookieStore.get(SESSION_COOKIE)?.value ?? null;
}

export async function getActiveOrgCookie(): Promise<string | null> {
  const cookieStore = await cookies();
  return cookieStore.get(ACTIVE_ORG_COOKIE)?.value ?? null;
}

export async function setActiveOrgCookie(orgSlug: string): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.set(ACTIVE_ORG_COOKIE, orgSlug, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: TTL_DAYS * 86400,
  });
}
