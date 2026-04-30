import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ATS Dashboard",
  description: "AI-powered resume screening — reviewer dashboard",
};

// Sets `class="dark"` on <html> before <body> renders, based on the
// localStorage preference (or the OS preference when the user hasn't
// chosen yet). Avoids a flash-of-light on first paint for dark-mode
// users. CONTENT IS A STATIC LITERAL — no user input is interpolated;
// this is the standard Next.js anti-FOUC theme pattern.
const ANTI_FOUC_SCRIPT =
  "(function(){try{var s=localStorage.getItem('ats-theme');" +
  "var d=s==='dark'||(s===null&&window.matchMedia('(prefers-color-scheme: dark)').matches);" +
  "if(d)document.documentElement.classList.add('dark');}catch(e){}})();";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* eslint-disable-next-line react/no-danger */}
        <script dangerouslySetInnerHTML={{ __html: ANTI_FOUC_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
