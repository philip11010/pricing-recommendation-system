"""
Shared fixtures for the mentor-facing API tests.

Two things these tests need and the rest of the suite does not: the prepared
models, and a database per test.

The models are a build output of a local training run, produced by
``scripts/prepare_app_assets.py``. They are not in the repository, so CI has
none and any test that needs one is skipped rather than failed. The skip is
explicit and names the command to run, so a skipped run is distinguishable
from a broken one.

The database is a fresh SQLite file per test, created from the models rather
than by running the migrations. The migrations are what deploys the schema,
and ``tests/test_mentor_db.py`` checks that they produce the same tables; for
every other test, creating them directly is the same schema in a fraction of
the time.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

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

# Enough of a track record to reach the full model. The values are plausible
# for a mentor a year or so in: a good but not perfect rating, a steady
# trickle of reviews, about half the offered slots taken.
SYNTHETIC_HISTORY: dict[str, float] = {
    "top_mentor": 1,
    "total_reviews": 40,
    "reviews_last_year": 12,
    "reviews_per_month": 1.2,
    "rating_overall": 4.8,
    "rating_accuracy": 4.8,
    "rating_preparation": 4.7,
    "rating_punctuality": 4.9,
    "rating_communication": 4.9,
    "rating_relevance": 4.8,
    "rating_value": 4.7,
    "open_slots_365d": 120,
    "booked_rate_30d": 0.6,
    "booked_rate_60d": 0.55,
    "booked_rate_90d": 0.5,
    "booked_rate_365d": 0.45,
    "weekend_booked_rate_365d": 0.5,
    "weekday_booked_rate_365d": 0.42,
    "weekend_minus_weekday_booked_rate": 0.08,
    "availability_blocks_365d": 12,
    "reviews_last_90d": 3,
    "reviews_last_180d": 6,
    "reviews_last_365d": 12,
    "days_since_last_review": 14,
    "review_growth": 1.1,
    "first_review_age_years": 3.2,
    "has_no_reviews": 0,
    "has_schedule_data": 1,
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
def client(tmp_path, pricing) -> TestClient:
    """
    The API, wired to a fresh database and the loaded models.

    The session dependency is overridden rather than the environment changed,
    so these tests cannot touch a developer's app.db however DATABASE_URL
    happens to be set.
    """
    from src.mentor.app import app

    engine = create_db_engine(f"sqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as test_client:
        # The lifespan loads the models itself; replacing them with the
        # session-scoped service keeps one copy in memory for the whole run.
        test_client.app.state.pricing = pricing
        test_client.app.state.pricing_error = None
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def modelless_client(tmp_path) -> TestClient:
    """The API as it behaves on a server where no models were prepared."""
    from src.mentor.app import app

    engine = create_db_engine(f"sqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as test_client:
        test_client.app.state.pricing = None
        test_client.app.state.pricing_error = "no models in this test"
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()
