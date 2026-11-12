import { expect, type Page } from "@playwright/test";

/**
 * The things more than one end to end test needs.
 *
 * Registering a mentor is the longest of them. It is written once rather than
 * repeated, because four of these tests start from a mentor who has just
 * registered, and a form filled four slightly different ways would be four
 * tests of four different things.
 *
 * Nothing here mocks the API. What these tests are for is the agreement
 * between this application and the pricing API: the names it sends, the
 * shapes it reads back and the statuses it acts on. A mocked API agrees with
 * whatever the mock was written to say.
 */

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

/** The seeded account the history tests sign in as. Never written in a test. */
export const DEMO_EMAIL = process.env.PLAYWRIGHT_DEMO_EMAIL ?? "";
export const DEMO_PASSWORD = process.env.PLAYWRIGHT_DEMO_PASSWORD ?? "";

/**
 * Stop with an explanation rather than with a wall of failed selectors.
 *
 * Every one of these tests needs the API, and some need the comparison table.
 * An API that is not running produces a page saying so, and a test that then
 * fails on a missing heading tells you nothing about why.
 */
export async function requireApi(options: { comparables?: boolean } = {}) {
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
}

/** An address nobody has registered with before, so registration never 409s. */
export function freshEmail(): string {
  return `mentor.${Date.now()}.${Math.floor(Math.random() * 10_000)}@example.com`;
}

export const PASSWORD = "a-long-enough-password";

export interface Registered {
  email: string;
  password: string;
  name: string;
  /** The address of the price screen the registration landed on. */
  priceUrl: string;
}

export interface RegistrationOptions {
  /** How many people can join. 1 keeps the one to one path, 3 makes a group. */
  maxMentees?: number;
  skills?: string[];
  name?: string;
  email?: string;
}

/**
 * Fill in the whole registration form and submit it.
 *
 * Leaves the browser on the suggested price for the new mentor's first
 * service, and hands back what is needed to log in as them again.
 */
export async function registerMentor(
  page: Page,
  options: RegistrationOptions = {},
): Promise<Registered> {
  const {
    maxMentees = 1,
    skills = ["CV review", "Interview preparation"],
    name = "Test Mentor",
    email = freshEmail(),
  } = options;

  await page.goto("/register");
  await expect(
    page.getByRole("heading", { name: "Create your mentor profile" }),
  ).toBeVisible();

  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByLabel("Your field").selectOption("technology_software");

  for (let seat = 1; seat < maxMentees; seat += 1) {
    await page.getByRole("button", { name: "More people" }).click();
  }

  for (const skill of skills) {
    await page.getByRole("checkbox", { name: skill, exact: true }).check();
  }

  await page.getByRole("button", { name: "See my suggested price" }).click();
  await expect(page).toHaveURL(/\/recommendation\/\d+$/);
  await expect(
    page.getByText("Suggested session price", { exact: true }),
  ).toBeVisible();

  return { email, password: PASSWORD, name, priceUrl: page.url() };
}

/** Log in through the form, as a returning mentor would. */
export async function logIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
}

/** True when the page is wider than the window, which it never should be. */
export async function hasHorizontalScroll(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const element = document.documentElement;
    // One pixel of slack: sub-pixel layout rounding is not a broken page.
    return element.scrollWidth > element.clientWidth + 1;
  });
}

/**
 * The height of every button a mentor can see, for the touch target check.
 *
 * Scoped to the header, the page and the footer, because the development
 * build draws an indicator button of its own that is not part of this
 * application and is not in the production build at all.
 */
export async function visibleButtonHeights(page: Page): Promise<number[]> {
  const buttons = await page
    .locator("header button:visible, #main button:visible, footer button:visible")
    .all();
  const heights: number[] = [];
  for (const button of buttons) {
    const box = await button.boundingBox();
    if (box) {
      heights.push(box.height);
    }
  }
  return heights;
}
