import { expect, test } from "@playwright/test";

import { API_URL, registerMentor, requireApi } from "./helpers";

/**
 * Two things the unit tests cannot check for themselves.
 *
 * The first is that every skill the running API publishes is actually drawn
 * on the form. The unit test checks the four headings against a copy of that
 * list; this checks the copy against the API, which is what catches the copy
 * going stale.
 *
 * The second is adding a second service, which is the only path that reaches
 * a price without going through registration.
 */
test("the form shows every skill the API publishes, once each", async ({ page }) => {
  await requireApi();

  const response = await fetch(`${API_URL}/meta/options`);
  const options = (await response.json()) as { skills: { label: string }[] };

  await page.goto("/register");
  await expect(page.getByRole("heading", { name: "Skills you cover" })).toBeVisible();

  const drawn = page.getByRole("checkbox");
  await expect(drawn).toHaveCount(options.skills.length);

  for (const skill of options.skills) {
    await expect(
      page.getByRole("checkbox", { name: skill.label, exact: true }),
    ).toHaveCount(1);
  }
});

test("a second service gets its own price", async ({ page }) => {
  await requireApi();

  await registerMentor(page);
  await page.getByRole("button", { name: /^Accept \$/ }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.getByRole("link", { name: "Add a service" }).first().click();
  await expect(page).toHaveURL(/\/dashboard\/add-service$/);
  await expect(page.getByRole("heading", { name: "Add a service" })).toBeVisible();

  // The field and the skills follow the mentor's profile, so only the group
  // size has to be answered to get a different price.
  await page.getByRole("button", { name: "More people" }).click();
  await page.getByRole("button", { name: "More people" }).click();
  await expect(page.locator("output")).toHaveText("3 people");

  await page.getByRole("button", { name: "See the suggested price" }).click();
  await expect(page).toHaveURL(/\/recommendation\/\d+$/);
  await expect(page.getByText("Suggested session price")).toBeVisible();
  await expect(page.getByText("AUD, group of 3")).toBeVisible();
});
