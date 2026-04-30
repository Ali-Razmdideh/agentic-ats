"use client";

import { useRef } from "react";

export default function OrgSwitcher({
  options,
  active,
}: {
  options: Array<{ slug: string; name: string }>;
  active: string;
}) {
  const formRef = useRef<HTMLFormElement>(null);
  return (
    <form ref={formRef} action="/api/auth/switch-org" method="post">
      <select
        name="slug"
        defaultValue={active}
        onChange={() => formRef.current?.submit()}
        className="rounded-md border border-slate-300 dark:border-slate-700 px-2 py-1 text-sm"
      >
        {options.map((o) => (
          <option key={o.slug} value={o.slug}>
            {o.name}
          </option>
        ))}
      </select>
    </form>
  );
}
