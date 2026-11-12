/**
 * One line, on every page.
 *
 * It restates the two things a mentor needs to keep in mind wherever they
 * are: the price is a suggestion, and it is in Australian dollars.
 */

import { BRAND, FOOTER_LINE } from "@/lib/copy";

export function SiteFooter() {
  return (
    <footer className="border-t border-line bg-surface">
      <div className="mx-auto flex w-full max-w-site flex-wrap justify-between gap-3 px-4 py-6 text-small text-ink-500 sm:px-6">
        <span>{BRAND}</span>
        <span>{FOOTER_LINE}</span>
      </div>
    </footer>
  );
}
