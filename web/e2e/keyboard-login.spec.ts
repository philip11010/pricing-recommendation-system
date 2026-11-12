import { expect, test } from "@playwright/test";

import { PASSWORD, freshEmail, registerMentor, requireApi } from "./helpers";

/**
 * Logging in without a pointer.
 *
 * Tab order follows visual order, the two fields are reachable in the order
 * they are read, and the form submits from the keyboard. A refusal is
 * announced rather than only drawn, which is what role="alert" is for.
 */
test("the log in form can be completed with the keyboard alone", async ({ page }) => {
  await requireApi();

  const email = freshEmail();
  await registerMentor(page, { email, name: "Keyboard Mentor" });
  await page.getByRole("button", { name: "Log out" }).click();

  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();

  // Walk forward until the focus lands on the email field, so the test is
  // about the order being sane rather than about a fixed number of presses.
  const emailField = page.getByLabel("Email", { exact: true });
  for (let press = 0; press < 12; press += 1) {
    if (await emailField.evaluate((node) => node === document.activeElement)) {
      break;
    }
    await page.keyboard.press("Tab");
  }
  await expect(emailField).toBeFocused();

  await page.keyboard.type(email);
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Password", { exact: true })).toBeFocused();
  await page.keyboard.type(PASSWORD);

  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Log in" })).toBeFocused();
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: /^Hello, / })).toBeVisible();
});

test("a wrong password is announced, in one sentence that names neither answer", async ({
  page,
}) => {
  await requireApi();

  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(freshEmail());
  await page.getByLabel("Password", { exact: true }).fill("not-the-password");
  await page.getByRole("button", { name: "Log in" }).click();

  // Scoped to the form: the framework keeps an empty alert of its own for
  // announcing route changes, which is not this message.
  const alert = page
    .locator("form")
    .getByRole("alert")
    .filter({ hasText: "do not match an account" });
  await expect(alert).toHaveText(
    "That email address and password do not match an account.",
  );
});
