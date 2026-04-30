import Link from "next/link";

export default function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  return <SignupForm searchParams={searchParams} />;
}

async function SignupForm({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const sp = await searchParams;
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
        <div>
          <h1 className="text-xl font-semibold">Create your account</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            We&apos;ll create an org from your email&apos;s domain.
          </p>
        </div>
        {sp.error && (
          <div className="rounded border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 p-2 text-sm text-red-800 dark:text-red-200">
            {sp.error === "taken"
              ? "That email is already registered."
              : sp.error === "validation"
                ? "Check email format and password length (≥ 8 chars)."
                : "Signup failed."}
          </div>
        )}
        <form action="/api/auth/signup" method="post" className="space-y-4">
          <Field label="Email" name="email" type="email" required />
          <Field
            label="Display name (optional)"
            name="display_name"
            type="text"
          />
          <Field
            label="Password"
            name="password"
            type="password"
            required
            min={8}
          />
          <button
            type="submit"
            className="w-full rounded-md bg-slate-900 dark:bg-slate-100 dark:text-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:hover:bg-slate-700"
          >
            Create account
          </button>
        </form>
        <p className="text-center text-sm text-slate-500 dark:text-slate-400">
          Already have one?{" "}
          <Link href="/login" className="font-medium text-slate-900 dark:text-slate-50 underline">
            Sign in
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
  min,
}: {
  label: string;
  name: string;
  type: string;
  required?: boolean;
  min?: number;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-700 dark:text-slate-200">{label}</span>
      <input
        name={name}
        type={type}
        required={required}
        minLength={min}
        className="mt-1 block w-full rounded-md border border-slate-300 dark:border-slate-700 px-3 py-2 text-sm focus:border-slate-900 dark:focus:border-slate-100 focus:outline-none focus:ring-1 focus:ring-slate-900 dark:focus:ring-slate-100"
      />
    </label>
  );
}
