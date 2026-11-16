/**
 * The footer is on every page, so a broken link in it is broken everywhere.
 *
 * The columns are data in lib/copy.ts and markup here, which is exactly the
 * arrangement where the two can drift apart without anyone noticing. So the
 * test reads the data and insists the rendered footer agrees with it, rather
 * than restating a list of routes a third time.
 *
 * The bottom bar is checked for what must be in it and for what must never
 * be: it carries the project line and no person's name.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SiteFooter } from "@/components/site-footer";
import {
  BRAND,
  FOOTER_COLUMNS,
  FOOTER_CTA,
  FOOTER_LINE,
  FOOTER_PROJECT_LINE,
  copyrightLine,
} from "@/lib/copy";

describe("the site footer", () => {
  it("carries the wordmark, the tagline and a way to a price", () => {
    render(<SiteFooter />);

    expect(screen.getByRole("link", { name: `${BRAND} home` })).toHaveAttribute(
      "href",
      "/",
    );
    expect(screen.getByText(FOOTER_LINE)).toBeInTheDocument();

    const calls = screen.getAllByRole("link", { name: FOOTER_CTA.label });
    expect(calls.length).toBeGreaterThan(0);
    for (const call of calls) {
      expect(call).toHaveAttribute("href", FOOTER_CTA.href);
    }
  });

  it("renders three named columns whose links go where the copy says", () => {
    render(<SiteFooter />);

    expect(FOOTER_COLUMNS.map((column) => column.title)).toEqual([
      "Product",
      "Mentors",
      "Account",
    ]);

    for (const column of FOOTER_COLUMNS) {
      const group = screen.getByRole("navigation", { name: column.title });
      expect(within(group).getByRole("heading")).toHaveTextContent(column.title);

      for (const link of column.links) {
        expect(within(group).getByRole("link", { name: link.label })).toHaveAttribute(
          "href",
          link.href,
        );
      }
    }
  });

  it("points About at the About page and How it works at its anchor", () => {
    render(<SiteFooter />);

    const product = screen.getByRole("navigation", { name: "Product" });
    expect(within(product).getByRole("link", { name: "About" })).toHaveAttribute(
      "href",
      "/about",
    );
    expect(within(product).getByRole("link", { name: "How it works" })).toHaveAttribute(
      "href",
      "/about#how-it-works",
    );
  });

  it("ends on the copyright and the project line, and names nobody", () => {
    render(<SiteFooter />);

    const year = new Date().getFullYear();
    expect(screen.getByText(copyrightLine(year))).toBeInTheDocument();
    expect(screen.getByText(FOOTER_PROJECT_LINE)).toBeInTheDocument();

    const text = document.body.textContent ?? "";
    expect(text).toContain(String(year));
    expect(text).toContain(BRAND);
    expect(text).not.toMatch(/@/);
  });

  it("writes no em dash", () => {
    const copy = [
      FOOTER_LINE,
      FOOTER_PROJECT_LINE,
      FOOTER_CTA.label,
      copyrightLine(2026),
      ...FOOTER_COLUMNS.flatMap((column) => [
        column.title,
        ...column.links.flatMap((link) => [link.label, link.href]),
      ]),
    ];
    // Escapes rather than the characters themselves, so the rule that they
    // do not appear in this repository holds in the test that enforces it.
    const emDash = String.fromCharCode(0x2014);
    const enDash = String.fromCharCode(0x2013);
    for (const sentence of copy) {
      expect(sentence).not.toContain(emDash);
      expect(sentence).not.toContain(enDash);
    }

    render(<SiteFooter />);
    expect(document.body.textContent ?? "").not.toContain(emDash);
  });
});
