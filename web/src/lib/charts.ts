/**
 * The arithmetic behind the three charts, kept out of the components.
 *
 * A marker in the wrong place on a price ladder is a lie about where a mentor
 * sits, so the sums that decide it are written where they can be tested
 * rather than inside a render.
 *
 * Nothing here knows a colour or a pixel. It returns percentages, which the
 * components turn into a position, so a chart stays correct at 320 pixels
 * wide and at 1440.
 */

/** The two ends of a price axis. */
export interface Scale {
  min: number;
  max: number;
}

function usable(values: Array<number | null | undefined>): number[] {
  return values.filter(
    (value): value is number => typeof value === "number" && Number.isFinite(value),
  );
}

function roundDown(value: number, step: number): number {
  return Math.floor(value / step) * step;
}

function roundUp(value: number, step: number): number {
  return Math.ceil(value / step) * step;
}

/**
 * An axis wide enough for every value, with room either side.
 *
 * Padded, so a marker at one end of the data does not sit on the end of the
 * track where it cannot be told apart from the end itself, and rounded to a
 * readable number so the end labels are the kind of figure a person says.
 */
export function priceScale(
  values: Array<number | null | undefined>,
  options: { padding?: number } = {},
): Scale {
  const found = usable(values);
  if (found.length === 0) {
    return { min: 0, max: 100 };
  }
  const { padding = 0.15 } = options;
  const lowest = Math.min(...found);
  const highest = Math.max(...found);
  const spread = Math.max(highest - lowest, Math.max(highest * 0.2, 10));
  const step = spread > 400 ? 50 : spread > 120 ? 10 : 5;

  const min = Math.max(0, roundDown(lowest - spread * padding, step));
  const max = roundUp(highest + spread * padding, step);
  return min === max ? { min, max: max + step } : { min, max };
}

/** Where one value sits on the axis, as a percentage from the left. */
export function positionPercent(value: number, scale: Scale): number {
  const span = scale.max - scale.min;
  if (!Number.isFinite(value) || span <= 0) {
    return 0;
  }
  const share = ((value - scale.min) / span) * 100;
  return Math.min(100, Math.max(0, share));
}

export interface BandGeometry {
  leftPercent: number;
  widthPercent: number;
}

/**
 * The shaded middle of the group.
 *
 * Given in the order it was received even when the two ends arrive the wrong
 * way round, and never narrower than a hairline, because a band of zero width
 * would draw its two edge rules on top of each other.
 */
export function bandGeometry(low: number, high: number, scale: Scale): BandGeometry {
  const start = positionPercent(Math.min(low, high), scale);
  const end = positionPercent(Math.max(low, high), scale);
  return {
    leftPercent: start,
    widthPercent: Math.max(end - start, 0.5),
  };
}

export interface DotPlacement {
  price: number;
  xPercent: number;
  /** Which stacked row the dot sits in, counted from the axis upwards. */
  row: number;
}

/**
 * One dot per comparable mentor, stacked where they would overlap.
 *
 * Mentors charging about the same would otherwise draw on top of each other
 * and a cluster of eight would read as one. Dots are placed cheapest first
 * and dropped into the lowest row that is far enough from what is already in
 * it, which keeps the strip shortest where the prices are spread out.
 */
export function dotStripLayout(
  prices: Array<number | null | undefined>,
  scale: Scale,
  options: { minGapPercent?: number; rows?: number } = {},
): DotPlacement[] {
  const { minGapPercent = 2.4, rows = 5 } = options;
  const sorted = usable(prices).sort((a, b) => a - b);
  const lastInRow: number[] = [];

  return sorted.map((price) => {
    const xPercent = positionPercent(price, scale);
    let row = lastInRow.findIndex((last) => xPercent - last >= minGapPercent);
    if (row === -1) {
      row = lastInRow.length < rows ? lastInRow.length : 0;
    }
    lastInRow[row] = xPercent;
    return { price, xPercent, row };
  });
}

/* --------------------------------------------------------------- months */

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** "2024-10-01" as "Oct". */
export function monthShort(iso: string): string {
  const name = monthName(iso);
  return name ? name.slice(0, 3) : "";
}

/** "2024-10-01" as "October". */
export function monthName(iso: string): string {
  const month = Number.parseInt((iso ?? "").slice(5, 7), 10);
  if (!Number.isInteger(month) || month < 1 || month > 12) {
    return "";
  }
  return MONTH_NAMES[month - 1];
}

/** "2024-10-01" as "October 2024". */
export function monthLabel(iso: string): string {
  const name = monthName(iso);
  const year = (iso ?? "").slice(0, 4);
  return name && year ? `${name} ${year}` : "";
}

export interface ReviewStats {
  /** Reviews over the most recent stretch of up to twelve months. */
  recent: number;
  recentMonths: number;
  /** Reviews over the same length of time before that, if there is any. */
  previous: number;
  previousMonths: number;
  /** "more", "fewer" or "about the same" against the earlier stretch. */
  direction: "more" | "fewer" | "same" | "unknown";
  busiest: { iso: string; label: string; count: number } | null;
  total: number;
}

/**
 * This year against the year before, and the month that stood out.
 *
 * Two windows of the same length rather than two calendar years: the series
 * starts when the mentor did, so a calendar year would compare a full twelve
 * months against however many of the previous one happen to be in the record
 * and report a collapse that is really a shorter window.
 *
 * `previousMonths` is zero when there is nothing earlier to compare with, and
 * the component says so instead of printing a fall to zero.
 */
export function reviewStats(
  months: string[],
  reviews: number[],
  options: { window?: number } = {},
): ReviewStats {
  const { window = 12 } = options;
  const counts = months.map((_, index) => {
    const value = reviews[index];
    return typeof value === "number" && Number.isFinite(value) ? value : 0;
  });

  const recentStart = Math.max(0, counts.length - window);
  const recentCounts = counts.slice(recentStart);
  const previousStart = Math.max(0, recentStart - recentCounts.length);
  const previousCounts = counts.slice(previousStart, recentStart);

  const recent = recentCounts.reduce((sum, value) => sum + value, 0);
  const previous = previousCounts.reduce((sum, value) => sum + value, 0);

  let busiest: ReviewStats["busiest"] = null;
  counts.forEach((count, index) => {
    if (busiest === null || count > busiest.count) {
      busiest = {
        iso: months[index],
        label: monthLabel(months[index]),
        count,
      };
    }
  });
  if (busiest !== null && (busiest as { count: number }).count === 0) {
    busiest = null;
  }

  let direction: ReviewStats["direction"] = "unknown";
  if (previousCounts.length > 0) {
    if (recent > previous) {
      direction = "more";
    } else if (recent < previous) {
      direction = "fewer";
    } else {
      direction = "same";
    }
  }

  return {
    recent,
    recentMonths: recentCounts.length,
    previous,
    previousMonths: previousCounts.length,
    direction,
    busiest,
    total: counts.reduce((sum, value) => sum + value, 0),
  };
}

/** The fewest points a chart is allowed to be drawn from. See DESIGN.md 8.1. */
export const MINIMUM_CHART_POINTS = 4;
