import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import type { ReactNode } from "react";

import { SiteHeader } from "@/components/site-header";
import { BRAND } from "@/lib/copy";

import "./globals.css";

/**
 * One typeface, loaded through next/font so it is served from this origin and
 * does not shift the page while it arrives.
 */
const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: BRAND,
    template: `%s | ${BRAND}`,
  },
  description:
    "Suggested session prices for mentors, based on what mentors like you charge. The suggestion is advice: you decide what to charge.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en-AU" className={sans.variable}>
      <body className="flex min-h-dvh flex-col">
        {/* The first thing in the tab order, for anyone who does not want to
            walk through the header on every page. */}
        <a
          href="#main"
          className="sr-only sr-only-focusable font-semibold text-accent-800"
        >
          Skip to main content
        </a>
        <SiteHeader />
        <main id="main" className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6">
          {children}
        </main>
        <footer className="border-t border-line bg-white">
          <div className="mx-auto max-w-5xl px-4 py-6 text-sm text-ink-soft sm:px-6">
            <p>
              {BRAND}. Every suggested price is advice, in Australian dollars. You
              decide what to charge.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
