import type { Metadata, Viewport } from "next";
import { Inter, Inter_Tight, Playfair_Display } from "next/font/google";
import type { ReactNode } from "react";

import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { BRAND, TAGLINE } from "@/lib/copy";

import "./globals.css";

/**
 * Three families, loaded through next/font so they are served from this
 * origin and cost no layout shift. One variable each, applied on <html>.
 *
 * Inter Tight is the headline voice, Inter is everything else, and Playfair
 * Display italic is the one accent word in a display heading. All three are
 * variable fonts, so one file per family covers every weight used.
 */
const display = Inter_Tight({
  subsets: ["latin"],
  weight: ["800"],
  variable: "--font-display",
  display: "swap",
});

const sans = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

const accent = Playfair_Display({
  subsets: ["latin"],
  weight: ["500"],
  style: ["italic"],
  variable: "--font-accent",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: BRAND,
    template: `%s | ${BRAND}`,
  },
  description: TAGLINE,
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en-AU"
      className={`${display.variable} ${sans.variable} ${accent.variable}`}
    >
      <body className="flex min-h-dvh flex-col bg-surface text-ink-900">
        {/* The first thing in the tab order, for anyone who does not want to
            walk through the header on every page. */}
        <a
          href="#main"
          className="sr-only sr-only-focusable font-semibold text-accent-800"
        >
          Skip to main content
        </a>
        <SiteHeader />
        <main id="main" className="flex-1">
          {children}
        </main>
        <SiteFooter />
      </body>
    </html>
  );
}
