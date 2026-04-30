"use client";

// Light/dark theme toggle. Reads the resolved theme from <html class>
// at mount (set by the anti-FOUC script in layout.tsx) and writes
// changes to localStorage + the same class. The anti-FOUC script in
// layout.tsx applies the saved theme before first paint, so the page
// never flashes the wrong palette.

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

function readInitial(): Theme {
  if (typeof document === "undefined") return "light";
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

function apply(theme: Theme) {
  const root = document.documentElement;
  if (theme === "dark") root.classList.add("dark");
  else root.classList.remove("dark");
  try {
    localStorage.setItem("ats-theme", theme);
  } catch {
    // Private mode / disabled storage — toggle still works for the session.
  }
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setTheme(readInitial());
    setMounted(true);
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    apply(next);
  }

  // Avoid hydration mismatch: render a placeholder until mounted.
  if (!mounted) {
    return (
      <span
        aria-hidden
        className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-300 dark:border-slate-700"
      />
    );
  }

  const isDark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      title={isDark ? "Switch to light theme" : "Switch to dark theme"}
      className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-300 text-sm hover:bg-slate-50 dark:bg-slate-950 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800 dark:bg-slate-200 dark:text-slate-900 dark:hover:bg-slate-700"
    >
      {isDark ? "☀" : "☾"}
    </button>
  );
}
