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
from dataclasses import dataclass
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

# Unless five rows would leave a grouped row larger than the smallest row on
# show. A reader who sees "other small effects" below a line twice its size
# has been told the arithmetic was tidied in a way it was not, so rather than
# print that, the account promotes the next largest lines until the grouped
# one really is the smallest, up to this many rows. Seven rather than no
# limit at all: past seven the list stops being read, and an account nobody
# reads is worse than one that groups honestly.
MAX_FACTORS_PROMOTED = 7

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
TRACK_RECORD_NOTE = "This is a pattern among similar mentors, not a cause."

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
@dataclass(frozen=True)
class Detail:
    """
    What a sentence may look at beyond the answer it is about.

    Two things, and both are here to stop a sentence contradicting the figure
    printed beside it. The size of the effect, so a line too small to matter
    says so rather than claiming a direction. And the group size the mentors
    in the comparison typically offer, so a sentence about a group compares
    it with the groups it is actually being compared against.
    """

    effect_pct: int = 0
    typical_group_size: int | None = None


def _field_sentence(answer: Any, direction: str, detail: Detail) -> str:
    label = mapping.field_label(answer)
    if direction == RAISES:
        return f"Mentors in {label} tend to charge more than mentors in other fields."
    if direction == LOWERS:
        return f"Mentors in {label} tend to charge less than mentors in other fields."
    return f"Mentors in {label} charge about what mentors in other fields charge."


# ---------------------------------------------------------------------------
# The group size sentence
#
# Rewritten because the first version of it said the opposite of the price it
# sat beside. It read the effect as though it had been measured against a one
# to one session, so a mentor seeing a group of three priced above their own
# one to one rate was told that "a session for a group of 3 tends to be
# priced lower than a one to one session". Both claims were on one screen.
#
# The effect is measured against the average mentor in the data, not against
# a one to one session, and there is no way to turn it into a statement about
# one to one sessions without inventing the comparison.
#
# So the sentence makes the one comparison this page can support: this group
# against the group the mentors in the comparison sample typically offer.
# Those mentors are already on the screen, directly below, which is what
# makes the two halves of it agree.
#
# Two rules follow from the fault. The direction word comes from the sign of
# the effect and from nothing else, so the words and the number can never
# disagree again. And one to one is named only when the mentor's own group is
# one, because anywhere else it is a comparison nobody asked for.
# ---------------------------------------------------------------------------
def _group_subject(seats: int) -> tuple[str, str]:
    """How a group is named, and the verb that follows it."""
    if seats <= 1:
        return "Your one to one sessions", "are"
    return f"Your group of {seats}", "is"


def _group_sentence(answer: Any, direction: str, detail: Detail) -> str:
    seats = int(answer)
    subject, verb = _group_subject(seats)

    # Too small to carry a direction. Said as such rather than dressed up: a
    # one per cent effect described as raising a price claims more than the
    # number holds.
    if abs(detail.effect_pct) < SMALL_EFFECT_PCT or direction == LITTLE:
        return f"{subject} make little difference to this suggestion."

    movement = "up" if direction == RAISES else "down"
    usual = detail.typical_group_size
    if usual is None:
        # Nobody to compare the group with. The effect is real and is still
        # reported, without a comparison that was never measured.
        return f"{subject} tend to move the price per session {movement}."

    if seats > usual:
        stands = (
            f"{verb} larger than the typical group of {usual} among similar mentors"
        )
    elif seats < usual:
        stands = (
            f"{verb} smaller than the typical group of {usual} among similar mentors"
        )
    else:
        stands = f"{verb} the same size as the typical group among similar mentors"
    return (
        f"{subject} {stands}, and that tends to move the price per session {movement}."
    )


NEVER_LOWERS = "Adding a skill never lowers this suggestion."


def _skills_sentence(answer: Any, direction: str, detail: Detail) -> str:
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


def _verified_sentence(answer: Any, direction: str, detail: Detail) -> str:
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


def _services_sentence(answer: Any, direction: str, detail: Detail) -> str:
    offered = _plural(int(answer), "service", "services")
    if direction == RAISES:
        return f"Mentors offering {offered} tend to charge more."
    if direction == LOWERS:
        return f"Mentors offering {offered} tend to charge less."
    return f"Offering {offered} makes little difference to this suggestion."


def _commitment_sentence(answer: Any, direction: str, detail: Detail) -> str:
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


# ---------------------------------------------------------------------------
# The two sentences about a mentor's record
#
# Demand keeps a sentence of its own whatever its size. It is the claim this
# system is built on, so an account that let it be grouped away would hide
# the thing the account was written to show.
#
# Everything else about a record is said in one sentence, and that sentence
# deliberately does not name which part of the record moved the price. Named
# on its own, the ratings line said that mentors rated like this mentor tend
# to charge less, which reads as an instruction to care less about ratings.
# What it records is that in this data the mentors charging most are not the
# ones rated highest, which is a fact about who charges what rather than
# advice about how to be rated. Said together, and said as an association, it
# is a description again.
# ---------------------------------------------------------------------------
def _demand_sentence(answer: Any, direction: str, detail: Detail) -> str:
    booked = "Mentors whose time is booked as much as yours"
    if direction == RAISES:
        return f"{booked} tend to charge more. {ASSOCIATION_NOTE}"
    if direction == LOWERS:
        return f"{booked} tend to charge less. {ASSOCIATION_NOTE}"
    return f"{booked} charge about the same as everybody else. {ASSOCIATION_NOTE}"


def _track_record_sentence(answer: Any, direction: str, detail: Detail) -> str:
    size = abs(detail.effect_pct)
    together = "Your ratings and activity history together"
    if direction == LITTLE or size == 0:
        return (
            f"{together} make little difference to this suggestion. "
            f"{TRACK_RECORD_NOTE}"
        )
    movement = "up" if direction == RAISES else "down"
    return (
        f"{together} move the suggestion {movement} by {size} percent. "
        f"{TRACK_RECORD_NOTE}"
    )


GROUP_SENTENCES = {
    mapping.THEME_DEMAND: _demand_sentence,
    mapping.THEME_TRACK_RECORD: _track_record_sentence,
}


# How a factor is named inside a sentence about the gap.
GAP_PHRASES = {
    mapping.CHOICE_FIELD: "your field",
    mapping.CHOICE_GROUP_SIZE: "your group size",
    mapping.CHOICE_SKILLS: "the skills you cover",
    mapping.CHOICE_VERIFIED: "your verification",
    mapping.CHOICE_SERVICES: "the services you offer",
    mapping.CHOICE_COMMITMENT: "your minimum commitment",
    mapping.THEME_DEMAND: "how much your time is in demand",
    mapping.THEME_TRACK_RECORD: "your track record on the platform",
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
    typical_group_size: int | None = None,
) -> dict[str, Any]:
    """
    One suggestion, taken apart into the answers behind it.

    ``suggested_price`` is the price the mentor was actually given, after the
    correction the prediction service applies, and everything here is made to
    reconcile against it rather than against the model's raw answer. The
    difference between the two is real and is carried by the skills line, which
    is the axis the correction acts on.

    ``typical_group_size`` is the group size the mentors in the comparison
    sample typically offer. It is passed in rather than looked up here so that
    the sentence about a group and the comparison below it are reading the
    same mentors. Absent when there is nobody to compare with, and the
    sentence then says less rather than inventing a comparison.
    """
    answers = mapping.answers_from_inputs(inputs)
    start, parts = pricing.log_contributions(inputs, model_used)

    # Fixed inputs are folded into the starting point. The session format is
    # held at one value for everybody; a mentor without a record is held at a
    # starting time on the platform, and for one with a record that is a
    # measurement instead, so it moves into the groups below.
    fixed = list(mapping.EXPLANATION_FIXED_COLUMNS)
    if model_used != FULL:
        fixed.append(mapping.COLUMN_TENURE)
    baseline_log = start + sum(parts[column] for column in fixed)
    baseline = max(float(math.expm1(baseline_log)), 1.0)

    detail = Detail(typical_group_size=typical_group_size)
    candidates = _candidates(parts, answers, model_used)

    # Demand is never a line that can be grouped away, so it is held out of
    # the ordering and placed whatever its size. The skills line is held out
    # for a different reason: it is worked out last, from whatever is left
    # over, because it carries the correction the prediction service applied.
    forced = [one for one in candidates if one["key"] == mapping.THEME_DEMAND]
    pool = sorted(
        (one for one in candidates if one not in forced),
        key=lambda one: abs(_as_pct(one["multiplier"])),
        reverse=True,
    )

    taken = 1 + len(forced)
    worth_showing = sum(
        1 for one in pool if abs(_as_pct(one["multiplier"])) >= SMALL_EFFECT_PCT
    )
    fewest = max(0, min(MAX_FACTORS - taken, worth_showing))
    most = max(fewest, MAX_FACTORS_PROMOTED - taken)

    # Widen until the grouped row is genuinely the smallest thing on the
    # card, or until there is no more room. A grouped row larger than a row
    # shown above it tells the reader the account was tidied in a way it was
    # not.
    rows, other_row = _settled(
        pool[:fewest],
        pool[fewest:],
        forced,
        answers,
        baseline,
        suggested_price,
        detail,
    )
    for slots in range(fewest + 1, most + 1):
        if _grouped_is_smallest(rows, other_row):
            break
        rows, other_row = _settled(
            pool[:slots],
            pool[slots:],
            forced,
            answers,
            baseline,
            suggested_price,
            detail,
        )

    started = int(round(baseline))
    return {
        "baseline_price": started,
        "baseline_sentence": (
            f"A typical mentor's price is around {started:,} {mapping.CURRENCY}."
        ),
        "summary_sentence": _summary_sentence(started, int(suggested_price)),
        "suggested_price": int(suggested_price),
        "currency": mapping.CURRENCY,
        "factors": rows,
        "other_small_effects": other_row,
        "combination_note": COMBINATION_NOTE,
        "limitation": LIMITATION,
        "profile_note": PROFILE_NOTE,
    }


def _summary_sentence(baseline: int, suggested: int) -> str:
    """
    The one line between the typical price and the rows that move it.

    Said as a distance from the typical price rather than as a verdict. A
    mentor reading "twenty per cent below" knows both numbers and which side
    of the other they are on; "below average" would tell them neither.
    """
    gap = 0 if baseline <= 0 else int(round(abs(suggested - baseline) / baseline * 100))
    price = f"{suggested:,} {mapping.CURRENCY}"
    if gap == 0:
        stands = "about the same as that typical price"
    else:
        side = "above" if suggested > baseline else "below"
        stands = f"{gap} percent {side} that typical price"
    return f"We suggest {price}, which is {stands}. Here is what moves it:"


def _settled(
    shown: list[dict[str, Any]],
    hidden: list[dict[str, Any]],
    forced: list[dict[str, Any]],
    answers: dict[str, Any],
    baseline: float,
    suggested_price: int,
    detail: Detail,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """
    One choice of rows, closed by the skills line so the arithmetic comes out.

    Whatever is not shown is multiplied into the grouped row, and the skills
    line is then whatever is needed for the baseline and the rows together to
    reach the price the mentor was quoted. That is where the monotone
    correction lands, which is why the skills line is never hidden.
    """
    rows = [
        _row(one, _as_pct(one["multiplier"]), detail) for one in forced + list(shown)
    ]
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
            detail,
        )
    )
    rows.sort(key=lambda row: abs(row["effect_pct"]), reverse=True)
    return rows, other_row


def _grouped_is_smallest(
    rows: list[dict[str, Any]], other_row: dict[str, Any] | None
) -> bool:
    """Whether the grouped row is smaller than every row shown above it."""
    if other_row is None:
        return True
    return abs(other_row["effect_pct"]) < min(abs(row["effect_pct"]) for row in rows)


def _candidates(
    parts: dict[str, float], answers: dict[str, Any], model_used: str
) -> list[dict[str, Any]]:
    """
    Everything that could be shown as a reason, before any of it is chosen.

    The skills line is left out: it is added last, with whatever effect makes
    the account come to the price the mentor was given.

    A mentor with a record adds two lines rather than four. Each carries the
    themes under it as components, so grouping two themes into one sentence
    does not amount to dropping either number: both are still reported in the
    table behind the disclosure.
    """
    candidates: list[dict[str, Any]] = [
        {
            "key": key,
            "label": choice["label"],
            "multiplier": math.exp(parts[choice["column"]]),
            "answer": answers[key],
            "association": False,
            "components": [],
        }
        for key, choice in mapping.EXPLANATION_CHOICES.items()
        if key != mapping.CHOICE_SKILLS
    ]
    if model_used == FULL:
        themes = {
            theme: math.exp(sum(parts[column] for column in columns))
            for theme, columns in mapping.explanation_theme_columns().items()
        }
        for group, names in mapping.explanation_group_themes().items():
            multiplier = 1.0
            for name in names:
                multiplier *= themes[name]
            candidates.append(
                {
                    "key": group,
                    "label": mapping.explanation_group_label(group),
                    "multiplier": multiplier,
                    "answer": None,
                    "association": True,
                    "components": [
                        {
                            "key": name,
                            "label": mapping.explanation_theme_label(name),
                            "effect_pct": _as_pct(themes[name]),
                        }
                        for name in names
                    ],
                }
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
        "components": [],
    }


def _row(one: dict[str, Any], effect_pct: int, detail: Detail) -> dict[str, Any]:
    direction = direction_of(effect_pct)
    key = one["key"]
    said = Detail(effect_pct=effect_pct, typical_group_size=detail.typical_group_size)
    write = GROUP_SENTENCES.get(key) or CHOICE_SENTENCES[key]
    return {
        "key": key,
        "label": one["label"],
        "direction": direction,
        "effect_pct": effect_pct,
        "sentence": write(one["answer"], direction, said),
        "association": bool(one["association"]),
        "components": list(one.get("components") or []),
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
