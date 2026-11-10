import { expect, test } from "@playwright/test";

import { registerMentor, requireApi } from "./helpers";

/**
 * Declining the suggestion, and then naming a price anyway.
 *
 * The most useful thing a mentor who disagrees can tell the system is what
 * they charge instead, so declining offers that rather than ending the
 * conversation. It is also allowed to end the conversation: "Decide later"
 * leaves the service charging whatever it charged.
 */
test.describe("a mentor declines the suggestion", () => {
  test.beforeAll(async () => {
    await requireApi();
  });

  test("declines, then sets their own price", async ({ page }) => {
    await registerMentor(page, { maxMentees: 1 });

    await page.getByRole("button", { name: "Decline" }).click();
    await expect(
      page.getByText("Would you like to set your own price instead", { exact: false }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Set my own price" }).click();
    await page.getByLabel("The price you want to charge, per session").fill("250");
    await page.getByRole("button", { name: "Save my price" }).click();

    await expect(page.getByRole("heading", { name: /^Declined/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: /\$250 a session/ })).toBeVisible();

    await page.getByRole("link", { name: "Go to my page" }).click();
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByText("$250").first()).toBeVisible();
  });

  test("or declines and decides later, leaving the price alone", async ({ page }) => {
    await registerMentor(page, { maxMentees: 2 });

    await page.getByRole("button", { name: "Decline" }).click();
    await page.getByRole("button", { name: "Decide later" }).click();

    await expect(page.getByRole("heading", { name: /^Declined/ })).toBeVisible();
    await expect(
      page.getByText("your service charges what it charged before", { exact: false }),
    ).toBeVisible();
  });

  test("a price already answered cannot be answered twice", async ({ page }) => {
    await registerMentor(page, { maxMentees: 1 });
    const url = page.url();

    await page.getByRole("button", { name: /^Accept \$/ }).click();
    await expect(page.getByRole("heading", { name: /^Accepted/ })).toBeVisible();

    // Coming back to the same suggestion shows the answer, not the form.
    await page.goto(url);
    await expect(
      page.getByRole("heading", { name: "What would you like to do?" }),
    ).toHaveCount(0);
    await expect(page.getByText(/Accepted/).first()).toBeVisible();
  });
});
