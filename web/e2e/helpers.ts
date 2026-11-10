import { expect, type Page } from "@playwright/test";

/**
 * The things more than one end-to-end test needs.
 *
 * Registering a mentor is the longest of them. It is written as a helper
 * rather than repeated because three of the five tests start from a mentor
 * who has just registered, and a form filled three slightly different ways
 * would be three different tests of three different things.
 */

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

/**
 * Stop with an explanation rather than with a wall of failed selectors.
 *
 * Every one of these tests needs the API, and most need the demonstration
 * mentors. An API that is not running produces a page saying so, and a test
 * that then fails on a missing heading tells you nothing about why.
 */
export async function requireApi(
  options: { demoMentors?: boolean; comparables?: boolean } = {},
) {
  let health: Response;
  try {
    health = await fetch(`${API_URL}/health`);
  } catch {
    throw new Error(
      `The pricing API is not answering at ${API_URL}. Start it with: uvicorn src.mentor.app:app --port 8000`,
    );
  }
  const body = (await health.json()) as {
    models_loaded: boolean;
    comparables_loaded: boolean;
  };
  if (!body.models_loaded) {
    throw new Error(
      "The pricing API is running without its models, so it cannot price anything. Run: python scripts/prepare_app_assets.py",
    );
  }
  if (options.comparables && !body.comparables_loaded) {
    throw new Error(
      "The pricing API has no table of comparable mentors, so it cannot say what mentors like you charge. Run: python scripts/build_comparables.py",
    );
  }

  if (options.demoMentors) {
    const response = await fetch(`${API_URL}/mentors/demo`);
    const mentors = (await response.json()) as unknown[];
    if (mentors.length === 0) {
      throw new Error(
        "There are no demonstration mentors. Run: python scripts/seed_demo_mentors.py",
      );
    }
  }
}

/** An address nobody has registered with before, so registration never 409s. */
export function freshEmail(): string {
  return `mentor.${Date.now()}.${Math.floor(Math.random() * 10_000)}@example.com`;
}

export interface RegistrationOptions {
  /** How many mentees can join. 1 keeps the one to one path, 3 makes a group. */
  maxMentees?: number;
  skills?: string[];
}

/**
 * Fill in the whole registration form and submit it.
 *
 * Leaves the browser on the suggestion for the new mentor's first service.
 */
export async function registerMentor(
  page: Page,
  options: RegistrationOptions = {},
): Promise<void> {
  const { maxMentees = 1, skills = ["CV review", "Interview preparation"] } = options;

  await page.goto("/register");

  // Step one: the account.
  await page.getByLabel("Full name").fill("Test Mentor");
  await page.getByLabel("Email address").fill(freshEmail());
  await page.getByRole("button", { name: "Continue" }).click();

  // Step two: the profile, none of which is priced.
  await page.getByLabel("Headline").fill("Helping new graduates find their footing");
  await page
    .getByLabel("Short bio")
    .fill("Ten years in the field, six of them leading a team.");
  await page.getByLabel("Highest education").selectOption("masters");
  await page
    .getByLabel("Professional experience")
    .fill("Senior practitioner, then a team lead.");
  await page.getByLabel("Years of mentoring experience").selectOption("3_to_5");
  await page.getByRole("button", { name: "Continue" }).click();

  // Step three: the answers that set the price.
  await page.getByLabel("Field", { exact: true }).selectOption("technology_software");

  const stepper = page.getByRole("spinbutton");
  for (let seat = 1; seat < maxMentees; seat += 1) {
    await page.getByRole("button", { name: "One more mentee" }).click();
  }
  await expect(stepper).toHaveAttribute("aria-valuenow", String(maxMentees));

  await page.getByLabel("Minimum booking commitment").selectOption("1");
  for (const skill of skills) {
    await page.getByRole("checkbox", { name: skill, exact: true }).check();
  }

  await page.getByRole("button", { name: "Suggest my price" }).click();
  await expect(page).toHaveURL(/\/recommendation\/\d+$/);
  await expect(page.getByText("Suggested price", { exact: true })).toBeVisible();
}

/** Open the first demonstration mentor's own page. */
export async function openDemoMentor(page: Page): Promise<string> {
  await page.goto("/mentors");
  const first = page.getByRole("button", { name: /^Continue as / }).first();
  await expect(first).toBeVisible();
  const label = (await first.textContent()) ?? "";
  await first.click();
  await expect(page).toHaveURL(/\/dashboard$/);
  return label.replace("Continue as ", "").trim();
}

/** True when the page is wider than the window, which it never should be. */
export async function hasHorizontalScroll(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const element = document.documentElement;
    // One pixel of slack: sub-pixel layout rounding is not a broken page.
    return element.scrollWidth > element.clientWidth + 1;
  });
}
