/** @type {import('tailwindcss').Config} */
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        serif: ['"IBM Plex Serif"', "Georgia", "serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      colors: {
        canvas: token("canvas"),
        surface: token("surface"),
        sunken: token("sunken"),
        line: token("line"),
        ink: token("ink"),
        muted: token("muted"),
        faint: token("faint"),
        navy: token("navy"),
        "navy-soft": token("navy-soft"),
        accent: token("accent"),
        "accent-soft": token("accent-soft"),
        version: token("version"),
        "version-soft": token("version-soft"),
        pass: token("pass"),
        "pass-soft": token("pass-soft"),
        fail: token("fail"),
        "fail-soft": token("fail-soft"),
        warn: token("warn"),
        "warn-soft": token("warn-soft"),
        na: token("na"),
        "na-soft": token("na-soft"),
        mark: token("mark"),
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      boxShadow: {
        panel: "0 1px 2px rgb(15 23 42 / 0.06), 0 0 0 1px rgb(var(--line) / 1)",
        pop: "0 12px 32px -8px rgb(15 23 42 / 0.25)",
      },
    },
  },
  plugins: [],
};
