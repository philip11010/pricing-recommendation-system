"""
Tests for the persistence layer.

Each test gets its own SQLite file under ``tmp_path``, so nothing here can
read or write the application's ``app.db``.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session, sessionmaker

from src.db import (
    DECISION_ACTIONS,
    DEFAULT_DATABASE_URL,
    Base,
    Decision,
    Recommendation,
    create_db_engine,
    database_url,
    get_engine,
    reset_engine,
)

DATA_SOURCE = "Inside Airbnb Sydney (proxy)"


@pytest.fixture
def session(tmp_path) -> Session:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


def make_recommendation(price: float = 250.0) -> Recommendation:
    return Recommendation(
        input_json='{"accommodates": 4}',
        model_name="XGBoost",
        predicted_price=price,
        data_source=DATA_SOURCE,
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def test_default_url_is_a_local_sqlite_file():
    assert DEFAULT_DATABASE_URL == "sqlite:///./app.db"


def test_database_url_prefers_the_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./from-env.db")

    assert database_url() == "sqlite:///./from-env.db"


def test_database_url_falls_back_to_the_default(monkeypatch):
    """
    With no DATABASE_URL anywhere, the SQLite default applies. A developer's
    own .env would otherwise decide the outcome of this test, so it is removed
    from the environment that load_dotenv populates.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("src.db.session.ENV_FILE", "does-not-exist.env")

    assert database_url() == DEFAULT_DATABASE_URL


def test_engine_is_cached_between_calls(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'cached.db'}")
    reset_engine()
    try:
        assert get_engine() is get_engine()
    finally:
        reset_engine()


def test_reset_engine_picks_up_a_new_url(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'first.db'}")
    reset_engine()
    try:
        first = get_engine()
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'second.db'}")
        reset_engine()

        assert get_engine() is not first
    finally:
        reset_engine()


def test_importing_the_session_module_creates_no_database_file(tmp_path, monkeypatch):
    """
    A module-level engine would create app.db in whatever directory happened
    to be current, including during a test run.
    """
    monkeypatch.chdir(tmp_path)

    import importlib

    import src.db.session as module

    importlib.reload(module)

    assert not list(tmp_path.iterdir())


def test_sqlite_parent_directory_is_created(tmp_path):
    target = tmp_path / "nested" / "deeper" / "app.db"

    create_db_engine(f"sqlite:///{target}")

    assert target.parent.exists()


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
def test_recommendation_round_trips(session):
    session.add(make_recommendation(312.45))
    session.commit()

    stored = session.scalars(select(Recommendation)).one()

    assert stored.id == 1
    assert stored.predicted_price == pytest.approx(312.45)
    assert stored.model_name == "XGBoost"
    assert stored.data_source == DATA_SOURCE
    assert stored.input_json == '{"accommodates": 4}'


def test_created_at_is_set_automatically(session):
    session.add(make_recommendation())
    session.commit()

    stored = session.scalars(select(Recommendation)).one()

    assert stored.created_at is not None
    assert stored.created_at.tzinfo is not None


def test_timestamp_is_still_utc_aware_after_a_round_trip(session):
    """
    SQLite has no timezone type, so without UtcDateTime the value comes back
    naive and comparing it to datetime.now(UTC) raises.
    """
    session.add(make_recommendation())
    session.commit()
    session.expire_all()

    stored = session.scalars(select(Recommendation)).one()

    assert stored.created_at.tzinfo is not None
    assert stored.created_at <= datetime.now(UTC)


def test_naive_timestamps_are_refused(session):
    session.add(
        Recommendation(
            input_json="{}",
            model_name="XGBoost",
            predicted_price=100.0,
            data_source=DATA_SOURCE,
            created_at=datetime(2026, 1, 1, 12, 0, 0),
        )
    )

    with pytest.raises(StatementError):
        session.commit()


def test_recommendation_rejects_a_non_positive_price(session):
    session.add(make_recommendation(0.0))

    with pytest.raises(IntegrityError):
        session.commit()


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("action", "price"),
    [("accept", 250.0), ("modify", 199.99), ("reject", None)],
)
def test_each_action_can_be_stored(session, action, price):
    recommendation = make_recommendation()
    session.add(recommendation)
    session.commit()

    session.add(
        Decision(recommendation_id=recommendation.id, action=action, final_price=price)
    )
    session.commit()

    stored = session.scalars(select(Decision)).one()
    assert stored.action == action
    assert stored.final_price == price


def test_three_actions_are_declared():
    assert DECISION_ACTIONS == ("accept", "modify", "reject")


def test_decision_rejects_an_unknown_action(session):
    recommendation = make_recommendation()
    session.add(recommendation)
    session.commit()

    session.add(
        Decision(recommendation_id=recommendation.id, action="maybe", final_price=10.0)
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_modify_without_a_price_is_refused_by_the_database(session):
    """
    The API validates this too. The constraint is the backstop for any code
    path that writes a row without going through the API.
    """
    recommendation = make_recommendation()
    session.add(recommendation)
    session.commit()

    session.add(
        Decision(recommendation_id=recommendation.id, action="modify", final_price=None)
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_reject_with_a_price_is_refused_by_the_database(session):
    recommendation = make_recommendation()
    session.add(recommendation)
    session.commit()

    session.add(
        Decision(recommendation_id=recommendation.id, action="reject", final_price=99.0)
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_decision_is_reachable_from_its_recommendation(session):
    recommendation = make_recommendation()
    session.add(recommendation)
    session.commit()
    session.add(
        Decision(
            recommendation_id=recommendation.id, action="accept", final_price=250.0
        )
    )
    session.commit()
    session.expire_all()

    stored = session.scalars(select(Recommendation)).one()

    assert [d.action for d in stored.decisions] == ["accept"]
    assert stored.decisions[0].recommendation.id == stored.id


def test_deleting_a_recommendation_removes_its_decisions(session):
    recommendation = make_recommendation()
    session.add(recommendation)
    session.commit()
    session.add(
        Decision(
            recommendation_id=recommendation.id, action="accept", final_price=250.0
        )
    )
    session.commit()

    session.delete(session.get(Recommendation, recommendation.id))
    session.commit()

    assert session.scalars(select(Decision)).all() == []
