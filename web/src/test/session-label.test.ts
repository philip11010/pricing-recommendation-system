/**
 * What a session is called, which the form has to decide while the mentor is
 * still moving the stepper.
 *
 * The API publishes this as a rule rather than as a list to choose from, so
 * the test does both: that the fallback matches the rule the API states
 * today, and that the rule wins when it has been loaded. The second half is
 * the one that matters, because the fallback is the thing that will go stale.
 */

import { describe, expect, it } from "vitest";

import type { SessionLabelRule } from "@/lib/api-types";
import {
  GROUP,
  GROUP_LABEL,
  ONE_TO_ONE,
  ONE_TO_ONE_LABEL,
  isOneToOne,
  labelFromId,
  sessionLabel,
  sessionLabelId,
} from "@/lib/session-label";

/** The rule exactly as /meta/options publishes it. */
const RULE: SessionLabelRule = {
  one_to_one: { id: "one_to_one", label: "One to one", max_mentees: 1 },
  group: { id: "group", label: "Group", max_mentees_from: 2 },
};

describe("sessionLabelId", () => {
  it("calls a session of one a one to one", () => {
    expect(sessionLabelId(1)).toBe(ONE_TO_ONE);
    expect(sessionLabelId(1, RULE)).toBe("one_to_one");
  });

  it("calls two or more a group", () => {
    expect(sessionLabelId(2)).toBe(GROUP);
    expect(sessionLabelId(4, RULE)).toBe("group");
    expect(sessionLabelId(8, RULE)).toBe("group");
  });
});

describe("sessionLabel", () => {
  it("matches the labels the API publishes", () => {
    expect(sessionLabel(1, RULE)).toBe("One to one");
    expect(sessionLabel(2, RULE)).toBe("Group");
  });

  it("falls back to the same answer before the options have loaded", () => {
    expect(sessionLabel(1)).toBe(ONE_TO_ONE_LABEL);
    expect(sessionLabel(3)).toBe(GROUP_LABEL);
    expect(sessionLabel(1, null)).toBe(ONE_TO_ONE_LABEL);
  });

  it("follows the API rather than its own constants when the two differ", () => {
    // If the API ever moved the boundary, the form has to move with it. This
    // is the whole reason the rule is read rather than hard coded.
    const moved: SessionLabelRule = {
      one_to_one: { id: "one_to_one", label: "Just the two of us", max_mentees: 2 },
      group: { id: "group", label: "A group", max_mentees_from: 3 },
    };
    expect(sessionLabel(2, moved)).toBe("Just the two of us");
    expect(sessionLabel(3, moved)).toBe("A group");
  });
});

describe("isOneToOne", () => {
  it("is what decides whether one figure or two are shown", () => {
    expect(isOneToOne(1)).toBe(true);
    expect(isOneToOne(2)).toBe(false);
    expect(isOneToOne(8, RULE)).toBe(false);
  });
});

describe("labelFromId", () => {
  it("turns the label stored on a service back into words", () => {
    expect(labelFromId("one_to_one", RULE)).toBe("One to one");
    expect(labelFromId("group", RULE)).toBe("Group");
  });

  it("reads an unknown id as the safer of the two", () => {
    expect(labelFromId("something_else", RULE)).toBe("One to one");
  });
});
