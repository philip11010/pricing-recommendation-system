"""
Request and response shapes for the mentor-facing API.

Validation is strict: unknown fields are refused rather than ignored, so a
frontend that misspells a key is told about it instead of silently sending
nothing. Every rule about what an answer may be lives in
:mod:`src.mentor.mapping`, and the validators here call into it, so the form
the frontend renders, the answers the API accepts and the values the model is
given can never describe three different things.

Error messages are written for the mentor. A message like "value is not a
valid enumeration member" is of no use to someone filling in a form, so each
validator raises the sentence the mentor should read.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.db.mentor_models import DECISION_ACTIONS
from src.mentor import comparables, mapping

# Deliberately permissive: enough to catch a missing "@" or a typed sentence,
# without rejecting the legitimate addresses that a stricter pattern tends to.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

NAME_MIN = 2
NAME_MAX = 200
EMAIL_MAX = 320
HEADLINE_MAX = 300
TEXT_MAX = 4000


class StrictModel(BaseModel):
    """Base for every request body: no unknown fields, no stray whitespace."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ServiceInput(StrictModel):
    """
    One service a mentor offers, as the mentor describes it.

    There is no session format question. How many mentees can join is the
    only thing asked about the shape of a session, and what the session is
    called follows from it: see ``session_label_rule`` on /meta/options.
    """

    field: str = Field(
        description="The field the mentor works in, from /meta/options.",
        examples=["technology_software"],
    )
    max_mentees: int = Field(
        description=(
            f"How many mentees can join one session, "
            f"{mapping.MAX_MENTEES_MIN} to {mapping.MAX_MENTEES_MAX}."
        ),
        examples=[1],
    )
    min_commitment: int = Field(
        description="Smallest number of sessions a mentee can book.",
        examples=[1],
    )
    skills: list[str] = Field(
        default_factory=list,
        description="Skill ids the mentor offers, from /meta/options.",
        examples=[["cv_review", "interview_preparation"]],
    )
    profile_verified: bool = Field(
        default=False,
        description="Whether the mentor has completed identity verification.",
    )

    @field_validator("field")
    @classmethod
    def _check_field(cls, value: str) -> str:
        return mapping.validate_field(value)

    # Every numeric validator below runs in "before" mode, so the mapping
    # rule sees what the frontend actually sent. Pydantic's default is to
    # coerce first, which quietly turns true into 1 and "4" into 4, and both
    # of those defeat a guard that exists for a reason: in Python True is an
    # int equal to 1, so a checkbox posted into a number box would be stored
    # as a group of one, or as a one dollar session.
    @field_validator("max_mentees", mode="before")
    @classmethod
    def _check_max_mentees(cls, value: object) -> int:
        return mapping.validate_max_mentees(value)

    @field_validator("min_commitment", mode="before")
    @classmethod
    def _check_min_commitment(cls, value: object) -> int:
        return mapping.validate_min_commitment(value)

    @field_validator("skills")
    @classmethod
    def _check_skills(cls, value: list[str]) -> list[str]:
        return mapping.validate_skills(value)


class MentorRegistration(StrictModel):
    """Everything asked at registration, including the mentor's first service."""

    full_name: str = Field(
        min_length=NAME_MIN, max_length=NAME_MAX, examples=["A. Mentor"]
    )
    email: str = Field(max_length=EMAIL_MAX, examples=["mentor@example.com"])
    years_mentoring_band: str = Field(
        description=(
            "How long the mentor has been mentoring, from /meta/options. "
            "Shown on the mentor's profile; it does not affect the price."
        ),
        examples=["3_to_5"],
    )
    services_planned: int = Field(
        description=(
            f"How many services the mentor plans to offer. "
            f"{mapping.SERVICES_CAP} means {mapping.SERVICES_CAP} or more."
        ),
        examples=[1],
    )
    service: ServiceInput = Field(description="The mentor's first service.")

    headline: str | None = Field(
        default=None,
        max_length=HEADLINE_MAX,
        examples=["Helping graduate engineers find their first role"],
    )
    bio: str | None = Field(default=None, max_length=TEXT_MAX)
    # Profile only. Collected for the mentor's public page; the model has no
    # equivalent input, so none of the three reaches it.
    education_level: str | None = Field(
        default=None, description="Highest level of education, from /meta/options."
    )
    experience_summary: str | None = Field(default=None, max_length=TEXT_MAX)
    credentials: str | None = Field(default=None, max_length=TEXT_MAX)

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        if not EMAIL_PATTERN.match(value):
            raise ValueError("Enter an email address the mentor can be reached at.")
        return value.lower()

    @field_validator("years_mentoring_band")
    @classmethod
    def _check_band(cls, value: str) -> str:
        return mapping.validate_years_mentoring(value)

    @field_validator("services_planned", mode="before")
    @classmethod
    def _check_services_planned(cls, value: object) -> int:
        return mapping.validate_services_planned(value)

    @field_validator("education_level")
    @classmethod
    def _check_education(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return mapping.validate_education_level(value)


class ServiceOut(BaseModel):
    """One of a mentor's services."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    mentor_id: int
    session_label: str = Field(
        description=(
            'Derived from max_mentees: "one_to_one" for a single mentee, '
            '"group" for two or more.'
        ),
        examples=["one_to_one"],
    )
    field: str
    max_mentees: int
    min_commitment: int
    skills: list[str]
    profile_verified: bool
    current_price: int | None = Field(
        default=None,
        description=(
            "What the mentor charges for this service today, in whole "
            "currency units, or null if they have not set a price."
        ),
    )
    created_at: datetime


class HistorySummaryOut(BaseModel):
    """
    A mentor's track record, in the figures worth putting on their own page.

    A summary rather than the whole row. The table holds twenty-nine
    quantities and most of them exist because a model takes them, not because
    a mentor would want to read them: nobody needs their weekend booked share
    minus their weekday one on their profile.

    ``complete`` is the one that decides which model prices them, so it is
    reported rather than left to be inferred from the rest.
    """

    model_config = ConfigDict(from_attributes=True)

    complete: bool = Field(
        description=(
            "True when every figure the more accurate model needs has a "
            "value. A partial record is priced like no record at all."
        )
    )
    top_rated_mentor: bool | None
    reviews_total: int | None
    reviews_last_12_months: int | None
    reviews_per_month: float | None
    rating_overall: float | None = Field(
        default=None, description="Overall mentee rating, out of 5."
    )
    booked_share_90d: float | None = Field(
        default=None,
        description="Share of the mentor's offered time booked over 90 days.",
    )
    booked_share_365d: float | None = Field(
        default=None,
        description="Share of the mentor's offered time booked over a year.",
    )
    open_slots_next_year: int | None
    days_since_last_review: int | None
    years_since_first_review: float | None
    tenure_years: float | None = Field(
        default=None, description="How long the mentor has been on the platform."
    )
    updated_at: datetime


class MentorOut(BaseModel):
    """
    A mentor's own record. The password hash is never serialised.

    ``services`` and ``history`` are what distinguish an established mentor
    from one who has just registered: the first carries what each service
    currently charges, and the second is null until the platform has a record
    to report.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    headline: str | None
    bio: str | None
    education_level: str | None
    experience_summary: str | None
    credentials: str | None
    years_mentoring_band: str
    services_planned: int
    is_demo: bool = Field(
        default=False,
        description=(
            "True for a mentor created by the demonstration seed script "
            "rather than by someone registering."
        ),
    )
    services: list[ServiceOut] = Field(default_factory=list)
    history: HistorySummaryOut | None = Field(
        default=None,
        description="The mentor's track record, or null if they have none yet.",
    )
    created_at: datetime


class DemoMentorOut(BaseModel):
    """
    One demonstration mentor, as the list of them is shown.

    Deliberately thin. The list exists so that someone opening the demo can
    pick a mentor to look at, and it is served without an identity header, so
    it carries nothing that is not already on a mentor's public profile.
    """

    id: int
    display_name: str
    headline: str | None
    field_label: str = Field(examples=["Technology and software"])
    session_label: str = Field(examples=["One to one"])
    has_history: bool = Field(
        description=(
            "True when the mentor has a complete track record and is "
            "therefore priced by the more accurate model."
        )
    )


class RecommendationOut(BaseModel):
    """One advisory price, as the mentor is shown it."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    service_id: int
    recommended_price: int = Field(
        description="The advised price for one session, in whole currency units."
    )
    price_low: int = Field(description="Low end of the range around the advice.")
    price_high: int = Field(description="High end of the range around the advice.")
    price_per_mentee: int = Field(
        description=(
            "The advised session price divided by the number of mentees who "
            "can join, rounded to whole currency units. Equal to "
            "recommended_price for a session of one."
        )
    )
    price_per_mentee_low: int = Field(description="Low end of the range, per mentee.")
    price_per_mentee_high: int = Field(description="High end of the range, per mentee.")
    currency: str = Field(default=mapping.CURRENCY, examples=[mapping.CURRENCY])
    model_used: str = Field(description='Either "core" or "full".')
    low_confidence: bool = Field(
        description=(
            "True when the price is based only on what the mentor entered, "
            "with no track record to draw on yet."
        )
    )
    model_version: str
    status: str
    # The three below compare the advice with what the mentor charges today.
    # All null together, for a service that has no current price: there is
    # nothing to compare against, and a zero would read as a free session.
    current_price: int | None = Field(
        default=None,
        description=(
            "What the mentor charges for this service today, in whole "
            "currency units, or null if they have not set a price."
        ),
    )
    difference_vs_current_percent: float | None = Field(
        default=None,
        description=(
            "How far the advice is from the current price, as a percentage "
            "of the current price. Positive means the advice is higher."
        ),
        examples=[12.4],
    )
    position_vs_range: str | None = Field(
        default=None,
        description=(
            "Where the current price sits relative to the advised range: "
            '"below", "within" or "above". Both ends of the range count as '
            '"within".'
        ),
        examples=["within"],
    )
    generated_at: datetime


class RegistrationOut(BaseModel):
    """What registration returns: the mentor, the service and the first price."""

    mentor: MentorOut
    service: ServiceOut
    recommendation: RecommendationOut


class ServiceCreatedOut(BaseModel):
    """
    What adding a service returns: the service and its first price.

    The same pairing registration returns, for the same reason: a mentor who
    has just described a service is waiting for the number, and making the
    frontend ask for it separately would show them a service with no price
    first.
    """

    service: ServiceOut
    recommendation: RecommendationOut


class HealthOut(BaseModel):
    """
    Liveness, plus whether a price can actually be produced.

    The two build outputs are reported separately because they are
    independent. A server with models and no comparison table prices every
    service perfectly well and simply cannot say what other mentors charge.
    """

    status: str = Field(examples=["ok"])
    models_loaded: bool
    comparables_loaded: bool = Field(
        default=False,
        description=(
            "Whether the table of comparable mentors was prepared on this " "server."
        ),
    )
    model_version: str | None
    trained_at: str | None
    currency: str = mapping.CURRENCY
    detail: str | None = Field(
        default=None,
        description="What is unavailable and how to prepare it, when something is.",
    )


class FieldError(BaseModel):
    """One answer that has to change, named in the words the form uses."""

    field: str
    message: str


class ErrorOut(BaseModel):
    """The body of every error response."""

    detail: str
    errors: list[FieldError] = Field(default_factory=list)


class OptionsOut(BaseModel):
    """
    Every option list the registration form needs.

    Declared field by field rather than as a free dictionary so the OpenAPI
    schema tells the frontend what it will receive.
    """

    currency: str
    fields: list[dict[str, Any]]
    skills: list[dict[str, Any]]
    max_mentees: dict[str, int]
    session_label_rule: dict[str, dict[str, Any]]
    min_commitment: list[dict[str, Any]]
    years_mentoring_bands: list[dict[str, Any]]
    services_planned: list[dict[str, Any]]
    education_levels: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Comparable mentors
# ---------------------------------------------------------------------------
class ComparableItemOut(BaseModel):
    """
    One mentor a price is compared against.

    No id of any kind. A mentor looking at who they are compared with is
    looking at a distribution, not at other people's accounts, and every
    figure here is one a mentor would recognise about themselves.
    """

    field_label: str = Field(examples=["Technology and software"])
    session_label: str = Field(examples=["Group"])
    max_mentees: int
    price: int = Field(description="What this mentor charges for one session.")
    price_per_mentee: int = Field(description="That price divided by the seats.")
    rating_overall: float = Field(description="Their overall rating, out of 5.")
    booked_share_percent: float = Field(
        description=("The percentage of their offered time booked over the last year."),
        examples=[42.5],
    )
    reviews_total: int


class ComparablesSummaryOut(BaseModel):
    """
    The headline figures for one set of comparable mentors.

    Quantiles rather than a mean: prices in any field have a long upper tail,
    and a mean sits above most of the mentors it claims to describe. Every
    price is null when there are no comparable mentors at all, rather than
    zero, which would read as mentors charging nothing.
    """

    count: int
    median_price: int | None
    p25_price: int | None
    p75_price: int | None
    median_price_per_mentee: int | None
    currency: str = Field(default=mapping.CURRENCY, examples=[mapping.CURRENCY])
    match_level: int = Field(
        description=(
            "How widely the system had to look. 0 is the mentor's own field "
            "at about their group size, 1 is their field at any group size, "
            "and 2 is any field at about their group size."
        ),
        examples=[0],
    )
    widened: bool = Field(
        description=(
            "True when even the widest match found fewer than the minimum "
            "number of comparable mentors, so the figures above describe "
            "fewer mentors than the system considers enough to generalise "
            "from."
        )
    )
    match_description: str = Field(
        description="Who the comparison covers, in words.",
        examples=["Technology and software mentors with 3 to 5 mentees per session"],
    )


class PriceHistogramOut(BaseModel):
    """
    The spread of session prices among the comparable mentors.

    Edges and counts rather than a drawn chart, so the frontend decides how it
    looks and the API decides only what it says. Both lists are empty when
    there is nothing to bin.
    """

    bin_edges: list[float] = Field(
        description="One more edge than there are counts.", examples=[[200.0, 250.0]]
    )
    counts: list[int]


class ComparablesOut(BaseModel):
    """What mentors like this one charge: the summary, the spread, the rows."""

    summary: ComparablesSummaryOut
    histogram: PriceHistogramOut
    items: list[ComparableItemOut]
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------
class DecisionInput(StrictModel):
    """
    What the mentor did about one advisory price.

    ``final_price`` means different things per action, and the endpoint is
    where those rules live, because two of the three need the recommendation
    to check against:

    * **accepted**: the mentor takes the advice, so the final price is the
      recommended price. Sending it is optional and sending a different
      number is refused rather than quietly recorded as acceptance of
      something else.
    * **modified**: the mentor charges something else, so the price is
      required and has to differ from the advice. A "modification" equal to
      the advice is an acceptance, and storing it as a modification would
      misreport what the mentor did.
    * **rejected**: the price is optional. A mentor who declines the advice
      may say what they charge instead, which is the most useful thing they
      could tell the system, or may simply decline.
    """

    action: str = Field(
        description='One of "accepted", "modified" or "rejected".',
        examples=["accepted"],
    )
    final_price: int | None = Field(
        default=None,
        description=(
            f"The price the mentor settled on, in whole {mapping.CURRENCY}, "
            f"between {mapping.FINAL_PRICE_MIN} and {mapping.FINAL_PRICE_MAX}."
        ),
        examples=[320],
    )

    @field_validator("action")
    @classmethod
    def _check_action(cls, value: str) -> str:
        if value not in DECISION_ACTIONS:
            allowed = ", ".join(DECISION_ACTIONS)
            raise ValueError(
                f"Say what you decided about the price. The options are {allowed}."
            )
        return value

    # "before" mode, for the reason given on ServiceInput.max_mentees. This
    # is the field where it matters most: the box a mentor types their own
    # price into is the one place a stray value becomes a stored price and is
    # then shown back to them as what they charge.
    @field_validator("final_price", mode="before")
    @classmethod
    def _check_final_price(cls, value: object) -> int | None:
        if value is None:
            return None
        return mapping.validate_final_price(value)


class DecisionOut(BaseModel):
    """One answer a mentor gave, as it is read back."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    recommendation_id: int
    action: str = Field(examples=["accepted"])
    final_price: int | None = Field(
        default=None,
        description=(
            "The price the mentor settled on, or null for a rejection that "
            "named no price of its own."
        ),
    )
    currency: str = Field(default=mapping.CURRENCY, examples=[mapping.CURRENCY])
    decided_at: datetime


class RecommendationHistoryOut(BaseModel):
    """
    One advisory price and what the mentor did about it.

    ``decision`` is null while the recommendation still stands, which is what
    ``status: "pending"`` on the price itself says as well. Both are reported:
    the status is on the price because that is where it is stored, and the
    decision is here because that is where its figures are.
    """

    recommendation: RecommendationOut
    decision: DecisionOut | None


class ServiceHistoryOut(BaseModel):
    """
    Every price one service has been given, newest first.

    Newest first because the current question is almost always "what was I
    last told", and the older rows are the record of whether the advice has
    been any good.
    """

    service_id: int
    count: int
    items: list[RecommendationHistoryOut]


# ---------------------------------------------------------------------------
# The dashboard
# ---------------------------------------------------------------------------
class DecisionCountsOut(BaseModel):
    """
    How a mentor has answered the advice so far, counted by action.

    ``pending`` is one of the four because it is the honest fourth case: a
    recommendation nobody has answered is not a rejection, and folding it into
    one would overstate how often the advice is turned down.
    """

    accepted: int = 0
    modified: int = 0
    rejected: int = 0
    pending: int = 0


class TimelinePointOut(BaseModel):
    """One price, and what the mentor settled on, at one point in time."""

    generated_at: datetime
    recommended_price: int
    final_price: int | None
    action: str | None = Field(
        default=None,
        description="Null while the recommendation has not been answered.",
        examples=["accepted"],
    )


class DashboardServiceOut(BaseModel):
    """
    One service, with everything the mentor's own page shows about it.

    No earnings and no income. The system has no bookings to count and would
    have to invent a volume to turn a price into a total, so it reports what
    it actually knows: what the mentor charges, what was advised, where that
    sits among comparable mentors, and what the mentor decided.
    """

    service_id: int
    field_label: str = Field(examples=["Technology and software"])
    session_label: str = Field(examples=["One to one"])
    max_mentees: int
    current_price: int | None
    currency: str = Field(default=mapping.CURRENCY, examples=[mapping.CURRENCY])
    latest_recommendation: RecommendationOut | None
    position_vs_range: str | None = Field(
        default=None,
        description=(
            "Where the current price sits against the latest advised range: "
            '"below", "within" or "above".'
        ),
    )
    price_percentile: float | None = Field(
        default=None,
        description=(
            "The percentage of comparable mentors charging the current price "
            "or less. Null when there is no current price or no comparable "
            "mentors to place it among."
        ),
        examples=[62.5],
    )
    decision_counts: DecisionCountsOut
    average_difference_percent: float | None = Field(
        default=None,
        description=(
            "On average, how far the price the mentor settled on sat from the "
            "price advised, as a percentage of the advice. Positive means "
            "they charged more than advised. Null until they have answered "
            "at least one recommendation with a price."
        ),
        examples=[-4.2],
    )
    timeline: list[TimelinePointOut]
    comparables: ComparablesSummaryOut | None = Field(
        default=None,
        description=(
            "The comparable mentors for this service, or null when the "
            "comparison table is not available on this server."
        ),
    )


class DashboardTotalsOut(BaseModel):
    """
    The mentor's own figures across every service they offer.

    Counts and percentages only, for the same reason as above: there is no
    volume in the system, so there is no honest total in currency to report.
    """

    services: int
    services_with_a_price: int
    recommendations: int
    decision_counts: DecisionCountsOut
    average_difference_percent: float | None = Field(
        default=None,
        description=(
            "The same average as on a service, across every service the "
            "mentor offers."
        ),
    )


class DashboardOut(BaseModel):
    """A mentor's own page: one block per service, plus their own totals."""

    mentor_id: int
    display_name: str
    currency: str = Field(default=mapping.CURRENCY, examples=[mapping.CURRENCY])
    comparables_available: bool = Field(
        description=(
            "False when the comparison table was never prepared on this "
            "server, which is why the comparables and percentile fields are "
            "null."
        )
    )
    totals: DashboardTotalsOut
    services: list[DashboardServiceOut]


# Values the comparables endpoint accepts, published so the frontend can
# render the controls from the API rather than from its own copies.
SORT_FIELDS: tuple[str, ...] = comparables.SORT_FIELDS
ORDERS: tuple[str, ...] = comparables.ORDERS
