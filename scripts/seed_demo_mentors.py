"""
Seed ten established mentors, so the whole platform can be demonstrated.

A mentor who has just registered is priced from eight answers and nothing
else. A mentor with a track record is priced from those eight plus
twenty-eight figures the platform has accumulated about them, and is shown
their advice next to what they charge today. The second path is the more
interesting half of the system and, on a fresh database, there is nobody on
it: the platform has no activity yet, so no mentor has a record.

This script supplies ten. They are fictional people, and so is every word
about them. What is real is the *shape* of the record: the thirty-odd figures
are taken from one row of the modelled population, so the track records are
internally consistent in the way a real one would be, which a hand-written
record would not be. Rating, review counts, booked shares and tenure all
describe the same provider.

The ten are chosen to be worth looking at rather than at random:

* **at least five different fields**, so the field list and the directory
  filters are visibly in use,
* **four one-to-one mentors and six running groups**, with the group sizes as
  different from each other as the population allows. A session for one is not
  a smaller group: it is the other thing the platform offers, it carries its
  own label, and its per-mentee figure is its session price rather than a
  division of it,
* **one mentor charging clearly above their advised range, one inside it and
  one below it.** Those three are what make the comparison on a
  recommendation demonstrable at all,
* **nine verified and one not**, so the checkmark on the directory is visibly
  something a mentor can be without and not a decoration every card carries.

Each of them gets the whole flow rather than just a profile: a service, a
track record, an advisory price from the full model, and a decision about that
price, so the dashboard and the history have something in them on a fresh
database. Their month-by-month activity comes from
``scripts/build_demo_activity.py``, which this script runs at the end unless
told not to.

They can all be signed in to. The password is read from ``DEMO_PASSWORD``, or
is ``Pathwise-demo-1`` when that is unset, and the addresses and the password
are printed at the end of a run: they are fictional accounts on a
documentation domain, created to be signed in to during a demonstration.

Nothing identifying is copied or stored. The names come from a fictional pool,
the addresses are all ``example.com``, and the only link back to the source
row is ``source_key``, an index into the filtered population: it exists so
that running this script twice recognises the mentors it already wrote, and it
is useless without the dataset.

Run from the project root, against the database ``DATABASE_URL`` points at:

    python scripts/seed_demo_mentors.py                  # create the ten
    python scripts/seed_demo_mentors.py --no-activity    # skip the chart data
    python scripts/seed_demo_mentors.py --reset          # remove them again

Both the dataset and the prepared models are git-ignored build inputs, so a
fresh clone cannot run this until both exist. A missing one fails with a
message naming it.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_demo_activity import (  # noqa: E402
    ActivityInputError,
    build_activity,
)
from scripts.build_demo_activity import describe as describe_activity  # noqa: E402
from src.data.population import (  # noqa: E402
    KEY_COLUMN,
    TARGET_COLUMN,
    PopulationError,
    modelled_population,
)
from src.db import Mentor, MentorHistory, Service, create_db_engine  # noqa: E402
from src.db.mentor_models import (  # noqa: E402
    PricingDecision,
    PricingRecommendation,
)
from src.mentor import mapping, security  # noqa: E402
from src.mentor.prediction import (  # noqa: E402
    FULL,
    POSITION_ABOVE,
    POSITION_BELOW,
    POSITION_WITHIN,
    AssetsUnavailableError,
    PriceRecommendation,
    PricingService,
    load_pricing_service,
    position_vs_range,
)

# Everything here is deterministic, and this is the one number that decides
# the parts of it that are arbitrary: which candidate is taken when several
# would do, which fictional name goes with which record, and which skills a
# mentor offers. The project uses 42 everywhere else for the same reason.
SEED = 42

DEMO_MENTORS = 10

# Four of the ten take a single mentee and six take a group. Both numbers are
# here rather than in the selection code because they are the shape of the
# demonstration rather than a detail of how it is assembled.
ONE_TO_ONE_MENTORS = 4
GROUP_MENTORS = DEMO_MENTORS - ONE_TO_ONE_MENTORS

# The fewest different fields the ten may cover. Ten different ones would be
# better and the selection prefers them, but only part of the population
# offers a session for one mentee and those rows do not cover every field, so
# a hard requirement of ten would fail on a dataset rather than describe one.
MIN_FIELDS = 5

# Nine of the ten are verified. The tenth is not, so that the checkmark on the
# directory is visibly something a mentor can be without: a list where every
# card carries it says nothing about any of them.
UNVERIFIED_MENTORS = 1

# What the demonstration accounts sign in with. Read from the environment so a
# shared demonstration can use something else, with a default that is printed
# at the end of every run. These are fictional accounts on a domain reserved
# for documentation, created to be signed in to.
DEMO_PASSWORD_VARIABLE = "DEMO_PASSWORD"
DEFAULT_DEMO_PASSWORD = "Pathwise-demo-1"

# ---------------------------------------------------------------------------
# The population
#
# The filters, and the opaque key, live in src.data.population, because
# scripts/build_comparables.py has to agree with this script about both. A key
# that meant one thing here and another there would compare a seeded mentor
# against themselves.
#
# One filter is set here rather than shared: how much of a record a row needs.
# A row turned into a mentor with a full track record needs more than a row
# shown as one of two hundred comparable mentors, so this asks for ten reviews
# where the comparables build asks for five.
# ---------------------------------------------------------------------------
MIN_REVIEWS = 10

# ---------------------------------------------------------------------------
# Who they are
#
# One template per field. The headline and the bio are what a mentee would
# read, so they are written per field rather than generated: a sentence about
# mentoring in law should not read as a sentence about mentoring in design
# with one word swapped.
# ---------------------------------------------------------------------------
FIRST_NAMES: tuple[str, ...] = (
    "Amara",
    "Daniel",
    "Priya",
    "Joseph",
    "Lerato",
    "Mitchell",
    "Fatima",
    "Grace",
    "Samuel",
    "Nadia",
    "Olivia",
    "Elias",
    "Wanjiru",
    "Thomas",
    "Yasmin",
)

SURNAME_INITIALS: tuple[str, ...] = tuple("ABDEHKLMNOPRSTW")


@dataclass(frozen=True)
class FieldProfile:
    """The profile text and education level for a mentor in one field."""

    headline: str
    bio: str
    education_level: str


FIELD_PROFILES: dict[str, FieldProfile] = {
    "executive_leadership": FieldProfile(
        headline="Coaching senior managers into their first executive role",
        bio=(
            "Twenty years in operations, the last eight on an executive team. "
            "I work with managers preparing for their first director or "
            "C-suite appointment."
        ),
        education_level="masters",
    ),
    "management_consulting": FieldProfile(
        headline="Case interviews, client work and the first two years",
        bio=(
            "Former strategy consultant, now independent. I help candidates "
            "through case interviews and help new joiners find their footing "
            "on client engagements."
        ),
        education_level="masters",
    ),
    "law": FieldProfile(
        headline="Pupillage, training contracts and early practice",
        bio=(
            "Admitted advocate in commercial practice. I mentor law graduates "
            "through applications, pupillage and the first years of practice."
        ),
        education_level="postgraduate_diploma",
    ),
    "investment_finance": FieldProfile(
        headline="Breaking into investment roles, and surviving year one",
        bio=(
            "Buy-side analyst turned portfolio manager. I cover technical "
            "interviews, modelling tests and what the first year on a desk "
            "actually asks of you."
        ),
        education_level="masters",
    ),
    "banking_accounting": FieldProfile(
        headline="Qualification, audit rotations and moving into industry",
        bio=(
            "Chartered accountant, ten years across audit and corporate "
            "finance. I mentor trainees through qualification and the move "
            "from practice into industry."
        ),
        education_level="bachelors",
    ),
    "medicine_health": FieldProfile(
        headline="Clinical training, specialty choice and applications",
        bio=(
            "Hospital physician and clinical supervisor. I work with students "
            "and junior doctors on specialty choice, applications and "
            "interviews."
        ),
        education_level="doctorate",
    ),
    "engineering": FieldProfile(
        headline="From graduate engineer to chartered, without the guesswork",
        bio=(
            "Structural engineer and chartership assessor. I mentor graduates "
            "through their competency reports, portfolios and professional "
            "review."
        ),
        education_level="bachelors",
    ),
    "technology_software": FieldProfile(
        headline="Helping engineers get hired, and then promoted",
        bio=(
            "Software engineer, then engineering manager. I cover interview "
            "preparation, technical portfolios and the step from senior "
            "engineer to lead."
        ),
        education_level="bachelors",
    ),
    "marketing_communications": FieldProfile(
        headline="Portfolios, pitches and your first brand role",
        bio=(
            "Brand and communications lead across agency and in-house teams. "
            "I help early-career marketers build a portfolio that gets read."
        ),
        education_level="bachelors",
    ),
    "creative_arts_design": FieldProfile(
        headline="Portfolio reviews for designers and illustrators",
        bio=(
            "Working designer and part-time lecturer. I review portfolios "
            "honestly and help people price and pitch their own work."
        ),
        education_level="diploma",
    ),
    "education_teaching": FieldProfile(
        headline="Classroom practice, registration and leadership tracks",
        bio=(
            "Teacher and head of department. I mentor newly qualified "
            "teachers through registration, observations and the move into "
            "school leadership."
        ),
        education_level="postgraduate_diploma",
    ),
    "community_social_work": FieldProfile(
        headline="Practice supervision for social and community workers",
        bio=(
            "Registered social worker and practice supervisor. I work with "
            "new practitioners on casework, boundaries and staying in the "
            "profession."
        ),
        education_level="bachelors",
    ),
}

# ---------------------------------------------------------------------------
# What the ten are chosen to show
#
# Five price levels, read as the ratio of what the mentor charges today to
# what the model advises. The three outer ones are the point of the exercise:
# the recommendation response reports whether a mentor's current price is
# below, within or above their advised range, and that claim is only
# demonstrable if there is a mentor in each case.
#
# The two middle bands exist so the ten do not all sit on top of each other
# inside the range. They are expressed against the range multipliers rather
# than as fixed ratios, so they keep their meaning if a retrained model comes
# with a wider or narrower range.
# ---------------------------------------------------------------------------
BAND_ABOVE = "above the range"
BAND_HIGH = "high in the range"
BAND_MIDDLE = "near the advice"
BAND_LOW = "low in the range"
BAND_BELOW = "below the range"

TARGET_BANDS: tuple[str, ...] = (
    BAND_ABOVE,
    BAND_HIGH,
    BAND_MIDDLE,
    BAND_LOW,
    BAND_BELOW,
)

# The three the comparison exists to show. One mentor in each is a
# requirement rather than a preference: without them the demonstration cannot
# show what the comparison is for.
REQUIRED_POSITIONS: tuple[str, ...] = (
    POSITION_BELOW,
    POSITION_WITHIN,
    POSITION_ABOVE,
)

SINGLE_MENTEE = mapping.MAX_MENTEES_MIN

# ---------------------------------------------------------------------------
# What the mentor did about their price
#
# Each seeded mentor has answered the advice once, so the dashboard, the
# history and the decision counts have something in them on a fresh database.
# Which answer they gave follows from where their own price sits, because that
# is the answer that is consistent with it:
#
# * a mentor charging roughly what the model advises has accepted it, and
#   their price becomes the advised one,
# * a mentor charging clearly more or less than the advised range has
#   rejected the advice and said what they charge instead, which is the most
#   useful thing a mentor can tell the system,
# * the two in between have modified it to their own figure.
#
# A mentor whose own price happens to equal the advice to the currency unit
# has accepted it, whichever band they fall in: a modification has to differ
# from the advice, and the endpoint that records one would refuse it.
# ---------------------------------------------------------------------------
ACTION_FOR_BAND: dict[str, str] = {
    BAND_MIDDLE: "accepted",
    BAND_HIGH: "modified",
    BAND_LOW: "modified",
    BAND_ABOVE: "rejected",
    BAND_BELOW: "rejected",
}


class SeedInputError(RuntimeError):
    """An input this script cannot work without is absent or unusable."""


@dataclass(frozen=True)
class Candidate:
    """
    One record of the modelled population, already in mentor terms.

    Everything a mentor row, a service row and a track-record row need, plus
    the advice the full model gives for it, so the five can be chosen on what
    the system would actually say about them.
    """

    source_key: int
    field: str
    max_mentees: int
    min_commitment: int
    skills: list[str]
    profile_verified: bool
    current_price: int
    history: dict[str, Any]
    advice: PriceRecommendation

    @property
    def position(self) -> str:
        return position_vs_range(
            self.current_price, self.advice.price_low, self.advice.price_high
        )

    @property
    def price_ratio(self) -> float:
        """What the mentor charges, as a multiple of what the model advises."""
        return self.current_price / self.advice.recommended_price


# ---------------------------------------------------------------------------
# Reading the population
# ---------------------------------------------------------------------------
def load_population() -> pd.DataFrame:
    """
    The rows that could become a demonstration mentor, each carrying its key.

    Deterministic because the dataset is a file: the same file filtered the
    same way gives the same rows with the same keys, which is what lets a
    rerun recognise the mentors it already wrote.
    """
    try:
        population = modelled_population(
            price_floor=price_fence_bounds()[0],
            price_ceiling=price_fence_bounds()[1],
            min_reviews=MIN_REVIEWS,
        )
    except PopulationError as error:
        raise SeedInputError(str(error)) from error

    # A track record is stored complete or not at all: a row with a gap in it
    # would be written as a partial record, which is priced by the core model
    # and would defeat the purpose of seeding it.
    population = population.dropna(subset=list(mapping.FULL_COLUMNS))
    if population.empty:
        raise SeedInputError(
            "every row of the population is missing part of a track record, "
            "so there is nothing to seed from"
        )
    return population.reset_index(drop=True)


def price_fence_bounds() -> tuple[float, float]:
    """The price fences the models were trained within, as whole AUD bounds."""
    pricing = pricing_service()
    return pricing.price_floor, pricing.price_ceiling


_pricing: PricingService | None = None


def pricing_service() -> PricingService:
    """
    The loaded models, once.

    Loaded lazily and cached by hand rather than with ``lru_cache``, so that
    the failure message belongs to this script rather than to the API.
    """
    global _pricing
    if _pricing is None:
        try:
            _pricing = load_pricing_service()
        except AssetsUnavailableError as error:
            raise SeedInputError(
                f"the prepared models could not be loaded, and the price a "
                f"mentor is seeded against comes from them\n  {error}"
            ) from error
    return _pricing


# ---------------------------------------------------------------------------
# One row, in mentor terms
# ---------------------------------------------------------------------------
def skills_for(source_key: int, count: int) -> list[str]:
    """
    ``count`` skills, chosen deterministically for this source record.

    Seeded on the record rather than on the run, so a mentor keeps the same
    skills whether they are seeded first or last, and a rerun after a reset
    produces the same profile.
    """
    chosen = random.Random(f"{SEED}-skills-{source_key}").sample(
        list(mapping.SKILLS), count
    )
    # Back into the canonical order, so the stored list reads the way the
    # options endpoint presents it.
    order = list(mapping.SKILLS)
    return sorted(chosen, key=order.index)


def mentor_terms(source_key: int, row: pd.Series) -> dict[str, Any]:
    """
    Describe one row of the population the way the application would.

    Every derivation here is one the application already makes from a mentor's
    own answers, through the mapping layer rather than beside it. That is what
    makes a seeded mentor indistinguishable from a registered one on the
    pricing path: there is no second code path for a demo mentor, and nothing
    in this script decides what a price should be.
    """
    return {
        "source_key": source_key,
        "field": mapping.field_from_column_value(row[mapping.COLUMN_FIELD]),
        "max_mentees": int(row[mapping.COLUMN_MAX_MENTEES]),
        "min_commitment": mapping.nearest_min_commitment(
            row[mapping.COLUMN_MIN_COMMITMENT]
        ),
        "skills": skills_for(
            source_key,
            mapping.skills_count_from_column_value(row[mapping.COLUMN_SKILLS]),
        ),
        # Not read from the row. Verification is the platform's own
        # statement about a mentor, and these mentors are the platform's own
        # invention: nine of the ten are verified, so every candidate is
        # scored as one, and the tenth is priced again with the answer turned
        # off when it is written. See advice_for.
        "profile_verified": True,
        "current_price": int(round(float(row[TARGET_COLUMN]))),
        "history": mapping.model_inputs_to_history(
            {column: row[column] for column in mapping.FULL_COLUMNS}
        ),
    }


def model_row(
    terms: dict[str, Any], *, profile_verified: bool | None = None
) -> dict[str, Any]:
    """
    The full-model row for a described mentor, exactly as the API builds it.

    One published service, so the service count is one. Anything else here
    would choose the ten on a price the endpoints then disagree with.

    ``profile_verified`` overrides the described answer, for the one seeded
    mentor who is not verified: their price has to be the price of a mentor
    who has not been checked, because that is what their service will say.
    """
    service_inputs = mapping.to_model_inputs(
        field=terms["field"],
        max_mentees=terms["max_mentees"],
        min_commitment=terms["min_commitment"],
        skills=terms["skills"],
        profile_verified=(
            terms["profile_verified"] if profile_verified is None else profile_verified
        ),
        services_count=1,
    )
    return {**service_inputs, **mapping.history_to_model_inputs(terms["history"])}


def model_row_for(candidate: Candidate, *, verified: bool) -> dict[str, Any]:
    """
    The full-model row behind one seeded mentor's stored price.

    Stored on the recommendation as its input snapshot, which is what the API
    does with the row it builds, so a seeded price can be explained months
    later from the row alone.
    """
    return model_row(
        {
            "field": candidate.field,
            "max_mentees": candidate.max_mentees,
            "min_commitment": candidate.min_commitment,
            "skills": candidate.skills,
            "profile_verified": candidate.profile_verified,
            "history": candidate.history,
        },
        profile_verified=verified,
    )


def advice_for(candidate: Candidate, *, verified: bool) -> PriceRecommendation:
    """
    What the full model says about one candidate, verified or not.

    Through the same prediction service and the same mapping layer as the API,
    so a seeded mentor's stored price is the price the endpoints go on to give
    for the same service.
    """
    return pricing_service().predict_many(
        [model_row_for(candidate, verified=verified)], FULL
    )[0]


def build_candidates(population: pd.DataFrame) -> list[Candidate]:
    """
    Every row of the population as a candidate, with the advice it would get.

    Scored in one call rather than one per row. There are thousands of
    candidates and the ten are chosen on what the model says about them, so
    the alternative is thousands of single-row model calls to arrive at the
    same numbers.
    """
    described = [
        mentor_terms(int(row[KEY_COLUMN]), row) for _, row in population.iterrows()
    ]
    advice = pricing_service().predict_many(
        [model_row(terms) for terms in described], FULL
    )
    return [
        Candidate(**terms, advice=one)
        for terms, one in zip(described, advice, strict=True)
    ]


# ---------------------------------------------------------------------------
# Choosing the ten
# ---------------------------------------------------------------------------
def band_for(current_price: int, advice: PriceRecommendation) -> str:
    """
    Which of the five price levels a price sits at, against one piece of advice.

    Takes the price and the advice rather than a candidate, because the one
    seeded mentor who is not verified is priced again after the ten are chosen
    and their band has to be read off the advice they actually keep.
    """
    position = position_vs_range(current_price, advice.price_low, advice.price_high)
    if position == POSITION_ABOVE:
        return BAND_ABOVE
    if position == POSITION_BELOW:
        return BAND_BELOW
    ratio = current_price / advice.recommended_price
    if ratio > 1.15:
        return BAND_HIGH
    if ratio < 0.87:
        return BAND_LOW
    return BAND_MIDDLE


def band_of(candidate: Candidate) -> str:
    """Which of the five price levels a candidate sits at."""
    return band_for(candidate.current_price, candidate.advice)


class Selection:
    """
    The ten being assembled, and what has already been spent on them.

    A small object rather than four sets passed between functions, because
    every rule about the ten is a rule about the whole set: a field is only
    worth taking once, a group size is only interesting once, and a price
    position only has to be covered once.
    """

    def __init__(self) -> None:
        self.chosen: list[Candidate] = []
        self.keys: set[int] = set()
        self.fields: set[str] = set()
        self.sizes: set[int] = set()

    def take(self, candidate: Candidate) -> Candidate:
        self.chosen.append(candidate)
        self.keys.add(candidate.source_key)
        self.fields.add(candidate.field)
        self.sizes.add(candidate.max_mentees)
        return candidate

    def positions(self) -> set[str]:
        return {candidate.position for candidate in self.chosen}

    def singles(self) -> int:
        return sum(
            1 for candidate in self.chosen if candidate.max_mentees == SINGLE_MENTEE
        )

    def groups(self) -> int:
        return len(self.chosen) - self.singles()


def fits(
    candidate: Candidate,
    selection: Selection,
    *,
    single_mentee: bool,
    position: str | None,
    new_field: bool,
    new_size: bool,
) -> bool:
    """Whether one candidate is still wanted, under the rules asked for."""
    if candidate.source_key in selection.keys:
        return False
    if single_mentee != (candidate.max_mentees == SINGLE_MENTEE):
        return False
    if position is not None and candidate.position != position:
        return False
    if new_field and candidate.field in selection.fields:
        return False
    if new_size and candidate.max_mentees in selection.sizes:
        return False
    return True


def first_fit(
    pool: list[Candidate],
    selection: Selection,
    *,
    single_mentee: bool,
    position: str | None = None,
) -> Candidate | None:
    """
    The first candidate in ``pool`` that is still wanted, relaxing in order.

    Three passes, each giving up one preference. A different field and a
    different group size are what make the ten worth looking at, but neither
    is worth failing over: only part of the population offers a session for
    one mentee, those rows do not cover every field, and there are seven group
    sizes for six group mentors. So the search asks for both, then for a new
    field alone, then for anything that fits the quota it is filling. The
    requirements that are not relaxed are the quotas themselves and the three
    price positions.
    """
    for new_field, new_size in ((True, True), (True, False), (False, False)):
        for candidate in pool:
            if fits(
                candidate,
                selection,
                single_mentee=single_mentee,
                position=position,
                new_field=new_field,
                new_size=new_size,
            ):
                return candidate
    return None


def choose(candidates: list[Candidate]) -> tuple[list[Candidate], list[str]]:
    """
    Ten candidates: four one-to-one, six groups, three price positions covered.

    Deterministic: the candidates are visited in one seeded order and the first
    that fits is taken. Seeded rather than taken in dataset order because
    dataset order correlates with the market segment, and the first matching
    rows would all come from the same few fields.

    The three price positions are filled first, from the group mentors, and
    only then are the quotas filled out. Filling the quotas first would spend
    the fields and the sizes on ordinary mentors and leave the one case the
    comparison exists to show with nothing to take.

    Returns the chosen and a list of what could not be satisfied, so the
    caller can say so rather than quietly seeding eight.
    """
    order = list(range(len(candidates)))
    random.Random(SEED).shuffle(order)
    pool = [candidates[index] for index in order]

    selection = Selection()
    unmet: list[str] = []

    # One group mentor per price position, in a fixed order.
    for position in REQUIRED_POSITIONS:
        pick = first_fit(pool, selection, single_mentee=False, position=position)
        if pick is None:
            unmet.append(f"a group mentor charging {position} their advised range")
            continue
        selection.take(pick)

    # The rest of the six group mentors, then the four one-to-one mentors.
    for single_mentee, wanted in ((False, GROUP_MENTORS), (True, ONE_TO_ONE_MENTORS)):
        filling = selection.groups if not single_mentee else selection.singles
        while filling() < wanted:
            pick = first_fit(pool, selection, single_mentee=single_mentee)
            if pick is None:
                shape = "one-to-one" if single_mentee else "group"
                unmet.append(
                    f"{wanted - filling()} more {shape} mentor(s): the "
                    f"population has no further record that fits"
                )
                break
            selection.take(pick)

    if len(selection.fields) < MIN_FIELDS:
        unmet.append(
            f"mentors in at least {MIN_FIELDS} different fields: these ten "
            f"cover {len(selection.fields)}"
        )
    missing = [
        position
        for position in REQUIRED_POSITIONS
        if position not in selection.positions()
    ]
    for position in missing:
        unmet.append(f"any mentor charging {position} their advised range")

    return selection.chosen, unmet


def names_for(count: int) -> list[str]:
    """
    ``count`` fictional display names, as a first name and an initial.

    Fictional on purpose, and only ever a first name and a letter: the demo is
    public, and a full name invented at random is a full name that belongs to
    somebody.
    """
    rng = random.Random(f"{SEED}-names")
    first = rng.sample(FIRST_NAMES, count)
    initials = rng.sample(SURNAME_INITIALS, count)
    return [f"{name} {initial}." for name, initial in zip(first, initials, strict=True)]


def email_for(display_name: str, source_key: int) -> str:
    """
    A reserved-for-documentation address, unique per seeded mentor.

    ``example.com`` exists for exactly this: it can never belong to anyone, so
    nothing here can be mistaken for a real address or receive mail.
    """
    local = display_name.lower().replace(" ", "").replace(".", "")
    return f"{local}{source_key}@example.com"


# ---------------------------------------------------------------------------
# What will be written for each of the ten
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Plan:
    """
    One seeded mentor, decided in full before anything is written.

    Everything that is not simply read off the source record: the fictional
    name, whether the platform has checked them, the advice they are given
    once that is settled, and what they did about it. Held as a value so the
    summary printed at the end describes the rows that were actually written
    rather than recomputing anything.
    """

    candidate: Candidate
    display_name: str
    verified: bool
    advice: PriceRecommendation
    action: str
    final_price: int

    @property
    def email(self) -> str:
        return email_for(self.display_name, self.candidate.source_key)

    @property
    def position(self) -> str:
        """Where what they charge sits against the range they were advised."""
        return position_vs_range(
            self.final_price, self.advice.price_low, self.advice.price_high
        )


def plan_for(chosen: list[Candidate]) -> list[Plan]:
    """
    Decide the whole of each of the ten, in one deterministic pass.

    Two things are settled here rather than during the selection, and both
    depend on the set being complete:

    **Which of them is not verified.** The last of the ten, so the nine that
    carry the three price positions and the field spread are untouched by it.
    Their price is then worked out again with the answer turned off, because
    the price a mentor is shown has to be the price of the service they
    actually have.

    **What each of them did about their advice.** It follows from where their
    own price sits: see ACTION_FOR_BAND. A mentor whose price happens to equal
    the advice has accepted it whatever band they fall in, because a
    modification has to differ from the advice and the endpoint that records
    one would refuse it.
    """
    names = names_for(len(chosen))
    verified_flags = [
        index < len(chosen) - UNVERIFIED_MENTORS for index in range(len(chosen))
    ]

    plans: list[Plan] = []
    for candidate, display_name, verified in zip(
        chosen, names, verified_flags, strict=True
    ):
        advice = candidate.advice if verified else advice_for(candidate, verified=False)
        advised = advice.recommended_price
        current = candidate.current_price
        action = (
            "accepted"
            if current == advised
            else ACTION_FOR_BAND[band_for(current, advice)]
        )
        plans.append(
            Plan(
                candidate=candidate,
                display_name=display_name,
                verified=verified,
                advice=advice,
                action=action,
                final_price=advised if action == "accepted" else current,
            )
        )
    return plans


# ---------------------------------------------------------------------------
# Writing them
# ---------------------------------------------------------------------------
def existing_source_keys(session: Session) -> set[int]:
    """The source records already seeded into this database."""
    return {
        key
        for key in session.scalars(
            select(Mentor.source_key).where(Mentor.is_demo.is_(True))
        )
        if key is not None
    }


def years_of_experience(candidate: Candidate) -> int:
    """
    How long the mentor says they have been mentoring, in whole years.

    Taken from the tenure in their own record and rounded, so the number on
    their profile and the band shown beside it agree with each other and with
    the record the full model reads. At least one year: a mentor with a
    complete track record has been doing this for a while, and a profile
    reading "under 1 year" beside forty reviews would contradict itself.
    """
    tenure = float(candidate.history[mapping.HISTORY_TENURE_FIELD])
    return min(max(int(round(tenure)), 1), mapping.YEARS_EXPERIENCE_MAX)


def seed_one(session: Session, plan: Plan, password_hash: str) -> Mentor:
    """
    Create one demonstration mentor, with everything the flow produces.

    A profile, a service, a track record, the advisory price the full model
    gives that service, and the mentor's answer to it. The last two are
    written here rather than left for someone to click, so that a fresh
    database has a dashboard, a history and a decision count with something in
    them.

    The price is not decided here: it comes from the prediction service,
    through the same mapping layer the API uses, and the row it was worked out
    from is stored beside it.
    """
    candidate = plan.candidate
    profile = FIELD_PROFILES[candidate.field]
    years = years_of_experience(candidate)
    mentor = Mentor(
        full_name=plan.display_name,
        email=plan.email,
        password_hash=password_hash,
        verified=plan.verified,
        headline=profile.headline,
        bio=profile.bio,
        education_level=profile.education_level,
        experience_summary=profile.bio,
        credentials=None,
        years_experience=years,
        years_mentoring_band=mapping.years_mentoring_band_for_experience(years),
        is_demo=True,
        source_key=candidate.source_key,
    )
    service = Service(
        session_label=mapping.session_label(candidate.max_mentees),
        field=candidate.field,
        max_mentees=candidate.max_mentees,
        min_commitment=candidate.min_commitment,
        skills=list(candidate.skills),
        # The same answer as the account, because they are the same claim and
        # this is the one the model reads.
        profile_verified=plan.verified,
        current_price=plan.final_price,
    )
    mentor.services.append(service)
    mentor.history = MentorHistory(**candidate.history)
    session.add(mentor)
    session.flush()

    advice = plan.advice
    recommendation = PricingRecommendation(
        service_id=service.id,
        model_used=advice.model_used,
        recommended_price=advice.recommended_price,
        price_low=advice.price_low,
        price_high=advice.price_high,
        low_confidence=advice.low_confidence,
        inputs_snapshot=model_row_for(candidate, verified=plan.verified),
        model_version=advice.model_version,
        status=plan.action,
    )
    session.add(recommendation)
    session.flush()
    session.add(
        PricingDecision(
            recommendation_id=recommendation.id,
            action=plan.action,
            final_price=plan.final_price,
        )
    )
    return mentor


def reset(session: Session) -> int:
    """
    Remove every demonstration mentor, and everything hanging off them.

    Deleted through the ORM rather than with a DELETE statement, so the
    relationship cascades take their services, track records,
    recommendations and decisions with them on SQLite as well as on
    PostgreSQL.
    """
    mentors = session.scalars(select(Mentor).where(Mentor.is_demo.is_(True))).all()
    for mentor in mentors:
        session.delete(mentor)
    session.commit()
    return len(mentors)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def summary_table(plans: list[Plan]) -> str:
    """The ten mentors as a table, in the words the application uses."""
    header = (
        f"{'Mentor':14s} {'Field':30s} {'Group':>5s} {'Charges':>8s} "
        f"{'Advice':>8s} {'Range':>17s} {'Answer':>9s} {'Checked':>7s}  Position"
    )
    lines = [header, "-" * len(header)]
    for plan in plans:
        advice = plan.advice
        band = f"{advice.price_low:,} to {advice.price_high:,}"
        lines.append(
            f"{plan.display_name:14s} "
            f"{mapping.field_label(plan.candidate.field):30s} "
            f"{plan.candidate.max_mentees:5d} {plan.final_price:8,d} "
            f"{advice.recommended_price:8,d} {band:>17s} "
            f"{plan.action:>9s} {'yes' if plan.verified else 'no':>7s}  "
            f"{plan.position}"
        )
    lines.append("")
    lines.append(f"Prices in {mapping.CURRENCY}, per session.")
    return "\n".join(lines)


def demo_password() -> str:
    """
    What the demonstration accounts sign in with.

    From the environment, so a shared demonstration can use something else,
    with a documented default. It is printed at the end of a run on purpose:
    these are fictional accounts on a domain reserved for documentation, and
    they exist to be signed in to.
    """
    return os.environ.get(DEMO_PASSWORD_VARIABLE) or DEFAULT_DEMO_PASSWORD


def sign_in_details(plans: list[Plan], password: str) -> str:
    """The addresses and the password, for whoever is running the demo."""
    lines = ["Sign in as any of them with the password below.", ""]
    for plan in plans:
        lines.append(f"  {plan.email}")
    lines.append("")
    lines.append(f"  password: {password}")
    lines.append("")
    lines.append(
        f"These are fictional accounts on example.com, which can never belong "
        f"to anyone. Set {DEMO_PASSWORD_VARIABLE} to use a different password."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Seed ten established mentors, each with a track record, a price "
            "and a decision, so the whole platform can be demonstrated on a "
            "fresh database."
        )
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "remove the demonstration mentors and everything belonging to "
            "them, and seed nothing"
        ),
    )
    parser.add_argument(
        "--no-activity",
        action="store_true",
        help=(
            "do not build the month-by-month activity, which reads the raw "
            "files and is the slow part"
        ),
    )
    arguments = parser.parse_args(argv)

    password = demo_password()
    engine = create_db_engine()
    activity: str | None = None
    try:
        with Session(engine, expire_on_commit=False) as session:
            if arguments.reset:
                removed = reset(session)
                print(f"Removed {removed} demonstration mentor(s).")
                return 0

            chosen, unmet = choose(build_candidates(load_population()))
            plans = plan_for(chosen)
            already = existing_source_keys(session)

            created = 0
            for plan in plans:
                if plan.candidate.source_key in already:
                    continue
                # One hash per mentor rather than one shared between them.
                # They all sign in with the same password, but a salt reused
                # across rows is a habit worth not having in a codebase.
                seed_one(session, plan, security.hash_password(password))
                created += 1
            session.commit()

            if not arguments.no_activity:
                try:
                    activity = describe_activity(build_activity(session))
                except ActivityInputError as error:
                    activity = (
                        f"The month-by-month activity was not built, so the "
                        f"chart on a mentor's page has nothing in it yet:\n"
                        f"  {error}\n"
                        f"  Build it with python scripts/build_demo_activity.py."
                    )
    except SeedInputError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    print(
        f"{created} demonstration mentor(s) created, "
        f"{len(plans) - created} already present."
    )
    print()
    print(summary_table(plans))
    print()
    print(sign_in_details(plans, password))
    if activity:
        print()
        print(activity)
    if unmet:
        print()
        print(
            "The population could not supply: "
            + "; ".join(unmet)
            + ". The demonstration is short of what it was meant to show, so "
            "say so rather than reading the table above as the whole picture."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
