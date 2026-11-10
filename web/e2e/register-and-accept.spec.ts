import { expect, test } from "@playwright/test";

import { registerMentor, requireApi } from "./helpers";

/**
 * A new mentor, from the form to an answer.
 *
 * The whole of the new-mentor path: they register, they are shown a price
 * that says plainly it is a first estimate, they can see what mentors like
 * them charge, and they accept it.
 */
test.describe("a new mentor registers and accepts the suggestion", () => {
  test.beforeAll(async () => {
    await requireApi({ comparables: true });
  });

  test("sees a first estimate, the comparison, and accepts", async ({ page }) => {
    await registerMentor(page, { maxMentees: 1 });

    // A price, in whole Australian dollars.
    await expect(page.getByText(/^\$[\d,]+$/).first()).toBeVisible();

    // Said to be an estimate, because a form is a weaker basis than a record.
    await expect(
      page.getByText("This is a first estimate from the details you gave us.", {
        exact: false,
      }),
    ).toBeVisible();
    await expect(page.getByText("First estimate", { exact: true })).toBeVisible();

    // And the market beside it.
    await expect(
      page.getByRole("heading", { name: "What similar mentors charge" }),
    ).toBeVisible();
    await expect(page.getByText("The middle of this group charges")).toBeVisible();
    await expect(
      page.getByRole("link", { name: "See all similar mentors" }),
    ).toBeVisible();

    // Nothing is set until the mentor answers.
    await expect(
      page.getByRole("heading", { name: "What would you like to do?" }),
    ).toBeVisible();

    const accept = page.getByRole("button", { name: /^Accept \$/ });
    await expect(accept).toBeVisible();
    await accept.click();

    await expect(page.getByRole("heading", { name: /^Accepted/ })).toBeVisible();
    await expect(page.getByRole("link", { name: "Go to my page" })).toBeVisible();
  });

  test("a group session is quoted per mentee and per session", async ({ page }) => {
    await registerMentor(page, { maxMentees: 4 });

    await expect(page.getByText("per mentee", { exact: true })).toBeVisible();
    await expect(page.getByText("Per session (whole group of up to 4)")).toBeVisible();
    await expect(
      page.getByText("Suggested range, per session (whole group)"),
    ).toBeVisible();
  });
});
