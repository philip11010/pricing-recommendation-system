/**
 * The footer, on every page.
 *
 * A dark band carrying the same gradient and the same three soft glows as the
 * landing hero, so the site closes on the colour it opened with. Everything
 * on it is white, which DESIGN.md section 2.4 measures as the one text colour
 * that clears 4.5:1 on every stop of this gradient at every window width.
 *
 * It still says the two things a mentor has to keep in mind wherever they
 * are: the price is a suggestion, and it is in Australian dollars. That line
 * used to be the whole footer and is now its tagline.
 *
 * The link columns come from lib/copy.ts rather than being written here, so
 * the footer, the tests and the copy cannot disagree about where a link goes.
 */

import Link from "next/link";

import { LogoMark } from "@/components/logo";
import { ButtonLink } from "@/components/ui";
import {
  BRAND,
  FOOTER_COLUMNS,
  FOOTER_CTA,
  FOOTER_LINE,
  FOOTER_PROJECT_LINE,
  copyrightLine,
} from "@/lib/copy";

export function SiteFooter() {
  return (
    <footer className="on-gradient bg-hero text-surface">
      <div className="mx-auto w-full max-w-site px-4 py-12 sm:px-6">
        <div className="grid gap-10 wide:grid-cols-[1.2fr_2fr] wide:gap-12">
          {/* The mark, the wordmark and the one line that outranks the rest. */}
          <div className="min-w-0">
            <Link
              href="/"
              aria-label={`${BRAND} home`}
              className="inline-flex items-center gap-3 font-display text-[2rem] font-extrabold leading-none tracking-[-0.03em] text-surface"
            >
              <LogoMark onDark className="h-10 w-10" />
              {BRAND}
            </Link>
            <p className="mt-4 max-w-lead text-on-gradient-lead">{FOOTER_LINE}</p>
            <div className="mt-6">
              <ButtonLink href={FOOTER_CTA.href} variant="white">
                {FOOTER_CTA.label}
              </ButtonLink>
            </div>
          </div>

          <div className="grid gap-8 xs:grid-cols-2 mid:grid-cols-3">
            {FOOTER_COLUMNS.map((column) => (
              <nav key={column.title} aria-label={column.title} className="min-w-0">
                <h2 className="text-overline uppercase text-surface">{column.title}</h2>
                <ul className="mt-3 list-none space-y-1 p-0">
                  {column.links.map((link) => (
                    <li key={`${column.title}-${link.label}`}>
                      <Link
                        href={link.href}
                        className="inline-flex min-h-[44px] items-center rounded-field text-surface underline-offset-[3px] transition-colors duration-[180ms] ease-entrance hover:underline mid:min-h-[36px]"
                      >
                        {link.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </nav>
            ))}
          </div>
        </div>

        {/* The thin bar. No names in it, by rule. */}
        <div className="mt-10 flex flex-wrap justify-between gap-x-6 gap-y-2 border-t border-surface/30 pt-6 text-small text-surface">
          <span>{copyrightLine(new Date().getFullYear())}</span>
          <span>{FOOTER_PROJECT_LINE}</span>
        </div>
      </div>
    </footer>
  );
}
