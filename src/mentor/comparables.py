"""
Similar mentors: who a price is compared against, and how they are found.

A number on its own does not help a mentor decide anything. "Charge 340" is
advice they have no way to judge; "charge 340, and mentors in your field
running sessions of about your size charge between 280 and 420" is advice they
can act on. This module is the second half of that sentence.

The comparison is drawn from the same population the models were fitted on,
prepared into ``app_assets/comparables.parquet`` by
``scripts/build_comparables.py``. That file holds no identifiers of any kind
except the opaque key described in :mod:`src.data.population`, which exists
only so that a mentor seeded from one of those rows can be left out of their
own comparison.

Two decisions worth knowing about:

**Matching widens in steps, and stops as soon as it has enough.** A mentor
wants to be compared with mentors like them, so the first attempt is their own
field at their own group size. But a narrow match over a thin slice of the
population gives a median built on three mentors, which is worse than no
median at all. So the match widens, field first and then group size, and stops
at the first level that clears :data:`MIN_MATCHES`. The level used is reported,
because "mentors in any field" is a weaker statement than "mentors in your
field" and the mentor should be told which one they are reading.

**The summary is quantiles, not a mean.** Prices in any field have a long
upper tail, and a mean sits above most of the mentors it claims to describe.
The median with the quartiles either side of it says what a typical mentor
charges and how much spread there is around that, which is the question.

**Everything the frontend draws comes out of one set of rows.** A match can
run to a thousand mentors, which is too many to draw as points and more than
anybody needs to see listed. So the match is reduced once, here, to an evenly
spread sample of it: :func:`spread`. The summary, the histogram, the mentor's
own percentile and the rows the frontend plots and tabulates are all read off
that same sample, so the band drawn around the middle of the group is the
quartiles of exactly the points drawn beside it.

That matters because the obvious alternative is what this used to do. The
frontend asked for a page of mentors sorted by price and plotted the page.
The first page of a cheapest-first sort over a thousand mentors is the
cheapest sixty of them, so the points described the bottom of the market
while the band beside them described the whole of it, and the mentor's own
price sat far to the right of every point for no reason anybody could see.
``items`` still pages, because a sorted list of rows is a reasonable thing to
ask an endpoint for, but nothing that claims to describe the market is built
from a page any more.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.mentor import mapping
from src.mentor.prediction import APP_ASSETS_DIR

COMPARABLES_FILENAME = "comparables.parquet"

# Exactly the columns the build script writes, in order. No identifier of the
# source row other than the opaque key, which never leaves this module.
COMPARABLES_COLUMNS: tuple[str, ...] = (
    "key",
    "field",
    "max_mentees",
    "price",
    "price_per_mentee",
    "rating_overall",
    "booked_share_365d",
    "reviews_total",
    # The four answers a mentor gives that a comparable mentor also has an
    # answer to. They are here so that "you charge more than most of them"
    # can be followed by what is different about what you offer, rather than
    # left as a figure with no account of itself. They are never published
    # per mentor: only the typical value across a match is reported, which is
    # why they are absent from :func:`as_item`.
    "skills_covered",
    "profile_verified",
    "services_count",
    "min_commitment",
)

# What a comparison can say a mentor differs from the others in. Mentor-facing
# names on both sides, in the order a difference reads most naturally.
PROFILE_COLUMNS: tuple[str, ...] = (
    "max_mentees",
    "skills_covered",
    "profile_verified",
    "services_count",
    "min_commitment",
)

# The fewest comparable mentors worth drawing a median from. Ten is a
# judgement rather than a derived figure: below it a quartile is decided by
# one or two mentors, and a range that moves that much when one mentor changes
# their price is not describing a market.
MIN_MATCHES = 10

# How far either side of the mentor's own group size still counts as a session
# of about their size. One seat: a session of four and a session of five ask
# much the same of a mentor, a session of four and a session of eight do not.
GROUP_SIZE_TOLERANCE = 1

# Bins in the price distribution the frontend draws. Twelve over the matched
# range is enough to show a shape and few enough that each bin holds mentors.
HISTOGRAM_BINS = 12

# The most mentors described at once. A match of a thousand is a thousand
# overlapping points on a strip that is six hundred pixels wide, and a table
# nobody reads to the end of. A hundred and twenty is enough points to show
# the shape of a market and few enough to draw and to scroll.
#
# The reduction is by rank rather than at random, and it keeps the cheapest
# and the dearest: a sample that dropped the ends would narrow the market
# every time it was taken, and a mentor at the top of their field would be
# told they were off the chart.
SPREAD_POINTS = 120

# Same field, about the same group size. What a mentor actually asked for.
MATCH_SAME_FIELD_AND_SIZE = 0
# Same field, any group size. Their field still describes them.
MATCH_SAME_FIELD = 1
# Any field, about the same group size. The weakest of the three, and only
# reached when a field is too thinly represented to say anything on its own.
MATCH_SAME_SIZE = 2

MATCH_LEVELS: tuple[int, ...] = (
    MATCH_SAME_FIELD_AND_SIZE,
    MATCH_SAME_FIELD,
    MATCH_SAME_SIZE,
)

SORT_PRICE = "price"
SORT_RATING = "rating"
SORT_FIELDS: tuple[str, ...] = (SORT_PRICE, SORT_RATING)

ORDER_ASCENDING = "asc"
ORDER_DESCENDING = "desc"
ORDERS: tuple[str, ...] = (ORDER_ASCENDING, ORDER_DESCENDING)

# The column each sort reads. Mentor-facing names on both sides: the file is
# written in them, so nothing here has to be translated.
SORT_COLUMNS: dict[str, str] = {
    SORT_PRICE: "price",
    SORT_RATING: "rating_overall",
}

COMPARABLES_MISSING_MESSAGE = (
    "Comparable mentors are not available on this server. The table of "
    "mentors a price is compared against is a build output rather than "
    "source, so it has to be prepared locally by running python "
    "scripts/build_comparables.py before this can be shown."
)


class ComparablesUnavailableError(RuntimeError):
    """The prepared table of comparable mentors could not be loaded."""


@dataclass(frozen=True)
class ComparableSet:
    """
    The mentors one service is compared against, and how they were found.

    ``widened`` says that the match ran out of levels before it reached
    :data:`MIN_MATCHES`, so the summary below describes fewer mentors than the
    system considers enough to generalise from. It is reported rather than
    hidden: a median over six mentors is still the best answer available, and
    the mentor is entitled to know that is what they are looking at.
    """

    rows: pd.DataFrame
    match_level: int
    widened: bool
    description: str

    @property
    def count(self) -> int:
        return int(len(self.rows))


def describe_match(match_level: int, field: str, max_mentees: int) -> str:
    """
    What the match covers, in the words a mentor would use for it.

    No column name, no market segment and no source-dataset term: this is a
    sentence a mentor reads above a chart of what other people charge.
    """
    label = mapping.field_label(field)
    low, high = group_size_window(max_mentees)
    if low == high:
        sizes = f"{low} mentee per session"
    else:
        sizes = f"{low} to {high} mentees per session"

    if match_level == MATCH_SAME_FIELD_AND_SIZE:
        return f"{label} mentors with {sizes}"
    if match_level == MATCH_SAME_FIELD:
        return f"{label} mentors, any group size"
    return f"Mentors in any field with {sizes}"


def group_size_window(max_mentees: int) -> tuple[int, int]:
    """
    The group sizes that count as about the same as ``max_mentees``.

    Held inside the range the form offers, so the window never describes a
    session size a mentor could not have set.
    """
    low = max(max_mentees - GROUP_SIZE_TOLERANCE, mapping.MAX_MENTEES_MIN)
    high = min(max_mentees + GROUP_SIZE_TOLERANCE, mapping.MAX_MENTEES_MAX)
    return low, high


def validate_sort(value: Any) -> str:
    """Which column to sort the comparable mentors by."""
    if value not in SORT_FIELDS:
        allowed = ", ".join(SORT_FIELDS)
        raise mapping.MentorInputError(
            "sort", f"Comparable mentors can be sorted by {allowed}."
        )
    return str(value)


def validate_order(value: Any) -> str:
    """Which direction to sort in."""
    if value not in ORDERS:
        allowed = ", ".join(ORDERS)
        raise mapping.MentorInputError(
            "order", f"The sort order has to be one of {allowed}."
        )
    return str(value)


@dataclass(frozen=True)
class ComparablesTable:
    """
    The prepared table, loaded once, with the matching rules over it.

    Built by :func:`load_comparables`, which is the only place that reads the
    filesystem, so a test can construct one from a handful of rows instead.
    """

    rows: pd.DataFrame

    def __post_init__(self) -> None:
        missing = [
            column for column in COMPARABLES_COLUMNS if column not in self.rows.columns
        ]
        if missing:
            raise ComparablesUnavailableError(
                f"the comparable mentors table is missing "
                f"{len(missing)} column(s): {', '.join(missing)}; rebuild it "
                f"with python scripts/build_comparables.py"
            )

    @property
    def count(self) -> int:
        return int(len(self.rows))

    @staticmethod
    def at_level(
        pool: pd.DataFrame, match_level: int, field: str, max_mentees: int
    ) -> pd.DataFrame:
        """The rows one match level selects, before the minimum is applied."""
        low, high = group_size_window(max_mentees)
        same_field = pool["field"] == field
        same_size = pool["max_mentees"].between(low, high)
        if match_level == MATCH_SAME_FIELD_AND_SIZE:
            return pool[same_field & same_size]
        if match_level == MATCH_SAME_FIELD:
            return pool[same_field]
        return pool[same_size]

    def match(
        self,
        *,
        field: str,
        max_mentees: int,
        exclude_key: int | None = None,
    ) -> ComparableSet:
        """
        The mentors this service is compared against.

        ``exclude_key`` leaves out the row a mentor was seeded from, which is
        the whole reason the key exists. A mentor compared against themselves
        would be told that their price is exactly typical, by a comparison in
        which they are one of the data points.
        """
        field = mapping.validate_field(field)
        max_mentees = mapping.validate_max_mentees(max_mentees)

        pool = self.rows
        if exclude_key is not None:
            pool = pool[pool["key"] != int(exclude_key)]

        # The levels are tried widest-last, and the loop keeps whichever it
        # tried most recently. So it leaves behind the first level that
        # cleared the minimum, or, if none did, the widest level, which is the
        # best answer available even though it is thin.
        chosen = pool.iloc[0:0]
        used = MATCH_LEVELS[-1]
        for match_level in MATCH_LEVELS:
            chosen = self.at_level(pool, match_level, field, max_mentees)
            used = match_level
            if len(chosen) >= MIN_MATCHES:
                break

        return ComparableSet(
            rows=chosen.reset_index(drop=True),
            match_level=used,
            widened=len(chosen) < MIN_MATCHES,
            description=describe_match(used, field, max_mentees),
        )


def spread(found: ComparableSet, points: int = SPREAD_POINTS) -> pd.DataFrame:
    """
    The matched mentors reduced to an evenly spread sample, cheapest first.

    Even by rank rather than by price: taking every nth mentor along the
    sorted list keeps the shape of the distribution, where taking every nth
    dollar along the range would hand back a flat line through whatever the
    prices happen to be. The two ends are always in, so the sample spans the
    market rather than a trimmed version of it.

    A match no larger than ``points`` is returned whole and sorted, which is
    the ordinary case for a thinly represented field. The sort is what makes
    the result the same rows in the same order every time it is asked for,
    which the summary beside it depends on.
    """
    rows = found.rows.sort_values(
        by=["price", "price_per_mentee"], kind="mergesort"
    ).reset_index(drop=True)
    if len(rows) <= points or points < 1:
        return rows
    taken = np.unique(np.round(np.linspace(0, len(rows) - 1, points)).astype(int))
    return rows.iloc[taken].reset_index(drop=True)


def summarise(found: ComparableSet, points: int = SPREAD_POINTS) -> dict[str, Any]:
    """
    The headline figures for one set of comparable mentors.

    Read off :func:`spread` rather than off the whole match, so that the band
    a frontend draws around the middle of the group is the quartiles of
    exactly the mentors it draws beside it. On a match small enough to be
    described whole the two are the same rows, so nothing changes; on a large
    one the quantiles move by a currency unit or two, which is the price of
    the two halves of a screen agreeing with each other.

    ``count`` is still the whole match. It answers "how many mentors is this
    based on", which is not the same question as how many of them are drawn,
    and reporting the sample size there would understate the comparison.

    Every price is null when there is nothing to summarise, rather than zero:
    a zero median would read as mentors charging nothing.
    """
    sample = spread(found, points)
    prices = sample["price"].to_numpy(dtype=float)
    each = sample["price_per_mentee"].to_numpy(dtype=float)
    empty = len(prices) == 0

    def quantile(values: np.ndarray, point: float) -> int | None:
        if empty:
            return None
        return int(round(float(np.percentile(values, point))))

    return {
        "count": found.count,
        "median_price": quantile(prices, 50),
        "p25_price": quantile(prices, 25),
        "p75_price": quantile(prices, 75),
        "median_price_per_mentee": quantile(each, 50),
        "match_level": found.match_level,
        "widened": found.widened,
        "match_description": found.description,
        "currency": mapping.CURRENCY,
    }


def distribution(found: ComparableSet, points: int = SPREAD_POINTS) -> dict[str, Any]:
    """
    The mentors a frontend plots and lists, and what they stand for.

    ``total`` is the whole match and ``shown`` is how many of them are here,
    so a sentence above the chart can say "a hundred and twenty mentors spread
    evenly across the one thousand and seventy we matched" rather than
    claiming the sample is the market. ``sampled`` is the one-line version of
    the same fact, for a frontend deciding which sentence to write.

    Every price in ``items`` is what that mentor charges for a whole session,
    which is the figure the mentor reading the page charges too. The per-seat
    figure is beside it, never instead of it.
    """
    sample = spread(found, points)
    return {
        "total": found.count,
        "shown": int(len(sample)),
        "sampled": bool(len(sample) < found.count),
        "items": [as_item(row) for _, row in sample.iterrows()],
    }


def typical_profile(
    found: ComparableSet, points: int = SPREAD_POINTS
) -> dict[str, Any]:
    """
    What a typical mentor in this match offers, not what they charge.

    Read off the same sample as the summary and the chart, so a sentence
    saying a mentor covers more skills than the mentors they are compared
    with is talking about the mentors that were drawn beside them.

    The median for the four counted answers, because one mentor offering
    thirty skills should not move what "typical" means, and the share
    verified for the one that is yes or no. Empty when there is nobody to
    describe: a median of nothing is not zero.
    """
    sample = spread(found, points)
    if sample.empty:
        return {}
    typical: dict[str, Any] = {
        column: float(sample[column].median())
        for column in PROFILE_COLUMNS
        if column != "profile_verified"
    }
    typical["profile_verified"] = float(sample["profile_verified"].mean())
    typical["count"] = int(len(sample))
    return typical


def typical_booked_share(
    found: ComparableSet, points: int = SPREAD_POINTS
) -> float | None:
    """
    How much of their offered time a typical comparable mentor has taken.

    The one measurement in this table that a mentor has a comparable figure
    of their own for, which is what makes a demand comparison possible at
    all. Everything else here is either what they charge or what they offer.

    Read off the same reduced sample as the summary and the chart, for the
    same reason as every other figure in this module: a sentence about demand
    and a dot on a chart beside it should be describing the same mentors.

    Null when there is nobody to read it from. A zero would say the mentors
    being compared with had none of their time taken, which is a claim about
    them rather than an absence of one.
    """
    sample = spread(found, points)
    if sample.empty:
        return None
    share = sample["booked_share_365d"].median()
    if pd.isna(share):
        return None
    return float(share)


def histogram(found: ComparableSet, bins: int = HISTOGRAM_BINS) -> dict[str, Any]:
    """
    The distribution of session prices among the comparable mentors.

    Returned as edges and counts rather than as a drawn chart, so the
    frontend decides how it looks and this module decides only what it says.
    Empty lists when there is nothing to bin: a single bar covering no
    mentors would imply a distribution that was never measured.

    Binned over the same sample the summary is read from, for the same
    reason: two charts on one screen describing two different sets of mentors
    is the fault this module was changed to remove.
    """
    prices = spread(found)["price"].to_numpy(dtype=float)
    if len(prices) == 0:
        return {"bin_edges": [], "counts": []}
    low, high = float(prices.min()), float(prices.max())
    if low == high:
        # Every comparable mentor charges the same. numpy would widen this
        # by half a unit either side, which invents a spread that is not
        # there, so the single value is reported as one bin.
        return {"bin_edges": [low, high], "counts": [int(len(prices))]}
    counts, edges = np.histogram(prices, bins=bins, range=(low, high))
    return {
        "bin_edges": [round(float(edge), 2) for edge in edges],
        "counts": [int(count) for count in counts],
    }


def price_percentile(found: ComparableSet, price: int | None) -> float | None:
    """
    Where ``price`` sits among the comparable mentors, as a percentage.

    The share of comparable mentors charging that much or less. Null when
    there is no price to place or nobody to place it among, because a zero
    would read as "cheaper than everyone" rather than "not known".

    Measured against the same sample as the band, so that a price sitting on
    the lower quartile is reported at about twenty-five per cent rather than
    at some other number worked out from a different set of mentors.
    """
    if price is None or price <= 0 or found.count == 0:
        return None
    prices = spread(found)["price"].to_numpy(dtype=float)
    return round(float((prices <= float(price)).sum()) / len(prices) * 100, 1)


def sorted_items(found: ComparableSet, sort: str, order: str) -> pd.DataFrame:
    """
    The matched mentors in the order asked for, with ties settled.

    The tie-break is the other sortable column and then the price per mentee,
    never the key: the order rows come back in must not depend on anything
    that identifies a source record, or the order itself would leak it.
    """
    sort = validate_sort(sort)
    order = validate_order(order)
    ascending = order == ORDER_ASCENDING
    primary = SORT_COLUMNS[sort]
    tie_breaks = [
        column
        for column in ("price", "rating_overall", "price_per_mentee")
        if column != primary
    ]
    return found.rows.sort_values(
        by=[primary, *tie_breaks],
        ascending=[ascending, *[True] * len(tie_breaks)],
        kind="mergesort",
    )


def as_item(row: Any) -> dict[str, Any]:
    """
    One comparable mentor, as the frontend is given them.

    No key and no id. A mentor looking at who they are compared with is
    looking at a distribution, not at other people's accounts, and the
    response carries nothing that could be joined back to a source record.
    """
    max_mentees = int(row["max_mentees"])
    return {
        "field_label": mapping.field_label(str(row["field"])),
        "session_label": mapping.SESSION_LABELS[mapping.session_label(max_mentees)],
        "max_mentees": max_mentees,
        "price": int(row["price"]),
        "price_per_mentee": int(row["price_per_mentee"]),
        "rating_overall": round(float(row["rating_overall"]), 2),
        "booked_share_percent": round(float(row["booked_share_365d"]) * 100, 1),
        "reviews_total": int(row["reviews_total"]),
    }


def load_comparables(assets_dir: Path = APP_ASSETS_DIR) -> ComparablesTable:
    """
    Load the prepared table, or say what to run to produce it.

    A missing file is an operational state rather than a fault the mentor
    caused, so the message names the command instead of describing a failure.
    """
    path = assets_dir / COMPARABLES_FILENAME
    if not path.exists():
        raise ComparablesUnavailableError(
            f"{COMPARABLES_MISSING_MESSAGE}\nMissing: {path}"
        )
    try:
        rows = pd.read_parquet(path, engine="pyarrow")
    except Exception as error:  # pragma: no cover - corrupt file guard
        raise ComparablesUnavailableError(
            f"the comparable mentors table could not be read: {path}"
        ) from error
    if rows.empty:
        raise ComparablesUnavailableError(
            f"the comparable mentors table is empty: {path}; rebuild it with "
            f"python scripts/build_comparables.py"
        )
    return ComparablesTable(rows)
