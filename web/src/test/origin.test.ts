/**
 * Where a reader came from, carried in the address.
 *
 * Two different problems with the same shape. A mentor who opens the
 * comparison from their price screen has to be able to get back to that
 * price, not to a freshly calculated one, and a reader who filtered the
 * directory has to be able to get back to the filtered list. Both are solved
 * by putting the origin in the address and reading it back.
 *
 * The half of this worth testing hardest is the reading back. The address is
 * typed by anybody, so every one of these functions has to answer with a real
 * link whatever it is handed, and the fallback has to be somewhere a signed
 * in mentor can always go.
 */

import { describe, expect, it } from "vitest";

import {
  DASHBOARD_BACK_LABEL,
  RECOMMENDATION_BACK_LABEL,
  backFromOrigin,
  directoryHref,
  mentorHref,
  similarHref,
} from "@/lib/origin";

describe("similarHref", () => {
  it("carries the price screen it was opened from", () => {
    expect(similarHref(12, { from: "recommendation", recommendationId: 34 })).toBe(
      "/similar/12?from=recommendation&rec=34",
    );
  });

  it("carries the dashboard as a word, with no id to carry", () => {
    expect(similarHref(12, { from: "dashboard" })).toBe("/similar/12?from=dashboard");
  });

  it("leaves the origin off when there is none", () => {
    expect(similarHref(12)).toBe("/similar/12");
    expect(similarHref(12, null)).toBe("/similar/12");
  });

  it("refuses to claim a price screen it cannot name", () => {
    expect(similarHref(12, { from: "recommendation" })).toBe("/similar/12");
    expect(similarHref(12, { from: "recommendation", recommendationId: 0 })).toBe(
      "/similar/12",
    );
    expect(similarHref(12, { from: "recommendation", recommendationId: -4 })).toBe(
      "/similar/12",
    );
  });
});

describe("backFromOrigin", () => {
  it("goes back to the price the mentor came from", () => {
    expect(backFromOrigin("recommendation", "34")).toEqual({
      href: "/recommendation/34",
      label: RECOMMENDATION_BACK_LABEL,
    });
  });

  it("goes back to the dashboard when that is where they came from", () => {
    expect(backFromOrigin("dashboard", null)).toEqual({
      href: "/dashboard",
      label: DASHBOARD_BACK_LABEL,
    });
  });

  it("always answers with a link, whatever the address says", () => {
    for (const [from, id] of [
      [null, null],
      [undefined, undefined],
      ["", ""],
      ["recommendation", null],
      ["recommendation", ""],
      ["recommendation", "0"],
      ["recommendation", "-4"],
      ["recommendation", "12.5"],
      ["recommendation", "abc"],
      ["recommendation", "4; drop"],
      ["somewhere-else", "34"],
    ] as const) {
      expect(backFromOrigin(from, id)).toEqual({
        href: "/dashboard",
        label: DASHBOARD_BACK_LABEL,
      });
    }
  });
});

describe("directoryHref and mentorHref", () => {
  it("keeps the chosen field in the address", () => {
    expect(directoryHref("law")).toBe("/mentors?field=law");
    expect(mentorHref(7, "law")).toBe("/mentors/7?field=law");
  });

  it("asks for the whole list when no field is chosen", () => {
    expect(directoryHref(null)).toBe("/mentors");
    expect(directoryHref("")).toBe("/mentors");
    expect(mentorHref(7)).toBe("/mentors/7");
    expect(mentorHref(7, "")).toBe("/mentors/7");
  });

  it("escapes a field rather than pasting it into the address", () => {
    expect(directoryHref("a&b=c")).toBe("/mentors?field=a%26b%3Dc");
    expect(mentorHref(7, "a b")).toBe("/mentors/7?field=a%20b");
  });
});
