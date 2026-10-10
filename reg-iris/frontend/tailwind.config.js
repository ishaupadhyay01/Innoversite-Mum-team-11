/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"IBM Plex Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        ink: { DEFAULT: "#14202b", soft: "#4a5866", faint: "#8796a5" },
        canvas: "#f4f6f8",
        line: "#dde3e9",
        brand: { DEFAULT: "#0f5e6e", dark: "#0a4652", tint: "#e3f0f2" },
        pass: { DEFAULT: "#1d7a4d", tint: "#e4f3ea" },
        fail: { DEFAULT: "#b4232c", tint: "#fbe7e8" },
        na: { DEFAULT: "#6b7785", tint: "#eef1f4" },
        warn: { DEFAULT: "#a86200", tint: "#fdf1de" },
      },
    },
  },
  plugins: [],
};
