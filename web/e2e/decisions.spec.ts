import { expect, test } from "@playwright/test";

import { registerMentor, requireApi } from "./helpers";

/**
 * The three answers, and the fact that there is only one of them.
 *
 * Changing a price is not accepting one, and the dashboard has to say which
 * happened: a modified price shown as accepted would put words in the
 * mentor's mouth about advice they turned down. A second answer to the same
 * price is refused, and the refusal is shown rather than swallowed.
 */
test.describe("answering a suggested price", () => {
  test.beforeEach(async () => {
    await requireApi();
  });

  test("a changed price is recorded as modified, with the price the mentor named", async ({
    page,
  }) => {
    await registerMentor(page);

    const accept = page.getByRole("button", { name: /^Accept \$/ });
    const advised = ((await accept.textContent()) ?? "").replace("Accept ", "").trim();
    const ownPrice = String(Number(advised.replace(/[^0-9]/g, "")) + 25);

    await page.getByLabel("Or set your own price (AUD)").fill(ownPrice);
    await page.getByRole("button", { name: "Change", exact: true }).click();

    await expect(page).toHaveURL(/\/dashboard$/);
    const row = page.getByRole("row").filter({ hasText: "Technology and software" });
    await expect(row.getByText(/^Modified to \$/)).toBeVisible();
    await expect(row.getByText("Accepted")).toHaveCount(0);
  });

  test("changing to the advised price is refused, with the reason beside the field", async ({
    page,
  }) => {
    await registerMentor(page);

    const accept = page.getByRole("button", { name: /^Accept \$/ });
    const advised = ((await accept.textContent()) ?? "").replace(/[^0-9]/g, "");

    await page.getByLabel("Or set your own price (AUD)").fill(advised);
    await page.getByRole("button", { name: "Change", exact: true }).click();

    await expect(page.locator("#own-price-error")).toContainText(
      "That is the advised price.",
    );
    await expect(page).toHaveURL(/\/recommendation\/\d+$/);
  });

  test("a declined price is recorded as declined, and cannot be answered twice", async ({
    page,
  }) => {
    const mentor = await registerMentor(page);

    await page.getByRole("button", { name: "Decline", exact: true }).click();
    await expect(page).toHaveURL(/\/dashboard$/);

    const row = page.getByRole("row").filter({ hasText: "Technology and software" });
    await expect(row.getByText("Declined")).toBeVisible();
    await expect(row.getByText("Accepted")).toHaveCount(0);

    // Going back to the same price screen says it has been answered already,
    // rather than offering the three buttons again.
    await page.goto(mentor.priceUrl);
    await expect(
      page.getByText("You have already answered this price", { exact: false }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /^Accept \$/ })).toHaveCount(0);
  });
});

test("another mentor's price screen is not found", async ({ page }) => {
  await requireApi();

  const first = await registerMentor(page);
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/$/);

  await registerMentor(page, { name: "Second Mentor" });
  await page.goto(first.priceUrl);

  await expect(page.getByText("We could not find that price")).toBeVisible();
  await expect(
    page.getByText("That price is not one of yours, or it no longer exists."),
  ).toBeVisible();
});
