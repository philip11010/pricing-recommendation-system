"""
The modelled population, and the one opaque key that identifies a row in it.

Two build scripts read the processed dataset and have to agree about it:
``scripts/seed_demo_mentors.py``, which turns five rows into demonstration
mentors, and ``scripts/build_comparables.py``, which turns the rest into the
table of similar mentors the application compares a price against. They need
the same filters and, more importantly, the same key, because a seeded mentor
has to be able to exclude their own record from the mentors they are compared
with. A key that meant one thing in one script and another in the other would
quietly compare a mentor against themselves.

So the key is defined here, once: **a row's position in the processed dataset
file**. That file is a build artefact with a fixed row order, so the position
is stable for as long as the file is, and it is deliberately not the
identifier the row carries. Nothing can be recovered from a key without the
dataset, and the dataset is git-ignored and never published, which is the
point: the identifiers in it never reach the database, a response, a log or
this repository.

The filters are the ones the models were trained and scored within. A row
outside them is one the models were never fitted to price, so neither a
seeded mentor nor a comparison drawn from it would describe what the system
can actually do. The only filter that differs between the two callers is how
many reviews a row must have, which each one passes in.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import PROJECT_ROOT
from src.mentor import mapping

MASTER_DATASET = PROJECT_ROOT / "data" / "processed" / "master_listings.parquet"

# The key column this module adds. Not a column of the dataset.
KEY_COLUMN = "key"

# The identifier each row of the dataset carries. Named here so that the one
# build script which has to join the raw files back to a row can do it without
# spelling the column itself, and so that this is the only place in the
# codebase where it appears at all.
#
# It never leaves a build script: it is not written to the database, not
# returned by any endpoint and not logged. :data:`KEY_COLUMN` exists precisely
# so that nothing downstream needs it, and a key is useless without the
# git-ignored dataset.
SOURCE_ID_COLUMN = "id"

# The two dataset columns named here are not model inputs: one is the
# prediction target and one is the scope flag the training run split on.
# Every column that *is* a model input is referred to through
# src.mentor.mapping, which is the only module that knows those names.
TARGET_COLUMN = "price_num"
SCOPE_COLUMN = "long_stay"
LONG_STAY_SCOPE = False

DATASET_MISSING_MESSAGE = (
    "missing the processed dataset: data/processed/master_listings.parquet\n"
    "  it is git-ignored and built locally by "
    "notebooks/03_build_master_dataset.ipynb"
)


class PopulationError(RuntimeError):
    """The processed dataset is absent, or not in the expected shape."""


def relative(path: Path) -> str:
    """
    ``path`` relative to the project root, with forward slashes.

    Falls back to the path as given when it is somewhere else entirely, so a
    message about a file is never replaced by a message about a path
    calculation.
    """
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def required_columns() -> tuple[str, ...]:
    """
    Every dataset column the filters below read, named once.

    Checked before any of them is used, so a dataset rebuilt without one of
    them fails with the column's name rather than with a KeyError from
    somewhere inside a boolean expression.
    """
    return (
        TARGET_COLUMN,
        SCOPE_COLUMN,
        mapping.COLUMN_SESSION_FORMAT,
        mapping.COLUMN_FIELD,
        mapping.COLUMN_MAX_MENTEES,
        mapping.HISTORY_FIELDS["has_booking_data"],
        mapping.HISTORY_FIELDS["reviews_total"],
    )


def load_master(path: Path | None = None) -> pd.DataFrame:
    """
    The processed dataset, with :data:`KEY_COLUMN` added.

    The index is reset first and the key taken from it, so the key is the
    row's position in the file rather than whatever index the reader happened
    to produce.

    ``path`` defaults to :data:`MASTER_DATASET`, read when the function is
    called rather than bound when it is defined, so pointing the module at
    another file takes effect.
    """
    path = MASTER_DATASET if path is None else path
    if not path.exists():
        raise PopulationError(DATASET_MISSING_MESSAGE)
    master = pd.read_parquet(path, engine="pyarrow").reset_index(drop=True)
    if KEY_COLUMN in master.columns:
        raise PopulationError(
            f"the dataset already has a column called {KEY_COLUMN!r}, which "
            f"this module adds; rename it in the dataset build"
        )
    master[KEY_COLUMN] = master.index.astype("int64")
    return master


def check_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    """Fail with the names of every column that is missing, not just the first."""
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise PopulationError(
            f"the processed dataset is missing {len(missing)} column(s) this "
            f"build needs: {', '.join(missing)}\n"
            f"  rebuild it with notebooks/03_build_master_dataset.ipynb"
        )


def modelled_population(
    *,
    price_floor: float,
    price_ceiling: float,
    min_reviews: int,
    master: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    The rows the models were fitted to price, carrying their keys.

    ``price_floor`` and ``price_ceiling`` are the fences from the training
    run, passed in rather than read here so that this module does not depend
    on the prepared models. ``min_reviews`` is the one filter the two callers
    set differently: a row worth seeding as a mentor needs a fuller record
    than a row worth showing as one of many comparable mentors.

    The returned frame is indexed from zero for the caller's convenience. The
    key is in :data:`KEY_COLUMN`, never in the index, so a caller that filters
    further cannot lose it.
    """
    frame = load_master() if master is None else master
    check_columns(frame, (KEY_COLUMN, *required_columns()))

    keep = (
        (frame[SCOPE_COLUMN] == LONG_STAY_SCOPE)
        & frame[TARGET_COLUMN].between(price_floor, price_ceiling)
        & (frame[mapping.COLUMN_SESSION_FORMAT] == mapping.SESSION_FORMAT_VALUE)
        & frame[mapping.COLUMN_MAX_MENTEES].between(
            mapping.MAX_MENTEES_MIN, mapping.MAX_MENTEES_MAX
        )
        & (frame[mapping.HISTORY_FIELDS["has_booking_data"]] == 1)
        & (frame[mapping.HISTORY_FIELDS["reviews_total"]] >= min_reviews)
        # Only the twelve market segments the field list is bound to, since
        # every row has to be describable as one of the twelve fields a mentor
        # can choose from.
        & frame[mapping.COLUMN_FIELD].isin(
            [spec["column_value"] for spec in mapping.FIELDS.values()]
        )
    )
    population = frame.loc[keep].reset_index(drop=True)
    if population.empty:
        raise PopulationError(
            "no row of the processed dataset passes the filters the models "
            "were fitted within, so there is nothing to build from"
        )
    return population
