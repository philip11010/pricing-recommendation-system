"""
Tests for the mentor-facing tables.

The constraints are declared at the database level as well as in the Pydantic
schemas, so a row cannot become inconsistent through a code path that bypasses
the API. These tests check the database half: each one writes a row the
application would never write and expects the database to refuse it.

The last section checks that the migration and the models agree. The
application's schema is deployed by Alembic, and the test suite creates it
from the models, so a divergence between the two would mean the tests pass
against a schema that is never deployed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from src.db import Base, create_db_engine
from src.db.mentor_models import (
    DECISION_ACTIONS,
    MODEL_CHOICES,
    RECOMMENDATION_STATUSES,
    Mentor,
    MentorHistory,
    PricingDecision,
    PricingRecommendation,
    Service,
)
from src.mentor import mapping

MENTOR_TABLES = {
    "mentors",
    "services",
    "mentor_history",
    "recommendations",
    "decisions",
}


def make_mentor(email: str = "mentor@example.com") -> Mentor:
    return Mentor(
        full_name="A. Mentor",
        email=email,
        years_mentoring_band="3_to_5",
        services_planned=1,
    )


def make_service(mentor_id: int, **overrides) -> Service:
    values = {
        "mentor_id": mentor_id,
        "session_label": "one_to_one",
        "field": "technology_software",
        "max_mentees": 1,
        "min_commitment": 1,
        "skills": ["cv_review", "interview_preparation"],
        "profile_verified": True,
    }
    values.update(overrides)
    return Service(**values)


def make_recommendation(service_id: int, **overrides) -> PricingRecommendation:
    values = {
        "service_id": service_id,
        "model_used": "core",
        "recommended_price": 180,
        "price_low": 120,
        "price_high": 270,
        "low_confidence": True,
        "inputs_snapshot": mapping.to_model_inputs(
            field="technology_software",
            max_mentees=1,
            min_commitment=1,
            skills=["cv_review"],
            profile_verified=True,
            services_planned=1,
            services_count=1,
        ),
        "model_version": "test-version",
    }
    values.update(overrides)
    return PricingRecommendation(**values)


@pytest.fixture
def stored(db_session):
    """A mentor with one service and one recommendation, already committed."""
    mentor = make_mentor()
    db_session.add(mentor)
    db_session.commit()
    service = make_service(mentor.id)
    db_session.add(service)
    db_session.commit()
    recommendation = make_recommendation(service.id)
    db_session.add(recommendation)
    db_session.commit()
    return mentor, service, recommendation


# ---------------------------------------------------------------------------
# Mentors
# ---------------------------------------------------------------------------
def test_a_mentor_round_trips(db_session):
    db_session.add(make_mentor())
    db_session.commit()

    mentor = db_session.scalar(select(Mentor))
    assert mentor.email == "mentor@example.com"
    assert mentor.created_at.tzinfo is not None


def test_the_password_hash_starts_empty(db_session):
    """
    There is no authentication yet. The column exists so that adding one does
    not mean rewriting every existing row.
    """
    db_session.add(make_mentor())
    db_session.commit()

    assert db_session.scalar(select(Mentor)).password_hash is None


def test_two_mentors_cannot_share_an_email(db_session):
    db_session.add(make_mentor())
    db_session.commit()
    db_session.add(make_mentor())

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_mentor_cannot_plan_more_services_than_the_form_offers(db_session):
    mentor = make_mentor()
    mentor.services_planned = 9
    db_session.add(mentor)

    with pytest.raises(IntegrityError):
        db_session.commit()


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
def test_a_service_round_trips_with_its_skill_list(db_session):
    mentor = make_mentor()
    db_session.add(mentor)
    db_session.commit()
    db_session.add(make_service(mentor.id))
    db_session.commit()

    service = db_session.scalar(select(Service))
    assert service.skills == ["cv_review", "interview_preparation"]


def test_a_group_larger_than_the_form_allows_is_refused(db_session):
    mentor = make_mentor()
    db_session.add(mentor)
    db_session.commit()
    service = make_service(mentor.id)
    service.max_mentees = 99
    db_session.add(service)

    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize(
    ("mentees", "label"),
    [(1, "one_to_one"), (2, "group"), (8, "group")],
)
def test_a_service_stores_the_label_its_group_size_implies(db_session, mentees, label):
    mentor = make_mentor()
    db_session.add(mentor)
    db_session.commit()
    db_session.add(
        make_service(
            mentor.id,
            max_mentees=mentees,
            session_label=mapping.session_label(mentees),
        )
    )
    db_session.commit()

    assert db_session.scalar(select(Service)).session_label == label


@pytest.mark.parametrize(
    ("mentees", "label"),
    [(1, "group"), (4, "one_to_one"), (2, "one_to_one")],
)
def test_a_label_that_contradicts_the_group_size_is_refused(db_session, mentees, label):
    """
    The label is derived, so a row where the two disagree describes a service
    that cannot exist. The database refuses it rather than trusting whichever
    code path wrote it.
    """
    mentor = make_mentor()
    db_session.add(mentor)
    db_session.commit()
    db_session.add(make_service(mentor.id, max_mentees=mentees, session_label=label))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_label_outside_the_two_the_system_uses_is_refused(db_session):
    mentor = make_mentor()
    db_session.add(mentor)
    db_session.commit()
    db_session.add(make_service(mentor.id, session_label="webinar"))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_a_mentor_removes_their_services(db_session, stored):
    mentor, _, _ = stored

    db_session.delete(mentor)
    db_session.commit()

    assert db_session.scalars(select(Service)).all() == []


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
def test_a_recommendation_round_trips_with_its_snapshot(db_session, stored):
    _, service, _ = stored

    recommendation = db_session.scalar(select(PricingRecommendation))
    assert recommendation.service_id == service.id
    assert set(recommendation.inputs_snapshot) == set(mapping.CORE_COLUMNS)
    assert mapping.max_mentees_from_inputs(recommendation.inputs_snapshot) == 1
    assert recommendation.status == "pending"


def test_a_recommendation_from_an_unknown_model_is_refused(db_session, stored):
    _, service, _ = stored
    db_session.add(make_recommendation(service.id, model_used="guesswork"))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_an_unknown_status_is_refused(db_session, stored):
    _, service, _ = stored
    db_session.add(make_recommendation(service.id, status="maybe"))

    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("status", RECOMMENDATION_STATUSES)
def test_every_status_the_flow_uses_is_accepted(db_session, stored, status):
    _, service, _ = stored
    db_session.add(make_recommendation(service.id, status=status))

    db_session.commit()


@pytest.mark.parametrize("model_used", MODEL_CHOICES)
def test_either_model_can_be_recorded(db_session, stored, model_used):
    _, service, _ = stored
    db_session.add(make_recommendation(service.id, model_used=model_used))

    db_session.commit()


def test_a_price_outside_its_own_range_is_refused(db_session, stored):
    """
    The range is what the mentor is shown around the price. A price outside it
    would make the display incoherent, so the row cannot exist.
    """
    _, service, _ = stored
    db_session.add(
        make_recommendation(
            service.id, recommended_price=400, price_low=120, price_high=270
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_free_price_is_refused(db_session, stored):
    _, service, _ = stored
    db_session.add(
        make_recommendation(service.id, recommended_price=0, price_low=0, price_high=0)
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_a_service_removes_its_recommendations(db_session, stored):
    _, service, _ = stored

    db_session.delete(service)
    db_session.commit()

    assert db_session.scalars(select(PricingRecommendation)).all() == []


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("action", ["accepted", "modified"])
def test_a_decision_that_settles_on_a_price_records_it(db_session, stored, action):
    _, _, recommendation = stored
    db_session.add(
        PricingDecision(
            recommendation_id=recommendation.id, action=action, final_price=195.50
        )
    )
    db_session.commit()

    decision = db_session.scalar(select(PricingDecision))
    assert float(decision.final_price) == pytest.approx(195.50)
    assert decision.decided_at.tzinfo is not None


def test_a_rejection_records_no_price(db_session, stored):
    """
    The mentor declined the advice and did not say what they charge instead,
    so there is nothing to record.
    """
    _, _, recommendation = stored
    db_session.add(
        PricingDecision(recommendation_id=recommendation.id, action="rejected")
    )
    db_session.commit()

    assert db_session.scalar(select(PricingDecision)).final_price is None


def test_a_rejection_carrying_a_price_is_refused(db_session, stored):
    _, _, recommendation = stored
    db_session.add(
        PricingDecision(
            recommendation_id=recommendation.id, action="rejected", final_price=195.0
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("action", ["accepted", "modified"])
def test_settling_on_no_price_is_refused(db_session, stored, action):
    _, _, recommendation = stored
    db_session.add(PricingDecision(recommendation_id=recommendation.id, action=action))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_an_unknown_action_is_refused(db_session, stored):
    _, _, recommendation = stored
    db_session.add(
        PricingDecision(
            recommendation_id=recommendation.id, action="ignored", final_price=10.0
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_three_actions_are_the_three_the_mentor_is_offered(db_session):
    assert set(DECISION_ACTIONS) == {"accepted", "modified", "rejected"}


# ---------------------------------------------------------------------------
# Track record
# ---------------------------------------------------------------------------
def test_a_mentor_starts_with_no_track_record(db_session, stored):
    """Until the platform writes one, every price comes from the core model."""
    assert db_session.scalars(select(MentorHistory)).all() == []


def test_the_track_record_table_holds_every_extra_model_input(db_session):
    """
    One column per extra input of the full model, under its mentor-facing
    name, plus tenure. A name in one place and not the other would be a column
    the model can never be given.
    """
    columns = set(inspect(MentorHistory).columns.keys())

    assert set(mapping.HISTORY_STORED_FIELDS) <= columns
    assert len(mapping.HISTORY_FIELDS) == 28
    assert len(mapping.HISTORY_STORED_FIELDS) == 29


def test_a_track_record_round_trips(db_session):
    mentor = make_mentor()
    db_session.add(mentor)
    db_session.commit()
    db_session.add(
        MentorHistory(
            mentor_id=mentor.id,
            reviews_total=40,
            rating_overall=4.8,
            booked_share_90d=0.5,
            top_rated_mentor=True,
            tenure_years=4.0,
            updated_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    record = db_session.scalar(select(MentorHistory))
    assert record.reviews_total == 40
    assert record.top_rated_mentor is True
    # Not yet computed, which is what keeps a mentor on the core model.
    assert record.reviews_per_month is None
    assert record.is_complete is False


def test_a_complete_track_record_says_so(db_session):
    """
    ``is_complete`` is what decides which model prices the mentor, so it is
    checked against a row that has everything rather than inferred.
    """
    from .conftest import SYNTHETIC_HISTORY

    mentor = make_mentor()
    db_session.add(mentor)
    db_session.commit()
    db_session.add(MentorHistory(mentor_id=mentor.id, **SYNTHETIC_HISTORY))
    db_session.commit()

    record = db_session.scalar(select(MentorHistory))
    assert record.is_complete is True
    assert set(record.stored_values()) == set(mapping.HISTORY_STORED_FIELDS)


def test_deleting_a_mentor_removes_their_track_record(db_session):
    mentor = make_mentor()
    db_session.add(mentor)
    db_session.commit()
    db_session.add(MentorHistory(mentor_id=mentor.id))
    db_session.commit()

    db_session.delete(mentor)
    db_session.commit()

    assert db_session.scalars(select(MentorHistory)).all() == []


# ---------------------------------------------------------------------------
# The migration and the models agree
# ---------------------------------------------------------------------------
@pytest.fixture
def migrated_engine(tmp_path, monkeypatch):
    """A database built by running the migrations, not by create_all."""
    from alembic import command
    from alembic.config import Config

    from src.config import PROJECT_ROOT

    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    command.upgrade(config, "head")

    engine = create_db_engine(url)
    yield engine
    engine.dispose()


def test_the_migration_creates_the_mentor_tables(migrated_engine):
    tables = set(inspect(migrated_engine).get_table_names())

    assert MENTOR_TABLES <= tables


def test_the_migration_and_the_models_describe_the_same_schema(migrated_engine):
    """
    Every table and column the models declare exists in the migrated database.

    The suite creates its schema from the models for speed; this is the test
    that keeps that shortcut honest.
    """
    inspector = inspect(migrated_engine)
    migrated = {
        table: {column["name"] for column in inspector.get_columns(table)}
        for table in inspector.get_table_names()
    }

    for name, table in Base.metadata.tables.items():
        assert name in migrated, f"{name} is declared but never migrated"
        declared = {column.name for column in table.columns}
        assert declared == migrated[name], f"{name} differs from the migration"


def test_the_prototype_tables_keep_their_own_names(migrated_engine):
    """
    The earlier dashboard owned "recommendations" and "decisions" with a
    different shape. The mentor-facing API took those names, so the
    prototype's two tables are migrated under legacy names rather than
    dropped.
    """
    tables = set(inspect(migrated_engine).get_table_names())

    assert {"legacy_recommendations", "legacy_decisions"} <= tables
