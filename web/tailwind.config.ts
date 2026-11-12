import type { Config } from "tailwindcss";

/**
 * The design system, as Tailwind reads it.
 *
 * Every value here points at a custom property declared in
 * `src/app/globals.css`, so a class name and a `var()` reference in a chart
 * resolve to the same colour. A raw hex value in a component is a defect, and
 * this file is what makes that rule possible to keep.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          900: "var(--ink-900)",
          700: "var(--ink-700)",
          500: "var(--ink-500)",
        },
        surface: {
          DEFAULT: "var(--surface)",
          sunk: "var(--surface-sunk)",
        },
        line: {
          DEFAULT: "var(--line)",
          strong: "var(--line-strong)",
        },
        accent: {
          100: "var(--accent-100)",
          700: "var(--accent-700)",
          800: "var(--accent-800)",
        },
        link: {
          700: "var(--link-700)",
          800: "var(--link-800)",
        },
        danger: {
          700: "var(--danger-700)",
          fill: "var(--danger-fill)",
        },
        success: {
          700: "var(--success-700)",
          fill: "var(--success-fill)",
        },
        caution: {
          700: "var(--caution-700)",
          fill: "var(--caution-fill)",
        },
        tint: {
          indigo: "var(--tint-indigo)",
          blue: "var(--tint-blue)",
          violet: "var(--tint-violet)",
          cyan: "var(--tint-cyan)",
        },
        "on-gradient": {
          lead: "var(--on-gradient-lead)",
          fine: "var(--on-gradient-fine)",
          dark: "var(--gradient-dark)",
        },
        chart: {
          track: "var(--chart-track)",
          band: "var(--chart-band)",
          edge: "var(--chart-band-edge)",
          grid: "var(--chart-grid)",
        },
      },
      backgroundImage: {
        hero: "var(--hero-gradient)",
        banner: "var(--banner-gradient)",
        closing: "var(--closing-gradient)",
      },
      fontFamily: {
        display: ["var(--font-display)", "var(--font-sans)", "sans-serif"],
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        accent: ["var(--font-accent)", "Georgia", "serif"],
      },
      fontSize: {
        "display-xl": [
          "clamp(2.5rem, 7vw, 4.5rem)",
          { lineHeight: "1.02", letterSpacing: "-0.03em", fontWeight: "800" },
        ],
        display: [
          "clamp(2rem, 6vw, 3.25rem)",
          { lineHeight: "1.08", letterSpacing: "-0.025em", fontWeight: "800" },
        ],
        "display-sm": [
          "clamp(1.75rem, 5vw, 2.5rem)",
          { lineHeight: "1.08", letterSpacing: "-0.025em", fontWeight: "800" },
        ],
        figure: [
          "clamp(2.5rem, 9vw, 4rem)",
          { lineHeight: "1", letterSpacing: "-0.03em", fontWeight: "800" },
        ],
        h2: [
          "clamp(1.375rem, 3vw, 1.75rem)",
          { lineHeight: "1.2", letterSpacing: "-0.015em", fontWeight: "700" },
        ],
        h3: ["1.125rem", { lineHeight: "1.3", letterSpacing: "-0.01em" }],
        "body-lg": ["1.125rem", { lineHeight: "1.6" }],
        body: ["1rem", { lineHeight: "1.55" }],
        small: ["0.875rem", { lineHeight: "1.5" }],
        label: ["0.8125rem", { lineHeight: "1.4", letterSpacing: "0.01em" }],
        overline: [
          "0.75rem",
          { lineHeight: "1.3", letterSpacing: "0.08em", fontWeight: "700" },
        ],
      },
      borderRadius: {
        pill: "9999px",
        card: "20px",
        band: "28px",
        chart: "16px",
        field: "12px",
        bar: "6px",
      },
      boxShadow: {
        card: "var(--shadow-card)",
      },
      maxWidth: {
        prose: "68ch",
        lead: "46ch",
        headline: "20ch",
        app: "1024px",
        site: "1152px",
      },
      transitionTimingFunction: {
        entrance: "var(--ease)",
      },
      screens: {
        xs: "375px",
        mid: "560px",
        wide: "900px",
      },
    },
  },
  plugins: [],
};

export default config;
