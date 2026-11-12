"""
Build the month-by-month activity of the demonstration mentors.

A demonstration mentor's record is one row of the modelled population, which
is the right shape for a model and the wrong shape for a page: it says what
the mentor's figures are now and nothing about how they got there. The chart
on a mentor's own page is about the second thing, so this script reads the raw
files behind the dataset and writes one row per mentor per month.

**Where the months come from, and what is not available.** The two raw files
cover different periods, and neither is a complete monthly history:

* The reviews file is a row per review with a date, going back years. Reviews
  per month is therefore a real measurement, and it is the measure this
  script actually produces.
* The availability file is a forward-looking snapshot: it covers the year
  *after* the dataset was taken, one row per day, saying whether that day is
  open or taken. It says nothing about any month that has already happened, so
  a booked share for a past month cannot be computed from it. The script
  checks whether the file overlaps the months it is building and uses it where
  it does, which in the export this project was built on is nowhere.
* That file also has no price column in this export, so there is no record of
  what anybody charged in any particular month. ``price`` is left null rather
  than filled with the one current price repeated twelve times, which would
  draw a flat line and call it history.

Nothing is invented to fill those gaps. A month with no measurement has a null
in that column, and the endpoint that serves this says plainly what it has.

**The mapping back to the raw files.** A seeded mentor carries ``source_key``,
which is a row position in the processed dataset and nothing else. That file
carries the identifier the raw files are keyed by, so the chain is
``source_key`` to a dataset row to the identifier to the review and
availability rows. It is exact rather than a guess: the position is stable for
a given build of the dataset, the identifiers are unique within it, and every
one of them appears in the availability file. The identifier stays inside this
script: it is not written to the database, returned by an endpoint or logged.

**Ratings over time are not available and are not shown.** The sources hold
one rating per mentor as it stands now, with no record of what it was in any
earlier month.

Run from the project root, against the database ``DATABASE_URL`` points at:

    python scripts/build_demo_activity.py
    python scripts/build_demo_activity.py --reviews data/raw/reviews.csv
    python scripts/build_demo_activity.py --months 6

The paths default to the project's own ``data/raw`` and can be given as
arguments or in ``REVIEWS_FILE`` and ``CALENDAR_FILE``, so nothing here is
tied to one machine's folders. All of these inputs are git-ignored, so a fresh
clone cannot run this until the dataset and the raw files exist; a missing one
fails with a message naming it.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import RAW_DATA_DIR  # noqa: E402
from src.data.population import (  # noqa: E402
    KEY_COLUMN,
    SOURCE_ID_COLUMN,
    PopulationError,
    load_master,
)
from src.db import Mentor, create_db_engine  # noqa: E402
from src.db.mentor_models import MentorActivity  # noqa: E402

# How many complete months the chart covers. A year, so the shape of a
# mentor's year is visible and a seasonal rise is distinguishable from a
# trend.
DEFAULT_MONTHS = 12

REVIEWS_VARIABLE = "REVIEWS_FILE"
CALENDAR_VARIABLE = "CALENDAR_FILE"

DEFAULT_REVIEWS = RAW_DATA_DIR / "reviews.csv"
DEFAULT_CALENDAR = RAW_DATA_DIR / "calendar.csv"

# The columns each raw file is read for, named here so a file missing one
# fails with the column's name rather than with a KeyError from inside a
# groupby. The availability file's price column is optional: the export this
# project was built on has none.
REVIEW_COLUMNS: tuple[str, ...] = ("listing_id", "date")
CALENDAR_COLUMNS: tuple[str, ...] = ("listing_id", "date", "available")
CALENDAR_PRICE_COLUMN = "price"

# What the availability file writes for a day that is still open.
AVAILABLE_YES = "t"

PRICE_UNAVAILABLE_NOTE = (
    "the availability file has no price column, so there is no record of what "
    "anybody charged in a particular month; price is left empty rather than "
    "filled with one current figure repeated"
)

BOOKED_SHARE_UNAVAILABLE_NOTE = (
    "the availability file covers {low} to {high}, which does not overlap the "
    "months being built ({start} to {end}); it is a forward-looking snapshot, "
    "so a booked share for a month that has already happened cannot be "
    "computed from it and is left empty"
)


class ActivityInputError(RuntimeError):
    """An input this script cannot work without is absent or unusable."""


@dataclass
class ActivityReport:
    """What one run built, and what it could not."""

    mentors: int = 0
    months_written: int = 0
    mentors_without_activity: int = 0
    first_month: date | None = None
    last_month: date | None = None
    notes: list[str] = field(default_factory=list)


def file_argument(given: str | None, variable: str, default: Path) -> Path:
    """
    One input file: the argument, then the environment, then the default.

    The default is inside the project rather than anywhere on a particular
    machine, so the script runs from a fresh clone of the repository with the
    git-ignored files restored into ``data/raw``.
    """
    if given:
        return Path(given).expanduser()
    from_environment = os.environ.get(variable)
    if from_environment:
        return Path(from_environment).expanduser()
    return default


def read_csv(path: Path, columns: tuple[str, ...], what: str) -> pd.DataFrame:
    """One raw file, with the columns this script needs and no others."""
    if not path.exists():
        raise ActivityInputError(
            f"missing the {what}: {path}\n"
            f"  it is git-ignored, so restore it into data/raw or name "
            f"another path"
        )
    try:
        frame = pd.read_csv(path, usecols=list(columns))
    except ValueError as error:
        raise ActivityInputError(
            f"the {what} does not have the columns this build needs "
            f"({', '.join(columns)}): {path}"
        ) from error
    return frame


def month_of(values: pd.Series) -> pd.Series:
    """Each date as the first day of its month."""
    parsed = pd.to_datetime(values, errors="coerce")
    return parsed.dt.to_period("M").dt.to_timestamp()


def month_window(anchor: pd.Timestamp, months: int) -> list[pd.Timestamp]:
    """
    The last ``months`` complete months up to ``anchor``.

    The month ``anchor`` falls in is left out, because it is the month the
    snapshot was taken in and is therefore incomplete: counting a part month
    beside eleven whole ones would show every mentor falling off a cliff at
    the right hand edge of the chart.
    """
    last = anchor.to_period("M") - 1
    first = last - (months - 1)
    return [period.to_timestamp() for period in pd.period_range(first, last, freq="M")]


def source_ids(keys: set[int]) -> dict[int, int]:
    """
    Each ``source_key`` mapped to the identifier the raw files are keyed by.

    The key is a row position in the processed dataset, so this is a lookup
    rather than a guess. A key with no row is a mentor seeded from a different
    build of the dataset, which is reported rather than silently skipped: the
    activity it would produce would belong to somebody else.
    """
    try:
        master = load_master()
    except PopulationError as error:
        raise ActivityInputError(str(error)) from error
    if SOURCE_ID_COLUMN not in master.columns:
        raise ActivityInputError(
            f"the processed dataset has no {SOURCE_ID_COLUMN} column, so the "
            f"raw files cannot be joined back to a seeded mentor"
        )
    lookup = master.set_index(KEY_COLUMN)[SOURCE_ID_COLUMN]
    missing = sorted(key for key in keys if key not in lookup.index)
    if missing:
        raise ActivityInputError(
            f"{len(missing)} seeded mentor(s) carry a source key that is not a "
            f"row of the current processed dataset, so their activity cannot "
            f"be built: reseed them with python scripts/seed_demo_mentors.py "
            f"--reset and then seed again"
        )
    return {key: int(lookup.loc[key]) for key in keys}


@dataclass(frozen=True)
class Reviews:
    """
    Everything the reviews file is read for, from one pass over it.

    Read once rather than three times: the file is hundreds of thousands of
    rows and each of these is a groupby over the same frame.

    ``latest`` is the newest review in the whole file rather than among the
    wanted records, because it is being used as the date the snapshot was
    taken, which is a fact about the file.

    ``began`` is the month each record was first reviewed in, however long
    ago, and it decides which months of the window are a measurement of zero
    and which are no measurement at all. A mentor who took their first session
    in March has no activity in February, and a row saying they had no reviews
    that month would be a figure about a month they were not there for. From
    their first month onwards a zero is real, because the file covers those
    months completely.
    """

    latest: pd.Timestamp
    counted: dict[tuple[int, pd.Timestamp], int]
    began: dict[int, pd.Timestamp]


def read_reviews(path: Path, wanted: set[int]) -> Reviews:
    """The reviews file, in the three shapes this script needs."""
    frame = read_csv(path, REVIEW_COLUMNS, "reviews file")
    frame["month"] = month_of(frame["date"])
    dates = pd.to_datetime(frame["date"], errors="coerce").dropna()
    if dates.empty:
        raise ActivityInputError(f"the reviews file has no readable dates: {path}")
    latest = dates.max()

    mine = frame[frame["listing_id"].isin(wanted)].dropna(subset=["month"])
    counted = mine.groupby(["listing_id", "month"]).size()
    return Reviews(
        latest=latest,
        counted={
            (int(listing), month): int(count)
            for (listing, month), count in counted.items()
        },
        began=dict(mine.groupby("listing_id")["month"].min()),
    )


def calendar_range(path: Path) -> tuple[pd.Timestamp, pd.Timestamp]:
    """The first and last day the availability file covers."""
    frame = read_csv(path, ("date",), "availability file")
    parsed = pd.to_datetime(frame["date"], errors="coerce").dropna()
    if parsed.empty:
        raise ActivityInputError(f"the availability file has no readable dates: {path}")
    return parsed.min(), parsed.max()


def booked_share_by_month(
    path: Path, wanted: set[int], window: list[pd.Timestamp]
) -> pd.DataFrame:
    """
    The share of each record's offered days that are taken, per month.

    Only for the months of the window the file actually covers. A month the
    file covers partly is still reported, because the share is a proportion of
    the days there are rather than a count of them.

    The price per month comes from the same file when it has a price column.
    The export this project was built on has none, so the column is absent and
    so is the figure.
    """
    columns = CALENDAR_COLUMNS
    with open(path, encoding="utf-8") as handle:
        header = handle.readline().strip().split(",")
    has_price = CALENDAR_PRICE_COLUMN in header
    if has_price:
        columns = (*columns, CALENDAR_PRICE_COLUMN)

    frame = read_csv(path, columns, "availability file")
    frame = frame[frame["listing_id"].isin(wanted)].copy()
    frame["month"] = month_of(frame["date"])
    frame = frame[frame["month"].isin(window)]
    if frame.empty:
        return pd.DataFrame(columns=["listing_id", "month", "booked_share", "price"])

    frame["booked"] = (
        frame["available"].astype(str).str.strip().str.lower() != AVAILABLE_YES
    )
    grouped = frame.groupby(["listing_id", "month"])
    built = grouped["booked"].mean().rename("booked_share").reset_index()
    if has_price:
        prices = (
            frame[CALENDAR_PRICE_COLUMN]
            .astype(str)
            .str.replace(r"[^0-9.]", "", regex=True)
        )
        frame["price_num"] = pd.to_numeric(prices, errors="coerce")
        median = (
            frame.groupby(["listing_id", "month"])["price_num"]
            .median()
            .rename("price")
            .reset_index()
        )
        built = built.merge(median, on=["listing_id", "month"], how="left")
    else:
        built["price"] = pd.NA
    return built


def demo_mentors(session: Session) -> list[Mentor]:
    """Every seeded mentor that carries a source record."""
    return list(
        session.scalars(
            select(Mentor)
            .where(Mentor.is_demo.is_(True), Mentor.source_key.is_not(None))
            .order_by(Mentor.id)
        )
    )


def build_activity(
    session: Session,
    *,
    reviews_path: Path = DEFAULT_REVIEWS,
    calendar_path: Path = DEFAULT_CALENDAR,
    months: int = DEFAULT_MONTHS,
) -> ActivityReport:
    """
    Write the last ``months`` complete months of activity for every demo mentor.

    Idempotent: the rows for the window are replaced rather than added to, so
    running this twice leaves the same table and running it after a reseed
    rebuilds it.
    """
    report = ActivityReport()
    mentors = demo_mentors(session)
    report.mentors = len(mentors)
    if not mentors:
        report.notes.append(
            "no seeded mentors carry a source record, so there is nothing to "
            "build; run python scripts/seed_demo_mentors.py first"
        )
        return report

    identifiers = source_ids({int(mentor.source_key) for mentor in mentors})
    wanted = set(identifiers.values())

    reviews = read_reviews(reviews_path, wanted)
    window = month_window(reviews.latest, months)
    report.first_month = window[0].date()
    report.last_month = window[-1].date()

    low, high = calendar_range(calendar_path)
    overlaps = low <= window[-1] and high >= window[0]
    if overlaps:
        shares = booked_share_by_month(calendar_path, wanted, window)
    else:
        shares = pd.DataFrame(columns=["listing_id", "month", "booked_share", "price"])
        report.notes.append(
            BOOKED_SHARE_UNAVAILABLE_NOTE.format(
                low=low.date(),
                high=high.date(),
                start=window[0].date(),
                end=window[-1].date(),
            )
        )
    report.notes.append(PRICE_UNAVAILABLE_NOTE)

    measured = {
        (int(row.listing_id), row.month): (row.booked_share, row.price)
        for row in shares.itertuples()
    }

    for mentor in mentors:
        identifier = identifiers[int(mentor.source_key)]
        session.execute(
            delete(MentorActivity).where(
                MentorActivity.mentor_id == mentor.id,
                MentorActivity.month >= window[0].date(),
                MentorActivity.month <= window[-1].date(),
            )
        )
        began = reviews.began.get(identifier)
        written = 0
        for month in window:
            # Before the mentor's first month there is no measurement at all,
            # as opposed to a measurement of none. See Reviews.began.
            if began is None or month < began:
                continue
            share, price = measured.get((identifier, month), (None, None))
            session.add(
                MentorActivity(
                    mentor_id=mentor.id,
                    month=month.date(),
                    reviews_count=reviews.counted.get((identifier, month), 0),
                    booked_share=(
                        float(share) if share is not None and pd.notna(share) else None
                    ),
                    price=(
                        int(round(float(price)))
                        if price is not None and pd.notna(price)
                        else None
                    ),
                )
            )
            written += 1
        report.months_written += written
        if written == 0:
            report.mentors_without_activity += 1

    session.commit()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build the month-by-month activity of the demonstration mentors "
            "from the raw files, so a mentor's own page has a chart with real "
            "measurements on it."
        )
    )
    parser.add_argument(
        "--reviews",
        default=None,
        help=(
            f"the reviews file; defaults to {REVIEWS_VARIABLE} or "
            f"data/raw/reviews.csv"
        ),
    )
    parser.add_argument(
        "--calendar",
        default=None,
        help=(
            f"the availability file; defaults to {CALENDAR_VARIABLE} or "
            f"data/raw/calendar.csv"
        ),
    )
    parser.add_argument(
        "--months",
        type=int,
        default=DEFAULT_MONTHS,
        help=f"how many complete months to build (default {DEFAULT_MONTHS})",
    )
    arguments = parser.parse_args(argv)
    if arguments.months < 1:
        print("FAILED: --months has to be at least 1", file=sys.stderr)
        return 1

    engine = create_db_engine()
    try:
        with Session(engine, expire_on_commit=False) as session:
            report = build_activity(
                session,
                reviews_path=file_argument(
                    arguments.reviews, REVIEWS_VARIABLE, DEFAULT_REVIEWS
                ),
                calendar_path=file_argument(
                    arguments.calendar, CALENDAR_VARIABLE, DEFAULT_CALENDAR
                ),
                months=arguments.months,
            )
    except ActivityInputError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    print(describe(report))
    return 0


def describe(report: ActivityReport) -> str:
    """What the run built, and what it could not, in full sentences."""
    lines = [
        f"{report.months_written} month(s) of activity written for "
        f"{report.mentors} demonstration mentor(s)."
    ]
    if report.first_month and report.last_month:
        lines.append(f"Period: {report.first_month} to {report.last_month}.")
    if report.mentors_without_activity:
        lines.append(
            f"{report.mentors_without_activity} mentor(s) have no activity in "
            f"that period, so they have no rows rather than rows of zeroes."
        )
    for note in report.notes:
        lines.append(f"Not available: {note}.")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
