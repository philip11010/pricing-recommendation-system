"""
Tests for the demonstration seed script.

Three things have to hold about it, and only the first is obvious.

It has to be **deterministic**. The five mentors are the demonstration: if
they change between runs, every screenshot, every figure quoted in the report
and every rehearsal of the demo describes a system that no longer exists.

It has to be **idempotent**. Running it twice is the normal mistake, and the
cost of getting it wrong is ten mentors where there should be five, half of
them duplicates of the other half.

The mentors it writes have to be **priced by the same code as everyone else**.
A seeded mentor whose price came from a shortcut in the script would
demonstrate the script rather than the system, so the test that matters most
here asks the API for a price and checks it against what the script said.

The script reads the processed dataset and the prepared models, both of which
are git-ignored local build outputs, so the whole module skips with a message
naming each one when it is absent.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from scripts import seed_demo_mentors as seed
from src.data import population as dataset
from src.db import Base, Mentor, MentorHistory, Service, create_db_engine, get_session
from src.mentor import mapping
from src.mentor.dependencies import MENTOR_ID_HEADER

from .conftest import DATASET_SKIP_REASON, dataset_present

pytestmark = [pytest.mark.app_assets, pytest.mark.dataset]


@pytest.fixture(scope="module", autouse=True)
def _needs_the_dataset():
    if not dataset_present():
        pytest.skip(DATASET_SKIP_REASON)


@pytest.fixture(scope="module")
def population(pricing):
    """
    The filtered population, read once for the whole module.

    The prepared models are handed to the script's own cache rather than let
    it load its own copy: both are several megabytes and the session already
    holds one.
    """
    seed._pricing = pricing
    return seed.load_population()


@pytest.fixture(scope="module")
def candidates(population):
    """Every row of the population, priced. The slow part, so done once."""
    return seed.build_candidates(population)


@pytest.fixture(scope="module")
def chosen(candidates):
    picked, unfilled = seed.choose(candidates)
    return picked, unfilled


@pytest.fixture
def quick_seed(monkeypatch, population, candidates):
    """
    The script's entry point, without re-reading and re-scoring the dataset.

    Only the two expensive steps are replaced, and with the real results of
    those steps. Everything the tests are about, which is the choosing, the
    writing and the recognising of rows already written, runs as it does on
    the command line.
    """
    monkeypatch.setattr(seed, "load_population", lambda: population)
    monkeypatch.setattr(seed, "build_candidates", lambda frame: candidates)


@pytest.fixture
def seed_db(tmp_path, monkeypatch):
    """A fresh database that the script's own engine will find."""
    url = f"sqlite:///{tmp_path / 'seeded.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_db_engine(url)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def seed_sessions(seed_db) -> sessionmaker[Session]:
    return sessionmaker(bind=seed_db, expire_on_commit=False)


@pytest.fixture
def seeded_client(seed_db, seed_sessions, quick_seed, pricing):
    """The API, against a database the script has just seeded."""
    from fastapi.testclient import TestClient

    from src.mentor.app import app

    assert seed.main([]) == 0

    def session_override():
        with seed_sessions() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        client.app.state.pricing = pricing
        client.app.state.pricing_error = None
        yield client
    app.dependency_overrides.clear()


def headers(mentor_id: int) -> dict[str, str]:
    return {MENTOR_ID_HEADER: str(mentor_id)}


# ---------------------------------------------------------------------------
# The population
# ---------------------------------------------------------------------------
def test_the_population_is_the_one_the_models_were_fitted_within(population, pricing):
    """
    Every filter the training run applied, applied again. A record outside
    them is one the models were never fitted to price, so a mentor seeded from
    it would demonstrate the system on input it does not support.
    """
    assert not population.empty
    assert population[dataset.TARGET_COLUMN].min() >= pricing.price_floor
    assert population[dataset.TARGET_COLUMN].max() <= pricing.price_ceiling
    assert (population[dataset.SCOPE_COLUMN] == dataset.LONG_STAY_SCOPE).all()
    assert (
        population[mapping.COLUMN_SESSION_FORMAT] == mapping.SESSION_FORMAT_VALUE
    ).all()
    assert (
        population[mapping.COLUMN_MAX_MENTEES]
        .between(mapping.MAX_MENTEES_MIN, mapping.MAX_MENTEES_MAX)
        .all()
    )
    assert (
        population[mapping.HISTORY_FIELDS["reviews_total"]] >= seed.MIN_REVIEWS
    ).all()
    assert (population[mapping.HISTORY_FIELDS["has_booking_data"]] == 1).all()


def test_every_record_in_the_population_can_be_described_as_a_mentor(population):
    """
    Each row has to yield a field, a group size and a complete track record,
    or it could not be seeded at all.
    """
    assert (
        population[mapping.COLUMN_FIELD]
        .map(lambda value: mapping.field_from_column_value(value) in mapping.FIELDS)
        .all()
    )
    assert population[list(mapping.FULL_COLUMNS)].notna().all().all()


# ---------------------------------------------------------------------------
# Choosing the five
# ---------------------------------------------------------------------------
def test_five_mentors_are_chosen(chosen):
    picked, unfilled = chosen

    assert len(picked) == seed.DEMO_MENTORS
    assert unfilled == []


def test_choosing_twice_chooses_the_same_five(candidates, chosen):
    picked, _ = chosen
    again, _ = seed.choose(candidates)

    assert [one.source_key for one in again] == [one.source_key for one in picked]


def test_the_five_are_in_five_different_fields_and_five_different_sizes(chosen):
    picked, _ = chosen

    assert len({one.field for one in picked}) == seed.DEMO_MENTORS
    assert len({one.max_mentees for one in picked}) == seed.DEMO_MENTORS


def test_exactly_one_of_the_five_takes_a_single_mentee(chosen):
    """
    A session for one is the other thing the platform offers, not a smaller
    group: it carries its own label and its per-mentee figure is its session
    price rather than a division of it. Five group sessions would leave both
    of those out of the demonstration, and two one-to-one mentors would be
    impossible anyway, since the five group sizes are all different.
    """
    picked, _ = chosen
    singles = [one for one in picked if one.max_mentees == seed.SINGLE_MENTEE]

    assert len(singles) == 1
    assert all(
        one.max_mentees >= mapping.GROUP_FROM_MENTEES
        for one in picked
        if one is not singles[0]
    )


def test_the_one_to_one_mentor_charges_inside_their_range(chosen):
    """
    The preferred case for the one-to-one mentor. The two cases outside the
    range are what the comparison exists to show, so they are spent on a
    group mentor if the population allows it, and this population does.
    """
    picked, _ = chosen
    (single,) = [one for one in picked if one.max_mentees == seed.SINGLE_MENTEE]

    assert single.position == "within"
    assert seed.band_of(single) in seed.ONE_TO_ONE_BAND_PREFERENCE[:3]


def test_the_one_to_one_mentor_is_labelled_a_one_to_one_session(chosen):
    picked, _ = chosen

    labels = [mapping.session_label(one.max_mentees) for one in picked]

    assert labels.count(mapping.LABEL_ONE_TO_ONE) == 1
    assert labels.count(mapping.LABEL_GROUP) == seed.DEMO_MENTORS - 1


def test_one_mentor_is_priced_above_their_range_one_within_and_one_below(chosen):
    """
    The three cases the comparison on a recommendation reports. Without one
    mentor in each, the demo cannot show what the comparison is for.
    """
    picked, _ = chosen

    assert {one.position for one in picked} == {"below", "within", "above"}


def test_the_five_sit_at_five_different_price_levels(chosen):
    picked, _ = chosen

    assert len({seed.band_of(one) for one in picked}) == seed.DEMO_MENTORS


def test_the_names_are_fictional_and_the_addresses_cannot_reach_anyone(chosen):
    picked, _ = chosen
    names = seed.names_for(len(picked))

    assert len(set(names)) == len(names)
    for name, candidate in zip(names, picked, strict=True):
        first, initial = name.split(" ")
        assert first in seed.FIRST_NAMES
        assert initial.endswith(".") and len(initial) == 2
        assert seed.email_for(name, candidate.source_key).endswith("@example.com")


def test_the_same_record_always_gets_the_same_skills():
    """
    Seeded on the record rather than on the run, so a mentor keeps the same
    profile across a reset and a reseed.
    """
    first = seed.skills_for(source_key=17, count=6)
    again = seed.skills_for(source_key=17, count=6)
    other = seed.skills_for(source_key=18, count=6)

    assert first == again
    assert first != other
    assert len(set(first)) == 6
    assert set(first) <= set(mapping.SKILLS)


# ---------------------------------------------------------------------------
# Writing them
# ---------------------------------------------------------------------------
def test_seeding_writes_five_mentors_each_with_a_service_and_a_record(
    seed_sessions, quick_seed
):
    assert seed.main([]) == 0

    with seed_sessions() as session:
        assert session.scalar(select(func.count()).select_from(Mentor)) == 5
        assert session.scalar(select(func.count()).select_from(Service)) == 5
        assert session.scalar(select(func.count()).select_from(MentorHistory)) == 5
        for mentor in session.scalars(select(Mentor)):
            assert mentor.is_demo is True
            assert mentor.source_key is not None
            assert mentor.history.is_complete is True
            assert len(mentor.services) == 1
            assert mentor.services[0].current_price > 0


def test_seeding_twice_does_not_duplicate_anyone(seed_sessions, quick_seed):
    assert seed.main([]) == 0
    assert seed.main([]) == 0

    with seed_sessions() as session:
        assert session.scalar(select(func.count()).select_from(Mentor)) == 5
        keys = list(session.scalars(select(Mentor.source_key)))
        assert len(set(keys)) == 5


def test_seeding_twice_writes_the_same_mentors(seed_sessions, quick_seed):
    assert seed.main([]) == 0
    with seed_sessions() as session:
        before = sorted(
            (mentor.source_key, mentor.full_name, mentor.email)
            for mentor in session.scalars(select(Mentor))
        )

    assert seed.main([]) == 0
    with seed_sessions() as session:
        after = sorted(
            (mentor.source_key, mentor.full_name, mentor.email)
            for mentor in session.scalars(select(Mentor))
        )

    assert before == after


def test_resetting_removes_the_mentors_and_everything_belonging_to_them(
    seed_sessions, quick_seed
):
    assert seed.main([]) == 0

    assert seed.main(["--reset"]) == 0

    with seed_sessions() as session:
        assert session.scalar(select(func.count()).select_from(Mentor)) == 0
        assert session.scalar(select(func.count()).select_from(Service)) == 0
        assert session.scalar(select(func.count()).select_from(MentorHistory)) == 0


def test_resetting_leaves_mentors_who_registered_alone(seed_sessions, quick_seed):
    """
    The flag is what the reset selects on, so a real registration survives it.
    """
    assert seed.main([]) == 0
    with seed_sessions() as session:
        session.add(
            Mentor(
                full_name="A. Mentor",
                email="real@example.com",
                years_mentoring_band="3_to_5",
                services_planned=1,
            )
        )
        session.commit()

    assert seed.main(["--reset"]) == 0

    with seed_sessions() as session:
        remaining = session.scalars(select(Mentor)).all()
        assert [mentor.email for mentor in remaining] == ["real@example.com"]


def test_seeding_after_a_reset_writes_the_same_five_again(
    seed_sessions, quick_seed, chosen
):
    picked, _ = chosen
    assert seed.main([]) == 0
    assert seed.main(["--reset"]) == 0
    assert seed.main([]) == 0

    with seed_sessions() as session:
        assert sorted(session.scalars(select(Mentor.source_key))) == sorted(
            candidate.source_key for candidate in picked
        )


def test_nothing_identifying_is_stored(seed_sessions, quick_seed, population):
    """
    The source row's own identifiers never leave the dataset. ``source_key``
    is a position in the filtered population, which is useless without the
    file and is not the identifier the row carries.
    """
    assert seed.main([]) == 0

    identifiers = set(population["id"].astype(int)) | set(
        population["host_id"].astype(int)
    )
    with seed_sessions() as session:
        for mentor in session.scalars(select(Mentor)):
            assert mentor.source_key not in identifiers
            assert mentor.email.endswith("@example.com")
            # The profile text is a per-field template and carries no figures
            # at all, so no identifier can have been written into it.
            written = " ".join(
                str(value)
                for value in (
                    mentor.full_name,
                    mentor.headline,
                    mentor.bio,
                    mentor.experience_summary,
                )
            )
            assert not any(character.isdigit() for character in written)


# ---------------------------------------------------------------------------
# What the API says about them
# ---------------------------------------------------------------------------
def test_every_seeded_mentor_is_listed_for_the_demo(seeded_client, chosen):
    picked, _ = chosen

    listed = seeded_client.get("/mentors/demo").json()

    assert len(listed) == len(picked)
    assert {entry["field_label"] for entry in listed} == {
        mapping.field_label(one.field) for one in picked
    }
    assert all(entry["has_history"] for entry in listed)
    # One of the five runs one-to-one sessions, so both labels the platform
    # offers appear in the list someone opens the demonstration on.
    labels = [entry["session_label"] for entry in listed]
    assert labels.count(mapping.SESSION_LABELS[mapping.LABEL_ONE_TO_ONE]) == 1
    assert labels.count(mapping.SESSION_LABELS[mapping.LABEL_GROUP]) == 4


def test_every_seeded_mentor_is_priced_by_the_full_model(seeded_client):
    for entry in seeded_client.get("/mentors/demo").json():
        mentor_id = entry["id"]
        mentor = seeded_client.get(
            f"/mentors/{mentor_id}", headers=headers(mentor_id)
        ).json()
        service = mentor["services"][0]

        priced = seeded_client.post(
            f"/services/{service['id']}/recommendations", headers=headers(mentor_id)
        )

        assert priced.status_code == 201, priced.text
        body = priced.json()
        assert body["model_used"] == "full"
        assert body["low_confidence"] is False


def test_the_api_gives_each_seeded_mentor_the_price_the_script_reported(
    seeded_client, seed_sessions, chosen
):
    """
    The test that matters most here. The script chooses the five on what the
    model says about them, so if the endpoints disagree, the five were chosen
    to show something the system does not do.
    """
    picked, _ = chosen
    by_key = {candidate.source_key: candidate for candidate in picked}

    with seed_sessions() as session:
        mentors = {
            mentor.source_key: (mentor.id, mentor.services[0].id)
            for mentor in session.scalars(select(Mentor))
        }

    assert set(mentors) == set(by_key)
    for source_key, (mentor_id, service_id) in mentors.items():
        candidate = by_key[source_key]
        body = seeded_client.post(
            f"/services/{service_id}/recommendations", headers=headers(mentor_id)
        ).json()

        assert body["recommended_price"] == candidate.advice.recommended_price
        assert body["price_low"] == candidate.advice.price_low
        assert body["price_high"] == candidate.advice.price_high


def test_the_api_reports_each_seeded_mentors_price_against_their_range(
    seeded_client, seed_sessions, chosen
):
    picked, _ = chosen
    by_key = {candidate.source_key: candidate for candidate in picked}

    with seed_sessions() as session:
        mentors = {
            mentor.source_key: (mentor.id, mentor.services[0].id)
            for mentor in session.scalars(select(Mentor))
        }

    positions = set()
    for source_key, (mentor_id, service_id) in mentors.items():
        candidate = by_key[source_key]
        body = seeded_client.post(
            f"/services/{service_id}/recommendations", headers=headers(mentor_id)
        ).json()

        assert body["current_price"] == candidate.current_price
        assert body["position_vs_range"] == candidate.position
        assert body["difference_vs_current_percent"] == round(
            (body["recommended_price"] - candidate.current_price)
            / candidate.current_price
            * 100,
            1,
        )
        positions.add(body["position_vs_range"])

    assert positions == {"below", "within", "above"}


def test_one_seeded_mentor_cannot_read_anothers_service_or_price(
    seeded_client, seed_sessions
):
    """
    The seeded mentors are the first several mentors in the database at once,
    which is the case the scoping rule exists for.
    """
    with seed_sessions() as session:
        mentors = [
            (mentor.id, mentor.services[0].id)
            for mentor in session.scalars(select(Mentor).order_by(Mentor.id))
        ]

    (first_id, _), (second_id, second_service) = mentors[0], mentors[1]

    assert (
        seeded_client.get(
            f"/mentors/{second_id}", headers=headers(first_id)
        ).status_code
        == 404
    )
    assert (
        seeded_client.post(
            f"/services/{second_service}/recommendations", headers=headers(first_id)
        ).status_code
        == 404
    )
    assert (
        seeded_client.post(
            f"/mentors/{second_id}/services",
            json={
                "field": "law",
                "max_mentees": 1,
                "min_commitment": 1,
                "skills": [],
                "profile_verified": False,
            },
            headers=headers(first_id),
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# The inputs it cannot work without
# ---------------------------------------------------------------------------
def test_a_missing_dataset_fails_with_a_message_naming_it(monkeypatch, tmp_path):
    """
    The script reports the dataset it could not find as its own failure, not
    as whatever the shared population module raised.
    """
    monkeypatch.setattr(dataset, "MASTER_DATASET", tmp_path / "absent.parquet")

    with pytest.raises(seed.SeedInputError) as error:
        seed.load_population()

    assert "master_listings.parquet" in str(error.value)
    assert "git-ignored" in str(error.value)


def test_the_skip_reason_says_where_the_dataset_comes_from():
    """
    A skipped run has to be distinguishable from a broken one, which means
    the reason has to say where the missing thing comes from.
    """
    assert "data/processed" in DATASET_SKIP_REASON
    assert "git-ignored" in DATASET_SKIP_REASON
