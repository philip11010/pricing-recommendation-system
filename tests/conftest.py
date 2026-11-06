"""
Shared fixtures for the mentor-facing API tests.

Three things these tests need and the rest of the suite does not: the prepared
models, the processed dataset, and a database per test.

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

The API fixtures are built in layers, so that a test can hold the application
and a session against the same database at once. That matters for anything
about an established mentor: a track record is written by the platform rather
than through an endpoint, so a test has to write one the same way.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from src.config import PROJECT_ROOT
from src.db import Base, create_db_engine, get_session
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
def client(api_sessions, pricing) -> TestClient:
    """
    The API, wired to a fresh database and the loaded models.

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
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def modelless_client(api_sessions) -> TestClient:
    """The API as it behaves on a server where no models were prepared."""
    from src.mentor.app import app

    with _api_client(app, api_sessions) as test_client:
        test_client.app.state.pricing = None
        test_client.app.state.pricing_error = "no models in this test"
        yield test_client
    app.dependency_overrides.clear()
