import { expect, test } from "@playwright/test";

import { freshEmail, PASSWORD, registerMentor, requireApi } from "./helpers";

/**
 * The whole first visit: register, watch the preview move, take the price.
 *
 * This is the path the system exists for. It is one test rather than four,
 * because what is being checked is that the four screens hand on to each
 * other, and a mentor who gets three of the four has got nothing.
 */
test.describe("a new mentor", () => {
  test.beforeEach(async () => {
    await requireApi();
  });

  test("sees the preview change with the group size, then accepts the price", async ({
    page,
  }) => {
    await page.goto("/register");
    await expect(
      page.getByRole("heading", { name: "Create your mentor profile" }),
    ).toBeVisible();

    const preview = page.getByRole("complementary", { name: "Live price preview" });
    await expect(
      preview.getByText("Choose your field to see an early price here."),
    ).toBeVisible();

    await page.getByLabel("Full name").fill("Preview Mentor");
    await page.getByLabel("Email", { exact: true }).fill(freshEmail());
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByLabel("Your field").selectOption("technology_software");

    // The panel is explicit that these are early numbers, not the suggestion.
    await expect(preview.getByText(/Early numbers\./)).toBeVisible();
    await expect(preview.getByText(/One to one session: \$/)).toBeVisible();

    await page.getByRole("button", { name: "More people" }).click();
    await page.getByRole("button", { name: "More people" }).click();
    await expect(page.locator("output")).toHaveText("3 people");
    await expect(preview.getByText(/Full session of 3: \$/)).toBeVisible();

    await page.getByRole("checkbox", { name: "CV review", exact: true }).check();
    await page.getByRole("button", { name: "See my suggested price" }).click();

    await expect(page).toHaveURL(/\/recommendation\/\d+$/);
    await expect(
      page.getByText("Suggested session price", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText(
        "This is advice, not a rule. Mentors like you usually charge close to this, and you decide the final price.",
      ),
    ).toBeVisible();
    // A price from the form alone says so, at full size and not in a tooltip.
    await expect(page.getByText("Early estimate.")).toBeVisible();

    await page.getByRole("button", { name: /^Accept \$/ }).click();

    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByRole("heading", { name: /^Hello, / })).toBeVisible();
    await expect(
      page.getByText(
        "You have no reviews recorded yet. Once mentees start reviewing your sessions, this is where you will see how they arrive month by month.",
      ),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Your services" })).toBeVisible();
    await expect(page.getByText("Accepted")).toBeVisible();
  });

  test("is told plainly when an answer is missing", async ({ page }) => {
    await registerMentorWithNothing(page);
  });
});

/** Submitting an empty form reports every missing answer, in one place. */
async function registerMentorWithNothing(page: import("@playwright/test").Page) {
  await page.goto("/register");
  await page.getByRole("button", { name: "See my suggested price" }).click();

  const summary = page.getByRole("alert").first();
  await expect(summary).toBeVisible();
  await expect(summary).toContainText("Tell us the name mentees will see.");
  await expect(summary).toContainText("Enter an email address so you can log back in.");
  await expect(summary).toContainText("Choose the field you mentor in most.");

  // The summary complements the inline messages and never replaces them.
  await expect(page.locator("#register-email-error")).toHaveText(
    "Enter an email address so you can log back in.",
  );
}

test("registering, then logging out and back in", async ({ page }) => {
  await requireApi();
  const mentor = await registerMentor(page);

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(
    page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Register", exact: true }),
  ).toBeVisible();

  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(mentor.email);
  await page.getByLabel("Password", { exact: true }).fill(mentor.password);
  await page.getByRole("button", { name: "Log in" }).click();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Hello, Test" })).toBeVisible();
});
