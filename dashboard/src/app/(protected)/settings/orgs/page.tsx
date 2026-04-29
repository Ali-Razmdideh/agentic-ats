import { listMembershipsWithOrg, requireUserAndOrg } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function OrgsPage() {
  const { user } = await requireUserAndOrg();
  const memberships = await listMembershipsWithOrg(user.id);
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Your orgs</h1>
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-4 py-2">Name</th>
              <th className="px-4 py-2">Slug</th>
              <th className="px-4 py-2">Role</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {memberships.map((m) => (
              <tr key={m.org.slug}>
                <td className="px-4 py-2 font-medium">{m.org.name}</td>
                <td className="px-4 py-2 text-slate-500">{m.org.slug}</td>
                <td className="px-4 py-2 text-slate-700">{m.role}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">
        Multi-org invitations land in a future sub-project. For now, signing up
        with an email at an existing org&apos;s domain auto-joins that org as a
        reviewer.
      </p>
    </div>
  );
}
