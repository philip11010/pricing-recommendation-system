/**
 * How an account of a price is written out, and the three ways it could lie.
 *
 * A bar could be scaled against the wrong number, so two rows of the same
 * length would mean two different things. A percentile could be printed as
 * though it were a mark out of a hundred, which is what "the 70th percentile"
 * reads as to anybody who has not met the word. And the running total could be
 * printed from the price the page was handed rather than worked out from the
 * rows it is showing, which would hide exactly the disagreement it is there to
 * expose.
 *
 * None of those would look wrong on the page. That is why they are tested
 * here, apart from the card that draws them.
 */

import { describe, expect, it } from "vitest";

import type { PriceFactor } from "@/lib/api-types";
import {
  MINIMUM_BAR_PERCENT,
  barPercent,
  describeEffect,
  formatEffect,
  largestEffect,
  percentilePhrase,
  positionWords,
  reconciledPrice,
} from "@/lib/explanation";

function factor(overrides: Partial<PriceFactor> = {}): PriceFactor {
  return {
    key: "group_size",
    label: "Your group size",
    direction: "raises",
    effect_pct: 10,
    sentence:
      "Your group of 4 is larger than the typical group of 2 among similar " +
      "mentors, and that tends to move the price per session up.",
    association: false,
    components: [],
    ...overrides,
  };
}

describe("formatEffect", () => {
  it("always carries the sign, so the bar never has to", () => {
    expect(formatEffect(12)).toBe("+12%");
    expect(formatEffect(-12)).toBe("-12%");
  });

  it("writes no effect without a sign that would imply one", () => {
    expect(formatEffect(0)).toBe("0%");
  });
});

describe("describeEffect", () => {
  it("reads as a sentence fragment, with the direction in words", () => {
    expect(describeEffect(factor({ effect_pct: 14 }))).toBe(
      "Your group size: raises the price by 14%",
    );
    expect(describeEffect(factor({ effect_pct: -9, direction: "lowers" }))).toBe(
      "Your group size: lowers the price by 9%",
    );
  });

  it("says little effect rather than raises by nothing", () => {
    expect(describeEffect(factor({ effect_pct: 0, direction: "little effect" }))).toBe(
      "Your group size: little effect",
    );
  });
});

describe("barPercent", () => {
  it("scales every bar against the largest effect on the card", () => {
    expect(barPercent(40, 40)).toBe(100);
    expect(barPercent(20, 40)).toBe(50);
    expect(barPercent(-20, 40)).toBe(50);
  });

  it("keeps a small effect visible rather than rounding it away", () => {
    expect(barPercent(1, 400)).toBe(MINIMUM_BAR_PERCENT);
  });

  it("draws nothing at all for no effect", () => {
    expect(barPercent(0, 40)).toBe(0);
    expect(barPercent(10, 0)).toBe(0);
  });

  it("never runs past the end of its track", () => {
    expect(barPercent(90, 40)).toBe(100);
  });
});

describe("largestEffect", () => {
  it("is the largest in either direction", () => {
    expect(
      largestEffect([
        factor({ effect_pct: 12 }),
        factor({ effect_pct: -31 }),
        factor({ effect_pct: 4 }),
      ]),
    ).toBe(31);
  });

  it("is zero when there is nothing to scale", () => {
    expect(largestEffect([])).toBe(0);
  });
});

describe("reconciledPrice", () => {
  it("applies each effect to the one before it, not to the baseline", () => {
    const reached = reconciledPrice(100, [
      factor({ effect_pct: 10 }),
      factor({ effect_pct: 10 }),
    ]);

    expect(reached).toBeCloseTo(121, 6);
  });

  it("comes back to the baseline when nothing moved it", () => {
    expect(reconciledPrice(250, [])).toBe(250);
    expect(reconciledPrice(250, [factor({ effect_pct: 0 })])).toBe(250);
  });

  it("falls with a negative effect", () => {
    expect(reconciledPrice(200, [factor({ effect_pct: -25 })])).toBeCloseTo(150, 6);
  });
});

describe("percentilePhrase", () => {
  it("says what a percentile means rather than naming it", () => {
    expect(percentilePhrase(70)).toBe(
      "Higher than about 70 out of 100 of the similar mentors we compared you with.",
    );
  });

  it("rounds to whole mentors, because there are no fractional ones", () => {
    expect(percentilePhrase(69.6)).toContain("70 out of 100");
  });

  it("says the two ends plainly instead of 0 or 100 out of 100", () => {
    expect(percentilePhrase(100)).toBe(
      "Higher than every similar mentor we compared you with.",
    );
    expect(percentilePhrase(0)).toBe(
      "Lower than every similar mentor we compared you with.",
    );
  });

  it("says nothing at all when there is no position to report", () => {
    expect(percentilePhrase(null)).toBeNull();
    expect(percentilePhrase(Number.NaN)).toBeNull();
  });
});

describe("positionWords", () => {
  it("names the position in words, never in a colour", () => {
    expect(positionWords("above")).toBe("Above the middle");
    expect(positionWords("within")).toBe("In the middle");
    expect(positionWords("below")).toBe("Below the middle");
  });

  it("admits when there is not enough to say", () => {
    expect(positionWords("unknown")).toBe("Not enough to say");
  });
});

/**
 * The two wording rules a row has to keep, checked on the shape the page
 * draws from rather than on the page itself.
 *
 * Neither of these is about looks. A row whose words disagree with its number
 * is wrong in a way that reads perfectly well, which is exactly the fault
 * these exist to catch.
 */
describe("a row's words beside its number", () => {
  it("never pairs a lowering sentence with a raising figure", () => {
    const raising = factor({
      effect_pct: 14,
      direction: "raises",
      sentence:
        "Your group of 4 is larger than the typical group of 2 among similar " +
        "mentors, and that tends to move the price per session up.",
    });

    expect(describeEffect(raising)).toContain("raises");
    expect(raising.sentence).toContain("up");
    expect(raising.sentence).not.toContain("down");
  });

  it("never names a one to one session for a larger group", () => {
    const grouped = factor({
      sentence:
        "Your group of 4 is larger than the typical group of 2 among similar " +
        "mentors, and that tends to move the price per session up.",
    });

    expect(grouped.sentence.toLowerCase()).not.toContain("one to one");
  });
});

describe("a grouped row's parts", () => {
  it("carries the themes behind it, for the numbers table", () => {
    const record = factor({
      key: "track_record",
      label: "Your track record on the platform",
      association: true,
      effect_pct: -12,
      direction: "lowers",
      sentence:
        "Your ratings and activity history together move the suggestion down " +
        "by 12 percent. This is a pattern among similar mentors, not a cause.",
      components: [
        { key: "ratings", label: "What mentees rate you", effect_pct: -9 },
        { key: "standing", label: "Your standing and time here", effect_pct: -3 },
      ],
    });

    expect(record.components).toHaveLength(2);
    expect(record.components.map((part) => formatEffect(part.effect_pct))).toEqual([
      "-9%",
      "-3%",
    ]);
  });

  it("is empty for a row that stands for one answer", () => {
    expect(factor().components).toEqual([]);
  });
});

describe("the bars across a card with a demand row on it", () => {
  it("scales a demand row against the largest effect like any other", () => {
    const rows = [
      factor({ key: "group_size", effect_pct: -40 }),
      factor({ key: "demand", effect_pct: 12, association: true }),
      factor({ key: "track_record", effect_pct: -12, association: true }),
    ];
    const largest = largestEffect(rows);

    expect(largest).toBe(40);
    expect(barPercent(12, largest)).toBe(30);
    expect(barPercent(-12, largest)).toBe(30);
    expect(barPercent(-40, largest)).toBe(100);
  });

  it("still draws a sliver for a demand row that barely moves anything", () => {
    expect(barPercent(1, 40)).toBe(MINIMUM_BAR_PERCENT);
  });
});
