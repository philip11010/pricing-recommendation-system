"""
Tests for the demonstration seed script.

Four things have to hold about it, and only the first is obvious.

It has to be **deterministic**. The ten mentors are the demonstration: if they
change between runs, every screenshot, every figure quoted in the report and
every rehearsal of the demo describes a system that no longer exists.

It has to be **idempotent**. Running it twice is the normal mistake, and the
cost of getting it wrong is twenty mentors where there should be ten, half of
them duplicates of the other half.

The mentors it writes have to be **priced by the same code as everyone else**.
A seeded mentor whose price came from a shortcut in the script would
demonstrate the script rather than the system, so the test that matters most
here asks the API for a price and checks it against what the script said.

And the ten have to **show what they were chosen to show**: four one-to-one
mentors and six running groups, several fields, one mentor charging above
their advised range and one below, nine verified and one not. Each of those is
a thing the demonstration cannot do without, so each of them is a test.

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
from src.db.mentor_models import PricingDecision, PricingRecommendation
from src.mentor import mapping, security

from .conftest import DATASET_SKIP_REASON, dataset_present, headers

# What every test that runs the script passes. The month-by-month activity is
# built from the raw files, which are a different build output and are tested
# on their own in tests/test_mentor_activity.py; reading them in each of these
# tests would make the module several times slower and would not be about the
# seed.
NO_ACTIVITY = ["--no-activity"]

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
    picked, unmet = seed.choose(candidates)
    return picked, unmet


@pytest.fixture(scope="module")
def planned(chosen):
    """The ten, decided in full: names, verification, advice, decisions."""
    picked, _ = chosen
    return seed.plan_for(picked)


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

    assert seed.main(NO_ACTIVITY) == 0

    def session_override():
        with seed_sessions() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        client.app.state.pricing = pricing
        client.app.state.pricing_error = None
        yield client
    app.dependency_overrides.clear()


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
def test_ten_mentors_are_chosen(chosen):
    picked, unmet = chosen

    assert len(picked) == seed.DEMO_MENTORS
    assert unmet == []


def test_choosing_twice_chooses_the_same_ten(candidates, chosen):
    picked, _ = chosen
    again, _ = seed.choose(candidates)

    assert [one.source_key for one in again] == [one.source_key for one in picked]


def test_the_ten_cover_several_fields(chosen):
    """
    At least five, so the field list and the directory filters are visibly in
    use. Not ten: only part of the population offers a session for one
    mentee and those rows do not cover every field, so requiring one field
    each would be a requirement about this dataset rather than about the
    demonstration.
    """
    picked, _ = chosen

    assert len({one.field for one in picked}) >= seed.MIN_FIELDS


def test_four_of_the_ten_take_a_single_mentee_and_six_take_a_group(chosen):
    """
    A session for one is the other thing the platform offers, not a smaller
    group: it carries its own label and its per-mentee figure is its session
    price rather than a division of it. A demonstration of ten group mentors
    would leave both of those out.
    """
    picked, _ = chosen
    singles = [one for one in picked if one.max_mentees == seed.SINGLE_MENTEE]
    groups = [one for one in picked if one.max_mentees >= mapping.GROUP_FROM_MENTEES]

    assert len(singles) == seed.ONE_TO_ONE_MENTORS
    assert len(groups) == seed.GROUP_MENTORS
    assert all(2 <= one.max_mentees <= mapping.MAX_MENTEES_MAX for one in groups)


def test_the_group_mentors_run_sessions_of_different_sizes(chosen):
    """
    Six different sizes out of the seven the form offers above one, so the
    per-mentee figures differ between them and a reader can see that the
    price follows the size.
    """
    picked, _ = chosen
    sizes = [
        one.max_mentees
        for one in picked
        if one.max_mentees >= mapping.GROUP_FROM_MENTEES
    ]

    assert len(set(sizes)) == len(sizes)


def test_the_sessions_are_labelled_four_one_to_one_and_six_group(chosen):
    picked, _ = chosen

    labels = [mapping.session_label(one.max_mentees) for one in picked]

    assert labels.count(mapping.LABEL_ONE_TO_ONE) == seed.ONE_TO_ONE_MENTORS
    assert labels.count(mapping.LABEL_GROUP) == seed.GROUP_MENTORS


def test_one_mentor_is_priced_above_their_range_one_within_and_one_below(chosen):
    """
    The three cases the comparison on a recommendation reports. Without one
    mentor in each, the demo cannot show what the comparison is for.
    """
    picked, _ = chosen

    assert {one.position for one in picked} >= {"below", "within", "above"}


def test_the_ten_do_not_all_sit_at_the_same_price_level(chosen):
    picked, _ = chosen

    assert len({seed.band_of(one) for one in picked}) >= 3


# ---------------------------------------------------------------------------
# What will be written for each of them
# ---------------------------------------------------------------------------
def test_nine_of_the_ten_are_verified(planned):
    """
    One mentor without the checkmark, so the directory shows it as something
    a mentor can be without rather than as a decoration every card carries.
    """
    verified = [plan for plan in planned if plan.verified]

    assert len(verified) == seed.DEMO_MENTORS - seed.UNVERIFIED_MENTORS
    assert len(planned) - len(verified) == seed.UNVERIFIED_MENTORS


def test_the_unverified_mentor_is_priced_as_an_unverified_mentor(planned):
    """
    Verification is one of the eight inputs behind a price, so the one mentor
    who is not verified has to be priced again with the answer turned off:
    the price they are shown has to be the price of the service they have.
    """
    (unverified,) = [plan for plan in planned if not plan.verified]

    expected = seed.advice_for(unverified.candidate, verified=False)

    assert unverified.advice.recommended_price == expected.recommended_price
    assert unverified.candidate.advice.recommended_price != 0


def test_the_unverified_mentor_is_not_one_of_the_three_price_positions(planned):
    """
    The three positions are filled first and the tenth mentor is the one left
    unverified, so repricing them cannot cost the demonstration the case the
    comparison exists to show.
    """
    verified = [plan for plan in planned if plan.verified]

    assert {plan.position for plan in verified} >= {"below", "within", "above"}


def test_every_mentor_answered_their_advice_consistently_with_their_price(planned):
    """
    The answers are not assigned at random: a mentor charging roughly what
    the model advises has accepted it, one charging clearly more or less has
    rejected it and said what they charge instead, and the two in between
    have modified it.
    """
    for plan in planned:
        advised = plan.advice.recommended_price
        if plan.action == "accepted":
            assert plan.final_price == advised
        elif plan.action == "modified":
            assert plan.final_price != advised
            assert plan.final_price == plan.candidate.current_price
        else:
            assert plan.action == "rejected"
            assert plan.final_price == plan.candidate.current_price


def test_the_answers_cover_more_than_one_of_the_three(planned):
    """
    A demonstration in which every mentor accepted the advice would say
    nothing about a system whose whole point is that the mentor decides.
    """
    assert len({plan.action for plan in planned}) >= 2


def test_planning_twice_plans_the_same_ten(chosen):
    picked, _ = chosen

    first = seed.plan_for(picked)
    again = seed.plan_for(picked)

    assert [(plan.display_name, plan.email, plan.action) for plan in first] == [
        (plan.display_name, plan.email, plan.action) for plan in again
    ]


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
def test_seeding_writes_ten_mentors_each_with_a_service_and_a_record(
    seed_sessions, quick_seed
):
    assert seed.main(NO_ACTIVITY) == 0

    with seed_sessions() as session:
        count = seed.DEMO_MENTORS
        assert session.scalar(select(func.count()).select_from(Mentor)) == count
        assert session.scalar(select(func.count()).select_from(Service)) == count
        assert session.scalar(select(func.count()).select_from(MentorHistory)) == count
        for mentor in session.scalars(select(Mentor)):
            assert mentor.is_demo is True
            assert mentor.source_key is not None
            assert mentor.history.is_complete is True
            assert len(mentor.services) == 1
            assert mentor.services[0].current_price > 0


def test_every_seeded_mentor_has_a_price_and_an_answer_to_it(seed_sessions, quick_seed):
    """
    The whole flow rather than just a profile, so a fresh database has a
    dashboard, a history and a decision count with something in them.
    """
    assert seed.main(NO_ACTIVITY) == 0

    with seed_sessions() as session:
        count = seed.DEMO_MENTORS
        assert (
            session.scalar(select(func.count()).select_from(PricingRecommendation))
            == count
        )
        assert (
            session.scalar(select(func.count()).select_from(PricingDecision)) == count
        )
        for record in session.scalars(select(PricingRecommendation)):
            assert record.model_used == "full"
            assert record.low_confidence is False
            assert record.price_low <= record.recommended_price <= record.price_high
            assert record.inputs_snapshot
            assert record.status == record.decision.action


def test_nine_seeded_mentors_are_verified_and_one_is_not(seed_sessions, quick_seed):
    assert seed.main(NO_ACTIVITY) == 0

    with seed_sessions() as session:
        mentors = list(session.scalars(select(Mentor)))
        verified = [mentor for mentor in mentors if mentor.verified]

        assert len(verified) == seed.DEMO_MENTORS - seed.UNVERIFIED_MENTORS
        # The flag on the service is the same claim in the form the model
        # reads, so the two may not disagree.
        for mentor in mentors:
            assert mentor.services[0].profile_verified == mentor.verified


def test_every_seeded_mentor_can_sign_in_with_the_demo_password(
    seed_sessions, quick_seed
):
    assert seed.main(NO_ACTIVITY) == 0

    with seed_sessions() as session:
        for mentor in session.scalars(select(Mentor)):
            assert security.verify_password(
                seed.DEFAULT_DEMO_PASSWORD, mentor.password_hash
            )


def test_the_demo_password_can_be_set_in_the_environment(
    seed_sessions, quick_seed, monkeypatch
):
    monkeypatch.setenv(seed.DEMO_PASSWORD_VARIABLE, "another-demo-password")

    assert seed.main(NO_ACTIVITY) == 0

    with seed_sessions() as session:
        mentor = session.scalar(select(Mentor))
        assert security.verify_password("another-demo-password", mentor.password_hash)
        assert not security.verify_password(
            seed.DEFAULT_DEMO_PASSWORD, mentor.password_hash
        )


def test_the_seed_prints_the_addresses_and_the_password(
    seed_sessions, quick_seed, capsys
):
    """
    They are fictional accounts on a documentation domain, created to be
    signed in to during a demonstration, so whoever ran the script is told
    how.
    """
    assert seed.main(NO_ACTIVITY) == 0

    printed = capsys.readouterr().out
    assert seed.DEFAULT_DEMO_PASSWORD in printed
    assert printed.count("@example.com") >= seed.DEMO_MENTORS


def test_the_seed_builds_the_activity_unless_told_not_to(
    seed_sessions, quick_seed, monkeypatch
):
    """
    The chart on a mentor's page needs the raw files, which are a separate
    build output, so the seed asks for it rather than owning it.
    """
    called = []
    monkeypatch.setattr(
        seed, "build_activity", lambda session: called.append(session) or report()
    )

    assert seed.main([]) == 0
    assert len(called) == 1

    assert seed.main(NO_ACTIVITY) == 0
    assert len(called) == 1


def report():
    from scripts.build_demo_activity import ActivityReport

    return ActivityReport()


def test_a_seed_whose_activity_cannot_be_built_still_succeeds_and_says_so(
    seed_sessions, quick_seed, monkeypatch, capsys
):
    """
    The raw files are git-ignored and the mentors are useful without them.
    Failing the whole seed over a chart would leave a database with nobody in
    it.
    """

    def refuse(session):
        raise seed.ActivityInputError("missing the reviews file: data/raw/reviews.csv")

    monkeypatch.setattr(seed, "build_activity", refuse)

    assert seed.main([]) == 0

    printed = capsys.readouterr().out
    assert "build_demo_activity" in printed
    assert "reviews.csv" in printed


def test_seeding_twice_does_not_duplicate_anyone(seed_sessions, quick_seed):
    assert seed.main(NO_ACTIVITY) == 0
    assert seed.main(NO_ACTIVITY) == 0

    with seed_sessions() as session:
        count = seed.DEMO_MENTORS
        assert session.scalar(select(func.count()).select_from(Mentor)) == count
        keys = list(session.scalars(select(Mentor.source_key)))
        assert len(set(keys)) == count
        assert (
            session.scalar(select(func.count()).select_from(PricingRecommendation))
            == count
        )


def test_seeding_twice_writes_the_same_mentors(seed_sessions, quick_seed):
    assert seed.main(NO_ACTIVITY) == 0
    with seed_sessions() as session:
        before = sorted(
            (mentor.source_key, mentor.full_name, mentor.email)
            for mentor in session.scalars(select(Mentor))
        )

    assert seed.main(NO_ACTIVITY) == 0
    with seed_sessions() as session:
        after = sorted(
            (mentor.source_key, mentor.full_name, mentor.email)
            for mentor in session.scalars(select(Mentor))
        )

    assert before == after


def test_resetting_removes_the_mentors_and_everything_belonging_to_them(
    seed_sessions, quick_seed
):
    assert seed.main(NO_ACTIVITY) == 0

    assert seed.main(["--reset"]) == 0

    with seed_sessions() as session:
        assert session.scalar(select(func.count()).select_from(Mentor)) == 0
        assert session.scalar(select(func.count()).select_from(Service)) == 0
        assert session.scalar(select(func.count()).select_from(MentorHistory)) == 0


def test_resetting_leaves_mentors_who_registered_alone(seed_sessions, quick_seed):
    """
    The flag is what the reset selects on, so a real registration survives it.
    """
    assert seed.main(NO_ACTIVITY) == 0
    with seed_sessions() as session:
        session.add(
            Mentor(
                full_name="A. Mentor",
                email="real@example.com",
                years_mentoring_band="3_to_5",
            )
        )
        session.commit()

    assert seed.main(["--reset"]) == 0

    with seed_sessions() as session:
        remaining = session.scalars(select(Mentor)).all()
        assert [mentor.email for mentor in remaining] == ["real@example.com"]


def test_seeding_after_a_reset_writes_the_same_ten_again(
    seed_sessions, quick_seed, chosen
):
    picked, _ = chosen
    assert seed.main(NO_ACTIVITY) == 0
    assert seed.main(["--reset"]) == 0
    assert seed.main(NO_ACTIVITY) == 0

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
    assert seed.main(NO_ACTIVITY) == 0

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
    # Four of the ten run one-to-one sessions, so both labels the platform
    # offers appear in the list someone opens the demonstration on.
    labels = [entry["session_label"] for entry in listed]
    assert (
        labels.count(mapping.SESSION_LABELS[mapping.LABEL_ONE_TO_ONE])
        == seed.ONE_TO_ONE_MENTORS
    )
    assert (
        labels.count(mapping.SESSION_LABELS[mapping.LABEL_GROUP]) == seed.GROUP_MENTORS
    )


def test_every_seeded_mentor_is_on_the_public_directory(seeded_client, chosen):
    """
    The directory is the list a mentee reads, and a demonstration where it is
    empty shows nothing. A seeded mentor appears on exactly the same terms as
    one who registered.
    """
    picked, _ = chosen

    listed = seeded_client.get("/mentors", params={"limit": 100}).json()

    assert listed["total"] == len(picked)
    for card in listed["items"]:
        assert card["price"] > 0
        assert card["review_count"] > 0
        assert card["service_name"]
    assert sum(1 for card in listed["items"] if card["verified"]) == (
        seed.DEMO_MENTORS - seed.UNVERIFIED_MENTORS
    )


def test_every_seeded_mentor_can_sign_in_through_the_api(seeded_client, seed_sessions):
    """
    The demonstration accounts are accounts: whoever is running the demo signs
    in as one of them.
    """
    with seed_sessions() as session:
        addresses = [mentor.email for mentor in session.scalars(select(Mentor))]

    assert len(addresses) == seed.DEMO_MENTORS
    for address in addresses:
        response = seeded_client.post(
            "/auth/login",
            json={"email": address, "password": seed.DEFAULT_DEMO_PASSWORD},
        )

        assert response.status_code == 200, response.text
        assert response.json()["mentor"]["email"] == address


def test_a_seeded_mentors_dashboard_opens_on_a_sentence(seeded_client, seed_sessions):
    """
    The demonstration's first screen. A seeded mentor has a price, an answer
    and comparable mentors, so the sentence has everything it needs.
    """
    with seed_sessions() as session:
        mentor_id = session.scalar(select(Mentor.id).order_by(Mentor.id))

    body = seeded_client.get(
        f"/mentors/{mentor_id}/dashboard", headers=headers(mentor_id)
    ).json()

    assert body["headline"]["your_price"] > 0
    assert body["headline"]["sentence"]
    assert body["totals"]["recommendations"] == 1
    assert sum(body["totals"]["decision_counts"].values()) == 1


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
    seeded_client, seed_sessions, planned
):
    """
    The test that matters most here. The script chooses the ten on what the
    model says about them, so if the endpoints disagree, the ten were chosen
    to show something the system does not do.

    Checked against the plan rather than the candidate, because the one
    mentor who is not verified is priced again before they are written: the
    price the endpoints give is the price of the service they have.
    """
    by_key = {plan.candidate.source_key: plan for plan in planned}

    with seed_sessions() as session:
        mentors = {
            mentor.source_key: (mentor.id, mentor.services[0].id)
            for mentor in session.scalars(select(Mentor))
        }

    assert set(mentors) == set(by_key)
    for source_key, (mentor_id, service_id) in mentors.items():
        plan = by_key[source_key]
        body = seeded_client.post(
            f"/services/{service_id}/recommendations", headers=headers(mentor_id)
        ).json()

        assert body["recommended_price"] == plan.advice.recommended_price
        assert body["price_low"] == plan.advice.price_low
        assert body["price_high"] == plan.advice.price_high


def test_the_api_reports_each_seeded_mentors_price_against_their_range(
    seeded_client, seed_sessions, planned
):
    """
    What each of them charges, against what they are advised. The price they
    charge is the one they settled on when they answered the advice, which
    for the mentor who accepted it is the advised price itself.
    """
    by_key = {plan.candidate.source_key: plan for plan in planned}

    with seed_sessions() as session:
        mentors = {
            mentor.source_key: (mentor.id, mentor.services[0].id)
            for mentor in session.scalars(select(Mentor))
        }

    positions = set()
    for source_key, (mentor_id, service_id) in mentors.items():
        plan = by_key[source_key]
        body = seeded_client.post(
            f"/services/{service_id}/recommendations", headers=headers(mentor_id)
        ).json()

        assert body["current_price"] == plan.final_price
        assert body["position_vs_range"] == plan.position
        assert body["difference_vs_current_percent"] == round(
            (body["recommended_price"] - plan.final_price) / plan.final_price * 100,
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
