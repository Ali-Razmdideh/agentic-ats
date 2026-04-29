import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ATS Dashboard",
  description: "AI-powered resume screening — reviewer dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
