import { expect, test, type Page } from "@playwright/test";

import { hasHorizontalScroll, registerMentor, requireApi } from "./helpers";

/**
 * Why we suggest this price, on the screen a mentor actually reads it on.
 *
 * The backend holds the arithmetic to its claim. What is left to check here is
 * everything between that and a mentor: that the rows reach the page, that the
 * figures printed beside them still come to the price printed above them, that
 * the two fixed lines are shown rather than tucked away, and that the card
 * failing does not take the three decisions down with it.
 *
 * The last of those is the one worth the stubbing. A mentor whose account of
 * their price fails to load has lost an explanation, not a price, and the
 * screen has to go on working. That cannot be checked by waiting for a real
 * failure.
 */
const CARD = "Why we suggest this price";
const LIMITATION =
  "These are patterns in what similar mentors charge. They are not guarantees, and the final price is yours to set.";
const PROFILE_NOTE =
  "Experience and credentials appear on your public card. They do not change this suggestion.";

/**
 * The card, once it holds an account rather than a skeleton.
 *
 * The account arrives in a request of its own, so the heading is on the page
 * before the rows are. Counting rows or reading text does not wait on its
 * own in Playwright, and a test that did either straight after the heading
 * appeared would be reading the loading state and calling it a result.
 */
async function readyCard(page: Page) {
  const card = page.getByRole("region", { name: CARD });
  await expect(card.getByRole("heading", { name: CARD })).toBeVisible();
  await expect(
    card.getByRole("list", { name: "What moved your price" }).locator("> li").first(),
  ).toBeVisible();
  return card;
}

/** Every signed percentage in the list of what moved the price, in order. */
async function shownEffects(page: Page): Promise<number[]> {
  const rows = await page
    .getByRole("region", { name: CARD })
    .getByRole("list", { name: "What moved your price" })
    .locator("> li")
    .all();
  const effects: number[] = [];
  for (const row of rows) {
    const text = (await row.textContent()) ?? "";
    const found = text.match(/([+-]?\d+)%/);
    expect(found, `no effect in "${text}"`).not.toBeNull();
    effects.push(Number((found as RegExpMatchArray)[1]));
  }
  return effects;
}

function moneyIn(text: string): number {
  const found = text.match(/\$([\d,]+)/);
  expect(found, `no amount in "${text}"`).not.toBeNull();
  return Number((found as RegExpMatchArray)[1].replace(/,/g, ""));
}

test("a new mentor is told why, in a short list plus the small ones", async ({
  page,
}) => {
  await requireApi({ comparables: true });

  await registerMentor(page);
  const card = await readyCard(page);

  const rows = card
    .getByRole("list", { name: "What moved your price" })
    .locator("> li");
  const count = await rows.count();
  // Scoped to the list: the same label appears again inside the numbers
  // table, which is closed but still in the page.
  const gathered = await rows.filter({ hasText: "Other small effects" }).count();

  expect(count).toBeGreaterThan(0);
  // Five, or up to seven where five would have left the gathered row larger
  // than a row above it.
  expect(count - gathered).toBeLessThanOrEqual(7);
  expect(gathered).toBeLessThanOrEqual(1);

  // Every row says which way it goes in words, not in a colour.
  const words = (await rows.allTextContents()).join(" ");
  expect(words).toMatch(/raises|lowers|little effect/);

  // The two fixed lines, at full size and not behind a disclosure.
  await expect(card.getByText(LIMITATION)).toBeVisible();
  await expect(card.getByText(PROFILE_NOTE)).toBeVisible();

  // The comparison, with its own heading.
  await expect(
    card.getByRole("heading", { name: "How this compares with similar mentors" }),
  ).toBeVisible();
});

test("the effects shown come to the price shown", async ({ page }) => {
  await requireApi({ comparables: true });

  await registerMentor(page);
  const card = await readyCard(page);

  const baseline = Number(
    ((await card.getByText(/A typical mentor's price is around/).textContent()) ?? "")
      .replace(/,/g, "")
      .match(/(\d+)/)?.[1],
  );
  const effects = await shownEffects(page);
  const total = effects.reduce(
    (running, effect) => running * (1 + effect / 100),
    baseline,
  );

  const stated = moneyIn((await card.getByText(/That comes to/).textContent()) ?? "");

  // One whole percent, which is the rounding every effect is shown at.
  expect(Math.abs(total - stated)).toBeLessThanOrEqual(Math.max(1, stated * 0.01));
});

test("the numbers behind the card open as a real table", async ({ page }) => {
  await requireApi({ comparables: true });

  await registerMentor(page);
  const card = await readyCard(page);
  const table = card.getByRole("group", {
    name: "From a typical mentor's price to yours, in AUD",
  });

  await expect(table).not.toBeVisible();
  await card.getByText("View the numbers").click();

  await expect(table).toBeVisible();
  await expect(
    table.getByRole("columnheader", { name: "Running total" }),
  ).toBeVisible();
  // By cell and exact: the caption says "the suggested price is reached",
  // so a loose text match for the row label finds the caption as well.
  await expect(
    table.getByRole("cell", { name: "A typical mentor's price", exact: true }),
  ).toBeVisible();
  await expect(
    table.getByRole("cell", { name: "Our suggestion", exact: true }),
  ).toBeVisible();
});

test("the link beside the price moves focus to the heading", async ({ page }) => {
  await requireApi({ comparables: true });

  await registerMentor(page);
  const link = page.getByRole("link", { name: "How is this calculated?" });
  await link.focus();
  await link.press("Enter");

  await expect(page.getByRole("heading", { name: CARD })).toBeFocused();
});

test("a suggestion above the middle is explained as advice, not as a fault", async ({
  page,
}) => {
  await requireApi({ comparables: true });

  // Stubbed: whether a freshly registered mentor lands above the band depends
  // on the field they happened to choose, and this is about what the page
  // does with that answer rather than about how often it happens.
  await page.route("**/recommendations/*/explanation", async (route) => {
    const answer = await route.fetch();
    const body = await answer.json();
    body.comparison.position = "above";
    body.comparison.percentile = 88;
    body.comparison.explains_gap =
      "Your suggestion is higher than most similar mentors, mainly because of your group size and the skills you cover.";
    await route.fulfill({ response: answer, json: body });
  });

  await registerMentor(page);
  const card = page.getByRole("region", { name: CARD });

  await expect(card.getByText("Above the middle")).toBeVisible();
  await expect(
    card.getByText("Higher than about 88 out of 100 of the similar mentors"),
  ).toBeVisible();
  await expect(card.getByText("mainly because of your group size")).toBeVisible();
});

test("the card failing leaves the price and the three answers working", async ({
  page,
}) => {
  await requireApi({ comparables: true });

  await page.route("**/recommendations/*/explanation", (route) =>
    route.fulfill({ status: 500, json: { detail: "no", errors: [] } }),
  );

  await registerMentor(page);
  const card = page.getByRole("region", { name: CARD });

  await expect(card.getByText("We could not put together the reasons")).toBeVisible();
  await expect(card.getByRole("button", { name: "Try again" })).toBeVisible();

  // The price screen is untouched: the suggestion, and all three answers.
  await expect(
    page.getByText("Suggested session price", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Change", exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Decline", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: /^Accept \$/ }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
});

test("the card fits a phone", async ({ page }) => {
  await requireApi({ comparables: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await registerMentor(page);
  await expect(page.getByRole("region", { name: CARD })).toBeVisible();

  expect(await hasHorizontalScroll(page)).toBe(false);

  await page.setViewportSize({ width: 320, height: 844 });
  await expect(page.getByRole("region", { name: CARD })).toBeVisible();
  expect(await hasHorizontalScroll(page)).toBe(false);
});

test("the card opens with a typical price and where this one sits against it", async ({
  page,
}) => {
  await requireApi({ comparables: true });

  await registerMentor(page);
  const card = await readyCard(page);

  // Not moneyIn: this line writes the amount as "386 AUD" rather than with a
  // currency symbol, which is how every price in a sentence is written here.
  const typical = Number(
    ((await card.getByText(/A typical mentor's price is around/).textContent()) ?? "")
      .replace(/,/g, "")
      .match(/(\d+)/)?.[1],
  );
  const summary = (await card.getByText(/Here is what moves it:/).textContent()) ?? "";

  expect(summary).toMatch(/We suggest/);
  expect(summary).toMatch(/percent (above|below) that typical price|about the same as/);
  expect(typical).toBeGreaterThan(0);
});

test("a group of more than one is never described against a one to one", async ({
  page,
}) => {
  await requireApi({ comparables: true });

  // Registered with a group, so any sentence naming a one to one session
  // would be describing a service this mentor does not offer.
  await registerMentor(page, { maxMentees: 3 });
  const card = await readyCard(page);

  const said = (await card.textContent()) ?? "";

  expect(said.toLowerCase()).not.toContain("one to one");
  expect(said).toMatch(/typical group of \d+ among similar mentors/);
});

test("a new mentor is shown no demand card on their own page", async ({ page }) => {
  await requireApi({ comparables: true });

  // Nothing has been measured about them, so there is nothing to compare.
  // An empty card reading zero per cent would be a claim nobody observed.
  await registerMentor(page);
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: /^Hello, / })).toBeVisible();

  await expect(page.getByRole("region", { name: "Demand for your time" })).toHaveCount(
    0,
  );
});
