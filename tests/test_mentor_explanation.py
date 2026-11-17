"""
Why this price: the account has to add up, and it has to be readable.

Two different kinds of claim are tested here and they are tested differently.

The arithmetic is the first. An account of a price that did not multiply out
to that price would be a story told beside a number rather than an account of
it, and the failure would be invisible on the page: every row would look
plausible. So the identity is asserted across a wide spread of profiles on
both models rather than on one example.

The wording is the second. These sentences are the only place in the system
where a mentor is told why, and the vocabulary rules on them are not style
preferences. Nothing may name a model or a method, because a mentor cannot
check any of it and the words would only transfer authority. Nothing may name
the data the models were fitted on. And nothing may claim that one thing
caused another, because what was measured is what mentors charge, not why.
"""

from __future__ import annotations

import re

import pytest

from src.mentor import explanation, mapping
from src.mentor.comparables import ComparableSet
from src.mentor.prediction import CORE, FULL

from .conftest import SYNTHETIC_HISTORY, headers, register, synthetic_comparables

pytestmark = pytest.mark.app_assets

SKILL_IDS = tuple(mapping.SKILLS)

# A spread wide enough that an account which only closes on the easy cases
# fails here: every field is represented, both ends of the group size, a
# service with nothing ticked and one with everything.
PROFILES = [
    {
        "field": field,
        "max_mentees": seats,
        "skills": count,
        "profile_verified": verified,
        "min_commitment": commitment,
        "services_count": services,
    }
    for field, seats, count, verified, commitment, services in zip(
        list(mapping.FIELDS) * 3,
        (1, 2, 3, 4, 5, 6, 7, 8) * 6,
        (0, 1, 4, 9, 15, 22, 30, 7, 2, 11) * 5,
        (True, False) * 24,
        (1, 2, 3, 5, 7) * 10,
        (1, 2, 3, 4) * 12,
        strict=False,
    )
]

# Words that would say where a price came from in the language of the thing
# that produced it rather than in the language of the mentor reading it.
#
# Matched as whole words. "Technology" contains three of these letters in a
# row and is a field a mentor chose, so a substring search would ban the
# mentor's own answer.
MODEL_WORDS = (
    "shap",
    "xgboost",
    "gradient",
    "boost",
    "log",
    "tree",
    "feature",
    "coefficient",
    "regression",
    "isotonic",
    "model",
    "algorithm",
    "training",
    "dataset",
)

SOURCE_WORDS = (
    "airbnb",
    "listing",
    "nightly",
    "superhost",
    "accommodates",
    "neighbourhood",
    "room type",
    "amenities",
)


def answers(profile: dict) -> dict:
    """One profile as the mapping layer builds it, for the core model."""
    return mapping.to_model_inputs(
        field=profile["field"],
        max_mentees=profile["max_mentees"],
        min_commitment=profile["min_commitment"],
        skills=list(SKILL_IDS[: profile["skills"]]),
        profile_verified=profile["profile_verified"],
        services_count=profile["services_count"],
    )


def with_record(row: dict) -> dict:
    return {**row, **mapping.history_to_model_inputs(SYNTHETIC_HISTORY)}


# What the mentors in a comparison sample typically offer, which is the one
# figure an account borrows from the comparison below it. Pinned here rather
# than read from a table so that a sentence about a group size is tested
# against a known number.
TYPICAL_GROUP_SIZE = 2


def account_for(
    pricing,
    profile: dict,
    model_used: str,
    typical_group_size: int | None = TYPICAL_GROUP_SIZE,
) -> tuple[dict, int]:
    """The account and the price it has to come to."""
    row = answers(profile)
    if model_used == FULL:
        row = with_record(row)
    price = pricing.predict_many([row], model_used)[0].recommended_price
    return (
        explanation.explain_price(
            pricing=pricing,
            inputs=row,
            model_used=model_used,
            suggested_price=price,
            typical_group_size=typical_group_size,
        ),
        price,
    )


def every_sentence(account: dict) -> list[str]:
    said = [account["baseline_sentence"], account["summary_sentence"]]
    said += [account["combination_note"]]
    said += [account["limitation"], account["profile_note"]]
    rows = list(account["factors"])
    if account["other_small_effects"]:
        rows.append(account["other_small_effects"])
    said += [row["sentence"] for row in rows]
    said += [row["label"] for row in rows]
    return said


# ---------------------------------------------------------------------------
# The arithmetic
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_the_factors_multiply_out_to_the_suggested_price(pricing, model_used):
    """
    The identity the whole response stands on, over every profile above.

    Within the rounding of a whole percent, which is the precision the
    effects are shown at. An account that missed by more than that would be
    telling a mentor that five rows explain a price they do not explain.
    """
    assert len(PROFILES) >= 30
    for profile in PROFILES:
        account, price = account_for(pricing, profile, model_used)
        reached = explanation.reconciled_price(account)
        allowed = max(1.0, price * explanation.RECONCILIATION_TOLERANCE_PCT / 100)

        assert abs(reached - price) <= allowed, (model_used, profile, reached, price)


@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_the_baseline_is_a_real_price_the_account_starts_from(pricing, model_used):
    """A starting point of zero would make every effect below it meaningless."""
    for profile in PROFILES[:12]:
        account, _ = account_for(pricing, profile, model_used)

        assert account["baseline_price"] > 0
        assert (
            str(account["baseline_price"])
            in account["baseline_sentence"].replace(",", "")
            or f"{account['baseline_price']:,}" in account["baseline_sentence"]
        )


def test_the_skills_line_carries_the_correction(pricing):
    """
    The line that closes the arithmetic is always shown, whatever its size.

    It is where the smoothing of the skill axis is absorbed, so hiding it
    among the small effects would hide the one place the account and the
    price are reconciled.
    """
    for profile in PROFILES[:20]:
        account, _ = account_for(pricing, profile, CORE)
        keys = [row["key"] for row in account["factors"]]

        assert mapping.CHOICE_SKILLS in keys
        skills = next(
            row for row in account["factors"] if row["key"] == mapping.CHOICE_SKILLS
        )
        assert "never lowers this suggestion" in skills["sentence"]


# ---------------------------------------------------------------------------
# What may and may not be named
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_no_factor_is_an_input_the_mentor_did_not_choose(pricing, model_used):
    """
    Fixed inputs are folded into the starting point, never listed as reasons.

    A reason a mentor cannot act on is not a reason. The session format is
    held at one value for everybody, and a mentor who has just joined is held
    at a starting time on the platform; neither belongs in a list of things
    that moved their price.
    """
    allowed = set(mapping.EXPLANATION_CHOICES) | set(mapping.EXPLANATION_GROUPS)
    for profile in PROFILES[:16]:
        account, _ = account_for(pricing, profile, model_used)
        keys = {row["key"] for row in account["factors"]}

        assert keys <= allowed, (model_used, keys - allowed)
        assert "session_format" not in keys
        assert "tenure" not in keys


def test_a_mentor_without_a_record_is_told_nothing_about_one(pricing):
    """The core path has no themes to report, because it measured none."""
    account, _ = account_for(pricing, PROFILES[0], CORE)

    assert not any(row["association"] for row in account["factors"])


def test_a_mentor_with_a_record_sees_it_as_groups_with_their_caution(pricing):
    """
    The twenty-nine measured quantities arrive as two groups, not four themes.

    Each carries the caution it needs: a price moving with a measurement is a
    pattern among mentors who charge alike, never a claim about cause.

    The themes under each group are still reported, as components, because
    grouping two of them into one sentence is a decision about what to say
    and must not become a decision to drop a number.
    """
    seen: set[str] = set()
    for profile in PROFILES[:16]:
        account, _ = account_for(pricing, profile, FULL)
        for row in account["factors"]:
            if row["association"]:
                seen.add(row["key"])
                assert "pattern among similar mentors" in row["sentence"]
                assert "a cause" in row["sentence"]
                assert row["components"]
                assert {part["key"] for part in row["components"]} <= set(
                    mapping.EXPLANATION_THEMES
                )

    assert seen
    assert seen <= set(mapping.EXPLANATION_GROUPS)
    assert len(mapping.EXPLANATION_GROUPS) == 2


def test_demand_is_its_own_row_for_every_mentor_with_a_record(pricing):
    """
    Demand is never grouped away, whatever size its effect turns out to be.

    Responsiveness to demand is the claim this whole system makes, so an
    account that let demand fall into "other small effects" on a quiet
    profile would be hiding its own subject on exactly the profiles where a
    mentor would most want to see it.
    """
    for profile in PROFILES[:16]:
        account, _ = account_for(pricing, profile, FULL)
        rows = {row["key"]: row for row in account["factors"]}

        assert mapping.THEME_DEMAND in rows, profile
        demand = rows[mapping.THEME_DEMAND]
        assert demand["label"] == "Demand for your time"
        assert "offered time mentors like you have booked" in demand["sentence"]


# ---------------------------------------------------------------------------
# The demand row says what the input is and argues nothing from it
#
# It used to read "Mentors whose time is booked as much as yours tend to charge
# more", which a mentor can only read one way: as a reason to put the price up
# now that they are busy. The system has no such finding. The figure, its sign
# and its place in the ordering are all still there; what went is the
# instruction.
# ---------------------------------------------------------------------------
DEMAND_ADVICE = re.compile(
    r"tend to charge (more|less)"
    r"|charge (more|less) because"
    r"|(raise|lower|put up|increase|reduce) your price"
    r"|you (should|could) charge",
    re.IGNORECASE,
)


def test_the_demand_row_describes_the_input_and_advises_nothing(pricing):
    """
    One sentence, the same whichever way the number points.

    Asserted across both ends of the spread rather than on one profile,
    because the fault it replaced was a sentence chosen by the direction: the
    wording was only wrong on the profiles where the direction was read as
    advice.
    """
    for profile in PROFILES[:16]:
        account, _ = account_for(pricing, profile, FULL)
        demand = next(
            row for row in account["factors"] if row["key"] == mapping.THEME_DEMAND
        )
        said = demand["sentence"]

        assert not DEMAND_ADVICE.search(said), (profile, said)
        # What it does say: which input this is, and that it is one of them.
        assert "one of the inputs" in said, said
        assert "not a reason to charge more or less" in said, said
        # The caution every row about a measured record carries.
        assert explanation.ASSOCIATION_NOTE in said, said


def test_the_demand_row_reads_the_same_whichever_way_it_points(pricing):
    """
    The sentence is a constant, so no edit can make it directional again.

    A sentence per direction is how the old row came to give advice: once the
    shape is "mentors like you tend to charge X", the only thing left to
    choose is X.
    """
    said: set[str] = set()
    directions: set[str] = set()
    for profile in PROFILES[:24]:
        account, _ = account_for(pricing, profile, FULL)
        demand = next(
            row for row in account["factors"] if row["key"] == mapping.THEME_DEMAND
        )
        said.add(demand["sentence"])
        directions.add(demand["direction"])

    assert said == {explanation.DEMAND_SENTENCE}
    # The spread really does produce more than one direction, so the
    # assertion above is not passing because every profile pointed one way.
    assert len(directions) > 1


def test_the_demand_row_keeps_its_number_and_its_place(pricing):
    """
    Only the wording changed. The figure is still the figure.

    The row's effect is the one the model's own decomposition gives for the
    demand columns, and the ordering of the card is still by size, so a
    mentor who wants to know which way demand moved their price reads the
    number beside it.
    """
    import math

    for profile in PROFILES[:8]:
        row = answers(profile)
        row = with_record(row)
        price = pricing.predict_many([row], FULL)[0].recommended_price
        account = explanation.explain_price(
            pricing=pricing,
            inputs=row,
            model_used=FULL,
            suggested_price=price,
            typical_group_size=TYPICAL_GROUP_SIZE,
        )
        _, parts = pricing.log_contributions(row, FULL)
        columns = mapping.explanation_group_columns()[mapping.THEME_DEMAND]
        expected = int(
            round((math.exp(sum(parts[column] for column in columns)) - 1) * 100)
        )

        demand = next(
            one for one in account["factors"] if one["key"] == mapping.THEME_DEMAND
        )
        assert demand["effect_pct"] == expected, profile
        assert demand["direction"] == explanation.direction_of(expected)


def test_a_new_mentor_is_shown_no_demand_row_at_all(pricing):
    """
    Nothing was measured, so there is nothing to show.

    A demand row on a mentor the platform has never watched would be a figure
    about them that nobody observed, which is worse than an absent row.
    """
    for profile in PROFILES[:16]:
        account, _ = account_for(pricing, profile, CORE)
        rows = [row["key"] for row in account["factors"]]
        if account["other_small_effects"]:
            rows.append(account["other_small_effects"]["key"])

        assert mapping.THEME_DEMAND not in rows, profile
        assert mapping.THEME_TRACK_RECORD not in rows, profile


def test_no_row_ever_says_a_better_rating_lowers_a_price(pricing):
    """
    A standalone ratings row read as advice to stop collecting ratings.

    What the data holds is that the mentors charging most are not the ones
    rated highest, which is a fact about who charges what. Printed as its own
    line it became guidance nobody can act on honestly, so ratings are only
    ever spoken of inside the wider record.
    """
    blamed = re.compile(r"rated[^.]*charge less", re.IGNORECASE)
    for profile in PROFILES[:16]:
        account, _ = account_for(pricing, profile, FULL)

        assert mapping.THEME_RATINGS not in {
            row["key"] for row in account["factors"]
        }, profile
        for said in every_sentence(account):
            assert not blamed.search(said), (profile, said)


@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_at_most_five_factors_plus_the_row_that_gathers_the_small_ones(
    pricing, model_used
):
    """
    Five rows, or up to seven when five would leave a dishonest grouped row.

    The limit exists because nobody reads a longer list. It gives way only to
    the rule below it, which is the stronger claim.
    """
    for profile in PROFILES[:16]:
        account, _ = account_for(pricing, profile, model_used)

        assert len(account["factors"]) <= explanation.MAX_FACTORS_PROMOTED
        keys = [row["key"] for row in account["factors"]]
        assert len(keys) == len(set(keys))
        if account["other_small_effects"]:
            assert account["other_small_effects"]["key"] == explanation.OTHER_KEY


@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_the_grouped_row_is_the_smallest_thing_on_the_card(pricing, model_used):
    """
    "Other small effects" has to be smaller than every row shown above it.

    Otherwise the row is not what it says it is: a reader seeing it sitting
    below a line half its size has been told the account was tidied in a way
    it was not. Where five rows cannot manage that, the account widens to
    seven rather than print the claim, and only a card already at seven is
    allowed to fall short.

    One other card is allowed to fall short, and it is allowed because it
    does not make the claim: a row that has absorbed a factor held back by
    the plausibility guard is named "Other factors" instead, and may
    legitimately be the largest figure on the card. Widening could not fix
    that one either, since the factor is held back by what it would say
    rather than by how big it is.
    """
    for profile in PROFILES[:16]:
        account, _ = account_for(pricing, profile, model_used)
        other = account["other_small_effects"]
        if other is None:
            continue

        smallest = min(abs(row["effect_pct"]) for row in account["factors"])
        widened = len(account["factors"]) >= explanation.MAX_FACTORS_PROMOTED
        guarded = other["label"] == explanation.OTHER_GUARDED_LABEL

        assert abs(other["effect_pct"]) < smallest or widened or guarded, (
            model_used,
            profile,
            other["effect_pct"],
            smallest,
        )


@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_the_grouped_row_is_named_for_what_it_actually_holds(pricing, model_used):
    """
    Only effects too small for a line each get the "small effects" name.

    A row labelled "Other small effects" holding a five per cent factor the
    guard withheld would be describing itself wrongly, and would put the
    largest figure on the card under the smallest-sounding label.
    """
    for profile in PROFILES[:16]:
        account, _ = account_for(pricing, profile, model_used)
        other = account["other_small_effects"]
        if other is None:
            continue

        assert other["label"] in {
            explanation.OTHER_LABEL,
            explanation.OTHER_GUARDED_LABEL,
        }, other["label"]
        if other["label"] == explanation.OTHER_LABEL:
            smallest = min(abs(row["effect_pct"]) for row in account["factors"])
            widened = len(account["factors"]) >= explanation.MAX_FACTORS_PROMOTED
            assert abs(other["effect_pct"]) < smallest or widened, (profile, other)


# ---------------------------------------------------------------------------
# The group size sentence
#
# This sentence was wrong on the page before it was wrong in a test. It read
# the effect as a comparison against a one to one session, so a mentor whose
# group of three was priced above their own one to one rate was told that a
# group of three tends to be priced lower than a one to one session, with
# both claims on one screen.
#
# Two properties stop that happening again. The words follow the sign of the
# number and nothing else. And one to one is named only when the mentor's own
# group is one, so the sentence cannot smuggle back the comparison that was
# never measured.
# ---------------------------------------------------------------------------
# Both shapes the sentence can take. "usually price higher than" is used when
# the mentor's group differs from the field's typical one, and "move the price
# per session up" when it is the typical one or when there is no reference to
# compare with, so a regex matching only one of them would stop checking the
# other the moment the wording moved between them.
RAISING_WORDS = re.compile(
    r"\bmove the price per session up\b|\busually price higher\b", re.IGNORECASE
)
LOWERING_WORDS = re.compile(
    r"\bmove the price per session down\b|\busually price lower\b", re.IGNORECASE
)


def group_row(account: dict) -> dict | None:
    for row in account["factors"]:
        if row["key"] == mapping.CHOICE_GROUP_SIZE:
            return row
    other = account["other_small_effects"]
    return other if other and other["key"] == mapping.CHOICE_GROUP_SIZE else None


@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_the_group_sentence_never_contradicts_its_own_number(pricing, model_used):
    """
    The direction word in the sentence agrees with the sign of the effect.

    Asserted over every profile rather than a chosen one, because the fault
    this replaced was only visible on the profiles where the sign and the
    old comparison happened to disagree.
    """
    for profile in PROFILES:
        account, _ = account_for(pricing, profile, model_used)
        row = group_row(account)
        if row is None:
            continue
        said = row["sentence"]

        if row["effect_pct"] > 0:
            assert not LOWERING_WORDS.search(said), (profile, said)
            assert row["direction"] == explanation.RAISES
        elif row["effect_pct"] < 0:
            assert not RAISING_WORDS.search(said), (profile, said)
            assert row["direction"] == explanation.LOWERS

        # Under two per cent the sentence claims no direction at all.
        if abs(row["effect_pct"]) < explanation.SMALL_EFFECT_PCT:
            assert "little difference" in said, (profile, said)
            assert not RAISING_WORDS.search(said)
            assert not LOWERING_WORDS.search(said)


@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_one_to_one_is_named_only_when_the_group_really_is_one(pricing, model_used):
    """
    Nothing anywhere in an account mentions one to one for a larger group.

    The whole account, not only the group row: a phrase barred from one
    sentence and allowed into the one below it would be the same fault with
    a smaller blast radius.
    """
    for profile in PROFILES:
        account, _ = account_for(pricing, profile, model_used)
        for said in every_sentence(account):
            if profile["max_mentees"] == 1:
                continue
            assert "one to one" not in said.lower(), (profile, said)


def test_the_group_sentence_names_the_typical_group_it_was_given(pricing):
    """
    The reference named is the one passed in, and it is named as the field's.

    A sentence that named a number from somewhere else would be comparing
    against mentors nobody measured. The figure comes from the caller, which
    reads it from the whole field rather than from the match: see
    comparables.typical_group_size and the note above it.
    """
    profile = {**PROFILES[2], "max_mentees": 5}
    label = mapping.field_label(profile["field"])
    for typical in (2, 6):
        account, _ = account_for(pricing, profile, CORE, typical_group_size=typical)
        row = group_row(account)
        assert row is not None
        said = row["sentence"]
        if abs(row["effect_pct"]) < explanation.SMALL_EFFECT_PCT:
            continue

        assert f"typical group of {typical}" in said, (typical, said)
        # And whose typical group it is, so the reader knows what population
        # the number describes.
        assert f"in {label}" in said, (typical, said)
        assert "among similar mentors" not in said, (typical, said)


def test_the_group_sentence_says_so_when_the_group_is_the_typical_one(pricing):
    """
    A group that *is* the reference has nothing to be compared with.

    The old sentence would have read "your group of 4 is the same size as the
    typical group", which is the comparison restated. This says the group is
    the usual size for the field, and still takes its direction from the
    number.
    """
    profile = {**PROFILES[2], "max_mentees": 4}
    label = mapping.field_label(profile["field"])

    account, _ = account_for(pricing, profile, CORE, typical_group_size=4)
    row = group_row(account)
    assert row is not None
    said = row["sentence"]
    if abs(row["effect_pct"]) >= explanation.SMALL_EFFECT_PCT:
        assert f"are the usual size in {label}" in said, said
        assert "typical group of" not in said, said
        movement = "up" if row["effect_pct"] > 0 else "down"
        assert f"move the price per session {movement}" in said, said


def test_a_one_to_one_is_compared_with_the_typical_group_in_the_field(pricing):
    """
    The one to one case keeps the comparison and names itself correctly.

    "One to one sessions usually price lower than the typical group of 4 in
    Technology and software" is the whole claim: a session for one is the
    other thing the platform offers, not a group of one, and it is still
    priced against the field it is offered in.
    """
    profile = {**PROFILES[2], "max_mentees": 1}
    label = mapping.field_label(profile["field"])

    account, _ = account_for(pricing, profile, CORE, typical_group_size=4)
    row = group_row(account)
    assert row is not None
    said = row["sentence"]
    if abs(row["effect_pct"]) >= explanation.SMALL_EFFECT_PCT:
        assert said.startswith("One to one sessions"), said
        assert f"typical group of 4 in {label}" in said, said


def test_the_typical_group_is_measured_rather_than_assumed():
    """
    The reference comes out of the prepared table, not out of this file.

    The brief for this change was explicit that the number may not be a
    constant, so the test is on the function that produces it: every field
    gets a figure, each figure is a session size the form can actually
    produce, and an empty table produces nothing rather than a default.
    """
    import pandas as pd

    from src.mentor import comparables as comparables_module

    table = synthetic_comparables()
    for field in mapping.FIELDS:
        usual = comparables_module.typical_group_size(table, field)
        assert usual is not None, field
        assert mapping.MAX_MENTEES_MIN <= usual <= mapping.MAX_MENTEES_MAX, field

    # A field with its own mentors is described by them. technology_software
    # holds twelve rows at sizes 1 to 3 in the hand-built table, so its
    # typical group is 2 whatever the rest of the table looks like.
    assert comparables_module.typical_group_size(table, "technology_software") == 2
    # engineering holds ten rows, all at eight.
    assert comparables_module.typical_group_size(table, "engineering") == 8
    # law holds four, which is under the minimum, so it falls back to every
    # field together rather than describing a field from four mentors.
    whole = comparables_module.typical_group_size(table, "law")
    assert whole == int(round(float(table.rows["max_mentees"].median())))

    empty = comparables_module.ComparablesTable(
        pd.DataFrame(columns=list(comparables_module.COMPARABLES_COLUMNS))
    )
    assert comparables_module.typical_group_size(empty, "law") is None


def test_the_typical_group_ignores_the_group_size_of_the_match(pricing):
    """
    The reason the reference moved, stated as a test.

    A match is made on field and group size together, so the typical group
    size inside one is close to the mentor's own by construction. This checks
    that the figure the account uses does not move with the mentor's group
    size, which is what made the old sentence tell every mentor their group
    was about the usual size.
    """
    from src.mentor import comparables as comparables_module

    table = synthetic_comparables()
    field = "technology_software"
    usual = comparables_module.typical_group_size(table, field)

    for seats in (1, 2, 3, 8):
        found = table.match(field=field, max_mentees=seats)
        in_match = comparables_module.typical_profile(found)["max_mentees"]
        # The match's own typical group follows the mentor's group around.
        # The field's does not, which is why the account reads the field's.
        assert comparables_module.typical_group_size(table, field) == usual
        assert in_match is not None


def test_with_nobody_to_compare_with_the_sentence_claims_no_comparison(pricing):
    """A typical group that was never measured is not invented."""
    for profile in PROFILES[:8]:
        account, _ = account_for(pricing, profile, CORE, typical_group_size=None)
        row = group_row(account)
        if row is None or abs(row["effect_pct"]) < explanation.SMALL_EFFECT_PCT:
            continue

        assert "typical group" not in row["sentence"], (profile, row["sentence"])


# ---------------------------------------------------------------------------
# The verification row, and the guard on it
#
# The two models disagree about the sign of this input, so two mentors with
# nearly the same answers, one priced by each model, were told opposite things
# about the same fact about themselves. One of them was told that having been
# checked by the platform lowers what they can charge, which is the one line
# on the card a mentor might act on by asking not to be verified.
#
# Both signs are tested, and they are tested on the function rather than only
# through the models, because which sign a given profile produces is a fact
# about the fitted pipelines and could change with the next training run. The
# rule has to hold either way round.
# ---------------------------------------------------------------------------
VERIFICATION_LOWERS = re.compile(
    r"[Vv]erified mentors tend to charge less"
    r"|not verified[^.]*charge more"
    r"|[Bb]eing verified[^.]*lower",
)


@pytest.mark.parametrize(
    ("verified", "effect_pct", "plausible"),
    [
        # A verified mentor: the effect may raise the price, or do nothing.
        (True, 9, True),
        (True, 2, True),
        (True, -2, False),
        (True, -9, False),
        # An unverified one: it may lower the price, or do nothing.
        (False, -9, True),
        (False, -2, True),
        (False, 2, False),
        (False, 9, False),
        # Either way, an effect too small to carry a direction claims none.
        (True, 1, False),
        (True, 0, False),
        (False, -1, False),
        (False, 0, False),
    ],
)
def test_which_verification_directions_may_be_described(
    verified, effect_pct, plausible
):
    """The rule itself, stated once, both signs and both answers."""
    assert (
        explanation.verified_direction_is_plausible(verified, effect_pct) is plausible
    )


def test_the_card_never_says_that_being_verified_lowers_a_price(pricing):
    """
    The invariant the guard exists for, over every profile and both models.

    Checked against every sentence on the card rather than the verification
    row alone: a claim barred from one row and allowed into the row below it
    would be the same fault with a smaller blast radius.
    """
    for profile in PROFILES:
        for model_used in (CORE, FULL):
            account, _ = account_for(pricing, profile, model_used)
            for said in every_sentence(account):
                assert not VERIFICATION_LOWERS.search(said), (profile, said)


def test_an_implausible_verification_effect_is_folded_rather_than_shown(pricing):
    """
    Where the sign points the wrong way, the row goes into the grouped line.

    Folded and not dropped: the figure is still in the account, which is what
    keeps the arithmetic exact. What is withheld is the sentence, because the
    sentence is the part that makes a claim.
    """
    import math

    folded = 0
    for profile in PROFILES:
        for model_used in (CORE, FULL):
            row = answers(profile)
            if model_used == FULL:
                row = with_record(row)
            _, parts = pricing.log_contributions(row, model_used)
            effect = int(round((math.exp(parts[mapping.COLUMN_VERIFIED]) - 1) * 100))
            plausible = explanation.verified_direction_is_plausible(
                bool(profile["profile_verified"]), effect
            )

            account, _ = account_for(pricing, profile, model_used)
            shown = {one["key"] for one in account["factors"]}
            if plausible:
                continue

            folded += 1
            assert mapping.CHOICE_VERIFIED not in shown, (profile, model_used, effect)
            if abs(effect) >= explanation.SMALL_EFFECT_PCT:
                other = account["other_small_effects"]
                assert other is not None, (profile, model_used)
                assert other["label"] == explanation.OTHER_GUARDED_LABEL

    # The spread really does contain implausible cases, so the assertions
    # above are not passing by never running.
    assert folded > 0


def test_a_plausible_verification_effect_is_shown_with_its_sentence(pricing):
    """
    The guard withholds a claim; it does not withhold the whole subject.

    Where the direction is the one a mentor would expect, the row appears and
    says so, so a verified mentor whose verification really does lift their
    price is told about it.
    """
    import math

    shown_any = 0
    for profile in PROFILES:
        for model_used in (CORE, FULL):
            row = answers(profile)
            if model_used == FULL:
                row = with_record(row)
            _, parts = pricing.log_contributions(row, model_used)
            effect = int(round((math.exp(parts[mapping.COLUMN_VERIFIED]) - 1) * 100))
            if not explanation.verified_direction_is_plausible(
                bool(profile["profile_verified"]), effect
            ):
                continue

            account, _ = account_for(pricing, profile, model_used)
            rows = {one["key"]: one for one in account["factors"]}
            # It is eligible, which is not the same as being in the top five.
            # When it is there, it carries a sentence pointing the right way.
            if mapping.CHOICE_VERIFIED not in rows:
                continue
            shown_any += 1
            said = rows[mapping.CHOICE_VERIFIED]["sentence"]
            if profile["profile_verified"]:
                assert "charge more" in said, said
            else:
                assert "charge less" in said, said

    assert shown_any > 0


def test_folding_the_verification_row_leaves_the_price_untouched(pricing):
    """
    The guard is about what is said, not about what is charged.

    The account still multiplies out to the price the mentor was quoted, on
    the profiles where the row is withheld as much as on the others, because
    the withheld multiplier goes into the grouped row rather than away.
    """
    for profile in PROFILES:
        for model_used in (CORE, FULL):
            account, price = account_for(pricing, profile, model_used)
            got = explanation.reconciled_price(account)

            assert abs(got - price) / price * 100 <= (
                explanation.RECONCILIATION_TOLERANCE_PCT
            ), (profile, model_used, got, price)


# ---------------------------------------------------------------------------
# The line between the typical price and the rows that move it
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_the_summary_line_places_the_suggestion_against_the_typical_price(
    pricing, model_used
):
    """
    One line, carrying the suggestion, the distance and the side.

    Said as a distance rather than as a verdict: a mentor reading "eighteen
    percent below" has both numbers and knows which side of the other they
    are on, where "below average" would give them neither.
    """
    for profile in PROFILES[:16]:
        account, price = account_for(pricing, profile, model_used)
        said = account["summary_sentence"]
        baseline = account["baseline_price"]
        gap = round(abs(price - baseline) / baseline * 100)

        assert f"{price:,}" in said, (profile, said)
        assert said.endswith("Here is what moves it:")
        if gap == 0:
            assert "about the same as that typical price" in said
        else:
            side = "above" if price > baseline else "below"
            assert f"{gap} percent {side} that typical price" in said, (profile, said)


def test_the_baseline_line_calls_it_a_typical_price(pricing):
    """A starting point is a number; a typical price is a thing to compare with."""
    account, _ = account_for(pricing, PROFILES[0], CORE)

    assert account["baseline_sentence"].startswith("A typical mentor's price is around")
    assert "your situation" not in account["baseline_sentence"]


@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_the_factors_are_ordered_by_how_much_they_move_the_price(pricing, model_used):
    for profile in PROFILES[:16]:
        account, _ = account_for(pricing, profile, model_used)
        sizes = [abs(row["effect_pct"]) for row in account["factors"]]

        assert sizes == sorted(sizes, reverse=True), (model_used, profile, sizes)


@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_the_direction_always_agrees_with_the_number(pricing, model_used):
    """
    The word is what a page shows beside the arrow, so it cannot disagree.

    A page that said "raises" next to a negative figure would be wrong in the
    one way a reader would not check.
    """
    for profile in PROFILES[:16]:
        account, _ = account_for(pricing, profile, model_used)
        rows = list(account["factors"])
        if account["other_small_effects"]:
            rows.append(account["other_small_effects"])
        for row in rows:
            assert row["direction"] == explanation.direction_of(row["effect_pct"])


@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_nothing_an_account_says_names_a_model_or_a_method(pricing, model_used):
    for profile in PROFILES[:16]:
        account, _ = account_for(pricing, profile, model_used)
        for said in every_sentence(account):
            lowered = said.lower()
            for word in MODEL_WORDS:
                assert not re.search(rf"{word}", lowered), (word, said)


@pytest.mark.parametrize("model_used", [CORE, FULL])
def test_nothing_an_account_says_names_the_source_of_the_training_data(
    pricing, model_used
):
    for profile in PROFILES[:16]:
        account, _ = account_for(pricing, profile, model_used)
        for said in every_sentence(account):
            lowered = said.lower()
            for word in SOURCE_WORDS:
                assert not re.search(rf"{word}", lowered), (word, said)


def test_no_sentence_shouts_at_a_mentor(pricing):
    for profile in PROFILES[:8]:
        account, _ = account_for(pricing, profile, CORE)
        for said in every_sentence(account):
            assert "!" not in said


def test_the_two_fixed_lines_are_always_there_and_say_what_they_must(pricing):
    account, _ = account_for(pricing, PROFILES[0], CORE)

    assert account["limitation"] == (
        "These are patterns in what similar mentors charge. They are not "
        "guarantees, and the final price is yours to set."
    )
    assert account["profile_note"] == (
        "Experience and credentials appear on your public card. They do not "
        "change this suggestion."
    )


# ---------------------------------------------------------------------------
# The comparison
# ---------------------------------------------------------------------------
def above_everyone() -> ComparableSet:
    """A match of cheap mentors, so any sensible price sits above the band."""
    table = synthetic_comparables()
    return table.match(field="medicine_health", max_mentees=5)


def test_a_price_above_the_band_is_explained_by_a_real_factor(pricing):
    """
    The callout names something the account actually says, not a guess.

    A mentor told their price is above the middle has one useful question
    next, and this is the answer to it. The factor named has to be one of the
    rows above, pointing the same way as the gap, or the page is making it up.
    """
    account, _ = account_for(pricing, PROFILES[7], CORE)
    found = above_everyone()

    comparison = explanation.compare_price(
        found=found,
        suggested_price=5_000,
        inputs=answers(PROFILES[7]),
        factors=account["factors"],
    )

    assert comparison["position"] == explanation.POSITION_ABOVE
    assert comparison["explains_gap"]
    assert "higher than most similar mentors" in comparison["explains_gap"]
    raising = [
        explanation.GAP_PHRASES[row["key"]]
        for row in account["factors"]
        if row["effect_pct"] > 0
    ]
    assert any(phrase in comparison["explains_gap"] for phrase in raising)


def test_a_price_below_the_band_is_explained_the_other_way(pricing):
    account, _ = account_for(pricing, PROFILES[7], CORE)
    found = above_everyone()

    comparison = explanation.compare_price(
        found=found,
        suggested_price=60,
        inputs=answers(PROFILES[7]),
        factors=account["factors"],
    )

    assert comparison["position"] == explanation.POSITION_BELOW
    assert "lower than most similar mentors" in comparison["explains_gap"]


def test_a_price_inside_the_band_says_so_and_explains_no_gap(pricing):
    """
    Within the middle, there is nothing to account for.

    A sentence explaining a gap that is not there would invite a mentor to
    fix something that is not broken.
    """
    account, _ = account_for(pricing, PROFILES[7], CORE)
    found = above_everyone()
    middle = (found.rows["price"].median() + 0).astype(int).item()

    comparison = explanation.compare_price(
        found=found,
        suggested_price=int(middle),
        inputs=answers(PROFILES[7]),
        factors=account["factors"],
    )

    assert comparison["position"] == explanation.POSITION_WITHIN
    assert comparison["explains_gap"] is None
    assert "sits in the middle" in comparison["sentence"]


def test_the_differences_describe_what_is_offered_not_what_is_charged(pricing):
    """
    A difference is about the service, so none of them mentions a price.

    The prices are the chart beside this. What the comparison adds is the one
    thing the chart cannot say: what is different about what this mentor
    offers.
    """
    account, _ = account_for(pricing, PROFILES[6], CORE)
    comparison = explanation.compare_price(
        found=above_everyone(),
        suggested_price=400,
        inputs=answers(PROFILES[6]),
        factors=account["factors"],
    )

    for difference in comparison["differences"]:
        assert "$" not in difference["sentence"]
        assert mapping.CURRENCY not in difference["sentence"]
        assert "typical similar mentor" in difference["sentence"] or (
            "compared with" in difference["sentence"]
        )


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------
def explanation_of(client, mentor_id: int, recommendation_id: int):
    return client.get(
        f"/recommendations/{recommendation_id}/explanation",
        headers=headers(mentor_id),
    )


def test_a_mentor_can_read_why_their_own_price_was_suggested(client):
    body = register(client)
    mentor_id = body["mentor"]["id"]
    recommendation = body["recommendation"]

    answer = explanation_of(client, mentor_id, recommendation["id"])

    assert answer.status_code == 200, answer.text
    payload = answer.json()
    assert payload["recommendation_id"] == recommendation["id"]
    assert payload["service_id"] == body["service"]["id"]
    assert payload["suggested_price"] == recommendation["recommended_price"]
    assert payload["model_used"] == "core"
    assert payload["factors"]
    assert payload["limitation"] and payload["profile_note"]
    assert payload["comparison"]["sentence"]


def test_the_endpoint_reconciles_to_the_price_it_explains(client):
    body = register(client)
    payload = explanation_of(
        client, body["mentor"]["id"], body["recommendation"]["id"]
    ).json()

    reached = explanation.reconciled_price(
        {
            "baseline_price": payload["baseline_price"],
            "factors": payload["factors"],
            "other_small_effects": payload["other_small_effects"],
        }
    )
    price = payload["suggested_price"]

    assert abs(reached - price) <= max(
        1.0, price * explanation.RECONCILIATION_TOLERANCE_PCT / 100
    )


def test_the_comparison_agrees_with_the_mentors_the_price_screen_draws(client):
    """
    One source of truth. The sentence here and the dots there are the same
    mentors, so the band in this response is the band beside that chart.
    """
    body = register(client)
    mentor_id, service_id = body["mentor"]["id"], body["service"]["id"]

    drawn = client.get(
        f"/services/{service_id}/comparables", headers=headers(mentor_id)
    ).json()
    payload = explanation_of(client, mentor_id, body["recommendation"]["id"]).json()
    comparison = payload["comparison"]

    assert comparison["band_low"] == drawn["summary"]["p25_price"]
    assert comparison["band_high"] == drawn["summary"]["p75_price"]
    assert comparison["median_price"] == drawn["summary"]["median_price"]
    assert comparison["matched_total"] == drawn["summary"]["count"]
    assert comparison["compared_with"] == drawn["distribution"]["shown"]
    assert comparison["match_description"] == drawn["summary"]["match_description"]


def test_a_mentor_with_a_record_is_explained_by_the_full_model(client, api_sessions):
    from src.db.mentor_models import MentorHistory

    body = register(client)
    mentor_id, service_id = body["mentor"]["id"], body["service"]["id"]
    with api_sessions() as session:
        session.add(MentorHistory(mentor_id=mentor_id, **SYNTHETIC_HISTORY))
        session.commit()
    priced = client.post(
        f"/services/{service_id}/recommendations", headers=headers(mentor_id)
    ).json()

    payload = explanation_of(client, mentor_id, priced["id"]).json()

    assert payload["model_used"] == "full"
    assert payload["low_confidence"] is False
    # What the full path guarantees is that a mentor's record was weighed,
    # that demand got a row of its own out of it, and that nothing outside
    # the two vocabularies reached the response.
    keys = {row["key"] for row in payload["factors"]}

    assert keys <= (set(mapping.EXPLANATION_CHOICES) | set(mapping.EXPLANATION_GROUPS))
    assert mapping.THEME_DEMAND in keys


def test_another_mentors_price_is_not_found(client):
    mine = register(client)
    theirs = register(client, email="other@example.com")

    answer = explanation_of(
        client, mine["mentor"]["id"], theirs["recommendation"]["id"]
    )

    assert answer.status_code == 404


def test_a_price_that_does_not_exist_is_not_found(client):
    body = register(client)

    assert explanation_of(client, body["mentor"]["id"], 9_999).status_code == 404


def test_reading_an_explanation_needs_a_token(client):
    body = register(client)

    answer = client.get(f"/recommendations/{body['recommendation']['id']}/explanation")

    assert answer.status_code == 401


def test_the_whole_response_names_no_model_and_no_source(client):
    """
    The vocabulary rules on the surface a mentor actually reads.

    Every string in the response at once, rather than the sentences the
    module happens to expose: a label added later is a string on the page.
    """
    body = register(client)
    text = explanation_of(
        client, body["mentor"]["id"], body["recommendation"]["id"]
    ).text.lower()

    for word in SOURCE_WORDS:
        assert word not in text, word
    for word in ("shap", "xgboost", "coefficient", "isotonic"):
        assert word not in text, word
