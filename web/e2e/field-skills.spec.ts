import { expect, test } from "@playwright/test";

import {
  FIELD_IDS_WITH_WORK_SKILLS,
  FIELD_WORK_SKILLS,
  WORK_SLOT_IDS,
} from "../src/lib/work-skills";
import { API_URL, registerMentor, requireApi } from "./helpers";

/**
 * The skills at work are named for the field, in the real form.
 *
 * The unit tests check the lists and the rules. What they cannot check is the
 * form as a mentor meets it: a select that redraws ten pills, ticks that go
 * when the field changes, and a price panel beside it that has to keep
 * working through both. The panel reaches its figure through a debounce, a
 * request that can be overtaken and three states, so it is read here against
 * the running API rather than against a mock.
 *
 * The first test is the drift check for the field list. lib/work-skills.ts
 * writes the twelve field ids out so TypeScript can hold every field to
 * having a list; this is what catches that copy going stale against the API,
 * the same way the skills copy is caught.
 */
test("every field the API publishes has a skills at work list", async () => {
  await requireApi();

  const response = await fetch(`${API_URL}/meta/options`);
  const options = (await response.json()) as { fields: { id: string }[] };
  const published = options.fields.map((field) => field.id);

  expect([...published].sort()).toEqual([...FIELD_IDS_WITH_WORK_SKILLS].sort());
  for (const field of FIELD_IDS_WITH_WORK_SKILLS) {
    expect(Object.keys(FIELD_WORK_SKILLS[field]), field).toEqual(WORK_SLOT_IDS);
  }
});

test("changing the field swaps the skills at work, and the preview keeps up", async ({
  page,
}) => {
  await requireApi();

  const law = Object.values(FIELD_WORK_SKILLS.law);
  const engineering = Object.values(FIELD_WORK_SKILLS.engineering);

  await page.goto("/register");
  await expect(
    page.getByRole("heading", { name: "Create your mentor profile" }),
  ).toBeVisible();

  const panel = page.getByRole("complementary", { name: "Live price preview" });
  const field = page.getByLabel("Your field");

  /** The figure in the panel, once it has settled on one. */
  async function sessionPrice(): Promise<number> {
    await expect(panel.getByText("Working out your price")).toHaveCount(0);
    const line = panel.getByText(/session(?: of \d+)?: \$/);
    const text = (await line.textContent()) ?? "";
    const found = text.match(/\$([\d,]+)/);
    expect(found, `no price in "${text}"`).not.toBeNull();
    return Number((found as RegExpMatchArray)[1].replace(/,/g, ""));
  }

  function priced() {
    return page.waitForResponse(
      (response) => response.url().includes("/preview") && response.status() === 200,
    );
  }

  // Before a field is picked, the pills carry the labels the API sent.
  await expect(page.getByRole("checkbox", { name: "Leadership" })).toHaveCount(1);
  await expect(page.getByRole("checkbox")).toHaveCount(30);

  // Law, and all ten swap.
  let answered = priced();
  await field.selectOption("law");
  await answered;
  for (const label of law) {
    await expect(page.getByRole("checkbox", { name: label, exact: true })).toHaveCount(
      1,
    );
  }
  await expect(page.getByRole("checkbox", { name: "Leadership" })).toHaveCount(0);
  await expect(page.getByRole("checkbox")).toHaveCount(30);
  expect(await sessionPrice()).toBeGreaterThan(0);

  // One skill from a constant heading and two from the field's own.
  answered = priced();
  await page.getByRole("checkbox", { name: "CV review", exact: true }).check();
  await page.getByRole("checkbox", { name: law[0], exact: true }).check();
  await page.getByRole("checkbox", { name: law[6], exact: true }).check();
  await answered;
  const withLawSkills = await sessionPrice();
  expect(withLawSkills).toBeGreaterThan(0);

  // Engineering. The labels swap again, the skills at work are cleared with a
  // note, the constant heading keeps its tick, and a new price arrives.
  answered = priced();
  await field.selectOption("engineering");
  await answered;

  await expect(
    page.getByText("Skills at work are different in each field"),
  ).toBeVisible();
  for (const label of engineering) {
    const pill = page.getByRole("checkbox", { name: label, exact: true });
    await expect(pill).toHaveCount(1);
    await expect(pill).not.toBeChecked();
  }
  for (const label of law) {
    await expect(page.getByRole("checkbox", { name: label, exact: true })).toHaveCount(
      0,
    );
  }
  await expect(
    page.getByRole("checkbox", { name: "CV review", exact: true }),
  ).toBeChecked();
  await expect(page.getByRole("checkbox")).toHaveCount(30);
  expect(await sessionPrice()).toBeGreaterThan(0);

  // And the panel still answers a tick, under the new labels.
  answered = priced();
  await page.getByRole("checkbox", { name: engineering[0], exact: true }).check();
  await answered;
  expect(await sessionPrice()).toBeGreaterThan(0);
});

/**
 * Same ticks, different fields, same price.
 *
 * The claim the whole change rests on, read off the real API rather than
 * argued from the constants: two profiles alike in everything but the field's
 * labels send the same skill ids, so the skills adjustment behind their
 * prices is the same one. The field itself moves the price, so this compares
 * the two /preview requests rather than the two figures.
 */
test("the same number of skills at work prices the same in two fields", async ({
  page,
}) => {
  await requireApi();

  /** What /preview was asked, after ticking three slots in one field. */
  async function askedFor(fieldId: "law" | "engineering"): Promise<string[]> {
    const labels = Object.values(FIELD_WORK_SKILLS[fieldId]);
    await page.goto("/register");
    await expect(page.getByLabel("Your field")).toBeVisible();

    await page.getByLabel("Your field").selectOption(fieldId);
    for (const index of [0, 3, 9]) {
      await page.getByRole("checkbox", { name: labels[index], exact: true }).check();
    }

    const response = await page.waitForResponse(
      (answer) =>
        answer.url().includes("/preview") &&
        answer.status() === 200 &&
        ((answer.request().postDataJSON() as { skills: string[] }).skills ?? [])
          .length === 3,
    );
    const sent = response.request().postDataJSON() as { skills: string[] };
    return [...sent.skills].sort();
  }

  const fromLaw = await askedFor("law");
  const fromEngineering = await askedFor("engineering");

  expect(fromLaw).toHaveLength(3);
  expect(fromLaw).toEqual(fromEngineering);
});

/**
 * A profile names the skills the way its own mentor was asked for them.
 *
 * The one place in the product that shows a skill's label rather than
 * counting it. The API sends the label as well, and for the twenty constant
 * skills that is what is shown; for the ten under "skills at work" the chip
 * reads the mentor's own field instead, so the words on their profile are the
 * words they ticked.
 */
test("a profile reads the skills at work under that mentor's field", async ({
  page,
}) => {
  await requireApi();

  const work = FIELD_WORK_SKILLS.technology_software;
  const name = "Skills Label Check";
  await registerMentor(page, {
    name,
    // One from a constant heading, two from the field's own. The helper picks
    // technology_software, which is the field these two labels belong to.
    skills: ["CV review", work.work_1, work.work_3],
  });

  // The profile is reached the way a reader reaches it, through the directory.
  const directory = await fetch(`${API_URL}/mentors?limit=50`);
  const listed = (await directory.json()) as {
    items: { id: number; display_name: string }[];
  };
  const mentor = listed.items.find((item) => item.display_name === name);
  expect(mentor, `no mentor called ${name} in the directory`).toBeTruthy();

  await page.goto(`/mentors/${mentor?.id}`);
  await expect(page.getByRole("heading", { name: "Skills covered" })).toBeVisible();

  const skills = page.getByRole("heading", { name: "Skills covered" }).locator("..");
  await expect(skills.getByText("CV review", { exact: true })).toBeVisible();
  await expect(skills.getByText(work.work_1, { exact: true })).toBeVisible();
  await expect(skills.getByText(work.work_3, { exact: true })).toBeVisible();
  // Never the API's own generic label for a slot this field has renamed.
  await expect(skills.getByText("Leadership", { exact: true })).toHaveCount(0);
  await expect(skills.getByText("Time management", { exact: true })).toHaveCount(0);
});
