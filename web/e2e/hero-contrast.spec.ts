import { expect, test, type Page } from "@playwright/test";

import { registerMentor, requireApi } from "./helpers";

/**
 * The lead paragraph on a gradient is white, at every width.
 *
 * It used to be a pale indigo tint. That tint measures comfortably against
 * the dark end of the gradient and fails against the blue end, and which end
 * a given line of the paragraph sits over depends on how wide the window is:
 * the same words passed on a phone and failed on a wide screen. Width is not
 * something a colour decision can be left to depend on, so the lead is white
 * everywhere and this test reads the colour the browser actually computed
 * rather than the class that was asked for.
 *
 * The widths are the five in web/DESIGN.md: the narrowest phone the layout
 * supports, a common phone, a tablet, the width where the two column hero
 * resolves, and a desktop.
 */
const WIDTHS = [320, 390, 768, 900, 1440];

const WHITE = "rgb(255, 255, 255)";

async function colourOf(page: Page, text: string | RegExp): Promise<string> {
  return page
    .getByText(text)
    .first()
    .evaluate((element) => getComputedStyle(element).color);
}

/** The colour the lead token resolves to, for a screen with no lead on it. */
async function leadToken(page: Page): Promise<string> {
  return page.evaluate(() => {
    const probe = document.createElement("p");
    probe.className = "text-on-gradient-lead";
    document.body.append(probe);
    const colour = getComputedStyle(probe).color;
    probe.remove();
    return colour;
  });
}

test("the landing hero lead is white at every width", async ({ page }) => {
  await page.goto("/");

  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    expect(await colourOf(page, /^Tell us about your sessions/), `${width}px`).toBe(
      WHITE,
    );
  }
});

test("the log in screen carries no tinted lead at any width", async ({ page }) => {
  await page.goto("/login");

  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    expect(await leadToken(page), `${width}px`).toBe(WHITE);
  }
});

test("the price hero lead is white at every width", async ({ page }) => {
  await requireApi();

  await registerMentor(page);

  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    expect(await colourOf(page, /^Based on your field/), `${width}px`).toBe(WHITE);
  }
});
