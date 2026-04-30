import { listMembershipsWithOrg } from "@/lib/auth";
import {
  clearSessionCookie,
  getSessionCookie,
  getUserBySession,
  revokeSession,
} from "@/lib/session";
import { appendAudit } from "@/lib/audit";
import { relativeRedirect } from "@/lib/redirect";

export async function POST() {
  const sid = await getSessionCookie();
  if (sid) {
    // Resolve user + first membership BEFORE revoking, so we can audit
    // who logged out.
    const user = await getUserBySession(sid);
    if (user) {
      const memberships = await listMembershipsWithOrg(user.id);
      if (memberships.length > 0) {
        await appendAudit({
          orgId: memberships[0]!.org.id,
          actorUserId: user.id,
          actorKind: "user",
          kind: "auth.logout",
          payload: { email: user.email },
        });
      }
    }
    await revokeSession(sid);
  }
  await clearSessionCookie();
  return relativeRedirect("/login");
}
