"""
Why this price: one account of one suggestion, in the mentor's own words.

A suggested price that arrives with no account of itself is a number to be
taken on trust, and a mentor deciding whether to accept it has nothing to work
with. This module turns one suggestion into something a mentor can read: where
the figure starts from, what about their own answers moved it, and where it
lands among mentors like them.

**Exact, not illustrative.** The parts come from the model's own decomposition
of its own answer, so they add up to it rather than approximating it. That is
what makes the account reconcilable: the starting point multiplied by every
effect shown gives back the suggested price, and a test holds it to that. An
account that only illustrated would be free to leave something out.

**Three kinds of input.** Which ones a mentor can do something about is the
organising idea, and :mod:`src.mentor.mapping` holds the classification.
Inputs nobody chose are folded into the starting point rather than shown as
reasons, because a reason a mentor cannot act on is not a reason. The answers
from the form are shown one at a time. What the platform has measured about a
mentor with a record is shown as four themes, each with the caution it needs.

**The skills line carries the correction.** The price a mentor is shown is not
the model's raw answer: the skill axis is smoothed so that covering more can
never be worth less, as :mod:`src.mentor.prediction` explains at length. That
correction has to appear somewhere in the account or the arithmetic would not
close, and the honest place is the line about skills, since that is the axis it
acts on. The sentence for it says so.

**What it may not say.** Nothing here names a model, a method, or anything
about where the training data came from, and the only percentages in it are the
effects themselves and the mentor's position among similar mentors. The
sentences describe what mentors like this one charge. They never claim that one
thing causes another, because nothing here measured that.
"""

from __future__ import annotations

import math
from typing import Any

from src.mentor import comparables as comparables_module
from src.mentor import mapping
from src.mentor.prediction import FULL, PricingService

# ---------------------------------------------------------------------------
# How an effect is described
#
# Three words rather than a signed number, because a mentor reads the word.
# The number is beside it and the arrow on the page is beside that, so the
# direction survives being printed, read aloud, or seen by somebody who cannot
# tell the two colours apart.
# ---------------------------------------------------------------------------
RAISES = "raises"
LOWERS = "lowers"
LITTLE = "little effect"

# Under two per cent, a line costs a reader more attention than it returns.
# Those lines are not dropped, which would break the arithmetic: they are
# multiplied together into one row that says what they come to.
SMALL_EFFECT_PCT = 2

# At most five rows before the small ones, which is as many as anybody reads.
MAX_FACTORS = 5

OTHER_KEY = "other_small_effects"
OTHER_LABEL = "Other small effects"

# How far the rounded effects may miss the suggested price by.
#
# Every effect is shown as a whole percent, and the line that closes the
# arithmetic is rounded like the rest, so half a percentage point of rounding
# on that line is the whole of the error. Half a point of a multiplier is more
# than half a per cent of the price when the multiplier is below one, which is
# why the allowance is a whole per cent rather than half of one. Anything
# larger than that is a fault rather than rounding.
RECONCILIATION_TOLERANCE_PCT = 1.0

LIMITATION = (
    "These are patterns in what similar mentors charge. They are not "
    "guarantees, and the final price is yours to set."
)
PROFILE_NOTE = (
    "Experience and credentials appear on your public card. They do not "
    "change this suggestion."
)
COMBINATION_NOTE = (
    "Each effect applies to the one before it, so the effects multiply rather "
    "than add."
)
ASSOCIATION_NOTE = "This is a pattern among similar mentors rather than a cause."

POSITION_BELOW = "below"
POSITION_WITHIN = "within"
POSITION_ABOVE = "above"
POSITION_UNKNOWN = "unknown"

# A difference worth a sentence. Below these the two answers are the same
# answer told twice, and a page listing them would bury the one that matters.
MEANINGFUL_SKILLS = 2
MEANINGFUL_SEATS = 1
MEANINGFUL_SERVICES = 1
MEANINGFUL_COMMITMENT = 1


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one}" if count == 1 else f"{count} {many}"


# ---------------------------------------------------------------------------
# The sentence for each answer
#
# Written out one at a time rather than assembled from parts, because the parts
# that would make them uniform are exactly what makes copy read as though it
# came out of a machine.
# ---------------------------------------------------------------------------
def _field_sentence(answer: Any, direction: str) -> str:
    label = mapping.field_label(answer)
    if direction == RAISES:
        return f"Mentors in {label} tend to charge more than mentors in other fields."
    if direction == LOWERS:
        return f"Mentors in {label} tend to charge less than mentors in other fields."
    return f"Mentors in {label} charge about what mentors in other fields charge."


def _group_sentence(answer: Any, direction: str) -> str:
    seats = int(answer)
    if seats <= 1:
        if direction == RAISES:
            return (
                "One to one sessions tend to be priced higher than sessions "
                "for a group."
            )
        if direction == LOWERS:
            return (
                "One to one sessions tend to be priced lower per session than "
                "sessions for a group."
            )
        return "Your group size makes little difference to this suggestion."
    if direction == RAISES:
        return (
            f"A session for a group of {seats} tends to be priced higher than "
            f"a one to one session."
        )
    if direction == LOWERS:
        return (
            f"A session for a group of {seats} tends to be priced lower than "
            f"a one to one session."
        )
    return f"A session for a group of {seats} is priced much like a one to one session."


NEVER_LOWERS = "Adding a skill never lowers this suggestion."


def _skills_sentence(answer: Any, direction: str) -> str:
    count = int(answer)
    covered = (
        "You have not listed any skills yet"
        if count == 0
        else f"Covering {_plural(count, 'skill', 'skills')}"
    )
    if direction == RAISES:
        return f"{covered} raises this suggestion. {NEVER_LOWERS}"
    if direction == LOWERS:
        return (
            f"{covered} lowers this suggestion, next to mentors covering a "
            f"more usual number. {NEVER_LOWERS}"
        )
    return f"{covered} makes little difference to this suggestion. {NEVER_LOWERS}"


def _verified_sentence(answer: Any, direction: str) -> str:
    if bool(answer):
        if direction == RAISES:
            return "Verified mentors tend to charge more than unverified ones."
        if direction == LOWERS:
            return "Verified mentors tend to charge less than unverified ones."
        return "Being verified makes little difference to this suggestion."
    if direction == RAISES:
        return "Mentors who are not verified yet tend to charge more here."
    if direction == LOWERS:
        return "Mentors who are not verified yet tend to charge less."
    return "Verification makes little difference to this suggestion."


def _services_sentence(answer: Any, direction: str) -> str:
    offered = _plural(int(answer), "service", "services")
    if direction == RAISES:
        return f"Mentors offering {offered} tend to charge more."
    if direction == LOWERS:
        return f"Mentors offering {offered} tend to charge less."
    return f"Offering {offered} makes little difference to this suggestion."


def _commitment_sentence(answer: Any, direction: str) -> str:
    asked = _plural(int(answer), "session", "sessions")
    if direction == RAISES:
        return f"Mentors asking for a minimum of {asked} tend to charge more."
    if direction == LOWERS:
        return f"Mentors asking for a minimum of {asked} tend to charge less."
    return (
        f"Asking for a minimum of {asked} makes little difference to this suggestion."
    )


CHOICE_SENTENCES = {
    mapping.CHOICE_FIELD: _field_sentence,
    mapping.CHOICE_GROUP_SIZE: _group_sentence,
    mapping.CHOICE_SKILLS: _skills_sentence,
    mapping.CHOICE_VERIFIED: _verified_sentence,
    mapping.CHOICE_SERVICES: _services_sentence,
    mapping.CHOICE_COMMITMENT: _commitment_sentence,
}

THEME_SUBJECTS = {
    mapping.THEME_REVIEWS: "Mentors whose reviews have come in like yours",
    mapping.THEME_RATINGS: "Mentors rated like you",
    mapping.THEME_BOOKINGS: "Mentors booked as much as you",
    mapping.THEME_STANDING: "Mentors with your standing and time here",
}


def _theme_sentence(theme: str, direction: str) -> str:
    subject = THEME_SUBJECTS[theme]
    if direction == RAISES:
        return f"{subject} tend to charge more. {ASSOCIATION_NOTE}"
    if direction == LOWERS:
        return f"{subject} tend to charge less. {ASSOCIATION_NOTE}"
    return f"{subject} charge about the same as everybody else. {ASSOCIATION_NOTE}"


# How a factor is named inside a sentence about the gap.
GAP_PHRASES = {
    mapping.CHOICE_FIELD: "your field",
    mapping.CHOICE_GROUP_SIZE: "your group size",
    mapping.CHOICE_SKILLS: "the skills you cover",
    mapping.CHOICE_VERIFIED: "your verification",
    mapping.CHOICE_SERVICES: "the services you offer",
    mapping.CHOICE_COMMITMENT: "your minimum commitment",
    mapping.THEME_REVIEWS: "how your reviews have come in",
    mapping.THEME_RATINGS: "what mentees rate you",
    mapping.THEME_BOOKINGS: "how much of your time is booked",
    mapping.THEME_STANDING: "your standing and time here",
    OTHER_KEY: "several smaller things together",
}


def direction_of(effect_pct: int) -> str:
    """Which of the three words an effect of this size is described by."""
    if effect_pct > 0:
        return RAISES
    if effect_pct < 0:
        return LOWERS
    return LITTLE


def _as_pct(multiplier: float) -> int:
    return int(round((multiplier - 1.0) * 100))


# ---------------------------------------------------------------------------
# The account itself
# ---------------------------------------------------------------------------
def explain_price(
    *,
    pricing: PricingService,
    inputs: dict[str, Any],
    model_used: str,
    suggested_price: int,
) -> dict[str, Any]:
    """
    One suggestion, taken apart into the answers behind it.

    ``suggested_price`` is the price the mentor was actually given, after the
    correction the prediction service applies, and everything here is made to
    reconcile against it rather than against the model's raw answer. The
    difference between the two is real and is carried by the skills line, which
    is the axis the correction acts on.
    """
    answers = mapping.answers_from_inputs(inputs)
    start, parts = pricing.log_contributions(inputs, model_used)

    # Fixed inputs are folded into the starting point. The session format is
    # held at one value for everybody; a mentor without a record is held at a
    # starting time on the platform, and for one with a record that is a
    # measurement instead, so it moves into the themes below.
    fixed = list(mapping.EXPLANATION_FIXED_COLUMNS)
    if model_used != FULL:
        fixed.append(mapping.COLUMN_TENURE)
    baseline_log = start + sum(parts[column] for column in fixed)
    baseline = max(float(math.expm1(baseline_log)), 1.0)

    candidates = _candidates(parts, answers, model_used)

    # Shown, hidden, and the one line that closes the arithmetic. The skills
    # line is always shown: it carries the correction, so hiding it would hide
    # the only place the account and the price are reconciled.
    big = [
        one for one in candidates if abs(_as_pct(one["multiplier"])) >= SMALL_EFFECT_PCT
    ]
    big.sort(key=lambda one: abs(_as_pct(one["multiplier"])), reverse=True)
    shown = big[: MAX_FACTORS - 1]
    hidden = [one for one in candidates if one not in shown]

    rows = [_row(one, _as_pct(one["multiplier"])) for one in shown]
    other_row = _other_row(hidden)

    settled = 1.0
    for row in rows + ([other_row] if other_row else []):
        settled *= 1.0 + row["effect_pct"] / 100.0
    wanted = float(suggested_price) / baseline
    rows.append(
        _row(
            {
                "key": mapping.CHOICE_SKILLS,
                "label": mapping.EXPLANATION_CHOICES[mapping.CHOICE_SKILLS]["label"],
                "answer": answers[mapping.CHOICE_SKILLS],
                "association": False,
            },
            _as_pct(wanted / settled if settled else 1.0),
        )
    )
    rows.sort(key=lambda row: abs(row["effect_pct"]), reverse=True)

    started = int(round(baseline))
    return {
        "baseline_price": started,
        "baseline_sentence": (
            f"A mentor in your situation starts around "
            f"{started:,} {mapping.CURRENCY}."
        ),
        "suggested_price": int(suggested_price),
        "currency": mapping.CURRENCY,
        "factors": rows,
        "other_small_effects": other_row,
        "combination_note": COMBINATION_NOTE,
        "limitation": LIMITATION,
        "profile_note": PROFILE_NOTE,
    }


def _candidates(
    parts: dict[str, float], answers: dict[str, Any], model_used: str
) -> list[dict[str, Any]]:
    """
    Everything that could be shown as a reason, before any of it is chosen.

    The skills line is left out: it is added last, with whatever effect makes
    the account come to the price the mentor was given.
    """
    candidates: list[dict[str, Any]] = [
        {
            "key": key,
            "label": choice["label"],
            "multiplier": math.exp(parts[choice["column"]]),
            "answer": answers[key],
            "association": False,
        }
        for key, choice in mapping.EXPLANATION_CHOICES.items()
        if key != mapping.CHOICE_SKILLS
    ]
    if model_used == FULL:
        candidates.extend(
            {
                "key": theme,
                "label": mapping.explanation_theme_label(theme),
                "multiplier": math.exp(sum(parts[column] for column in columns)),
                "answer": None,
                "association": True,
            }
            for theme, columns in mapping.explanation_theme_columns().items()
        )
    return candidates


def _other_row(hidden: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The lines too small to show, multiplied into one that says so."""
    if not hidden:
        return None
    together = 1.0
    for one in hidden:
        together *= one["multiplier"]
    effect = _as_pct(together)
    return {
        "key": OTHER_KEY,
        "label": OTHER_LABEL,
        "direction": direction_of(effect),
        "effect_pct": effect,
        "sentence": "Everything else about your answers comes to this together.",
        "association": False,
    }


def _row(one: dict[str, Any], effect_pct: int) -> dict[str, Any]:
    direction = direction_of(effect_pct)
    key = one["key"]
    sentence = (
        _theme_sentence(key, direction)
        if one["association"]
        else CHOICE_SENTENCES[key](one["answer"], direction)
    )
    return {
        "key": key,
        "label": one["label"],
        "direction": direction,
        "effect_pct": effect_pct,
        "sentence": sentence,
        "association": bool(one["association"]),
    }


def reconciled_price(explanation: dict[str, Any]) -> float:
    """
    What the shown effects multiply out to, from the baseline.

    The identity the account stands on, written once so that the service, the
    tests and anybody reading this file check the same arithmetic.
    """
    total = float(explanation["baseline_price"])
    rows = list(explanation["factors"])
    if explanation["other_small_effects"]:
        rows.append(explanation["other_small_effects"])
    for row in rows:
        total *= 1.0 + row["effect_pct"] / 100.0
    return total


# ---------------------------------------------------------------------------
# Where the price lands among similar mentors
# ---------------------------------------------------------------------------
def _difference(key: str, label: str, sentence: str) -> dict[str, str]:
    return {"key": key, "label": label, "sentence": sentence}


def _differences(
    answers: dict[str, Any], typical: dict[str, Any]
) -> list[dict[str, str]]:
    """What this mentor offers that the mentors beside them do not."""
    if not typical:
        return []
    found: list[dict[str, str]] = []

    seats = int(answers[mapping.CHOICE_GROUP_SIZE])
    usual_seats = int(round(typical["max_mentees"]))
    if abs(seats - usual_seats) >= MEANINGFUL_SEATS:
        found.append(
            _difference(
                mapping.CHOICE_GROUP_SIZE,
                "Group size",
                f"Your sessions take {_plural(seats, 'mentee', 'mentees')}, "
                f"where a typical similar mentor takes "
                f"{_plural(usual_seats, 'mentee', 'mentees')}.",
            )
        )

    skills = int(answers[mapping.CHOICE_SKILLS])
    usual_skills = int(round(typical["skills_covered"]))
    if abs(skills - usual_skills) >= MEANINGFUL_SKILLS:
        found.append(
            _difference(
                mapping.CHOICE_SKILLS,
                "Skills covered",
                f"You cover {_plural(skills, 'skill', 'skills')}, where a "
                f"typical similar mentor covers "
                f"{_plural(usual_skills, 'skill', 'skills')}.",
            )
        )

    verified = bool(answers[mapping.CHOICE_VERIFIED])
    share = float(typical["profile_verified"])
    if verified and share < 0.5:
        found.append(
            _difference(
                mapping.CHOICE_VERIFIED,
                "Verification",
                "Your profile is verified, where most of the mentors you are "
                "compared with are not.",
            )
        )
    elif not verified and share >= 0.5:
        found.append(
            _difference(
                mapping.CHOICE_VERIFIED,
                "Verification",
                "Your profile is not verified yet, where most of the mentors "
                "you are compared with are.",
            )
        )

    services = int(answers[mapping.CHOICE_SERVICES])
    usual_services = int(round(typical["services_count"]))
    if abs(services - usual_services) >= MEANINGFUL_SERVICES:
        found.append(
            _difference(
                mapping.CHOICE_SERVICES,
                "Services offered",
                f"You offer {_plural(services, 'service', 'services')}, where "
                f"a typical similar mentor offers "
                f"{_plural(usual_services, 'service', 'services')}.",
            )
        )

    commitment = int(answers[mapping.CHOICE_COMMITMENT])
    usual_commitment = int(round(typical["min_commitment"]))
    if abs(commitment - usual_commitment) >= MEANINGFUL_COMMITMENT:
        found.append(
            _difference(
                mapping.CHOICE_COMMITMENT,
                "Minimum commitment",
                f"You ask for a minimum of "
                f"{_plural(commitment, 'session', 'sessions')}, where a "
                f"typical similar mentor asks for "
                f"{_plural(usual_commitment, 'session', 'sessions')}.",
            )
        )
    return found


def _gap_sentence(position: str, factors: list[dict[str, Any]]) -> str | None:
    """
    The one or two things that most account for the gap, named in words.

    Only the factors pointing the same way as the gap: a mentor told their
    price is high because of two things that lower it would rightly stop
    reading. Two at most, because a list of five is not an explanation.
    """
    if position == POSITION_ABOVE:
        pointing = [row for row in factors if row["effect_pct"] > 0]
        way = "higher"
    elif position == POSITION_BELOW:
        pointing = [row for row in factors if row["effect_pct"] < 0]
        way = "lower"
    else:
        return None
    if not pointing:
        return None
    named = [GAP_PHRASES[row["key"]] for row in pointing[:2]]
    reason = named[0] if len(named) == 1 else f"{named[0]} and {named[1]}"
    return (
        f"Your suggestion is {way} than most similar mentors, mainly because "
        f"of {reason}."
    )


def compare_price(
    *,
    found: comparables_module.ComparableSet,
    suggested_price: int,
    inputs: dict[str, Any],
    factors: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Where this suggestion sits among the mentors the price screen draws.

    Read off the same reduced sample as the chart and the band beside it, so a
    sentence here and a dot there are describing the same mentors.
    """
    summary = comparables_module.summarise(found)
    typical = comparables_module.typical_profile(found)
    answers = mapping.answers_from_inputs(inputs)

    low, high = summary["p25_price"], summary["p75_price"]
    if low is None or high is None:
        position = POSITION_UNKNOWN
        sentence = (
            "We do not have enough similar mentors to say where this "
            "suggestion sits among them."
        )
    elif suggested_price < low:
        position = POSITION_BELOW
        sentence = (
            f"Your suggestion is below the middle of what similar mentors "
            f"charge, which is {low:,} to {high:,} {mapping.CURRENCY}."
        )
    elif suggested_price > high:
        position = POSITION_ABOVE
        sentence = (
            f"Your suggestion is above the middle of what similar mentors "
            f"charge, which is {low:,} to {high:,} {mapping.CURRENCY}."
        )
    else:
        position = POSITION_WITHIN
        sentence = (
            f"Your suggestion sits in the middle of what similar mentors "
            f"charge, which is {low:,} to {high:,} {mapping.CURRENCY}."
        )

    return {
        "position": position,
        "percentile": comparables_module.price_percentile(found, suggested_price),
        "median_price": summary["median_price"],
        "band_low": low,
        "band_high": high,
        "compared_with": int(typical.get("count", 0)),
        "matched_total": int(summary["count"]),
        "match_description": summary["match_description"],
        "sentence": sentence,
        "explains_gap": _gap_sentence(position, factors),
        "differences": _differences(answers, typical),
    }
