import { expect, test } from "@playwright/test";

import { hasHorizontalScroll, registerMentor, requireApi } from "./helpers";

/**
 * The two pages that matter most, on the narrowest screen worth supporting.
 *
 * 375 pixels is an iPhone SE held upright, and a mentor filling in a form on
 * one should not have to scroll sideways to find the rest of a field. The
 * suggestion page is the other half of it, because it carries a chart and a
 * table, and both are the usual culprits.
 */
test.use({ viewport: { width: 375, height: 812 } });

test.describe("at 375 pixels wide", () => {
  test.beforeAll(async () => {
    await requireApi({ comparables: true });
  });

  test("registration fits, and so does the suggestion it leads to", async ({
    page,
  }) => {
    await page.goto("/register");
    await expect(page.getByText("Step 1 of 3")).toBeVisible();
    expect(await hasHorizontalScroll(page)).toBe(false);

    // A group session, so the suggestion page shows every figure it has.
    await registerMentor(page, { maxMentees: 3 });

    await expect(page.getByText("Suggested price", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "What similar mentors charge" }),
    ).toBeVisible();
    expect(await hasHorizontalScroll(page)).toBe(false);

    // And with the price table open, which is the widest the page ever gets.
    await page.getByText("Show these figures as a table").first().click();
    await expect(page.getByRole("table").first()).toBeVisible();
    expect(await hasHorizontalScroll(page)).toBe(false);
  });

  test("every control is big enough to tap", async ({ page }) => {
    await page.goto("/register");

    for (const name of ["Continue"]) {
      const box = await page.getByRole("button", { name }).boundingBox();
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
    }
    const field = await page.getByLabel("Full name").boundingBox();
    expect(field?.height ?? 0).toBeGreaterThanOrEqual(44);
  });

  test("the landing page fits too", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /Know what to charge/ }),
    ).toBeVisible();
    expect(await hasHorizontalScroll(page)).toBe(false);
  });
});
