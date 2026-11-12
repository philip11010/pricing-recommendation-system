"""
Build the table of comparable mentors, into ``app_assets/comparables.parquet``.

A price with nothing to compare it against is a number a mentor has no way to
judge. This script prepares the comparison: for every row of the modelled
population, what that provider charges, for a session of what size, in what
field, with what rating and how much of their time booked. The application
reads it to answer "and what do mentors like me charge".

What it deliberately does not write is anything that identifies a source
record. Eight columns go in the file and seven of them are quantities a mentor
would recognise about themselves. The eighth is the opaque key defined in
:mod:`src.data.population`, which is a row's position in the processed dataset
and exists for one reason: a mentor seeded from one of these rows has to be
left out of their own comparison. Without the dataset, which is git-ignored
and never published, a key says nothing. The original identifiers are never
read, never printed and never written.

The population is the one the models were fitted and scored within, through
the same module the demonstration seed script uses, so the two agree about
both the filters and the key. One filter differs: a row needs five reviews
here rather than ten. A row worth showing as one of two hundred comparable
mentors needs less of a record than a row worth turning into a mentor with a
full track record of their own, and the extra rows make the narrow match
levels usable in the thinner fields.

Run from the project root, after preparing the application assets:

    python scripts/prepare_app_assets.py
    python scripts/build_comparables.py

Both the processed dataset and ``app_assets/model_info.json`` are needed, and
both are git-ignored build outputs. A missing one fails with its name.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.population import (  # noqa: E402
    KEY_COLUMN,
    TARGET_COLUMN,
    PopulationError,
    check_columns,
    modelled_population,
    relative,
)
from src.mentor import mapping  # noqa: E402
from src.mentor.comparables import (  # noqa: E402
    COMPARABLES_COLUMNS,
    COMPARABLES_FILENAME,
)
from src.mentor.prediction import (  # noqa: E402
    APP_ASSETS_DIR,
    AssetsUnavailableError,
    read_price_fences,
)

OUTPUT = APP_ASSETS_DIR / COMPARABLES_FILENAME

# Five rather than the ten the seed script asks for. See the module docstring:
# a row shown as one of many comparable mentors needs less of a record than a
# row turned into a mentor with a track record of their own.
MIN_REVIEWS = 5

# The track-record quantities the file carries, under their mentor-facing
# names. Named through the mapping layer so the dataset column each one comes
# from is spelled in exactly one place in the project.
RATING_FIELD = "rating_overall"
BOOKED_SHARE_FIELD = "booked_share_365d"
REVIEWS_FIELD = "reviews_total"

CARRIED_FIELDS: tuple[str, ...] = (RATING_FIELD, BOOKED_SHARE_FIELD, REVIEWS_FIELD)


class BuildError(RuntimeError):
    """An input this script cannot work without is absent or unusable."""


def source_columns() -> tuple[str, ...]:
    """The dataset columns read beyond the ones the population filters use."""
    return tuple(mapping.HISTORY_FIELDS[name] for name in CARRIED_FIELDS) + (
        mapping.COLUMN_SKILLS,
        mapping.COLUMN_VERIFIED,
        mapping.COLUMN_SERVICES,
        mapping.COLUMN_MIN_COMMITMENT,
    )


def population() -> pd.DataFrame:
    """The modelled rows with at least :data:`MIN_REVIEWS` reviews."""
    try:
        floor, ceiling = read_price_fences()
    except AssetsUnavailableError as error:
        raise BuildError(
            f"the price fences come from the prepared model metadata, and it "
            f"could not be read\n  {error}\n  run python "
            f"scripts/prepare_app_assets.py first"
        ) from error

    try:
        rows = modelled_population(
            price_floor=floor, price_ceiling=ceiling, min_reviews=MIN_REVIEWS
        )
        check_columns(rows, source_columns())
    except PopulationError as error:
        raise BuildError(str(error)) from error
    return rows


def build(rows: pd.DataFrame) -> pd.DataFrame:
    """
    Turn the population into the eight columns the application reads.

    Rows missing any carried quantity are dropped rather than filled. An
    imputed rating would be a rating nobody gave, averaged into a figure a
    mentor is shown as what their peers are rated.
    """
    field = rows[mapping.COLUMN_FIELD].map(mapping.field_from_column_value)
    max_mentees = rows[mapping.COLUMN_MAX_MENTEES].astype("int64")
    price = rows[TARGET_COLUMN].round().astype("int64")

    table = pd.DataFrame(
        {
            KEY_COLUMN: rows[KEY_COLUMN].astype("int64"),
            "field": field.astype("string"),
            "max_mentees": max_mentees,
            "price": price,
            # What one mentee pays, rounded the same way the application
            # rounds it, so the two never disagree by a unit.
            "price_per_mentee": (price / max_mentees).round().astype("int64"),
            RATING_FIELD: rows[mapping.HISTORY_FIELDS[RATING_FIELD]].astype("float64"),
            BOOKED_SHARE_FIELD: rows[mapping.HISTORY_FIELDS[BOOKED_SHARE_FIELD]].astype(
                "float64"
            ),
            REVIEWS_FIELD: rows[mapping.HISTORY_FIELDS[REVIEWS_FIELD]].astype("int64"),
            # The four answers a mentor is asked that a comparable mentor
            # also has an answer to, carried so that a comparison can say
            # what is different about what this mentor offers and not only
            # what they charge. Counted the way the form counts them, so
            # "you cover four more skills than most of them" is four of the
            # same things the mentor ticked.
            "skills_covered": (
                (rows[mapping.COLUMN_SKILLS] / mapping.SKILL_WEIGHT)
                .round()
                .clip(lower=0, upper=mapping.SKILL_COUNT)
                .astype("int64")
            ),
            "profile_verified": rows[mapping.COLUMN_VERIFIED].astype("int64"),
            "services_count": rows[mapping.COLUMN_SERVICES].round().astype("int64"),
            "min_commitment": (
                rows[mapping.COLUMN_MIN_COMMITMENT].round().astype("int64")
            ),
        }
    )
    table = table.dropna(subset=list(CARRIED_FIELDS)).reset_index(drop=True)
    if table.empty:
        raise BuildError(
            "every row of the population is missing a rating, a booked share "
            "or a review count, so there is nothing to compare against"
        )
    return table[list(COMPARABLES_COLUMNS)]


def summary(table: pd.DataFrame) -> str:
    """Rows per field, with the price spread, in mentor language."""
    header = (
        f"{'Field':30s} {'Mentors':>8s} {'Median':>8s} "
        f"{'p25':>8s} {'p75':>8s} {'Sizes':>8s}"
    )
    lines = [header, "-" * len(header)]
    for field_id in mapping.FIELDS:
        rows = table[table["field"] == field_id]
        if rows.empty:
            lines.append(f"{mapping.field_label(field_id):30s} {0:>8d}")
            continue
        sizes = f"{int(rows['max_mentees'].min())}-{int(rows['max_mentees'].max())}"
        lines.append(
            f"{mapping.field_label(field_id):30s} {len(rows):8d} "
            f"{int(rows['price'].median()):8,d} "
            f"{int(rows['price'].quantile(0.25)):8,d} "
            f"{int(rows['price'].quantile(0.75)):8,d} {sizes:>8s}"
        )
    lines.append("-" * len(header))
    lines.append(
        f"{'All fields':30s} {len(table):8d} "
        f"{int(table['price'].median()):8,d} "
        f"{int(table['price'].quantile(0.25)):8,d} "
        f"{int(table['price'].quantile(0.75)):8,d}"
    )
    lines.append("")
    lines.append(f"Prices in {mapping.CURRENCY}, per session.")
    return "\n".join(lines)


def main() -> int:
    try:
        table = build(population())
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        table.to_parquet(OUTPUT, engine="pyarrow", index=False)
    except BuildError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1

    print(f"Wrote {relative(OUTPUT)}  ({OUTPUT.stat().st_size:,} bytes)")
    print(f"{len(table):,} comparable mentors, {len(COMPARABLES_COLUMNS)} columns")
    print(f"Columns: {', '.join(COMPARABLES_COLUMNS)}")
    print()
    print(summary(table))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
