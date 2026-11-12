"""
Tests for the one promise a mentor can check without reading anything.

Offering more must never be worth less. A mentor who ticks one more skill, or
who opens one more seat, is offering more of what they do, and a suggested
price that fell when they did would not be advice they could act on: it would
read as the system telling them to narrow what they offer.

The models do not provide that on their own. Both learned shapes for breadth
of offering and for group size that dip in places, which is an artefact of the
rows they were fitted on rather than a rule. So the prediction service reads a
price off a monotone envelope over those two inputs, and this module is where
the envelope is held to its claim.

Two kinds of test here, and the pairing matters. The sweeps assert the
property across the whole surface the form can produce, which is what makes it
a guarantee rather than a spot check. The pinned cases assert that the raw
model really does dip where the sweeps would otherwise have nothing to prove:
if a retrained model stopped dipping at those points, the pinned tests would
say so rather than passing quietly on a correction that was no longer doing
anything.

Every test needs the prepared models, so the whole module skips when they are
absent. The sweeps are module scoped and batched into one call per model,
because the alternative is several thousand single-row calls to arrive at the
same numbers.
"""

from __future__ import annotations

import pytest

from src.mentor import mapping
from src.mentor.prediction import CORE, FULL, SKILL_COUNT_MIN

from .conftest import SYNTHETIC_HISTORY

pytestmark = pytest.mark.app_assets

SKILL_IDS = tuple(mapping.SKILLS)

# Every count the form can produce, from a service with nothing ticked to one
# with everything.
SKILL_COUNTS = tuple(range(SKILL_COUNT_MIN, mapping.SKILL_COUNT + 1))

GROUP_SIZES = tuple(range(mapping.MAX_MENTEES_MIN, mapping.MAX_MENTEES_MAX + 1))

VERIFICATIONS = (False, True)

# One profile where the raw core model falls a long way as skills are added:
# the suggested price for a group of eight in this field drops by nearly four
# hundred between twelve skills and thirteen. Pinned so the correction is
# always being asked to do something.
CORE_DIP = {
    "field": "medicine_health",
    "max_mentees": 8,
    "profile_verified": False,
}

# The same for the full model, which dips later and less steeply.
FULL_DIP = {
    "field": "law",
    "max_mentees": 7,
    "profile_verified": False,
}


def answers(field: str, max_mentees: int, verified: bool, skills: int) -> dict:
    """One profile at one skill count, as the mapping layer builds it."""
    return mapping.to_model_inputs(
        field=field,
        max_mentees=max_mentees,
        min_commitment=mapping.MIN_COMMITMENT_DEFAULT,
        skills=list(SKILL_IDS[:skills]),
        profile_verified=verified,
        services_count=1,
    )


def history() -> dict:
    return mapping.history_to_model_inputs(SYNTHETIC_HISTORY)


def ladder_rows(field: str, max_mentees: int, verified: bool, model_used: str):
    """One profile at every skill count, in order."""
    rows = [answers(field, max_mentees, verified, count) for count in SKILL_COUNTS]
    if model_used == FULL:
        rows = [{**row, **history()} for row in rows]
    return rows


def is_rising(values: list[int]) -> bool:
    return all(
        later >= earlier for earlier, later in zip(values, values[1:], strict=False)
    )


@pytest.fixture(scope="module")
def sweeps(pricing):
    """
    Every field, every group size, verified and not, at every skill count.

    Scored as one call per model rather than one per profile: there are close
    to six thousand profiles on each side and each of them is an envelope of
    its own, so the batching is what makes this a test rather than a wait.
    """
    answered = {}
    for model_used in (CORE, FULL):
        plan = [
            (field, mentees, verified)
            for field in mapping.FIELDS
            for mentees in GROUP_SIZES
            for verified in VERIFICATIONS
        ]
        rows = [
            row
            for field, mentees, verified in plan
            for row in ladder_rows(field, mentees, verified, model_used)
        ]
        advice = pricing.predict_many(rows, model_used)
        step = len(SKILL_COUNTS)
        answered[model_used] = {
            key: advice[index * step : (index + 1) * step]
            for index, key in enumerate(plan)
        }
    return answered


# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_the_price_never_falls_as_a_skill_is_added(sweeps, model_used):
    """
    The claim, over every profile the form can produce.

    A failure here names the profile and prints the whole ladder, because the
    useful question when it breaks is where along the ladder it broke.
    """
    for key, ladder in sweeps[model_used].items():
        prices = [advice.recommended_price for advice in ladder]
        assert is_rising(prices), (model_used, key, prices)


@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_neither_end_of_the_range_falls_as_a_skill_is_added(sweeps, model_used):
    """
    The range is derived from the corrected price, so it inherits the shape.

    Worth asserting separately all the same: a mentor reads the range as much
    as the figure, and a band that narrowed downwards while the figure held
    would be the same broken promise in a different place.
    """
    for key, ladder in sweeps[model_used].items():
        lows = [advice.price_low for advice in ladder]
        highs = [advice.price_high for advice in ladder]
        assert is_rising(lows), (model_used, key, "low", lows)
        assert is_rising(highs), (model_used, key, "high", highs)


@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_the_per_mentee_price_never_falls_as_a_skill_is_added(sweeps, model_used):
    """
    The figure a mentee is quoted moves with the session it is divided out of.

    The group size is fixed along one ladder, so this follows from the session
    total. It is asserted because it is the number shown largest on the live
    preview, and a derived figure that disagreed with the one it was derived
    from would be the version a mentor actually noticed.
    """
    for key, ladder in sweeps[model_used].items():
        each = [advice.price_per_mentee for advice in ladder]
        assert is_rising(each), (model_used, key, each)


@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_the_price_never_falls_as_a_seat_is_added(sweeps, model_used):
    """
    The other input a mentor can only raise by offering more.

    Read across the sweep rather than along it: the same field, the same
    verification and the same skill count, at each group size in turn.
    """
    for field in mapping.FIELDS:
        for verified in VERIFICATIONS:
            for index, count in enumerate(SKILL_COUNTS):
                prices = [
                    sweeps[model_used][(field, mentees, verified)][
                        index
                    ].recommended_price
                    for mentees in GROUP_SIZES
                ]
                assert is_rising(prices), (model_used, field, verified, count, prices)


# ---------------------------------------------------------------------------
# The dips the correction exists for
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("model_used", "profile"),
    [(CORE, CORE_DIP), (FULL, FULL_DIP)],
)
def test_the_raw_model_really_does_fall_on_these_profiles(pricing, model_used, profile):
    """
    The regression case, stated as what it is a regression against.

    Without this the sweeps above could pass on a model that never dipped, and
    nobody would know the correction had stopped mattering. The numbers are
    not pinned: what is pinned is that somewhere along this profile's ladder
    the raw model asks a mentor to charge less for offering more.
    """
    row = answers(
        profile["field"],
        profile["max_mentees"],
        profile["profile_verified"],
        mapping.SKILL_COUNT,
    )
    if model_used == FULL:
        row = {**row, **history()}

    raw = [
        int(round(price))
        for price in pricing.raw_prices_by_skill_count(row, model_used)
    ]

    assert not is_rising(raw), (model_used, profile, raw)


@pytest.mark.parametrize(
    ("model_used", "profile"),
    [(CORE, CORE_DIP), (FULL, FULL_DIP)],
)
def test_the_envelope_holds_the_price_up_through_that_fall(
    pricing, model_used, profile
):
    """The same profile, priced the way the application prices it."""
    rows = ladder_rows(
        profile["field"],
        profile["max_mentees"],
        profile["profile_verified"],
        model_used,
    )
    prices = [
        advice.recommended_price for advice in pricing.predict_many(rows, model_used)
    ]

    assert is_rising(prices), (model_used, profile, prices)


def test_the_corrected_price_is_never_below_the_models_own(pricing):
    """
    The envelope only ever holds a price up, never pushes one down.

    Worth stating as a test because it is the bias the correction carries:
    every price it changes, it raises. Anywhere these prices are reported,
    that is the sentence that has to go with them.
    """
    for field in list(mapping.FIELDS)[:4]:
        for mentees in (1, 4, 8):
            for count in (1, 7, 15, 30):
                row = answers(field, mentees, False, count)
                raw = pricing.raw_prices_by_skill_count(row, CORE)[-1]
                corrected = pricing.predict_many([row], CORE)[0].recommended_price

                assert corrected >= int(round(raw)) - 1, (field, mentees, count)


def test_a_service_with_no_skills_is_still_priced(pricing):
    """
    Zero is a real answer: a mentor may publish a service before filling it.

    It is also where the envelope starts, so a failure here would mean the
    correction had no floor to stand on.
    """
    advice = pricing.predict_many([answers("law", 2, False, 0)], CORE)[0]

    assert advice.recommended_price > 0
    assert advice.price_low < advice.recommended_price < advice.price_high


def test_the_envelope_covers_every_smaller_service(pricing):
    """
    What the price is the largest of, stated once as a list of rows.

    Eight group sizes and thirty-one skill counts for a full service, which
    is the whole grid below the one asked for rather than the two edges of it.
    """
    rows = pricing.envelope_rows(answers("law", 8, False, mapping.SKILL_COUNT))

    assert len(rows) == mapping.MAX_MENTEES_MAX * (mapping.SKILL_COUNT + 1)
    assert answers("law", 8, False, mapping.SKILL_COUNT) in rows
    assert min(int(row[mapping.COLUMN_MAX_MENTEES]) for row in rows) == (
        mapping.MAX_MENTEES_MIN
    )
    assert min(int(row[mapping.COLUMN_SKILLS]) for row in rows) == (
        SKILL_COUNT_MIN * mapping.SKILL_WEIGHT
    )


def test_a_row_that_does_not_say_how_many_skills_is_refused(pricing):
    row = answers("law", 2, False, 5)
    del row[mapping.COLUMN_SKILLS]

    with pytest.raises(ValueError):
        pricing.predict_many([row], CORE)
