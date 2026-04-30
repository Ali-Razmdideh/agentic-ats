import Link from "next/link";
import OrgSwitcher from "@/components/OrgSwitcher";
import ThemeToggle from "@/components/ThemeToggle";
import {
  listMembershipsWithOrg,
  requireUserAndOrg,
} from "@/lib/auth";

export default async function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, org, role } = await requireUserAndOrg();
  const memberships = await listMembershipsWithOrg(user.id);

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
          <Link
            href="/runs"
            className="text-sm font-semibold tracking-tight"
          >
            ATS
          </Link>
          <nav className="flex items-center gap-4 text-sm text-slate-600 dark:text-slate-300">
            <Link href="/runs" className="hover:text-slate-900 dark:hover:text-slate-50">
              Runs
            </Link>
            <Link href="/runs/new" className="hover:text-slate-900 dark:hover:text-slate-50">
              New run
            </Link>
            {role === "admin" && (
              <>
                <Link href="/settings/orgs" className="hover:text-slate-900 dark:hover:text-slate-50">
                  Orgs
                </Link>
                <Link href="/settings/audit" className="hover:text-slate-900 dark:hover:text-slate-50">
                  Audit
                </Link>
              </>
            )}
          </nav>
          <div className="ml-auto flex items-center gap-4 text-sm">
            {memberships.length > 1 ? (
              <OrgSwitcher
                options={memberships.map((m) => ({
                  slug: m.org.slug,
                  name: m.org.name,
                }))}
                active={org.slug}
              />
            ) : (
              <span className="rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-1 font-medium text-slate-700 dark:text-slate-200">
                {org.name}
              </span>
            )}
            <span className="text-slate-500 dark:text-slate-400">{user.email}</span>
            <ThemeToggle />
            <form action="/api/auth/logout" method="post">
              <button
                type="submit"
                className="rounded-md border border-slate-300 dark:border-slate-700 px-2 py-1 text-sm hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                Sign out
              </button>
            </form>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
    </div>
  );
}
