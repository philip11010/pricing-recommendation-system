/**
 * The twelve "skills at work" lists, and the one thing they may not do.
 *
 * These labels are the only part of the skill list that changes with the
 * field, so they are the only part that can change what a mentor reads. What
 * they may not change is what a mentor is charged. The API is given a count
 * and the ids behind that count are the same ten in every field, so the last
 * group of tests here is the important one: same ticks, different fields,
 * identical payload.
 *
 * PUBLISHED_FIELDS below is the field list /meta/options sends. It is a
 * fixture, checked in both directions, and the end to end suite checks the
 * fixture itself against the running API.
 */

import { describe, expect, it } from "vitest";

import { SKILL_GROUPS } from "@/lib/copy";
import {
  FIELD_IDS_WITH_WORK_SKILLS,
  FIELD_WORK_SKILLS,
  WORK_SKILL_IDS,
  WORK_SLOT_COUNT,
  WORK_SLOT_IDS,
  WORK_SLOT_SKILL_IDS,
  countWorkSkills,
  hasWorkSkills,
  withoutWorkSkills,
  workSkillLabels,
} from "@/lib/work-skills";

/** The twelve field ids /meta/options publishes. */
const PUBLISHED_FIELDS = [
  "executive_leadership",
  "management_consulting",
  "law",
  "investment_finance",
  "banking_accounting",
  "medicine_health",
  "engineering",
  "technology_software",
  "marketing_communications",
  "creative_arts_design",
  "education_teaching",
  "community_social_work",
];

/** The labels under the three headings that are the same in every field. */
const CONSTANT_LABELS = [
  "CV review",
  "Cover letter writing",
  "Interview preparation",
  "LinkedIn profile review",
  "Portfolio review",
  "Graduate applications",
  "Job search strategy",
  "Career planning",
  "Career change",
  "Salary negotiation",
  "Promotion planning",
  "Performance reviews",
  "Personal branding",
  "Further studies guidance",
  "Networking",
  "Entrepreneurship",
  "Work-life balance",
  "Goal setting",
  "Remote work",
  "Professional ethics",
];

const workGroup = SKILL_GROUPS.find((group) => group.fieldSpecific);

describe("the slots the field-specific heading is made of", () => {
  it("is the heading the groups mark as following the field", () => {
    expect(SKILL_GROUPS.filter((group) => group.fieldSpecific)).toHaveLength(1);
    expect(workGroup?.name).toBe("Skills at work");
  });

  it("holds the same skill ids, in the same order, as that heading", () => {
    expect(WORK_SKILL_IDS).toEqual(workGroup?.skillIds);
  });

  it("has one slot per skill, and ten of them", () => {
    expect(WORK_SLOT_COUNT).toBe(10);
    expect(WORK_SLOT_IDS).toHaveLength(WORK_SKILL_IDS.length);
    expect(WORK_SLOT_IDS).toEqual([
      "work_1",
      "work_2",
      "work_3",
      "work_4",
      "work_5",
      "work_6",
      "work_7",
      "work_8",
      "work_9",
      "work_10",
    ]);
  });

  it("binds each slot to a different skill id", () => {
    const ids = WORK_SLOT_IDS.map((slot) => WORK_SLOT_SKILL_IDS[slot]);

    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe("the field lists", () => {
  it("covers every field the API publishes", () => {
    const missing = PUBLISHED_FIELDS.filter(
      (id) => !FIELD_IDS_WITH_WORK_SKILLS.includes(id as never),
    );

    expect(missing).toEqual([]);
  });

  it("names no field the API does not publish", () => {
    const unknown = FIELD_IDS_WITH_WORK_SKILLS.filter(
      (id) => !PUBLISHED_FIELDS.includes(id),
    );

    expect(unknown).toEqual([]);
    expect(FIELD_IDS_WITH_WORK_SKILLS).toHaveLength(12);
  });

  it.each(FIELD_IDS_WITH_WORK_SKILLS)("gives %s a label for every slot", (field) => {
    const labels = FIELD_WORK_SKILLS[field];

    expect(Object.keys(labels)).toHaveLength(WORK_SLOT_COUNT);
    for (const slot of WORK_SLOT_IDS) {
      expect(labels[slot], `${field} ${slot}`).toBeTypeOf("string");
      expect(labels[slot].trim(), `${field} ${slot}`).not.toBe("");
    }
  });

  it.each(FIELD_IDS_WITH_WORK_SKILLS)("repeats no label within %s", (field) => {
    const labels = WORK_SLOT_IDS.map((slot) => FIELD_WORK_SKILLS[field][slot]);

    expect(new Set(labels).size).toBe(labels.length);
  });

  it.each(FIELD_IDS_WITH_WORK_SKILLS)(
    "keeps %s clear of the three constant headings",
    (field) => {
      const clash = WORK_SLOT_IDS.map((slot) => FIELD_WORK_SKILLS[field][slot]).filter(
        (label) =>
          CONSTANT_LABELS.some(
            (constant) => constant.toLowerCase() === label.toLowerCase(),
          ),
      );

      expect(clash).toEqual([]);
    },
  );

  it.each(FIELD_IDS_WITH_WORK_SKILLS)("keeps %s short enough to read", (field) => {
    for (const slot of WORK_SLOT_IDS) {
      const words = FIELD_WORK_SKILLS[field][slot].trim().split(/\s+/);

      expect(words.length, `${field} ${slot}`).toBeGreaterThanOrEqual(2);
      expect(words.length, `${field} ${slot}`).toBeLessThanOrEqual(4);
    }
  });

  it("gives two different fields two different lists", () => {
    const law = WORK_SLOT_IDS.map((slot) => FIELD_WORK_SKILLS.law[slot]);
    const engineering = WORK_SLOT_IDS.map(
      (slot) => FIELD_WORK_SKILLS.engineering[slot],
    );

    expect(law).not.toEqual(engineering);
  });
});

describe("reading the labels for one field", () => {
  it("keys them by the skill id that gets sent", () => {
    const labels = workSkillLabels("law");

    expect(labels.size).toBe(WORK_SLOT_COUNT);
    expect(labels.get("leadership")).toBe("Legal research");
    expect(labels.get("technical_skills_coaching")).toBe("Compliance review");
  });

  it("swaps every label when the field changes", () => {
    const before = workSkillLabels("medicine_health");
    const after = workSkillLabels("technology_software");

    for (const id of WORK_SKILL_IDS) {
      expect(before.get(id)).not.toBe(after.get(id));
    }
  });

  it("has nothing to say before a field is picked", () => {
    expect(workSkillLabels("").size).toBe(0);
    expect(workSkillLabels(null).size).toBe(0);
    expect(workSkillLabels(undefined).size).toBe(0);
    expect(hasWorkSkills("")).toBe(false);
  });

  it("has nothing to say about a field it does not know", () => {
    expect(workSkillLabels("underwater_basket_weaving").size).toBe(0);
    expect(hasWorkSkills("underwater_basket_weaving")).toBe(false);
  });
});

describe("what a field change leaves ticked", () => {
  const ticked = [
    "cv_review",
    "leadership",
    "career_planning",
    "data_analysis",
    "work_life_balance",
  ];

  it("drops the skills at work and nothing else", () => {
    expect(withoutWorkSkills(ticked)).toEqual([
      "cv_review",
      "career_planning",
      "work_life_balance",
    ]);
  });

  it("counts how many were dropped, so the note is only shown when some were", () => {
    expect(countWorkSkills(ticked)).toBe(2);
    expect(countWorkSkills(["cv_review", "networking"])).toBe(0);
    expect(countWorkSkills([])).toBe(0);
  });

  it("leaves a list with no skills at work exactly as it was", () => {
    const constant = ["cv_review", "networking", "goal_setting"];

    expect(withoutWorkSkills(constant)).toEqual(constant);
  });
});

/**
 * The promise the whole change rests on.
 *
 * Two mentors in different fields who tick the same positions send the same
 * ids, so the pricing API sees the same skill count and applies the same
 * adjustment. The labels they read while ticking are completely different.
 */
describe("two mentors, two fields, the same ticks", () => {
  /** The ids a mentor sends after ticking some slots in some field. */
  function sent(field: string, slots: readonly (typeof WORK_SLOT_IDS)[number][]) {
    const labels = workSkillLabels(field);
    const ids = slots.map((slot) => WORK_SLOT_SKILL_IDS[slot]);
    // Every one of them has a label in that field, so the pills were really
    // drawn and really tickable.
    for (const id of ids) {
      expect(labels.get(id)).toBeTypeOf("string");
    }
    return ids;
  }

  const slots = ["work_1", "work_3", "work_7", "work_10"] as const;

  it("sends identical skill ids, so the skills adjustment is identical", () => {
    const fromLaw = sent("law", slots);
    const fromEngineering = sent("engineering", slots);

    expect(fromLaw).toEqual(fromEngineering);
    expect(fromLaw).toHaveLength(4);
  });

  it("shows them completely different labels while they tick", () => {
    const law = slots.map((slot) => FIELD_WORK_SKILLS.law[slot]);
    const engineering = slots.map((slot) => FIELD_WORK_SKILLS.engineering[slot]);

    expect(new Set([...law, ...engineering]).size).toBe(law.length * 2);
  });

  it("counts the same in every field, for every number of ticks", () => {
    for (const field of FIELD_IDS_WITH_WORK_SKILLS) {
      for (let count = 0; count <= WORK_SLOT_COUNT; count += 1) {
        const ids = WORK_SLOT_IDS.slice(0, count).map(
          (slot) => WORK_SLOT_SKILL_IDS[slot],
        );

        expect(countWorkSkills(ids), `${field} at ${count}`).toBe(count);
        expect(ids, `${field} at ${count}`).toEqual(WORK_SKILL_IDS.slice(0, count));
      }
    }
  });
});
