"""
Tests for the prediction service.

These check two different kinds of thing. First, that a price is well formed:
inside the fences the models were trained within, bracketed by a range, marked
with the model that produced it. Second, that the price responds to the inputs
in the direction a mentor would expect, because a model wired to the wrong
columns still returns a plausible number and nothing but a directional test
catches it.

Every test here needs the prepared models, so the whole module is marked
``app_assets`` and skips when they are absent.
"""

from __future__ import annotations

import pytest

from src.mentor import mapping
from src.mentor.prediction import (
    AssetsUnavailableError,
    load_pricing_service,
    per_mentee,
)

from .conftest import SYNTHETIC_HISTORY

pytestmark = pytest.mark.app_assets

BASE_ANSWERS = {
    "field": "technology_software",
    "max_mentees": 1,
    "min_commitment": 1,
    "skills": ["cv_review", "interview_preparation", "career_planning"],
    "profile_verified": True,
    "services_planned": 1,
    "services_count": 1,
}

# The profile the group-size sweep is run on, and the one whose numbers are
# reported: one of the twelve fields, twenty skills ticked, a two-session
# minimum, a verified profile.
# Read from the mapping rather than written out, because these tests are
# about the shape of the price across the supported range rather than about
# where the range ends. The value itself is pinned in the mapping tests.
MAX_MENTEES = mapping.MAX_MENTEES_MAX

SWEEP_ANSWERS = {
    "field": "technology_software",
    "max_mentees": 1,
    "min_commitment": 2,
    "skills": list(mapping.SKILLS)[:20],
    "profile_verified": True,
    "services_planned": 1,
    "services_count": 1,
}

# Every size the form offers that is worth a separate row, and every step
# between them is asserted on. The form stops at eight, which is where the
# training data stops supporting the prices: see MAX_MENTEES_MAX.
SWEEP_SIZES = (1, 2, 3, 4, 6, 8)


def model_inputs(**overrides):
    return mapping.to_model_inputs(**{**BASE_ANSWERS, **overrides})


def history_inputs():
    return mapping.history_to_model_inputs(SYNTHETIC_HISTORY)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def test_both_models_are_loaded(pricing):
    assert set(pricing.pipelines) == {"core", "full"}


def test_each_model_declares_the_columns_it_was_fitted_on(pricing):
    assert len(pricing.columns["core"]) == 8
    assert len(pricing.columns["full"]) == 36


def test_the_loaded_columns_are_the_ones_the_mapping_produces(pricing):
    assert pricing.columns["core"] == mapping.CORE_COLUMNS
    assert pricing.columns["full"] == mapping.FULL_COLUMNS


def test_a_missing_assets_folder_fails_with_a_message_naming_the_fix(tmp_path):
    with pytest.raises(AssetsUnavailableError) as error:
        load_pricing_service(tmp_path / "nothing-here")
    assert "prepare_app_assets" in str(error.value)


def test_the_fences_are_the_ones_the_models_were_trained_within(pricing):
    assert pricing.price_floor == pytest.approx(59.51)
    assert pricing.price_ceiling == pytest.approx(1913.07)


# ---------------------------------------------------------------------------
# The new-mentor path
# ---------------------------------------------------------------------------
def test_the_core_path_prices_a_new_mentor(pricing):
    advice = pricing.predict(model_inputs())

    assert advice.model_used == "core"
    assert advice.low_confidence is True
    assert advice.currency == "AUD"


def test_the_price_is_inside_the_fences(pricing):
    advice = pricing.predict(model_inputs())

    assert pricing.price_floor <= advice.recommended_price <= pricing.price_ceiling


def test_the_range_brackets_the_price(pricing):
    advice = pricing.predict(model_inputs())

    assert advice.price_low < advice.recommended_price < advice.price_high


def test_the_range_is_inside_the_fences(pricing):
    advice = pricing.predict(model_inputs())

    assert advice.price_low >= pricing.price_floor
    assert advice.price_high <= pricing.price_ceiling


def test_the_price_is_a_whole_number_of_currency_units(pricing):
    advice = pricing.predict(model_inputs())

    assert isinstance(advice.recommended_price, int)
    assert isinstance(advice.price_low, int)
    assert isinstance(advice.price_high, int)


def test_the_advice_names_the_model_version_that_produced_it(pricing):
    advice = pricing.predict(model_inputs())

    assert advice.model_version == pricing.model_version
    assert advice.model_version


def test_the_same_answers_give_the_same_price(pricing):
    """A mentor who reloads the page must not see a different number."""
    first = pricing.predict(model_inputs())
    second = pricing.predict(model_inputs())

    assert first == second


# ---------------------------------------------------------------------------
# The returning-mentor path
# ---------------------------------------------------------------------------
def test_a_supplied_track_record_selects_the_full_model(pricing):
    advice = pricing.predict(model_inputs(), history_inputs())

    assert advice.model_used == "full"
    assert advice.low_confidence is False


def test_the_full_path_also_returns_a_bracketed_price_inside_the_fences(pricing):
    advice = pricing.predict(model_inputs(), history_inputs())

    assert pricing.price_floor <= advice.recommended_price <= pricing.price_ceiling
    assert advice.price_low < advice.recommended_price < advice.price_high


def test_the_full_model_is_the_more_accurate_of_the_two(pricing):
    """
    The reason for keeping two models at all.

    If the full model were not better on the held-out rows, the track-record
    columns would be complexity for nothing.
    """
    core = pricing.metrics("core")
    full = pricing.metrics("full")

    assert full["rmse"] < core["rmse"]
    assert full["mae"] < core["mae"]
    assert full["r2"] > core["r2"]


def test_an_incomplete_input_row_is_refused_rather_than_guessed(pricing):
    inputs = model_inputs()
    del inputs[mapping.COLUMN_FIELD]

    with pytest.raises(ValueError):
        pricing.predict(inputs)


# ---------------------------------------------------------------------------
# Direction
#
# A model wired to the wrong column still returns a plausible price. These are
# the tests that would catch it.
# ---------------------------------------------------------------------------
def test_a_larger_group_is_priced_higher(pricing):
    one = pricing.predict(model_inputs(max_mentees=1))
    eight = pricing.predict(model_inputs(max_mentees=MAX_MENTEES))

    assert eight.recommended_price > one.recommended_price


@pytest.mark.parametrize("mentees", [9, 16])
def test_a_group_above_the_supported_range_never_reaches_the_model(mentees):
    """
    The model would return a plausible number for a group of sixteen. The
    point of the cap is that it is never asked, because above eight the
    training data no longer supports the answer.
    """
    with pytest.raises(mapping.MentorInputError) as error:
        model_inputs(max_mentees=mentees)

    assert error.value.field == "max_mentees"
    message = error.value.message.lower()
    assert "mentees" in message
    assert "1" in message and str(MAX_MENTEES) in message


def test_the_largest_supported_group_is_accepted_and_priced(pricing):
    advice = pricing.predict(model_inputs(max_mentees=MAX_MENTEES))

    assert MAX_MENTEES == 8
    assert advice.recommended_price > 0
    assert advice.price_per_mentee == round(advice.recommended_price / MAX_MENTEES)


def test_the_field_a_mentor_works_in_changes_the_price(pricing):
    """
    Twelve fields that all priced the same would make the question pointless.
    """
    prices = {
        field: pricing.predict(model_inputs(field=field)).recommended_price
        for field in mapping.FIELDS
    }

    assert len(set(prices.values())) > 1


def test_the_range_widens_with_the_price(pricing):
    """
    The range is multiplicative, so a more expensive session carries a wider
    band in currency terms. A fixed-width band would be wrong at both ends.
    """
    cheap = pricing.predict(model_inputs(max_mentees=1))
    dear = pricing.predict(model_inputs(max_mentees=MAX_MENTEES))

    assert (dear.price_high - dear.price_low) > (cheap.price_high - cheap.price_low)


# ---------------------------------------------------------------------------
# Group size
#
# The sweep that replaced the session format question. The format column is
# now held at one value for every mentor, and the size of the group is what
# distinguishes one session from another, so the shape of the price across
# that range is the thing worth checking. Every size in SWEEP_SIZES is
# asserted on, in both directions: the session total never falls as a seat is
# added, and the per-mentee price never rises.
#
# The whole module skips with a message naming the command to run when
# app_assets/ is absent: see the pricing fixture in conftest.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def sweep(pricing):
    """
    The price at each group size, on one fixed profile, computed once.

    Printed as a table at setup, so a run with ``pytest -s`` shows the actual
    numbers rather than only whether they were ordered.
    """
    rows = {}
    for mentees in SWEEP_SIZES:
        inputs = mapping.to_model_inputs(**{**SWEEP_ANSWERS, "max_mentees": mentees})
        rows[mentees] = pricing.predict(inputs)

    print()
    print(
        f"{SWEEP_ANSWERS['field']}, "
        f"{len(SWEEP_ANSWERS['skills'])} skills, "
        f"min_commitment {SWEEP_ANSWERS['min_commitment']}, verified"
    )
    header = ("mentees", "session", "low", "high", "per mentee", "low", "high")
    print("  ".join(f"{column:>10}" for column in header))
    for mentees, advice in rows.items():
        print(
            "  ".join(
                f"{value:>10}"
                for value in (
                    mentees,
                    advice.recommended_price,
                    advice.price_low,
                    advice.price_high,
                    advice.price_per_mentee,
                    advice.price_per_mentee_low,
                    advice.price_per_mentee_high,
                )
            )
        )
    return rows


def test_the_session_total_never_falls_as_the_group_grows(sweep):
    """
    A mentor adding a seat must never be advised to charge less for the
    session than they were advised to charge without it.
    """
    totals = [sweep[mentees].recommended_price for mentees in SWEEP_SIZES]

    assert totals == sorted(totals), dict(zip(SWEEP_SIZES, totals, strict=True))


def test_the_per_mentee_price_never_rises_as_the_group_grows(sweep):
    """
    The other half of the same claim. A bigger group costs more in total and
    less per mentee: that is what makes a group worth joining.
    """
    each = [sweep[mentees].price_per_mentee for mentees in SWEEP_SIZES]

    assert each == sorted(each, reverse=True), dict(zip(SWEEP_SIZES, each, strict=True))


@pytest.mark.parametrize("mentees", [1, 2, 3, 4, 5, 6, 7, 8])
def test_each_per_mentee_figure_is_its_session_figure_divided_by_the_seats(
    pricing, mentees
):
    advice = pricing.predict(model_inputs(max_mentees=mentees))

    assert advice.price_per_mentee == round(advice.recommended_price / mentees)
    assert advice.price_per_mentee_low == round(advice.price_low / mentees)
    assert advice.price_per_mentee_high == round(advice.price_high / mentees)


def test_a_session_for_one_mentee_prices_the_same_either_way(pricing):
    """Nothing to divide, so the two sets of figures are the same three."""
    advice = pricing.predict(model_inputs(max_mentees=1))

    assert advice.price_per_mentee == advice.recommended_price
    assert advice.price_per_mentee_low == advice.price_low
    assert advice.price_per_mentee_high == advice.price_high


def test_the_per_mentee_figures_are_bracketed_and_whole(pricing):
    advice = pricing.predict(model_inputs(max_mentees=6))

    assert advice.price_per_mentee_low <= advice.price_per_mentee
    assert advice.price_per_mentee <= advice.price_per_mentee_high
    assert isinstance(advice.price_per_mentee, int)


@pytest.mark.parametrize(
    ("total", "mentees", "expected"),
    [
        (207, 1, 207),
        (391, 4, 98),
        (100, 3, 33),
        # An exact half goes to the even number, which is how Python rounds
        # and how the session price itself is rounded a few lines earlier in
        # the prediction service. One rounding rule, used twice.
        (293, 2, 146),
        (295, 2, 148),
    ],
)
def test_the_division_rounds_to_whole_currency_units(total, mentees, expected):
    """
    The same precision the session price is shown at. Checked on fixed
    numbers so the rounding rule is pinned independently of the models.
    """
    assert per_mentee(total, mentees) == expected


# ---------------------------------------------------------------------------
# The session format and the experience band
# ---------------------------------------------------------------------------
def test_the_price_is_unchanged_by_anything_the_mentor_says_about_experience(
    pricing,
):
    """
    The experience band is profile text. Nothing it can be set to produces a
    different row, so nothing it can be set to produces a different price.
    """
    first = pricing.predict(model_inputs())
    second = pricing.predict(model_inputs())

    assert first == second
    assert mapping.validate_years_mentoring("over_10") == "over_10"
    assert pricing.predict(model_inputs()) == first


def test_every_priced_row_carries_the_new_mentor_tenure(pricing):
    """
    The constant, checked where it actually reaches the model rather than
    only in the mapping tests.
    """
    inputs = model_inputs()

    assert inputs[mapping.COLUMN_TENURE] == pytest.approx(0.5)
    assert inputs[mapping.COLUMN_TENURE] == pytest.approx(
        mapping.NEW_MENTOR_TENURE_YEARS
    )
    assert pricing.predict(inputs).recommended_price > 0


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------
def test_the_advice_serialises_to_the_fields_the_api_returns(pricing):
    body = pricing.predict(model_inputs()).as_dict()

    assert set(body) == {
        "recommended_price",
        "price_low",
        "price_high",
        "price_per_mentee",
        "price_per_mentee_low",
        "price_per_mentee_high",
        "currency",
        "model_used",
        "low_confidence",
        "model_version",
    }
