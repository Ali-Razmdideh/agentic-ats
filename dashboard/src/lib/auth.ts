// Auth helpers: signup/login + requireUser/requireOrg guards.

import bcrypt from "bcryptjs";
import { redirect } from "next/navigation";
import { pool, withTx } from "@/lib/db";
import {
  createSession,
  getActiveOrgCookie,
  getSessionCookie,
  getUserBySession,
  setSessionCookie,
} from "@/lib/session";
import type { Membership, Org, User } from "@/lib/types";

const ROUNDS = 10;

export async function hashPassword(plain: string): Promise<string> {
  return bcrypt.hash(plain, ROUNDS);
}

export async function verifyPassword(
  plain: string,
  hashed: string,
): Promise<boolean> {
  return bcrypt.compare(plain, hashed);
}

function slugFromEmail(email: string): string {
  const domain = email.split("@")[1] ?? "personal";
  return domain.split(".")[0]?.toLowerCase() ?? "personal";
}

/** Create user + auto-create or join an org via the email-domain rule. */
export async function signup(
  email: string,
  password: string,
  displayName?: string | null,
): Promise<{ user: User; org: Org }> {
  const hash = await hashPassword(password);
  const slug = slugFromEmail(email);
  return withTx(async (c) => {
    const dup = await c.query<User>(
      `SELECT id, email, display_name FROM users WHERE email = $1`,
      [email],
    );
    if (dup.rows.length > 0) {
      throw new Error("EMAIL_TAKEN");
    }
    const userRes = await c.query<User>(
      `INSERT INTO users (email, display_name, password_hash)
       VALUES ($1, $2, $3)
       RETURNING id, email, display_name`,
      [email, displayName ?? null, hash],
    );
    const user = userRes.rows[0]!;
    const orgRes = await c.query<Org>(
      `INSERT INTO orgs (slug, name)
       VALUES ($1, $2)
       ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug
       RETURNING id, slug, name`,
      [slug, slug.charAt(0).toUpperCase() + slug.slice(1)],
    );
    const org = orgRes.rows[0]!;
    const memberCount = await c.query<{ n: string }>(
      `SELECT count(*)::text AS n FROM memberships WHERE org_id = $1`,
      [org.id],
    );
    const role = Number(memberCount.rows[0]!.n) === 0 ? "admin" : "reviewer";
    await c.query(
      `INSERT INTO memberships (org_id, user_id, role) VALUES ($1, $2, $3)
       ON CONFLICT (org_id, user_id) DO NOTHING`,
      [org.id, user.id, role],
    );
    return { user, org };
  });
}

export async function login(
  email: string,
  password: string,
): Promise<User | null> {
  const res = await pool.query<{
    id: number;
    email: string;
    display_name: string | null;
    password_hash: string | null;
  }>(
    `SELECT id, email, display_name, password_hash
       FROM users WHERE email = $1 AND disabled_at IS NULL`,
    [email],
  );
  const row = res.rows[0];
  if (!row || !row.password_hash) return null;
  const ok = await verifyPassword(password, row.password_hash);
  if (!ok) return null;
  return { id: row.id, email: row.email, display_name: row.display_name };
}

export async function startSessionFor(
  userId: number,
  userAgent: string | null,
  ip: string | null,
): Promise<void> {
  const sid = await createSession(userId, userAgent, ip);
  await setSessionCookie(sid);
}

export async function listMembershipsWithOrg(
  userId: number,
): Promise<Array<Membership & { org: Org }>> {
  const res = await pool.query(
    `SELECT m.org_id, m.user_id, m.role,
            o.id AS o_id, o.slug AS o_slug, o.name AS o_name
       FROM memberships m JOIN orgs o ON o.id = m.org_id
      WHERE m.user_id = $1
      ORDER BY o.slug`,
    [userId],
  );
  return res.rows.map((r) => ({
    org_id: r.org_id,
    user_id: r.user_id,
    role: r.role,
    org: { id: r.o_id, slug: r.o_slug, name: r.o_name },
  }));
}

/** Resolves the current user from cookies; null if not logged in. */
export async function getCurrentUser(): Promise<User | null> {
  const sid = await getSessionCookie();
  if (!sid) return null;
  return getUserBySession(sid);
}

/** Returns user + active org or redirects to /login.
 *
 * READ-ONLY: this function MUST be safe to call from a server component
 * (page / layout). Next.js 15 forbids ``cookies().set()`` outside Server
 * Actions / Route Handlers, so the active-org cookie is only persisted
 * by ``/api/auth/switch-org``. If the cookie is missing or stale, we
 * fall back to the user's first membership for this request — the next
 * login or org switch will write the cookie.
 */
export async function requireUserAndOrg(): Promise<{
  user: User;
  org: Org;
  role: Membership["role"];
}> {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  const memberships = await listMembershipsWithOrg(user.id);
  if (memberships.length === 0) {
    throw new Error("user has no org memberships");
  }
  const activeSlug = await getActiveOrgCookie();
  const active =
    memberships.find((m) => m.org.slug === activeSlug) ?? memberships[0]!;
  return { user, org: active.org, role: active.role };
}
