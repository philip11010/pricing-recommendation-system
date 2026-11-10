"""
Shared fixtures for the mentor-facing API tests.

Four things these tests need and the rest of the suite does not: the prepared
models, the table of comparable mentors, the processed dataset, and a database
per test.

The models are a build output of a local training run, produced by
``scripts/prepare_app_assets.py``. They are not in the repository, so CI has
none and any test that needs one is skipped rather than failed. The skip is
explicit and names the command to run, so a skipped run is distinguishable
from a broken one. The dataset is the same kind of thing and skips the same
way.

The database is a fresh SQLite file per test, created from the models rather
than by running the migrations. The migrations are what deploys the schema,
and ``tests/test_mentor_db.py`` checks that they produce the same tables; for
every other test, creating them directly is the same schema in a fraction of
the time.

The comparable mentors are a build output too, but a small synthetic table is
better than the real one for most tests: a match level reached on 6,000 real
rows is a fact about this dataset, while the same level reached on fifteen
rows written out by hand is a fact about the matching rules. So the default
fixture is synthetic and shaped to exercise each level, and the tests that
want the real file ask for it and skip when it is absent.

The API fixtures are built in layers, so that a test can hold the application
and a session against the same database at once. That matters for anything
about an established mentor: a track record is written by the platform rather
than through an endpoint, so a test has to write one the same way.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from src.config import PROJECT_ROOT
from src.db import Base, create_db_engine, get_session
from src.mentor.comparables import (
    COMPARABLES_FILENAME,
    ComparablesTable,
    load_comparables,
)
from src.mentor.prediction import (
    APP_ASSETS_DIR,
    AssetsUnavailableError,
    load_pricing_service,
)

ASSETS_SKIP_REASON = (
    "prepared models are missing from app_assets/; they are a local build "
    "output, so run python scripts/prepare_app_assets.py to produce them"
)

MASTER_DATASET = PROJECT_ROOT / "data" / "processed" / "master_listings.parquet"

DATASET_SKIP_REASON = (
    "the processed dataset is missing from data/processed/; it is git-ignored "
    "and built locally by notebooks/03_build_master_dataset.ipynb"
)

# Enough of a track record to reach the full model. The values are plausible
# for a mentor a few years in: a good but not perfect rating, a steady trickle
# of reviews, about half the offered slots taken. Tenure is included because
# the full path takes it from the record rather than from the new-mentor
# constant, so a history without it is not a usable one.
SYNTHETIC_HISTORY: dict[str, object] = {
    "top_rated_mentor": True,
    "reviews_total": 40,
    "reviews_last_12_months": 12,
    "reviews_per_month": 1.2,
    "rating_overall": 4.8,
    "rating_accuracy": 4.8,
    "rating_preparedness": 4.7,
    "rating_onboarding": 4.9,
    "rating_communication": 4.9,
    "rating_accessibility": 4.8,
    "rating_value": 4.7,
    "open_slots_next_year": 120,
    "booked_share_30d": 0.6,
    "booked_share_60d": 0.55,
    "booked_share_90d": 0.5,
    "booked_share_365d": 0.45,
    "booked_share_weekend_365d": 0.5,
    "booked_share_weekday_365d": 0.42,
    "booked_share_weekend_minus_weekday": 0.08,
    "availability_blocks_365d": 12,
    "reviews_90d": 3,
    "reviews_180d": 6,
    "reviews_365d": 12,
    "days_since_last_review": 14,
    "review_growth": 1.1,
    "years_since_first_review": 3.2,
    "has_no_reviews": False,
    "has_booking_data": True,
    "tenure_years": 4.0,
}


def assets_present(assets_dir: Path = APP_ASSETS_DIR) -> bool:
    """Whether a prepared models folder looks complete enough to load."""
    return all(
        (assets_dir / name).exists()
        for name in (
            "model_info.json",
            "ranges.json",
            "models/core.joblib",
            "models/full.joblib",
        )
    )


def dataset_present(path: Path = MASTER_DATASET) -> bool:
    """Whether the processed dataset the seed script reads from is present."""
    return path.exists()


def comparables_present(assets_dir: Path = APP_ASSETS_DIR) -> bool:
    """Whether the real table of comparable mentors has been built."""
    return (assets_dir / COMPARABLES_FILENAME).exists()


COMPARABLES_SKIP_REASON = (
    "the comparable mentors table is missing from app_assets/; it is a local "
    "build output, so run python scripts/build_comparables.py to produce it"
)

# A hand-built table of comparable mentors, shaped to reach each match level.
#
# The field ids are real ones from the mapping, because the response renders
# their labels, but the counts are chosen rather than measured:
#
# * technology_software has 12 rows at sizes 1 to 3, so a technology mentor
#   running sessions of 1 or 2 matches at level 0 on its own.
# * law has 4 rows spread across sizes 1 and 8, so a law mentor with 1 mentee
#   finds too few at level 0, too few in their field at level 1, and has to
#   reach level 2.
# * engineering has exactly 10 rows, all at size 8, so an engineering mentor
#   with 1 mentee finds none at level 0 and clears the minimum at level 1, and
#   one at size 8 clears it at level 0 by a single row, which is what makes it
#   possible to test that excluding a mentor's own record can widen the match.
# * medicine_health has 3 rows at size 5, which is the only size in that
#   window, so a medicine mentor with 5 mentees cannot reach the minimum at
#   any level and comes back widened.
#
# Prices are spread widely enough that a median and quartiles are
# distinguishable from each other, and every one is a whole number so a test
# can state the expected quantile exactly.
SYNTHETIC_COMPARABLES: list[dict[str, object]] = [
    # technology_software, sizes 1 to 3: twelve rows, so level 0 is enough.
    *(
        {
            "key": 100 + index,
            "field": "technology_software",
            "max_mentees": 1 + index % 3,
            "price": 100 + index * 50,
            "rating_overall": 4.0 + (index % 5) / 10,
            "booked_share_365d": 0.2 + (index % 4) / 10,
            "reviews_total": 10 + index,
        }
        for index in range(12)
    ),
    # engineering, all at size 8: exactly ten rows, so an engineering mentor at
    # any other size reaches them only at level 1, and one at size 8 clears the
    # minimum at level 0 by a single row.
    *(
        {
            "key": 200 + index,
            "field": "engineering",
            "max_mentees": 8,
            "price": 700 + index * 20,
            "rating_overall": 4.5,
            "booked_share_365d": 0.5,
            "reviews_total": 30 + index,
        }
        for index in range(10)
    ),
    # medicine_health, all at size 5: three rows, and the only rows anywhere
    # near that size, so a medicine mentor with 5 mentees comes back widened.
    *(
        {
            "key": 400 + index,
            "field": "medicine_health",
            "max_mentees": 5,
            "price": 400 + index * 100,
            "rating_overall": 4.6,
            "booked_share_365d": 0.4,
            "reviews_total": 20 + index,
        }
        for index in range(3)
    ),
    # law: four rows, never enough on their own at any level.
    {
        "key": 300,
        "field": "law",
        "max_mentees": 1,
        "price": 900,
        "rating_overall": 5.0,
        "booked_share_365d": 0.9,
        "reviews_total": 80,
    },
    {
        "key": 301,
        "field": "law",
        "max_mentees": 2,
        "price": 950,
        "rating_overall": 4.9,
        "booked_share_365d": 0.8,
        "reviews_total": 70,
    },
    {
        "key": 302,
        "field": "law",
        "max_mentees": 8,
        "price": 1000,
        "rating_overall": 4.8,
        "booked_share_365d": 0.7,
        "reviews_total": 60,
    },
    {
        "key": 303,
        "field": "law",
        "max_mentees": 8,
        "price": 1100,
        "rating_overall": 4.7,
        "booked_share_365d": 0.6,
        "reviews_total": 50,
    },
]


def synthetic_comparables() -> ComparablesTable:
    """The hand-built table above, as the application reads it."""
    rows = pd.DataFrame(SYNTHETIC_COMPARABLES)
    rows["price_per_mentee"] = (rows["price"] / rows["max_mentees"]).round().astype(int)
    return ComparablesTable(rows)


@pytest.fixture
def comparables() -> ComparablesTable:
    """
    The default table for the API tests: small, synthetic and predictable.

    Synthetic so that what a test asserts is a fact about the matching rules
    rather than about how many mentors happen to be in one field of one
    dataset.
    """
    return synthetic_comparables()


@pytest.fixture(scope="session")
def real_comparables() -> ComparablesTable:
    """The table built from the dataset, for the end-to-end checks."""
    if not comparables_present():
        pytest.skip(COMPARABLES_SKIP_REASON)
    return load_comparables()


@pytest.fixture(scope="session")
def pricing():
    """
    The loaded models, once for the whole session.

    Session-scoped because loading two gradient-boosted pipelines per test
    would dominate the run. Nothing in the service is mutable, so sharing it
    is safe.
    """
    if not assets_present():
        pytest.skip(ASSETS_SKIP_REASON)
    try:
        return load_pricing_service()
    except AssetsUnavailableError as error:  # pragma: no cover - guard
        pytest.skip(f"{ASSETS_SKIP_REASON} ({error})")


@pytest.fixture
def db_session(tmp_path) -> Session:
    """A session against a fresh SQLite file holding the whole schema."""
    engine = create_db_engine(f"sqlite:///{tmp_path / 'mentor.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


@pytest.fixture
def api_engine(tmp_path):
    """A fresh database for one API test, holding the whole schema."""
    engine = create_db_engine(f"sqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def api_sessions(api_engine) -> sessionmaker[Session]:
    """
    Sessions against the same database the API fixtures are wired to.

    What this is for: writing the rows the platform writes rather than the
    mentor. A track record has no endpoint that creates it, so a test about an
    established mentor registers one through the API and then writes their
    record through here.
    """
    return sessionmaker(bind=api_engine, expire_on_commit=False)


def _api_client(app, factory: sessionmaker[Session]) -> TestClient:
    """The application with its session dependency pointed at ``factory``."""

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    return TestClient(app)


@pytest.fixture
def client(api_sessions, pricing, comparables) -> TestClient:
    """
    The API, wired to a fresh database, the loaded models and a small table.

    The session dependency is overridden rather than the environment changed,
    so these tests cannot touch a developer's app.db however DATABASE_URL
    happens to be set.
    """
    from src.mentor.app import app

    with _api_client(app, api_sessions) as test_client:
        # The lifespan loads the models itself; replacing them with the
        # session-scoped service keeps one copy in memory for the whole run.
        test_client.app.state.pricing = pricing
        test_client.app.state.pricing_error = None
        test_client.app.state.comparables = comparables
        test_client.app.state.comparables_error = None
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def modelless_client(api_sessions) -> TestClient:
    """The API as it behaves on a server where nothing was prepared."""
    from src.mentor.app import app

    with _api_client(app, api_sessions) as test_client:
        test_client.app.state.pricing = None
        test_client.app.state.pricing_error = "no models in this test"
        test_client.app.state.comparables = None
        test_client.app.state.comparables_error = "no comparables in this test"
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def comparableless_client(api_sessions, pricing) -> TestClient:
    """
    The API on a server that can price but has no comparison table.

    A real deployment state rather than a contrived one: the two build outputs
    are produced by different scripts, and the second is easy to forget.
    """
    from src.mentor.app import app

    with _api_client(app, api_sessions) as test_client:
        test_client.app.state.pricing = pricing
        test_client.app.state.pricing_error = None
        test_client.app.state.comparables = None
        test_client.app.state.comparables_error = "no comparables in this test"
        yield test_client
    app.dependency_overrides.clear()
