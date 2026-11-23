/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        accent: "var(--color-accent)",
        "accent-dim": "var(--color-accent-strong)",
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
      fontSize: {
        "3xs": ["var(--text-3xs)", { lineHeight: "1.4" }],
        "2xs": ["var(--text-2xs)", { lineHeight: "1.4" }],
        xs: ["var(--text-xs)", { lineHeight: "1.45" }],
        sm: ["var(--text-sm)", { lineHeight: "1.55" }],
        base: ["var(--text-base)", { lineHeight: "1.6" }],
        lg: ["var(--text-lg)", { lineHeight: "1.4" }],
        xl: ["var(--text-xl)", { lineHeight: "1.3" }],
        "2xl": ["var(--text-2xl)", { lineHeight: "1.2" }],
        "3xl": ["var(--text-3xl)", { lineHeight: "1.15" }],
        "4xl": ["var(--text-4xl)", { lineHeight: "1.05" }],
      },
      letterSpacing: {
        tight: "var(--tracking-tight)",
      },
    },
  },
  plugins: [],
};
