import { expect, test } from "@playwright/test";

import { hasHorizontalScroll } from "./helpers";

/**
 * The two pieces of furniture a reader meets on every page.
 *
 * Neither of these needs the pricing API, so they are the only specs in this
 * directory that do not call requireApi: the About page is static copy and
 * the footer is static links. What they check is the part a unit test cannot,
 * which is that the real routes exist and resolve, that the navigation link
 * actually arrives at the page, and that the anchor button moves the reader
 * to the section it names.
 */

test.describe("About", () => {
  test("is reachable from the header and marked as the current page", async ({
    page,
  }) => {
    await page.goto("/");

    const about = page.getByRole("navigation", { name: "Main" }).getByRole("link", {
      name: "About",
    });
    await expect(about).toBeVisible();
    await about.click();

    await expect(page).toHaveURL(/\/about$/);
    await expect(
      page.getByRole("navigation", { name: "Main" }).getByRole("link", {
        name: "About",
      }),
    ).toHaveAttribute("aria-current", "page");
  });

  test("shows its headings, its scores and both calls to action", async ({ page }) => {
    await page.goto("/about");

    await expect(
      page.getByRole("heading", {
        level: 1,
        name: "Pricing guidance you can understand, built on real market patterns.",
      }),
    ).toBeVisible();

    for (const heading of [
      "Most mentors are guessing.",
      "How it works",
      "Where the data came from",
      "How it was built",
      "How accurate is it",
      "What it does not do",
    ]) {
      await expect(
        page.getByRole("heading", { level: 2, name: heading }),
      ).toBeVisible();
    }

    // Both models' score cards, by their own headings and one figure each.
    await expect(page.getByRole("heading", { name: "Core model" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Full model" })).toBeVisible();
    await expect(page.getByText("0.544", { exact: true })).toBeVisible();
    await expect(page.getByText("0.625", { exact: true })).toBeVisible();

    await expect(
      page.getByRole("link", { name: "Get your price" }).first(),
    ).toHaveAttribute("href", "/register");
    await expect(page.getByRole("link", { name: "Create an account" })).toHaveAttribute(
      "href",
      "/register",
    );
  });

  test("the hero's second button moves the reader to How it works", async ({
    page,
  }) => {
    await page.goto("/about");

    await page.getByRole("link", { name: "See how it works" }).click();
    await expect(page).toHaveURL(/#how-it-works$/);
    await expect(
      page.getByRole("heading", { level: 2, name: "How it works" }),
    ).toBeInViewport();
  });

  test("fits a narrow phone", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 780 });
    await page.goto("/about");

    await expect(
      page.getByRole("heading", { level: 2, name: "How accurate is it" }),
    ).toBeVisible();
    expect(await hasHorizontalScroll(page)).toBe(false);
  });
});

test.describe("the footer", () => {
  test("carries its three columns to the right routes", async ({ page }) => {
    await page.goto("/");

    const footer = page.locator("footer");
    await expect(footer).toBeVisible();

    for (const [column, label, href] of [
      ["Product", "Get your price", "/register"],
      ["Product", "How it works", "/about#how-it-works"],
      ["Product", "About", "/about"],
      ["Mentors", "Browse mentors", "/mentors"],
      ["Mentors", "For mentors dashboard", "/dashboard"],
      ["Account", "Log in", "/login"],
      ["Account", "Register", "/register"],
    ] as const) {
      const group = footer.getByRole("navigation", { name: column });
      await expect(
        group.getByRole("link", { name: label, exact: true }),
      ).toHaveAttribute("href", href);
    }

    await expect(footer.getByText("A final-year university project")).toBeVisible();
  });

  test("its About link opens the About page", async ({ page }) => {
    await page.goto("/");

    await page
      .locator("footer")
      .getByRole("navigation", { name: "Product" })
      .getByRole("link", { name: "About", exact: true })
      .click();

    await expect(page).toHaveURL(/\/about$/);
    await expect(
      page.getByRole("heading", { level: 2, name: "Where the data came from" }),
    ).toBeVisible();
  });
});
