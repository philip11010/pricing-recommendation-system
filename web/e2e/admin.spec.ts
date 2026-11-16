import { expect, test } from "@playwright/test";

import { hasHorizontalScroll, logIn, registerMentor, requireApi } from "./helpers";

/**
 * The administration pages, against a real API.
 *
 * What only an end to end test can check here is the agreement between the
 * guard in the browser and the gate on the server. The unit tests cover both
 * halves separately: the component sends a mentor to their own dashboard, and
 * the API answers 403. Neither of them can catch the case where the flag the
 * browser reads and the flag the API checks have come apart, which is exactly
 * what would happen if `is_admin` were dropped from the mentor response.
 *
 * The administrator's credentials come from the environment. An administrator
 * password written into a test file is a password in the repository, so these
 * skip themselves with a line saying so when the two variables are not set.
 * The mentor half does not need them and runs either way.
 */

const ADMIN_EMAIL = process.env.ADMIN_EMAIL ?? "";
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD ?? "";

/**
 * Open a route that may redirect before it has finished loading.
 *
 * `page.goto` waits for the load event by default, and the guard on /admin
 * calls `router.replace` as soon as it knows the answer, which cancels the
 * navigation and makes goto throw `ERR_ABORTED`. Waiting for `commit`
 * instead returns as soon as the response arrives, which is all these tests
 * need: what they assert is where the browser ends up.
 */
async function open(page: import("@playwright/test").Page, path: string) {
  await page.goto(path, { waitUntil: "commit" });
}

/**
 * Sign in as the administrator, and wait until the browser holds the session.
 *
 * `logIn` submits the form and returns; the token is stored when the request
 * answers, which is after it. Navigating straight to /admin from there races
 * the sign in, and the guard, finding no account yet, sends the browser to
 * the log in screen. Waiting for the dashboard is waiting for the token.
 */
async function signInAsAdmin(page: import("@playwright/test").Page) {
  await logIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("link", { name: "Admin" })).toBeVisible();
}

/**
 * Every section: the sidebar label, the heading it opens with, and the id it
 * is addressed by in the query string.
 *
 * The id is written out rather than derived from the label, because they are
 * not the same word: "Model usage" is `usage`, and a test that guessed at it
 * would open the overview and then assert nothing useful about it.
 */
const SECTIONS: Array<{ id: string; link: string; heading: string }> = [
  { id: "overview", link: "Overview", heading: "Overview" },
  { id: "usage", link: "Model usage", heading: "Model usage" },
  { id: "outputs", link: "Outputs", heading: "Outputs" },
  { id: "users", link: "Users", heading: "Users" },
  { id: "models", link: "Models", heading: "Models" },
];

test.describe("the administration pages", () => {
  test.skip(
    !ADMIN_EMAIL || !ADMIN_PASSWORD,
    "Set ADMIN_EMAIL and ADMIN_PASSWORD to run this. Create the account with: python scripts/seed_admin.py",
  );

  test.beforeEach(async () => {
    await requireApi();
  });

  test("an administrator reaches every section", async ({ page }) => {
    await signInAsAdmin(page);
    await page.getByRole("link", { name: "Admin" }).click();
    await expect(page).toHaveURL(/\/admin/);

    await expect(page.getByRole("heading", { name: "Administration" })).toBeVisible();

    for (const section of SECTIONS) {
      await page
        .getByRole("navigation", { name: "Administration sections" })
        .getByRole("button", { name: section.link })
        .click();
      await expect(
        page.getByRole("heading", { name: section.heading, exact: true }),
      ).toBeVisible();
    }
  });

  test("the overview carries the summary cards and the daily chart", async ({
    page,
  }) => {
    await signInAsAdmin(page);
    await open(page, "/admin");

    await expect(page.getByText("Accounts").first()).toBeVisible();
    await expect(page.getByText("Recommendations").first()).toBeVisible();
    await expect(page.getByText("Median response").first()).toBeVisible();

    const chart = page.getByRole("region", { name: "Pricing calls per day" });
    await expect(chart).toBeVisible();
    // Either a chart or the empty state, and never an axis with nothing on
    // it: which of the two depends on whether this deployment has traffic.
    await expect(
      chart.getByRole("img").first().or(chart.getByText("No activity yet")),
    ).toBeVisible();

    await expect(page.getByRole("region", { name: "Recent activity" })).toBeVisible();
  });

  test("the models section names both models and labels every scale", async ({
    page,
  }) => {
    await signInAsAdmin(page);
    await open(page, "/admin?section=models");

    const core = page.getByRole("region", { name: "Core model" });
    const full = page.getByRole("region", { name: "Full model" });
    await expect(core).toBeVisible();
    await expect(full).toBeVisible();

    await expect(core.getByText(/Eight profile inputs/)).toBeVisible();
    await expect(full.getByText(/track record inputs/)).toBeVisible();
    await expect(core.getByText("core.joblib")).toBeVisible();
    await expect(full.getByText("full.joblib")).toBeVisible();
  });

  test("no section claims the price responds to demand", async ({ page }) => {
    await signInAsAdmin(page);

    for (const section of SECTIONS) {
      await open(page, `/admin?section=${section.id}`);
      // The sections render once the figures arrive, so this waits for one
      // heading rather than reading an empty main and passing on nothing.
      await expect(
        page.getByRole("heading", { name: section.heading, exact: true }),
      ).toBeVisible();
      const said = ((await page.locator("#main").textContent()) ?? "").toLowerCase();
      for (const banned of [
        "demand-responsive",
        "demand responsive",
        "responds to demand",
      ]) {
        expect(said).not.toContain(banned);
      }
    }
  });

  test("reads at tablet width, with the sidebar above the content", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await signInAsAdmin(page);
    await open(page, "/admin");

    const nav = page.getByRole("navigation", { name: "Administration sections" });
    const heading = page.getByRole("heading", { name: "Overview", exact: true });
    await expect(nav).toBeVisible();
    await expect(heading).toBeVisible();

    // Below 900px the sidebar becomes a row above the content rather than a
    // column beside it, so its bottom edge sits above the section heading.
    const navBox = await nav.boundingBox();
    const headingBox = await heading.boundingBox();
    expect(navBox && headingBox && navBox.y < headingBox.y).toBe(true);

    expect(await hasHorizontalScroll(page)).toBe(false);
  });

  test("reads at 360 pixels wide", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 780 });
    await signInAsAdmin(page);
    await open(page, "/admin");

    await expect(page.getByRole("heading", { name: "Administration" })).toBeVisible();
    expect(await hasHorizontalScroll(page)).toBe(false);
  });
});

test.describe("a mentor and the administration pages", () => {
  test.beforeEach(async () => {
    await requireApi();
  });

  test("is never shown the link", async ({ page }) => {
    await registerMentor(page);
    await open(page, "/dashboard");

    await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Admin" })).toHaveCount(0);
  });

  test("is sent to their own dashboard if they go there anyway", async ({ page }) => {
    await registerMentor(page);

    await open(page, "/admin");

    // Their own dashboard and not the log in screen: they are already signed
    // in, and logging in again would change nothing.
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByRole("heading", { name: /^Hello, / })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Administration" })).toHaveCount(0);
  });
});

test.describe("a visitor and the administration pages", () => {
  test.beforeEach(async () => {
    await requireApi();
  });

  test("is sent to log in", async ({ page }) => {
    await open(page, "/admin");

    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
  });

  test("sees no sign that the pages exist", async ({ page }) => {
    await open(page, "/");

    const header = page.locator("header");
    await expect(header.getByRole("link", { name: "Admin" })).toHaveCount(0);
    await expect(header.getByRole("link", { name: "Register" })).toBeVisible();
  });
});
