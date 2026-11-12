/**
 * What a session is called, which follows from how many mentees can join.
 *
 * The API publishes this as a rule rather than as a list to choose from, and
 * the rule is applied here so the form can name the session while the mentor
 * is still moving the stepper, with no request in between.
 *
 * The constants below are the rule as the API states it today. They are a
 * fallback for the moment before the options have loaded, never a second
 * source of truth: when the rule is to hand, it is the rule that is used.
 */

import type { SessionLabelRule } from "./api-types";

export const ONE_TO_ONE = "one_to_one";
export const GROUP = "group";

export const ONE_TO_ONE_LABEL = "One to one";
export const GROUP_LABEL = "Group";

/** The number of mentees at which a session stops being one to one. */
export const GROUP_FROM = 2;

/**
 * The id of the label for a session of this size.
 *
 * One mentee is one to one. Two or more is a group. A session of one is not a
 * small group: its per-mentee figures equal its session figures rather than
 * being a division of them, which is why the distinction is worth making at
 * all.
 */
export function sessionLabelId(
  maxMentees: number,
  rule?: SessionLabelRule | null,
): string {
  const groupFrom = rule?.group?.max_mentees_from ?? GROUP_FROM;
  const singleAt = rule?.one_to_one?.max_mentees ?? 1;
  if (maxMentees <= singleAt) {
    return rule?.one_to_one?.id ?? ONE_TO_ONE;
  }
  return maxMentees >= groupFrom
    ? (rule?.group?.id ?? GROUP)
    : (rule?.one_to_one?.id ?? ONE_TO_ONE);
}

/** The words for a session of this size. */
export function sessionLabel(
  maxMentees: number,
  rule?: SessionLabelRule | null,
): string {
  const id = sessionLabelId(maxMentees, rule);
  if (id === (rule?.one_to_one?.id ?? ONE_TO_ONE)) {
    return rule?.one_to_one?.label ?? ONE_TO_ONE_LABEL;
  }
  return rule?.group?.label ?? GROUP_LABEL;
}

/** True when one mentee takes the session, so one price is the whole story. */
export function isOneToOne(
  maxMentees: number,
  rule?: SessionLabelRule | null,
): boolean {
  return sessionLabelId(maxMentees, rule) === (rule?.one_to_one?.id ?? ONE_TO_ONE);
}

/** The label the API stored on a service, turned back into words. */
export function labelFromId(id: string, rule?: SessionLabelRule | null): string {
  if (id === (rule?.group?.id ?? GROUP)) {
    return rule?.group?.label ?? GROUP_LABEL;
  }
  return rule?.one_to_one?.label ?? ONE_TO_ONE_LABEL;
}

/**
 * How a session of this size is described inside a sentence.
 *
 * "groups of 2" rather than "group", because the sentences these go into
 * compare one mentor's price with other mentors' prices and the size of the
 * session is the thing that makes those prices comparable. A reader who is
 * not told the size has no way to judge whether the comparison is fair.
 */
export function groupWords(maxMentees: number, rule?: SessionLabelRule | null): string {
  return isOneToOne(maxMentees, rule)
    ? "one to one sessions"
    : `groups of ${maxMentees}`;
}

/** The same, capitalised to open a sentence. */
export function groupWordsLeading(
  maxMentees: number,
  rule?: SessionLabelRule | null,
): string {
  const words = groupWords(maxMentees, rule);
  return words.charAt(0).toUpperCase() + words.slice(1);
}
