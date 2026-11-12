import { expect, test } from "@playwright/test";

import { API_URL, registerMentor, requireApi } from "./helpers";

/**
 * What mentees rate a mentor overall, and the case where there is no rating.
 *
 * The second half is the one worth a test. A mentor nobody has rated has not
 * been rated badly, so an absent rating has to show as nothing at all: not a
 * zero, not a dash, not a row of empty stars, any of which would read as a
 * verdict that nobody gave. The null case is also the one every mentor is in
 * on the day they register, which is the first thing they see of their own
 * card.
 *
 * One figure and never a series. The platform records a rating as it stands
 * rather than month by month, so there is nothing honest to draw over time
 * and nothing here looks for one.
 */
const RATING = /\d\.\d out of 5/;

test("a mentor with no rating is shown no rating at all", async ({ page }) => {
  await requireApi();

  const name = `Unrated Mentor ${Date.now()}`;
  await registerMentor(page, { name });

  await page.goto("/mentors");
  const card = page.locator("article").filter({ hasText: name }).first();
  await expect(card).toBeVisible();
  await expect(card.getByText(RATING)).toHaveCount(0);
  await expect(card.getByText("0 out of 5")).toHaveCount(0);
  await expect(card.getByText("No reviews yet")).toBeVisible();

  await card.getByRole("link", { name }).click();
  await expect(page).toHaveURL(/\/mentors\/\d+/);
  await expect(page.getByText(RATING)).toHaveCount(0);
});

test("a mentor's own page shows no rating card until there is a rating", async ({
  page,
}) => {
  await requireApi();

  await registerMentor(page);
  await page.getByRole("button", { name: /^Accept \$/ }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await expect(page.getByText("Your price now").first()).toBeVisible();
  await expect(page.getByText("Average rating")).toHaveCount(0);
});

test("a rated mentor's profile shows the rating, to one decimal place", async ({
  page,
}) => {
  await requireApi();

  // Whichever mentor the running API holds a rating for, rather than an id
  // written into the test: the seeded accounts are rebuilt from time to time.
  // Read page by page, because the directory is newest first and the mentors
  // with a record are the oldest on a server these tests have been run
  // against a few times.
  type Card = { id: number; average_rating: number | null };
  let rated: Card | undefined;
  for (let offset = 0; !rated; offset += 100) {
    const response = await fetch(`${API_URL}/mentors?limit=100&offset=${offset}`);
    const body = (await response.json()) as { total: number; items: Card[] };
    rated = body.items.find((mentor) => mentor.average_rating !== null);
    if (!rated && offset + body.items.length >= body.total) {
      break;
    }
  }
  test.skip(!rated, "No mentor on this server has a rating yet.");

  await page.goto(`/mentors/${rated?.id}`);

  const shown = `${(rated?.average_rating as number).toFixed(1)} out of 5`;
  await expect(page.getByText(shown)).toBeVisible();

  // One figure, never a series: nothing on the page offers a rating over time.
  await expect(page.getByText(/rating.*month/i)).toHaveCount(0);
});
