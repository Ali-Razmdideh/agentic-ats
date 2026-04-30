import Link from "next/link";

export default function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; signed_up?: string }>;
}) {
  return <LoginForm searchParams={searchParams} />;
}

async function LoginForm({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; signed_up?: string }>;
}) {
  const sp = await searchParams;
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
        <div>
          <h1 className="text-xl font-semibold">Sign in to ATS</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Reviewer dashboard
          </p>
        </div>
        {sp.signed_up && (
          <div className="rounded border border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950/40 p-2 text-sm text-emerald-800 dark:text-emerald-200">
            Account created — sign in to continue.
          </div>
        )}
        {sp.error && (
          <div className="rounded border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 p-2 text-sm text-red-800 dark:text-red-200">
            {sp.error === "invalid"
              ? "Invalid email or password."
              : "Login failed."}
          </div>
        )}
        <form action="/api/auth/login" method="post" className="space-y-4">
          <Field label="Email" name="email" type="email" required />
          <Field label="Password" name="password" type="password" required />
          <button
            type="submit"
            className="w-full rounded-md bg-slate-900 dark:bg-slate-100 dark:text-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:hover:bg-slate-700"
          >
            Sign in
          </button>
        </form>
        <p className="text-center text-sm text-slate-500 dark:text-slate-400">
          No account?{" "}
          <Link href="/signup" className="font-medium text-slate-900 dark:text-slate-50 underline">
            Create one
          </Link>
        </p>
      </div>
    </main>
  );
}

function Field({
  label,
  name,
  type,
  required,
}: {
  label: string;
  name: string;
  type: string;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-700 dark:text-slate-200">{label}</span>
      <input
        name={name}
        type={type}
        required={required}
        className="mt-1 block w-full rounded-md border border-slate-300 dark:border-slate-700 px-3 py-2 text-sm focus:border-slate-900 dark:focus:border-slate-100 focus:outline-none focus:ring-1 focus:ring-slate-900 dark:focus:ring-slate-100"
      />
    </label>
  );
}
