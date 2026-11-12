import { expect, test } from "@playwright/test";

import {
  freshEmail,
  hasHorizontalScroll,
  PASSWORD,
  requireApi,
  visibleButtonHeights,
} from "./helpers";

/**
 * A phone, at 390 pixels wide.
 *
 * Two things are checked on every screen a new mentor passes through: that
 * the page does not scroll sideways, which is what a fixed width or a glow
 * escaping its container produces, and that every button a thumb has to find
 * is at least 44 pixels tall.
 */
test.use({ viewport: { width: 390, height: 844 } });

test.describe("on a phone", () => {
  test.beforeEach(async () => {
    await requireApi();
  });

  test("the landing, register and price screens fit and can be tapped", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /Know what your time is/ }),
    ).toBeVisible();
    expect(await hasHorizontalScroll(page)).toBe(false);
    for (const height of await visibleButtonHeights(page)) {
      expect(height).toBeGreaterThanOrEqual(44);
    }

    await page.goto("/register");
    await expect(
      page.getByRole("heading", { name: "Create your mentor profile" }),
    ).toBeVisible();
    expect(await hasHorizontalScroll(page)).toBe(false);
    for (const height of await visibleButtonHeights(page)) {
      expect(height).toBeGreaterThanOrEqual(44);
    }

    await page.getByLabel("Full name").fill("Narrow Mentor");
    await page.getByLabel("Email", { exact: true }).fill(freshEmail());
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByLabel("Your field").selectOption("technology_software");
    await page.getByRole("checkbox", { name: "CV review", exact: true }).check();

    // The preview stacks below the form on a phone rather than covering it.
    const preview = page.getByRole("complementary", { name: "Live price preview" });
    const form = page.locator("form");
    const previewBox = await preview.boundingBox();
    const formBox = await form.boundingBox();
    expect(previewBox && formBox ? previewBox.y > formBox.y : false).toBe(true);

    await page.getByRole("button", { name: "See my suggested price" }).click();
    await expect(page).toHaveURL(/\/recommendation\/\d+$/);
    await expect(
      page.getByText("Suggested session price", { exact: true }),
    ).toBeVisible();

    expect(await hasHorizontalScroll(page)).toBe(false);
    for (const height of await visibleButtonHeights(page)) {
      expect(height).toBeGreaterThanOrEqual(44);
    }
  });
});
