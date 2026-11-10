import { expect, test } from "@playwright/test";

import { freshEmail, requireApi } from "./helpers";

/**
 * A form that refuses to go forward, and says why, next to the answer.
 *
 * The thing being checked is not that validation exists but that it is
 * attached: each message sits with the field it is about and the field is
 * marked invalid, which is what a screen reader reads out. A page that turns
 * three boxes red and says nothing passes a screenshot and fails a mentor.
 */
test.describe("registration refuses answers it cannot use", () => {
  test.beforeAll(async () => {
    await requireApi();
  });

  test("an empty first step does not advance, and says what is missing", async ({
    page,
  }) => {
    await page.goto("/register");
    await expect(page.getByText("Step 1 of 3")).toBeVisible();

    await page.getByRole("button", { name: "Continue" }).click();

    await expect(page.getByText("Enter your full name.")).toBeVisible();
    await expect(
      page.getByText("Enter an email address we can reach you at."),
    ).toBeVisible();

    // Still on the first step, and still on the registration page.
    await expect(page.getByText("Step 1 of 3")).toBeVisible();
    await expect(page).toHaveURL(/\/register$/);

    // The message is tied to the field, not merely printed near it.
    await expect(page.getByLabel("Full name")).toHaveAttribute("aria-invalid", "true");
    const describedBy = await page
      .getByLabel("Full name")
      .getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    // Matched by attribute rather than by "#id": React's generated ids
    // contain characters a CSS id selector would have to escape.
    await expect(page.locator(`[id="${describedBy}"]`)).toHaveText(
      "Enter your full name.",
    );
  });

  test("a malformed email is caught before anything is sent", async ({ page }) => {
    await page.goto("/register");
    await page.getByLabel("Full name").fill("Test Mentor");
    await page.getByLabel("Email address").fill("not-an-address");
    await page.getByRole("button", { name: "Continue" }).click();

    // The form carries noValidate, so this is the application's message and
    // not the browser's tooltip. The browser's own one would have stopped the
    // submission before onSubmit ran, and it cannot be tied to the field.
    await expect(page.locator("form")).toHaveAttribute("novalidate", "");

    const email = page.getByLabel("Email address");
    await expect(
      page.getByText("Enter an email address we can reach you at."),
    ).toBeVisible();
    await expect(email).toHaveAttribute("aria-invalid", "true");

    // Tied to the field, and announced rather than merely drawn in red.
    const describedBy = (await email.getAttribute("aria-describedby")) ?? "";
    expect(describedBy).toBeTruthy();
    const message = page
      .locator(
        describedBy
          .split(" ")
          .map((id) => `[id="${id}"]`)
          .join(", "),
      )
      .filter({ hasText: "Enter an email address we can reach you at." });
    await expect(message).toHaveCount(1);
    await expect(message).toHaveAttribute("role", "alert");

    await expect(page.getByText("Step 1 of 3")).toBeVisible();
  });

  test("the service step will not submit without a field or a skill", async ({
    page,
  }) => {
    await page.goto("/register");

    await page.getByLabel("Full name").fill("Test Mentor");
    await page.getByLabel("Email address").fill(freshEmail());
    await page.getByRole("button", { name: "Continue" }).click();

    await page.getByLabel("Headline").fill("Helping new graduates find their footing");
    await page.getByLabel("Short bio").fill("Ten years in the field.");
    await page.getByLabel("Highest education").selectOption("masters");
    await page.getByLabel("Professional experience").fill("Senior practitioner.");
    await page.getByLabel("Years of mentoring experience").selectOption("3_to_5");
    await page.getByRole("button", { name: "Continue" }).click();

    await expect(page.getByText("Step 3 of 3")).toBeVisible();
    await page.getByRole("button", { name: "Suggest my price" }).click();

    await expect(page.getByText("Choose the field you mentor in.")).toBeVisible();
    await expect(
      page.getByText("Choose at least one skill or topic you cover."),
    ).toBeVisible();
    await expect(page).toHaveURL(/\/register$/);
  });
});
