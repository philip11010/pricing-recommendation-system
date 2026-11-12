import { expect, test } from "@playwright/test";

import { DEMO_EMAIL, DEMO_PASSWORD, logIn, requireApi } from "./helpers";

/**
 * A mentor with a track record sees their months, as a chart and as a table.
 *
 * The credentials come from the environment. A seeded password written into
 * a test file is a password written into the repository, and this one is
 * shared by every demonstration account.
 */
test.describe("a mentor with a history", () => {
  test.skip(
    !DEMO_EMAIL || !DEMO_PASSWORD,
    "Set PLAYWRIGHT_DEMO_EMAIL and PLAYWRIGHT_DEMO_PASSWORD to run this.",
  );

  test.beforeEach(async () => {
    await requireApi({ comparables: true });
  });

  test("sees the reviews chart, its sentence and its data table", async ({ page }) => {
    await logIn(page, DEMO_EMAIL, DEMO_PASSWORD);
    await expect(page).toHaveURL(/\/dashboard$/);

    await expect(page.getByRole("heading", { name: /^Hello, / })).toBeVisible();
    await expect(page.getByText("Your price now").first()).toBeVisible();
    await expect(page.getByText("Reviews this year")).toBeVisible();
    await expect(page.getByText("Busiest month").first()).toBeVisible();

    const reviews = page.getByRole("region", { name: "Reviews each month" });
    await expect(reviews).toBeVisible();

    // The wrapper states the answer in words; the chart library draws its own
    // svg inside it, which is why this takes the first of the two.
    await expect(reviews.getByRole("img").first()).toBeVisible();

    const table = reviews.getByRole("group", { name: "Reviews received by month" });
    await expect(table).not.toBeVisible();

    await reviews.getByText("View data as a table").click();
    await expect(table).toBeVisible();
    await expect(reviews.getByRole("columnheader", { name: "Reviews" })).toBeVisible();
  });

  test("sees how they compare, in words before the ladder", async ({ page }) => {
    await logIn(page, DEMO_EMAIL, DEMO_PASSWORD);
    await expect(page).toHaveURL(/\/dashboard$/);

    const compare = page.getByRole("region", { name: "How you compare" });
    await expect(compare).toBeVisible();
    await expect(compare.getByText("Where most mentors sit").first()).toBeVisible();
  });

  test("sees how booked they are against similar mentors", async ({ page }) => {
    await logIn(page, DEMO_EMAIL, DEMO_PASSWORD);
    await expect(page).toHaveURL(/\/dashboard$/);

    const demand = page.getByRole("region", { name: "Demand for your time" });
    await expect(demand).toBeVisible();

    // The answer is in the sentence, not in a colour or a bar.
    await expect(demand.getByText(/Your time is booked/)).toBeVisible();

    const table = demand.getByRole("group", {
      name: "How booked you are, against similar mentors",
    });
    await expect(table).not.toBeVisible();
    await demand.getByText("View the numbers").click();

    await expect(table).toBeVisible();
    await expect(table.getByRole("cell", { name: "You", exact: true })).toBeVisible();
  });
});
