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
        assert "booked as much as yours" in demand["sentence"]


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
    """
    for profile in PROFILES[:16]:
        account, _ = account_for(pricing, profile, model_used)
        other = account["other_small_effects"]
        if other is None:
            continue

        smallest = min(abs(row["effect_pct"]) for row in account["factors"])
        widened = len(account["factors"]) >= explanation.MAX_FACTORS_PROMOTED

        assert abs(other["effect_pct"]) < smallest or widened, (
            model_used,
            profile,
            other["effect_pct"],
            smallest,
        )


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
RAISING_WORDS = re.compile(r"\bmove the price per session up\b", re.IGNORECASE)
LOWERING_WORDS = re.compile(r"\bmove the price per session down\b", re.IGNORECASE)


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


def test_the_group_sentence_compares_with_the_mentors_on_the_screen(pricing):
    """
    The comparison named is the sample's typical group, not a fixed one.

    A sentence that named a number from somewhere else would be describing
    mentors the page never drew, and a reader checking it against the
    comparison below would find two different sets of mentors.
    """
    profile = {**PROFILES[2], "max_mentees": 5}
    for typical in (2, 6):
        account, _ = account_for(pricing, profile, CORE, typical_group_size=typical)
        row = group_row(account)
        assert row is not None
        said = row["sentence"]
        if abs(row["effect_pct"]) < explanation.SMALL_EFFECT_PCT:
            continue

        assert f"typical group of {typical}" in said, (typical, said)
        bigger = "larger" if 5 > typical else "smaller"
        assert bigger in said, (typical, said)


def test_with_nobody_to_compare_with_the_sentence_claims_no_comparison(pricing):
    """A typical group that was never measured is not invented."""
    for profile in PROFILES[:8]:
        account, _ = account_for(pricing, profile, CORE, typical_group_size=None)
        row = group_row(account)
        if row is None or abs(row["effect_pct"]) < explanation.SMALL_EFFECT_PCT:
            continue

        assert "typical group" not in row["sentence"], (profile, row["sentence"])


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
