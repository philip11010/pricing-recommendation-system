import { expect, test, type Page } from "@playwright/test";

import { freshEmail, logIn, registerMentor, requireApi, PASSWORD } from "./helpers";

/**
 * Every screen has a way out, and the way out goes where the reader came from.
 *
 * The fault these are written against is a screen that can only be left
 * through the browser's own back button, and its quieter cousin: a link
 * called "back" that goes somewhere plausible rather than somewhere the
 * reader has been. Asking for a price again is the clearest example. It
 * creates a new recommendation, so a mentor who went off to read the
 * comparison and came back to a fresh price would find a different number
 * with its three answers still unanswered, and would have no way at all to
 * reach the one they were deciding about.
 *
 * So the origin travels in the address and the link is read back from it.
 * These tests follow the two journeys that carry an origin, the one that
 * carries a filter, and the three redirects that must not be reachable
 * backwards.
 */

/** The field every mentor these tests register is in, and its two addresses. */
const FIELD_LABEL = "Technology and software";
const FILTERED = /\/mentors\?field=technology_software$/;
const PROFILE = /\/mentors\/\d+\?field=technology_software$/;

/** The price on the suggestion card, as the mentor reads it. */
async function suggestedPrice(page: Page): Promise<string> {
  const card = page
    .locator("p")
    .filter({ hasText: /^\$[\d,]+/ })
    .first();
  return ((await card.textContent()) ?? "").trim();
}

/** The three answers a mentor can give a price. */
async function expectTheThreeDecisions(page: Page) {
  await expect(page.getByRole("button", { name: /^Accept \$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Change", exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Decline", exact: true }),
  ).toBeVisible();
}

test("the comparison comes back to the same price, not a fresh one", async ({
  page,
}) => {
  await requireApi({ comparables: true });

  await registerMentor(page);
  const priceUrl = page.url();
  const price = await suggestedPrice(page);
  await expectTheThreeDecisions(page);

  await page.getByRole("link", { name: "See all similar mentors" }).click();
  await expect(page).toHaveURL(/\/similar\/\d+\?from=recommendation&rec=\d+$/);
  await expect(
    page.getByRole("heading", { name: "What similar mentors charge" }),
  ).toBeVisible();

  await page.getByRole("link", { name: "Back to your price" }).first().click();

  await expect(page).toHaveURL(priceUrl);
  expect(await suggestedPrice(page)).toBe(price);
  await expectTheThreeDecisions(page);
});

test("the comparison opened from the dashboard comes back to the dashboard", async ({
  page,
}) => {
  await requireApi({ comparables: true });

  await registerMentor(page);
  await page.getByRole("button", { name: /^Accept \$/ }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.getByRole("link", { name: "See similar mentors" }).first().click();
  await expect(page).toHaveURL(/\/similar\/\d+\?from=dashboard$/);

  await page.getByRole("link", { name: "Back to your dashboard" }).first().click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: /^Hello, / })).toBeVisible();
});

test("a comparison reached with no origin still offers a way out", async ({ page }) => {
  await requireApi({ comparables: true });

  await registerMentor(page);
  await page.getByRole("link", { name: "See all similar mentors" }).click();
  const withOrigin = new URL(page.url());

  // The same page, addressed without the origin, and then with one that is
  // not readable. Both fall back to the dashboard rather than to no link.
  for (const address of [
    withOrigin.pathname,
    `${withOrigin.pathname}?from=recommendation`,
    `${withOrigin.pathname}?from=elsewhere&rec=0`,
  ]) {
    await page.goto(address);
    await page.getByRole("link", { name: "Back to your dashboard" }).first().click();
    await expect(page).toHaveURL(/\/dashboard$/);
  }
});

test("the directory keeps its filter through a profile and back", async ({ page }) => {
  await requireApi();

  // A field the test itself has just put a mentor in, so the filtered list
  // is never empty however the demonstration data happens to be seeded.
  await registerMentor(page);
  await page.goto("/mentors");
  await page.getByRole("button", { name: FIELD_LABEL, exact: true }).click();
  await expect(page).toHaveURL(FILTERED);

  const card = page.locator("article").first();
  const name = ((await card.locator("a").first().textContent()) ?? "").trim();
  await card.getByRole("link", { name }).click();

  await expect(page).toHaveURL(PROFILE);
  await expect(page.getByRole("heading", { name })).toBeVisible();

  await page.getByRole("link", { name: "Back to mentors" }).click();
  await expect(page).toHaveURL(FILTERED);
  await expect(
    page.getByRole("button", { name: FIELD_LABEL, exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});

test("the browser's own back button out of the directory keeps the filter", async ({
  page,
}) => {
  await requireApi();

  // A field the test itself has just put a mentor in, so the filtered list
  // is never empty however the demonstration data happens to be seeded.
  await registerMentor(page);
  await page.goto("/mentors");
  await page.getByRole("button", { name: FIELD_LABEL, exact: true }).click();
  await expect(page).toHaveURL(FILTERED);

  const card = page.locator("article").first();
  const name = ((await card.locator("a").first().textContent()) ?? "").trim();
  await card.getByRole("link", { name }).click();
  await expect(page).toHaveURL(PROFILE);

  await page.goBack();
  await expect(page).toHaveURL(FILTERED);
  await expect(
    page.getByRole("button", { name: FIELD_LABEL, exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});

test("going back after logging in does not return to the log in form", async ({
  page,
}) => {
  await requireApi();

  const email = freshEmail();
  await registerMentor(page, { email });
  await page.getByRole("button", { name: /^Accept \$/ }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.getByRole("button", { name: "Log out" }).click();

  await page.goto("/");
  await logIn(page, email, PASSWORD);
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.goBack();

  await expect(page).not.toHaveURL(/\/login/);
  await expect(page.getByRole("button", { name: "Log in" })).toHaveCount(0);
});

test("going back after registering does not return to the registration form", async ({
  page,
}) => {
  await requireApi();

  await page.goto("/");
  await registerMentor(page);
  await expect(page).toHaveURL(/\/recommendation\/\d+$/);

  await page.goBack();

  await expect(page).not.toHaveURL(/\/register/);
});

test("every screen a reader can land on offers a way onwards", async ({ page }) => {
  await requireApi();

  // The public screens, including the one for an address that is not ours.
  for (const [address, link] of [
    ["/", "Browse all mentors"],
    ["/mentors", "Pathwise home"],
    ["/login", "Register as a mentor"],
    ["/register", "Log in instead"],
    ["/nowhere-at-all", "Go to the start"],
  ] as const) {
    await page.goto(address);
    await expect(page.getByRole("link", { name: link }).first()).toBeVisible();
  }
});
