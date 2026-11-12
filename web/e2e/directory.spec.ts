import { expect, test } from "@playwright/test";

import { registerMentor, requireApi } from "./helpers";

/**
 * A mentor who registered a minute ago is in the directory.
 *
 * On the same terms as anybody else, with their verification shown as what it
 * is. That is the claim the directory makes, and it is worth a test because
 * the easy way to build a public list is to show only the checked ones, which
 * would leave every new mentor invisible to themselves.
 */
test("a newly registered mentor appears in the directory, not yet verified", async ({
  page,
}) => {
  await requireApi();

  const name = `Directory Mentor ${Date.now()}`;
  await registerMentor(page, { name });

  await page.goto("/mentors");
  await expect(page.getByRole("heading", { name: "Browse mentors" })).toBeVisible();

  const card = page.locator("article").filter({ hasText: name }).first();
  await expect(card).toBeVisible();
  await expect(card.getByText("New, not verified yet")).toBeVisible();
  await expect(
    card.getByText("Technology and software", { exact: true }),
  ).toBeVisible();
  await expect(card.getByText("One to one session")).toBeVisible();
  await expect(card.getByText("No reviews yet")).toBeVisible();

  // The card leads to the public profile, which says the same things.
  await card.getByRole("link", { name }).click();
  await expect(page).toHaveURL(/\/mentors\/\d+$/);
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Skills covered" })).toBeVisible();
  await expect(page.getByText("CV review")).toBeVisible();
});

test("the field filter narrows the list and can be widened again", async ({ page }) => {
  await requireApi();
  await page.goto("/mentors");

  await expect(page.getByRole("button", { name: "All fields" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  await page.getByRole("button", { name: "Law", exact: true }).click();
  await expect(page.getByRole("button", { name: "Law", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  await page.getByRole("button", { name: "All fields" }).click();
  await expect(page.getByRole("button", { name: "All fields" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});
