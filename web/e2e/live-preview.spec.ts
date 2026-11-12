import { expect, test, type Locator } from "@playwright/test";

import { requireApi } from "./helpers";

/**
 * Ticking one more skill never lowers the price in the panel beside the form.
 *
 * This is the promise a mentor can check without reading anything, and it is
 * the one the model does not keep on its own: the shape it learned for
 * breadth of offering dips in places, which is an artefact of the rows it was
 * fitted on rather than a rule anybody would defend. The service reads its
 * price off a monotone envelope instead, and the backend sweep holds that to
 * its claim across every profile the form can produce.
 *
 * What this adds is the panel. A mentor does not read the service, they read
 * the figure that appears while they are still answering, and the figure gets
 * there through a debounce, a request that can be overtaken, and a component
 * with three states. So this ticks the skills one at a time in the real form,
 * waits for each answer, and reads the price off the page.
 */
test("the live preview never goes down as skills are ticked", async ({ page }) => {
  // Thirty skills, one price each, against a real API.
  test.setTimeout(240_000);

  await requireApi();

  await page.goto("/register");
  await expect(
    page.getByRole("heading", { name: "Create your mentor profile" }),
  ).toBeVisible();

  const panel = page.getByRole("complementary", { name: "Live price preview" });

  /** The whole session price, which is the figure the mentor charges. */
  async function sessionPrice(within: Locator): Promise<number> {
    const line = within.getByText(/session(?: of \d+)?: \$/);
    const text = (await line.textContent()) ?? "";
    const found = text.match(/\$([\d,]+)/);
    expect(found, `no price in "${text}"`).not.toBeNull();
    return Number((found as RegExpMatchArray)[1].replace(/,/g, ""));
  }

  const first = page.waitForResponse(
    (response) => response.url().includes("/preview") && response.status() === 200,
  );
  await page.getByLabel("Your field").selectOption("technology_software");
  await first;
  await expect(panel.getByText("Working out your price")).toHaveCount(0);

  let previous = await sessionPrice(panel);
  const skills = await page.getByRole("checkbox").all();
  expect(skills.length).toBeGreaterThan(0);

  for (const [index, skill] of skills.entries()) {
    const answered = page.waitForResponse(
      (response) => response.url().includes("/preview") && response.status() === 200,
    );
    await skill.check();
    await answered;
    await expect(panel.getByText("Working out your price")).toHaveCount(0);

    const now = await sessionPrice(panel);
    expect(now, `skill ${index + 1} of ${skills.length}`).toBeGreaterThanOrEqual(
      previous,
    );
    previous = now;
  }
});
