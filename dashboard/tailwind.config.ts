import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  // Class-based dark mode — toggled by <ThemeToggle> writing
  // `class="dark"` on <html> via localStorage. The anti-FOUC script in
  // app/layout.tsx applies the class before first paint.
  darkMode: "class",
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
