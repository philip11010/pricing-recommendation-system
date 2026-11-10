import type { Config } from "tailwindcss";

/**
 * One accent colour, one neutral scale, one type scale.
 *
 * The accent is used for actions and for the figure a mentor came to read,
 * and nowhere else. Everything structural is a neutral, so the eye goes to
 * the price rather than to the furniture around it.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        accent: {
          50: "#effcf9",
          100: "#cbfbf1",
          200: "#99f2e4",
          300: "#5fe2d1",
          400: "#2cc8b8",
          500: "#14a99c",
          600: "#0c877f",
          700: "#0f6b67",
          800: "#115553",
          900: "#124745",
        },
        ink: {
          DEFAULT: "#111827",
          muted: "#4b5563",
          soft: "#6b7280",
        },
        shell: "#f7f8f9",
        line: "#e3e6ea",
        caution: {
          50: "#fff8ec",
          200: "#fcd9a4",
          700: "#9a5b08",
        },
        notice: {
          50: "#eef4ff",
          200: "#c3d4fe",
          700: "#2f4c9b",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      fontSize: {
        display: [
          "clamp(2rem, 6vw, 3.25rem)",
          { lineHeight: "1.08", letterSpacing: "-0.02em" },
        ],
        figure: [
          "clamp(2.5rem, 9vw, 4rem)",
          { lineHeight: "1", letterSpacing: "-0.03em" },
        ],
      },
      maxWidth: {
        prose: "68ch",
      },
      boxShadow: {
        card: "0 1px 2px rgba(17, 24, 39, 0.04), 0 8px 24px -12px rgba(17, 24, 39, 0.12)",
      },
      borderRadius: {
        xl2: "1.25rem",
      },
    },
  },
  plugins: [],
};

export default config;
