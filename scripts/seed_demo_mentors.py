"""
Seed five established mentors, so the existing-mentor path can be demonstrated.

A mentor who has just registered is priced from eight answers and nothing
else. A mentor with a track record is priced from those eight plus
twenty-eight figures the platform has accumulated about them, and is shown
their advice next to what they charge today. The second path is the more
interesting half of the system and, on a fresh database, there is nobody on
it: the platform has no activity yet, so no mentor has a record.

This script supplies five. They are fictional people, and so is every word
about them. What is real is the *shape* of the record: the thirty-odd figures
are taken from one row of the modelled population, so the track records are
internally consistent in the way a real one would be, which a hand-written
record would not be. Rating, review counts, booked shares and tenure all
describe the same provider.

The five are chosen to be worth looking at rather than at random:

* five different fields, so the field list is visibly in use,
* five different group sizes, so the per-mentee figures differ, exactly one of
  them a single mentee. Without that one, every seeded mentor runs a group
  session and the one-to-one label never appears in the demonstration,
* five different price levels relative to what the model advises, including
  one mentor charging clearly above their recommended range, one inside it
  and one below it. Those three are what make the comparison on the
  recommendation response demonstrable at all.

Nothing identifying is copied or stored. The names come from a fictional pool,
the addresses are all ``example.com``, and the only link back to the source
row is ``source_key``, an index into the filtered population: it exists so
that running this script twice recognises the mentors it already wrote, and it
is useless without the dataset.

Run from the project root, against the database ``DATABASE_URL`` points at:

    python scripts/seed_demo_mentors.py            # create the five
    python scripts/seed_demo_mentors.py --reset    # remove them again

Both the dataset and the prepared models are git-ignored build inputs, so a
fresh clone cannot run this until both exist. A missing one fails with a
message naming it.
"""

from __future__ import annotations

import argparse
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

from src.data.population import (  # noqa: E402
    KEY_COLUMN,
    TARGET_COLUMN,
    PopulationError,
    modelled_population,
)
from src.db import Mentor, MentorHistory, Service, create_db_engine  # noqa: E402
from src.mentor import mapping  # noqa: E402
from src.mentor.prediction import (  # noqa: E402
    FULL,
    POSITION_ABOVE,
    POSITION_BELOW,
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

DEMO_MENTORS = 5

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
# What the five are chosen to show
#
# Five price levels, read as the ratio of what the mentor charges today to
# what the model advises. The first three are the whole point of the exercise:
# the recommendation response reports whether a mentor's current price is
# below, within or above their advised range, and that claim is only
# demonstrable if there is a mentor in each case.
#
# The two middle bands exist so the five do not all sit on top of each other
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

# ---------------------------------------------------------------------------
# The one-to-one mentor
#
# One of the five takes a single mentee and the other four take two or more.
# A session for one is not a smaller group: it is the other thing the platform
# offers, it carries its own label, and its per-mentee figure is its session
# price rather than a division of it. Five group sessions would leave both of
# those unrepresented.
#
# Which price level it occupies is a preference rather than a rule, because
# only a small part of the population offers a session for one. The three
# levels inside the range come first, since a mentor charging roughly what the
# system advises is the ordinary case and the least informative one to spend
# on a constraint; the two outside it are the fallback, and are given up last
# because they are the cases the comparison exists to show.
# ---------------------------------------------------------------------------
SINGLE_MENTEE = mapping.MAX_MENTEES_MIN

ONE_TO_ONE_BAND_PREFERENCE: tuple[str, ...] = (
    BAND_MIDDLE,
    BAND_HIGH,
    BAND_LOW,
    BAND_ABOVE,
    BAND_BELOW,
)


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
    services_planned: int
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
        "profile_verified": bool(row[mapping.COLUMN_VERIFIED]),
        "services_planned": min(
            max(int(row[mapping.COLUMN_SERVICES]), 1), mapping.SERVICES_CAP
        ),
        "current_price": int(round(float(row[TARGET_COLUMN]))),
        "history": mapping.model_inputs_to_history(
            {column: row[column] for column in mapping.FULL_COLUMNS}
        ),
    }


def model_row(terms: dict[str, Any]) -> dict[str, Any]:
    """
    The full-model row for a described mentor, exactly as the API builds it.

    One published service, so the service count is one. Anything else here
    would choose the five on a price the endpoints then disagree with.
    """
    service_inputs = mapping.to_model_inputs(
        field=terms["field"],
        max_mentees=terms["max_mentees"],
        min_commitment=terms["min_commitment"],
        skills=terms["skills"],
        profile_verified=terms["profile_verified"],
        services_planned=terms["services_planned"],
        services_count=1,
    )
    return {**service_inputs, **mapping.history_to_model_inputs(terms["history"])}


def build_candidates(population: pd.DataFrame) -> list[Candidate]:
    """
    Every row of the population as a candidate, with the advice it would get.

    Scored in one call rather than one per row. There are thousands of
    candidates and the five are chosen on what the model says about them, so
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
# Choosing the five
# ---------------------------------------------------------------------------
def band_of(candidate: Candidate) -> str:
    """Which of the five price levels a candidate sits at."""
    position = candidate.position
    if position == POSITION_ABOVE:
        return BAND_ABOVE
    if position == POSITION_BELOW:
        return BAND_BELOW
    ratio = candidate.price_ratio
    if ratio > 1.15:
        return BAND_HIGH
    if ratio < 0.87:
        return BAND_LOW
    return BAND_MIDDLE


def first_fit(
    pool: list[Candidate],
    used_fields: set[str],
    used_sizes: set[int],
    *,
    single_mentee: bool,
) -> Candidate | None:
    """
    The first candidate in ``pool`` that none of the five already covers.

    ``single_mentee`` picks which side of the group-size split to draw from:
    the one-to-one mentor, or one of the four who take a group.
    """
    return next(
        (
            candidate
            for candidate in pool
            if candidate.field not in used_fields
            and candidate.max_mentees not in used_sizes
            and (
                candidate.max_mentees == SINGLE_MENTEE
                if single_mentee
                else candidate.max_mentees >= mapping.GROUP_FROM_MENTEES
            )
        ),
        None,
    )


def choose(candidates: list[Candidate]) -> tuple[list[Candidate], list[str]]:
    """
    Five candidates, one per price level, all in different fields and sizes.

    Deterministic: the candidates are visited in one seeded order and the
    first that fits each band is taken. Seeded rather than taken in dataset
    order because dataset order correlates with the market segment, and the
    first matching rows would all come from the same few fields.

    The one-to-one mentor is chosen before the loop rather than inside it, and
    their field and group size are reserved. Choosing them in band order would
    not work: whichever band they land in, the bands picked before it would
    have already spent the field they need, with no way to know it was wanted.

    Returns the five and the bands that could not be filled, so the caller can
    say so rather than quietly seeding four.
    """
    order = list(range(len(candidates)))
    random.Random(SEED).shuffle(order)
    by_band: dict[str, list[Candidate]] = {band: [] for band in TARGET_BANDS}
    for index in order:
        candidate = candidates[index]
        by_band[band_of(candidate)].append(candidate)

    used_fields: set[str] = set()
    used_sizes: set[int] = set()
    reserved: dict[str, Candidate] = {}
    for band in ONE_TO_ONE_BAND_PREFERENCE:
        pick = first_fit(by_band[band], used_fields, used_sizes, single_mentee=True)
        if pick is not None:
            reserved[band] = pick
            used_fields.add(pick.field)
            used_sizes.add(pick.max_mentees)
            break

    chosen: list[Candidate] = []
    unfilled: list[str] = []
    for band in TARGET_BANDS:
        pick = reserved.get(band) or first_fit(
            by_band[band], used_fields, used_sizes, single_mentee=False
        )
        if pick is None:
            unfilled.append(band)
            continue
        chosen.append(pick)
        used_fields.add(pick.field)
        used_sizes.add(pick.max_mentees)
    return chosen, unfilled


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


def seed_one(session: Session, candidate: Candidate, display_name: str) -> Mentor:
    """Create one demonstration mentor, with a service and a track record."""
    profile = FIELD_PROFILES[candidate.field]
    mentor = Mentor(
        full_name=display_name,
        email=email_for(display_name, candidate.source_key),
        headline=profile.headline,
        bio=profile.bio,
        education_level=profile.education_level,
        experience_summary=profile.bio,
        credentials=None,
        years_mentoring_band=mapping.years_mentoring_band_for_tenure(
            candidate.history[mapping.HISTORY_TENURE_FIELD]
        ),
        services_planned=candidate.services_planned,
        is_demo=True,
        source_key=candidate.source_key,
    )
    mentor.services.append(
        Service(
            session_label=mapping.session_label(candidate.max_mentees),
            field=candidate.field,
            max_mentees=candidate.max_mentees,
            min_commitment=candidate.min_commitment,
            skills=list(candidate.skills),
            profile_verified=candidate.profile_verified,
            current_price=candidate.current_price,
        )
    )
    mentor.history = MentorHistory(**candidate.history)
    session.add(mentor)
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
def summary_table(rows: list[tuple[str, Candidate]]) -> str:
    """The five mentors as a table, in the words the application uses."""
    header = (
        f"{'Mentor':14s} {'Field':30s} {'Group':>5s} {'Now':>8s} "
        f"{'Advice':>8s} {'Range':>17s} {'Model':>6s}  Position"
    )
    lines = [header, "-" * len(header)]
    for display_name, candidate in rows:
        advice = candidate.advice
        band = f"{advice.price_low:,} to {advice.price_high:,}"
        lines.append(
            f"{display_name:14s} {mapping.field_label(candidate.field):30s} "
            f"{candidate.max_mentees:5d} {candidate.current_price:8,d} "
            f"{advice.recommended_price:8,d} {band:>17s} "
            f"{advice.model_used:>6s}  {candidate.position}"
        )
    lines.append("")
    lines.append(f"Prices in {mapping.CURRENCY}, per session.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Seed five established mentors, each with a track record, so the "
            "existing-mentor pricing path can be demonstrated."
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
    arguments = parser.parse_args(argv)

    engine = create_db_engine()
    try:
        with Session(engine, expire_on_commit=False) as session:
            if arguments.reset:
                removed = reset(session)
                print(f"Removed {removed} demonstration mentor(s).")
                return 0

            candidates = build_candidates(load_population())
            chosen, unfilled = choose(candidates)
            already = existing_source_keys(session)

            rows: list[tuple[str, Candidate]] = []
            created = 0
            for display_name, candidate in zip(
                names_for(len(chosen)), chosen, strict=True
            ):
                if candidate.source_key in already:
                    mentor = session.scalar(
                        select(Mentor).where(Mentor.source_key == candidate.source_key)
                    )
                    rows.append((mentor.full_name, candidate))
                    continue
                seed_one(session, candidate, display_name)
                rows.append((display_name, candidate))
                created += 1
            session.commit()
    except SeedInputError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    print(
        f"{created} demonstration mentor(s) created, "
        f"{len(rows) - created} already present."
    )
    print()
    print(summary_table(rows))

    if unfilled:
        print()
        print(
            "Could not find a candidate for: "
            + ", ".join(unfilled)
            + ". The population has no record at that price level with a field "
            "and group size the other mentors are not already using."
        )
    if rows and all(candidate.max_mentees > SINGLE_MENTEE for _, candidate in rows):
        print()
        print(
            "No record in the population offers a session for a single mentee "
            "in a field the other mentors are not using, so all five are "
            "group sessions and the one-to-one label is not demonstrated."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
