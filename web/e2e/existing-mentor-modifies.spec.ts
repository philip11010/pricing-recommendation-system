import { expect, test } from "@playwright/test";

import { openDemoMentor, requireApi } from "./helpers";

/**
 * A mentor with a track record, from their own page to a changed price.
 *
 * This is the other half of the system: the same endpoints, but the price is
 * worked out from the mentor's own ratings and booking history rather than
 * from a form, and their advice is shown against what they charge today.
 *
 * The last assertion is the one worth having. A modification is stored as a
 * modification however close to the suggestion it is, because the share of
 * advice that gets changed is the clearest evidence the system will ever have
 * about its own usefulness, and the mentor's own record has to say so.
 */
test.describe("an existing mentor reviews and modifies their price", () => {
  test.beforeAll(async () => {
    await requireApi({ demoMentors: true, comparables: true });
  });

  test("reviews the price, modifies it, and the record says Modified", async ({
    page,
  }) => {
    const name = await openDemoMentor(page);

    await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
    await expect(page.getByText("You charge now")).toBeVisible();

    await page.getByRole("button", { name: "Review my price" }).first().click();
    await expect(page).toHaveURL(/\/recommendation\/\d+$/);

    // Priced on their record, so no first-estimate caveat.
    await expect(page.getByText("Based on your record")).toBeVisible();
    await expect(
      page.getByText("This suggestion also reflects your ratings and booking history", {
        exact: false,
      }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Modify the price" }).click();

    const priceBox = page.getByLabel("The price you want to charge, per session");
    const suggested = Number.parseInt((await priceBox.inputValue()) || "0", 10);
    expect(suggested).toBeGreaterThan(0);

    const mine = Math.min(5000, suggested + 25);
    await priceBox.fill(String(mine));
    await page.getByRole("button", { name: "Save my price" }).click();

    await expect(page.getByRole("heading", { name: /^Modified/ })).toBeVisible();

    await page.getByRole("link", { name: "Go to my page" }).click();
    await expect(page).toHaveURL(/\/dashboard$/);

    const record = page
      .locator("li")
      .filter({ has: page.getByRole("link", { name: "Open" }) })
      .first();
    await expect(record).toContainText("Modified");
  });

  test("a modification equal to the suggestion is refused with a reason", async ({
    page,
  }) => {
    await openDemoMentor(page);
    await page.getByRole("button", { name: "Review my price" }).first().click();
    await expect(page).toHaveURL(/\/recommendation\/\d+$/);

    await page.getByRole("button", { name: "Modify the price" }).click();
    // The box opens pre-filled with the suggested price, so saving it
    // unchanged is exactly the case the API refuses.
    await page.getByRole("button", { name: "Save my price" }).click();

    await expect(
      page.getByText("That is the suggested price. Accept it instead."),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: /^Modified/ })).toHaveCount(0);
  });
});
