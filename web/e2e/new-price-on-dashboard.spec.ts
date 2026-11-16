import { expect, test, type Page } from "@playwright/test";

import { DEMO_EMAIL, DEMO_PASSWORD, logIn, requireApi } from "./helpers";

/**
 * A price answered is a price the mentor's own page reports.
 *
 * This is the regression test for the one thing that made the dashboard look
 * broken: a mentor who already had a service added another, answered its
 * price, landed back on their page and read the price of the service they
 * registered with. The page was reading the first service in the list rather
 * than the one the mentor had just settled on, so the figure they had come
 * to see was the one figure the page would not show them.
 *
 * It runs as a seeded mentor, because the mentor has to already have a
 * service for the bug to exist at all, and the credentials come from the
 * environment: a seeded password written into a test file is a password
 * written into the repository.
 */
test.describe("a second price on an existing mentor's page", () => {
  test.skip(
    !DEMO_EMAIL || !DEMO_PASSWORD,
    "Set PLAYWRIGHT_DEMO_EMAIL and PLAYWRIGHT_DEMO_PASSWORD to run this.",
  );

  test.beforeEach(async () => {
    await requireApi({ comparables: true });
  });

  /**
   * The "Your price now" card.
   *
   * The first match: the same words appear again in the table under the
   * comparison chart, which is below this card on the page.
   */
  function priceCard(page: Page) {
    return page.getByText("Your price now", { exact: true }).first().locator("..");
  }

  function amountIn(text: string): number {
    const found = text.match(/\$([\d,]+)/);
    expect(found, `no amount in "${text}"`).not.toBeNull();
    return Number((found as RegExpMatchArray)[1].replace(/,/g, ""));
  }

  test("adding a service and accepting its price updates the dashboard", async ({
    page,
  }) => {
    await logIn(page, DEMO_EMAIL, DEMO_PASSWORD);
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByRole("heading", { name: /^Hello, / })).toBeVisible();

    const before = amountIn((await priceCard(page).textContent()) ?? "");

    await page.getByRole("link", { name: "Add a service" }).first().click();
    await expect(page).toHaveURL(/\/dashboard\/add-service$/);

    // The group size opens on the mentor's most recent service rather than
    // empty, which is the second half of what this flow was reported for.
    const size = page.locator("output");
    await expect(size).not.toBeEmpty();

    // Two more seats than that, so the new service is a different service
    // and asks the models a different question.
    await page.getByRole("button", { name: "More people" }).click();
    await page.getByRole("button", { name: "More people" }).click();
    const seats = Number(((await size.textContent()) ?? "").match(/\d+/)?.[0]);
    expect(seats).toBeGreaterThan(1);

    await page.getByRole("button", { name: "See the suggested price" }).click();
    await expect(page).toHaveURL(/\/recommendation\/\d+$/);

    const accept = page.getByRole("button", { name: /^Accept \$/ });
    const accepted = amountIn((await accept.textContent()) ?? "");
    await accept.click();

    // Back on the dashboard without a reload: whatever this page shows now
    // is what a mentor sees the moment they answer.
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByRole("heading", { name: /^Hello, / })).toBeVisible();

    const card = priceCard(page);
    await expect(card).toContainText(`$${accepted.toLocaleString("en-AU")}`);
    expect(amountIn((await card.textContent()) ?? "")).toBe(accepted);

    // The mentor now has more than one service, so the card says which of
    // their prices this is.
    await expect(card).toContainText(`per session of ${seats}`);

    // And the comparison is drawn against the price that was just accepted,
    // not against the one it replaced.
    const compare = page.getByRole("region", { name: "How you compare" });
    await expect(compare).toBeVisible();

    const table = compare.getByRole("group", {
      name: "Your price against similar mentors, in AUD",
    });
    await expect(table).not.toBeVisible();
    await compare.getByText("View data as a table").click();
    await expect(table).toBeVisible();

    const marked = table.getByRole("row").filter({ hasText: "Your price now" });
    await expect(marked).toContainText(`$${accepted.toLocaleString("en-AU")}`);

    if (accepted !== before) {
      expect(amountIn((await card.textContent()) ?? "")).not.toBe(before);
    }
  });
});
