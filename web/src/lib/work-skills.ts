/**
 * The "skills at work" labels, one list per field.
 *
 * Three of the four skill headings mean the same thing to every mentor:
 * getting hired, growing your career, and business and balance. The fourth
 * does not. Leadership to a barrister and leadership to a ward registrar are
 * different conversations, and a list written for neither of them reads as
 * filler on both.
 *
 * So this file holds twelve lists of ten, one per field, and the form swaps
 * the labels when the mentor picks a field.
 *
 * ## Why slots, and why the price cannot move
 *
 * The pricing API is given a count and nothing else: every ticked skill is
 * worth the same on one breadth-of-offering column, capped at the thirty the
 * form offers. There is no evidence anywhere in the system for one skill
 * being worth more than another, and the API never sees a label.
 *
 * That is what makes this safe, and it is also what this file has to protect.
 * Each of the ten positions is a slot, work_1 to work_10, and a slot is
 * permanently bound to one of the skill ids the API published before any of
 * this existed. The label is what a mentor reads; the slot's skill id is what
 * gets sent, stored and priced. A mentor in law who ticks four skills at work
 * sends the same four ids as a mentor in engineering who ticks the same four
 * positions, so the two of them get the same skills adjustment. Changing a
 * label here cannot reach a price, and a test holds it to that.
 *
 * ## Why the field ids are written out here
 *
 * The field list comes from /meta/options, and the twelve ids below are a
 * copy of it. A copy, so that TypeScript can check that every field has a
 * list and that no list is missing a slot. It is the same arrangement
 * SKILL_GROUPS already uses for the thirty skills, and it drifts the same
 * way, so it is checked the same way: a unit test against a fixture, and an
 * end to end test against the running API, which is what catches the fixture.
 */

/** One of the ten positions under the "skills at work" heading. */
export type WorkSlotId =
  | "work_1"
  | "work_2"
  | "work_3"
  | "work_4"
  | "work_5"
  | "work_6"
  | "work_7"
  | "work_8"
  | "work_9"
  | "work_10";

/** The field a mentor picks, as /meta/options names it. */
export type FieldId =
  | "executive_leadership"
  | "management_consulting"
  | "law"
  | "investment_finance"
  | "banking_accounting"
  | "medicine_health"
  | "engineering"
  | "technology_software"
  | "marketing_communications"
  | "creative_arts_design"
  | "education_teaching"
  | "community_social_work";

/**
 * Which skill id each slot sends, in the order the slots are drawn.
 *
 * The one declaration in this file that touches the API contract. These are
 * the ten ids the "skills at work" group has always held, in the order it
 * always held them, and a test checks that against SKILL_GROUPS. Nothing may
 * be reordered or substituted here: a mentor's stored list is read back
 * through this map, so moving a slot would silently relabel a profile that is
 * already published.
 */
export const WORK_SLOT_SKILL_IDS: Readonly<Record<WorkSlotId, string>> = {
  work_1: "leadership",
  work_2: "public_speaking",
  work_3: "time_management",
  work_4: "project_management",
  work_5: "workplace_communication",
  work_6: "conflict_resolution",
  work_7: "mentoring_skills",
  work_8: "presentation_skills",
  work_9: "data_analysis",
  work_10: "technical_skills_coaching",
};

/** The slots in drawing order. */
export const WORK_SLOT_IDS = Object.keys(WORK_SLOT_SKILL_IDS) as WorkSlotId[];

/** How many skills the "skills at work" heading holds. Ten, and it stays ten. */
export const WORK_SLOT_COUNT = WORK_SLOT_IDS.length;

/** The skill ids that sit under "skills at work", whatever the field. */
export const WORK_SKILL_IDS: string[] = WORK_SLOT_IDS.map(
  (slot) => WORK_SLOT_SKILL_IDS[slot],
);

/**
 * What each slot is called, per field.
 *
 * Written to be recognised rather than to be exhaustive: ten things a mentor
 * in that field would actually be asked about, short enough to read as a
 * pill, and none of them a restatement of the three constant headings.
 */
export const FIELD_WORK_SKILLS: Readonly<
  Record<FieldId, Readonly<Record<WorkSlotId, string>>>
> = {
  executive_leadership: {
    work_1: "Executive presence",
    work_2: "Board reporting",
    work_3: "Strategic planning",
    work_4: "Organisational change",
    work_5: "Stakeholder management",
    work_6: "Crisis leadership",
    work_7: "Succession planning",
    work_8: "Culture building",
    work_9: "Delegating effectively",
    work_10: "Decision making",
  },
  management_consulting: {
    work_1: "Client engagement",
    work_2: "Problem structuring",
    work_3: "Hypothesis testing",
    work_4: "Project scoping",
    work_5: "Stakeholder interviews",
    work_6: "Workshop facilitation",
    work_7: "Slide storytelling",
    work_8: "Proposal writing",
    work_9: "Cost benefit analysis",
    work_10: "Change management",
  },
  law: {
    work_1: "Legal research",
    work_2: "Courtroom advocacy",
    work_3: "Matter management",
    work_4: "Contract drafting",
    work_5: "Client advising",
    work_6: "Negotiation tactics",
    work_7: "Case analysis",
    work_8: "Legal writing",
    work_9: "Due diligence",
    work_10: "Compliance review",
  },
  investment_finance: {
    work_1: "Investment research",
    work_2: "Pitch book preparation",
    work_3: "Deal execution",
    work_4: "Portfolio construction",
    work_5: "Client reporting",
    work_6: "Risk assessment",
    work_7: "Market analysis",
    work_8: "Valuation methods",
    work_9: "Financial modelling",
    work_10: "Regulatory awareness",
  },
  banking_accounting: {
    work_1: "Financial reporting",
    work_2: "Client bookkeeping",
    work_3: "Management accounts",
    work_4: "Budgeting and forecasting",
    work_5: "Audit preparation",
    work_6: "Internal controls",
    work_7: "Credit assessment",
    work_8: "Reconciliation practice",
    work_9: "Tax compliance",
    work_10: "Accounting software",
  },
  medicine_health: {
    work_1: "Clinical reasoning",
    work_2: "Case presentations",
    work_3: "Ward handover",
    work_4: "Clinical audit",
    work_5: "Patient communication",
    work_6: "Infection control",
    work_7: "Clinical supervision",
    work_8: "Evidence appraisal",
    work_9: "Research methods",
    work_10: "Clinical documentation",
  },
  engineering: {
    work_1: "Site supervision",
    work_2: "Technical drawings",
    work_3: "Project estimation",
    work_4: "Design calculations",
    work_5: "Safety compliance",
    work_6: "Failure investigation",
    work_7: "Quality assurance",
    work_8: "Specification writing",
    work_9: "Materials selection",
    work_10: "Commissioning and testing",
  },
  technology_software: {
    work_1: "System design",
    work_2: "Technical documentation",
    work_3: "Agile delivery",
    work_4: "Code review",
    work_5: "Incident response",
    work_6: "Debugging practice",
    work_7: "Test automation",
    work_8: "Cloud deployment",
    work_9: "Data modelling",
    work_10: "Security basics",
  },
  marketing_communications: {
    work_1: "Brand positioning",
    work_2: "Media relations",
    work_3: "Campaign planning",
    work_4: "Content strategy",
    work_5: "Crisis communications",
    work_6: "Audience research",
    work_7: "Copywriting craft",
    work_8: "Social media strategy",
    work_9: "Marketing analytics",
    work_10: "Email marketing",
  },
  creative_arts_design: {
    work_1: "Art direction",
    work_2: "Client pitching",
    work_3: "Commission management",
    work_4: "Creative briefs",
    work_5: "Studio collaboration",
    work_6: "Design critique",
    work_7: "Visual storytelling",
    work_8: "Typography craft",
    work_9: "Pricing creative work",
    work_10: "Prototyping and sketching",
  },
  education_teaching: {
    work_1: "Classroom management",
    work_2: "Teaching observations",
    work_3: "Curriculum mapping",
    work_4: "Lesson planning",
    work_5: "Parent communication",
    work_6: "Behaviour support",
    work_7: "Differentiated teaching",
    work_8: "Marking and feedback",
    work_9: "Assessment design",
    work_10: "Digital teaching tools",
  },
  community_social_work: {
    work_1: "Advocacy and referral",
    work_2: "Community outreach",
    work_3: "Case management",
    work_4: "Funding bids",
    work_5: "Client assessment",
    work_6: "Crisis intervention",
    work_7: "Reflective supervision",
    work_8: "Group facilitation",
    work_9: "Record keeping",
    work_10: "Safeguarding practice",
  },
};

/** The twelve fields this file has a list for. */
export const FIELD_IDS_WITH_WORK_SKILLS = Object.keys(FIELD_WORK_SKILLS) as FieldId[];

/** True when this file has a list for the given field. */
export function hasWorkSkills(field: string | null | undefined): field is FieldId {
  return typeof field === "string" && field in FIELD_WORK_SKILLS;
}

/**
 * What to call each skill at work, for one field.
 *
 * Keyed by skill id, so a caller holding a stored list of ids can read the
 * right label straight off it. Empty for a mentor who has not picked a field
 * yet, and the caller falls back to the label the API sent: an empty form has
 * nothing to be specific about, and inventing a thirteenth generic list would
 * mean maintaining one.
 */
export function workSkillLabels(
  field: string | null | undefined,
): ReadonlyMap<string, string> {
  const labels = new Map<string, string>();
  if (!hasWorkSkills(field)) {
    return labels;
  }
  const forField = FIELD_WORK_SKILLS[field];
  for (const slot of WORK_SLOT_IDS) {
    labels.set(WORK_SLOT_SKILL_IDS[slot], forField[slot]);
  }
  return labels;
}

/**
 * The ticked skills, with the skills at work dropped.
 *
 * What a field change leaves behind. The three constant headings survive it
 * because they still say what they said; the ten under "skills at work" do
 * not, so a tick that was made against "Ward handover" is not carried over to
 * "Site supervision" as though the mentor had chosen it.
 */
export function withoutWorkSkills(skills: readonly string[]): string[] {
  return skills.filter((skill) => !WORK_SKILL_IDS.includes(skill));
}

/** How many of the ticked skills sit under "skills at work". */
export function countWorkSkills(skills: readonly string[]): number {
  return skills.filter((skill) => WORK_SKILL_IDS.includes(skill)).length;
}
