/**
 * The About page is mostly claims, so what is tested is the claims.
 *
 * Three things can go wrong here and not be noticed by eye. A section can be
 * dropped in an edit and the page still looks finished. A call to action can
 * point at a route that does not exist, and a link that goes nowhere is worse
 * on this page than anywhere else, because this is the page that asks to be
 * trusted. And an em dash can arrive with a pasted sentence, which the house
 * style forbids everywhere.
 *
 * The scores are not re-derived here. They are transcribed from the training
 * report into lib/copy.ts, and what this checks is that both models' figures
 * reach the page and are not silently showing the same column twice.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AboutPage, { metadata } from "@/app/about/page";
import {
  ABOUT_ACCURACY,
  ABOUT_BUILD,
  ABOUT_CLOSING,
  ABOUT_DATA,
  ABOUT_HERO,
  ABOUT_HOW,
  ABOUT_HOW_IT_WORKS_ID,
  ABOUT_LIMITS,
  ABOUT_META_DESCRIPTION,
  ABOUT_PROBLEM,
  ABOUT_SCORE_MODELS,
  ABOUT_SCORE_ROWS,
  ABOUT_TITLE,
} from "@/lib/copy";

const EM_DASH = String.fromCharCode(0x2014);
const EN_DASH = String.fromCharCode(0x2013);

/** Every string reachable from a value, however deeply it is nested. */
function stringsIn(value: unknown): string[] {
  if (typeof value === "string") {
    return [value];
  }
  if (Array.isArray(value)) {
    return value.flatMap(stringsIn);
  }
  if (value && typeof value === "object") {
    return Object.values(value).flatMap(stringsIn);
  }
  return [];
}

const ABOUT_COPY = [
  ABOUT_TITLE,
  ABOUT_META_DESCRIPTION,
  ABOUT_HERO,
  ABOUT_PROBLEM,
  ABOUT_HOW,
  ABOUT_DATA,
  ABOUT_BUILD,
  ABOUT_ACCURACY,
  ABOUT_LIMITS,
  ABOUT_SCORE_MODELS,
  ABOUT_SCORE_ROWS,
  ABOUT_CLOSING,
];

describe("the About page", () => {
  it("carries its own title and description", () => {
    expect(metadata.title).toBe(ABOUT_TITLE);
    expect(metadata.description).toBe(ABOUT_META_DESCRIPTION);
  });

  it("opens with the headline and leads with two ways on", () => {
    render(<AboutPage />);

    expect(
      screen.getByRole("heading", { level: 1, name: ABOUT_HERO.title }),
    ).toBeInTheDocument();

    const start = screen.getAllByRole("link", { name: ABOUT_HERO.primary.label })[0];
    expect(start).toHaveAttribute("href", "/register");

    expect(
      screen.getByRole("link", { name: ABOUT_HERO.secondary.label }),
    ).toHaveAttribute("href", `#${ABOUT_HOW_IT_WORKS_ID}`);
  });

  it("renders every section heading, in the order they were written", () => {
    const { container } = render(<AboutPage />);

    const expected = [
      ABOUT_PROBLEM.title,
      ABOUT_HOW.title,
      ABOUT_DATA.title,
      ABOUT_BUILD.title,
      ABOUT_ACCURACY.title,
      ABOUT_LIMITS.title,
      ABOUT_CLOSING.title,
    ];
    const headings = screen
      .getAllByRole("heading", { level: 2 })
      .map((heading) => heading.textContent);

    expect(headings).toEqual(expected);
    expect(container.querySelector(`#${ABOUT_HOW_IT_WORKS_ID}`)).not.toBeNull();
  });

  it("shows the three steps, the five build points and the three limits", () => {
    render(<AboutPage />);

    for (const step of ABOUT_HOW.steps) {
      expect(screen.getByRole("heading", { name: step.title })).toBeInTheDocument();
    }
    for (const point of ABOUT_BUILD.points) {
      expect(screen.getByText(point)).toBeInTheDocument();
    }
    for (const limit of ABOUT_LIMITS.points) {
      expect(screen.getByRole("heading", { name: limit.title })).toBeInTheDocument();
    }
    expect(screen.getByText(ABOUT_BUILD.curious)).toBeInTheDocument();
  });

  it("is honest about where the data came from, in its own words", () => {
    render(<AboutPage />);

    for (const paragraph of ABOUT_DATA.paragraphs) {
      expect(screen.getByText(paragraph)).toBeInTheDocument();
    }
    // The word that must never appear: this is not mentorship data.
    const body = document.body.textContent ?? "";
    expect(body).not.toMatch(/mentor data/i);
  });

  it("gives each model its own column of scores", () => {
    render(<AboutPage />);

    for (const model of ABOUT_SCORE_MODELS) {
      const heading = screen.getByRole("heading", { name: model.name });
      const card = heading.closest("div");
      expect(card).not.toBeNull();

      for (const row of ABOUT_SCORE_ROWS) {
        const value = model.key === "core" ? row.core : row.full;
        const term = within(card as HTMLElement).getByText(row.label);
        const definition = term.parentElement?.querySelector("dd");
        expect(definition).toHaveTextContent(value);
      }
    }
  });

  it("names the scale every score is on", () => {
    render(<AboutPage />);

    for (const row of ABOUT_SCORE_ROWS) {
      expect(screen.getAllByText(row.scale).length).toBeGreaterThan(0);
    }
    expect(screen.getByText(ABOUT_ACCURACY.verdict)).toBeInTheDocument();
    expect(screen.getByText(ABOUT_ACCURACY.limit)).toBeInTheDocument();
  });

  it("closes on two routes that exist", () => {
    render(<AboutPage />);

    for (const link of screen.getAllByRole("link", {
      name: ABOUT_CLOSING.primary.label,
    })) {
      expect(link).toHaveAttribute("href", "/register");
    }
    expect(
      screen.getByRole("link", { name: ABOUT_CLOSING.secondary.label }),
    ).toHaveAttribute("href", "/register");
  });

  it("writes no em dash, in the copy or on the page", () => {
    // Written as escapes on purpose. The rule is that the character does not
    // appear in this repository, and a test that spelled it out would be the
    // one place it did.
    for (const sentence of ABOUT_COPY.flatMap(stringsIn)) {
      expect(sentence).not.toContain(EM_DASH);
      expect(sentence).not.toContain(EN_DASH);
    }

    render(<AboutPage />);
    expect(document.body.textContent ?? "").not.toContain(EM_DASH);
  });
});
