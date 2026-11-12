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
from src.mentor import comparables, mapping, security

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

    There is no verification flag either. Whether a mentor has been checked is
    something the platform says about them rather than something they tell it,
    so a service takes that from the mentor's account and not from this body.
    It is one of the eight things a price is worked out from, which is exactly
    why a mentor cannot set it.
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


class ProfileFields(StrictModel):
    """
    The optional things a mentor says about themselves.

    Every field here is profile only. None of them reaches a model: the
    training data has no equivalent of a qualification or a number of years
    mentoring, so routing one into a column would be inventing a
    relationship rather than using one. They are stored, shown on the
    mentor's public profile, and that is all they do.
    """

    years_experience: int | None = Field(
        default=None,
        description=(
            f"How many years the mentor has been mentoring, "
            f"{mapping.YEARS_EXPERIENCE_MIN} to "
            f"{mapping.YEARS_EXPERIENCE_MAX}. Shown on their profile; it does "
            f"not affect the price."
        ),
        examples=[7],
    )
    education_level: str | None = Field(
        default=None, description="Highest level of education, from /meta/options."
    )
    credentials: str | None = Field(default=None, max_length=TEXT_MAX)

    @field_validator("years_experience", mode="before")
    @classmethod
    def _check_years(cls, value: object) -> int | None:
        if value is None:
            return None
        return mapping.validate_years_experience(value)

    @field_validator("education_level")
    @classmethod
    def _check_education(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return mapping.validate_education_level(value)


class MentorRegistration(ProfileFields):
    """
    Everything the single-page registration form sends, in one body.

    One call creates the account, the profile and the first service, because
    the form is one page and the mentor is waiting for a price at the end of
    it. Splitting it would leave a mentor who abandoned the second request
    with an account and nothing to price.

    What it no longer asks is worth naming. There is no question about how
    many services the mentor plans to offer: it was a guess about the future
    that moved their price today. There is no verification flag either; a
    mentor cannot tell the platform that the platform has checked them, so
    every new account starts unverified.
    """

    name: str = Field(
        min_length=NAME_MIN,
        max_length=NAME_MAX,
        description="The name shown on the mentor's profile.",
        examples=["A. Mentor"],
    )
    email: str = Field(max_length=EMAIL_MAX, examples=["mentor@example.com"])
    password: str = Field(
        description=(
            f"Between {security.PASSWORD_MIN_LENGTH} and "
            f"{security.PASSWORD_MAX_LENGTH} characters."
        ),
        examples=["a-long-enough-password"],
    )
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
    skills: list[str] = Field(
        default_factory=list,
        description="Skill ids the mentor offers, from /meta/options.",
        examples=[["cv_review", "interview_preparation"]],
    )
    min_commitment: int = Field(
        default=mapping.MIN_COMMITMENT_DEFAULT,
        description=(
            "Smallest number of sessions a mentee can book. Optional: one "
            "session when the form does not ask."
        ),
        examples=[1],
    )
    headline: str | None = Field(
        default=None,
        max_length=HEADLINE_MAX,
        examples=["Helping graduate engineers find their first role"],
    )
    bio: str | None = Field(default=None, max_length=TEXT_MAX)
    experience_summary: str | None = Field(default=None, max_length=TEXT_MAX)

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        normalised = security.normalise_email(value)
        if not EMAIL_PATTERN.match(normalised):
            raise ValueError("Enter an email address the mentor can be reached at.")
        return normalised

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return security.validate_password(value)

    @field_validator("field")
    @classmethod
    def _check_field(cls, value: str) -> str:
        return mapping.validate_field(value)

    # "before" mode, for the reason given on ServiceInput.max_mentees: in
    # Python True is an int equal to 1, so a checkbox posted into a number box
    # would otherwise be stored as a group of one.
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


class MentorLogin(StrictModel):
    """An email address and a password, and nothing else."""

    email: str = Field(max_length=EMAIL_MAX, examples=["mentor@example.com"])
    password: str = Field(examples=["a-long-enough-password"])

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return security.normalise_email(value)


class MentorUpdate(ProfileFields):
    """
    The parts of their own record a mentor may change.

    Their name and the three optional profile fields. Nothing here reaches a
    model, and nothing here is a thing the platform says about the mentor: a
    mentor cannot edit their own verification, their email address or anything
    about a service, each of which has its own reason to be settled elsewhere.

    Every field is optional, and a field that was not sent is left alone
    rather than cleared. Sending one as null does clear it, which is how a
    mentor removes something they would rather not show.
    """

    name: str | None = Field(
        default=None, min_length=NAME_MIN, max_length=NAME_MAX, examples=["A. Mentor"]
    )


class PreviewInput(StrictModel):
    """
    The three answers a live price preview needs, and no account.

    Exactly the answers the registration form asks that affect a price, with
    the same validation, so the number shown beside a half-filled form is the
    number the form will produce when it is submitted.
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
    skills: list[str] = Field(
        default_factory=list,
        description="Skill ids the mentor offers, from /meta/options.",
        examples=[["cv_review", "interview_preparation"]],
    )

    @field_validator("field")
    @classmethod
    def _check_field(cls, value: str) -> str:
        return mapping.validate_field(value)

    @field_validator("max_mentees", mode="before")
    @classmethod
    def _check_max_mentees(cls, value: object) -> int:
        return mapping.validate_max_mentees(value)

    @field_validator("skills")
    @classmethod
    def _check_skills(cls, value: list[str]) -> list[str]:
        return mapping.validate_skills(value)


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
    years_experience: int | None = Field(
        default=None,
        description=(
            "How many years the mentor has been mentoring, or null if they "
            "have not said. Profile only: it does not affect the price."
        ),
    )
    years_mentoring_band: str | None = Field(
        default=None,
        description=(
            "The band years_experience falls in, from /meta/options, or null "
            "if the mentor has not said how long they have been mentoring."
        ),
    )
    verified: bool = Field(
        default=False,
        description=(
            "True once the platform has checked who this mentor is. False for "
            "every new account: nothing a mentor sends can set it."
        ),
    )
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


class MentorCardOut(BaseModel):
    """
    One mentor as the public directory shows them.

    Deliberately short, and the list is deliberately exhaustive: this is the
    one response in the API that is served to anybody at all, so what it
    carries was chosen field by field rather than trimmed from a record. No
    address, no password hash, no demonstration flag, no source record, and
    none of the figures a model reads.

    ``price`` is what the mentor charges today, which is null until they have
    settled on one. A mentor who has only been advised a price has not set it,
    and showing advice as though it were their price would put a number on
    their card that they never chose.
    """

    id: int
    display_name: str
    field_label: str = Field(examples=["Technology and software"])
    service_name: str = Field(
        description="What the service is called, derived from the field and "
        "the group size.",
        examples=["Technology and software: one-to-one mentoring"],
    )
    price: int | None = Field(
        default=None,
        description=(
            f"What the mentor charges for one session, in whole "
            f"{mapping.CURRENCY}, or null if they have not set a price yet."
        ),
    )
    max_mentees: int
    session_label: str = Field(examples=["one_to_one"])
    verified: bool = Field(
        description="True once the platform has checked who this mentor is."
    )
    review_count: int = Field(
        description=(
            "How many reviews the mentor has, or zero for a mentor with no "
            "record on the platform yet."
        )
    )
    average_rating: float | None = Field(
        default=None,
        description=(
            "What mentees rate this mentor overall, out of five, to one "
            "decimal place, or null when the platform holds no rating for "
            "them. Null rather than zero: a mentor nobody has rated yet has "
            "not been rated badly, and a frontend is expected to show "
            "nothing at all rather than a zero or a row of empty stars."
        ),
        examples=[4.8],
    )


class MentorDirectoryOut(BaseModel):
    """
    A page of the public directory, and how many mentors there are in all.

    ``total`` counts every mentor the filters match rather than the ones on
    this page, so a frontend can say how many there are without asking for
    all of them.
    """

    total: int
    limit: int
    offset: int
    items: list[MentorCardOut]


class SkillOut(BaseModel):
    """One skill, with the label a mentee reads for it."""

    id: str = Field(examples=["cv_review"])
    label: str = Field(examples=["CV review"])


class PublicMentorOut(MentorCardOut):
    """
    One mentor's public profile: their card, their skills, what they told us.

    The three optional fields are profile only and are shown exactly as the
    mentor entered them, or null where they chose not to answer. None of them
    reaches a model, which is why a mentor can fill them in or clear them
    without their price moving.
    """

    skills: list[SkillOut] = Field(default_factory=list)
    years_experience: int | None = Field(
        default=None,
        description="How many years the mentor has been mentoring, if they said.",
    )
    years_mentoring_band: str | None = Field(
        default=None, description="The band those years fall in, from /meta/options."
    )
    education_level: str | None = Field(
        default=None, description="The id of their education level, if they gave one."
    )
    education_label: str | None = Field(
        default=None, description="The label a mentee reads for that level."
    )
    credentials: str | None = None


class PreviewOut(BaseModel):
    """
    A price for answers nobody has registered yet.

    The same four numbers the registration form will produce, so a mentor
    filling it in watches the figure they are about to be given rather than
    waiting to find out. Nothing is stored: there is no mentor to store it
    against, and a preview is not advice the mentor has been offered.
    """

    session_price: int = Field(
        description="The advised price for one session, in whole currency units."
    )
    per_person_price: int = Field(
        description=(
            "That price divided by the number of mentees who can join, which "
            "is what one mentee pays. Equal to session_price for a session of "
            "one."
        )
    )
    range_low: int = Field(description="Low end of the range around the advice.")
    range_high: int = Field(description="High end of the range around the advice.")
    currency: str = Field(default=mapping.CURRENCY, examples=[mapping.CURRENCY])
    low_confidence: bool = Field(
        default=True,
        description=(
            "Always true here. A preview is worked out from a part-filled "
            "form, with no record of completed sessions to draw on."
        ),
    )


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
    # Both read from the row's own input snapshot rather than from the service
    # as it stands now, for the same reason the per-mentee figures are: a
    # mentor who changes the number of seats afterwards must not change what
    # an old price says it was a price for.
    max_mentees: int = Field(
        description="How many mentees the session this price is for can hold."
    )
    session_label: str = Field(
        description=(
            'What that size of session is called: "one_to_one" or "group". '
            "The labels to show are in /meta/options."
        ),
        examples=["one_to_one"],
    )
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
    decision: DecisionOut | None = Field(
        default=None,
        description=(
            "What the mentor decided about this price, where the endpoint "
            "reports it. Null on a price nobody has answered, and null on the "
            "endpoints that report the decision beside the price instead."
        ),
    )


class TokenOut(BaseModel):
    """
    An access token, and how long it is good for.

    ``token_type`` is always "bearer" and is reported rather than assumed, so
    a client can build the header from the response instead of from a
    convention it remembers. There is no refresh token: a token lasts seven
    days and signing in again is how a mentor gets another one.
    """

    access_token: str = Field(
        description="Send as the Authorization header: `Bearer <token>`."
    )
    token_type: str = Field(default=security.TOKEN_TYPE, examples=[security.TOKEN_TYPE])
    expires_in: int = Field(
        description="Seconds until the token stops being accepted.",
        examples=[security.token_lifetime_seconds()],
    )


class LoginOut(TokenOut):
    """What signing in returns: a token and the mentor it belongs to."""

    mentor: MentorOut


class RegistrationOut(TokenOut):
    """
    What registration returns: a signed-in mentor, their service, its price.

    The token is included so the frontend does not have to sign in again
    immediately after registering, and the price is included because the
    mentor filled in the form to get it.
    """

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
    min_commitment_default: int
    years_mentoring_bands: list[dict[str, Any]]
    years_experience: dict[str, int]
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


class PriceDistributionOut(BaseModel):
    """
    The comparable mentors a frontend plots and lists, and what they stand for.

    A match can run to a thousand mentors. Drawing all of them is a solid bar
    of overlapping points, and a table of every one of them is a table nobody
    reaches the end of, so this is an evenly spread sample by price rank,
    with the cheapest and the dearest always kept.

    ``total`` is how many mentors were matched and ``shown`` how many are
    here. Both are reported because a sentence above a chart has to be able to
    say which number it is talking about, and a sample presented as the whole
    market would overstate what the chart shows.

    The summary beside this is read from exactly these mentors, so the band
    drawn around the middle of the group is the quartiles of the points drawn
    beside it rather than of some other set.
    """

    total: int = Field(description="How many comparable mentors were matched.")
    shown: int = Field(description="How many of them are in items below.")
    sampled: bool = Field(
        description=(
            "True when the match was larger than the number shown, so items "
            "is a spread across it rather than all of it."
        )
    )
    items: list[ComparableItemOut] = Field(
        description="Cheapest first, by what each mentor charges for a session."
    )


class FactorPartOut(BaseModel):
    """
    One of the measured themes a grouped factor was built from.

    A row a mentor reads may stand for more than one thing about their
    record. These are the parts behind it, reported so that grouping two
    themes into one sentence does not amount to hiding either number: a page
    shows them in the table behind its disclosure rather than in the row.
    """

    key: str = Field(examples=["ratings"])
    label: str = Field(examples=["What mentees rate you"])
    effect_pct: int = Field(examples=[-4])


class PriceFactorOut(BaseModel):
    """
    One thing about a mentor's answers, and what it does to their price.

    ``effect_pct`` is relative: a factor at 12 says this answer leaves the
    price twelve per cent above what it would otherwise have been, and the
    factors multiply rather than add. It is a whole percent because a reader
    cannot act on a tenth of one and because a figure carried to decimals
    invites a confidence the number does not have.

    ``direction`` carries the sign in words so that a page never has to rely
    on a colour or an arrow alone to say which way a factor goes.

    ``association`` is true for the themes drawn from what the platform has
    measured about a mentor. Those are patterns among mentors who charge
    alike, not things the mentor did that produced a price, and the sentence
    says so.
    """

    key: str = Field(examples=["group_size"])
    label: str = Field(examples=["Your group size"])
    direction: str = Field(
        description="One of raises, lowers, little effect.", examples=["raises"]
    )
    effect_pct: int = Field(
        description=(
            "How much this answer multiplies the price by, as a whole "
            "percent above or below."
        ),
        examples=[12],
    )
    sentence: str = Field(description="The factor in one plain sentence.")
    association: bool = Field(
        default=False,
        description=(
            "True when this is a pattern among similar mentors rather than "
            "an answer the mentor gave."
        ),
    )
    components: list[FactorPartOut] = Field(
        default_factory=list,
        description=(
            "The measured themes behind a grouped row, empty for a row that "
            "stands for one answer. Reported so that a page can show the "
            "parts of a group in its numbers table."
        ),
    )


class PriceDifferenceOut(BaseModel):
    """One way this mentor's service differs from the ones beside it."""

    key: str = Field(examples=["skills"])
    label: str = Field(examples=["Skills covered"])
    sentence: str


class PriceComparisonOut(BaseModel):
    """
    Where a suggestion lands among the mentors the price screen draws.

    Read off the same reduced sample as the chart and the band, so the
    sentence here and the dots there describe the same mentors.

    ``explains_gap`` is present only when the suggestion is outside the
    middle band. It names the one or two largest factors pointing that way,
    as advice rather than as a fault: a mentor whose price is above the
    middle may have good reason for it, and the page says what the reason
    looks like rather than telling them to change it.
    """

    position: str = Field(
        description="below, within, above, or unknown when there are too few.",
        examples=["within"],
    )
    percentile: float | None = Field(
        default=None,
        description=(
            "The share of the compared mentors charging this much or less, "
            "or null when there is nobody to place it among."
        ),
    )
    median_price: int | None = None
    band_low: int | None = None
    band_high: int | None = None
    compared_with: int = Field(
        description="How many mentors the comparison was read from."
    )
    matched_total: int = Field(description="How many mentors were matched in all.")
    match_description: str
    sentence: str
    explains_gap: str | None = None
    differences: list[PriceDifferenceOut] = Field(default_factory=list)


class ExplanationOut(BaseModel):
    """
    Why one price was suggested, in the mentor's own words.

    The arithmetic closes: the baseline multiplied by every effect below,
    including the small ones gathered into one row, gives back
    ``suggested_price`` to within the rounding of a whole percent. That is
    the point of the response rather than a detail of it, because an account
    that did not close would be a story told beside a number instead of an
    account of it.

    ``limitation`` and ``profile_note`` are fixed sentences and are always
    present. They are part of the answer rather than small print: the first
    says what these patterns are and are not, and the second says plainly
    that the three things a mentor is most likely to expect to count here do
    not.
    """

    recommendation_id: int
    service_id: int
    model_used: str = Field(examples=["core"])
    low_confidence: bool
    currency: str = Field(default=mapping.CURRENCY, examples=[mapping.CURRENCY])
    baseline_price: int = Field(
        description="Where a price for a mentor in this situation starts."
    )
    baseline_sentence: str
    summary_sentence: str = Field(
        description=(
            "The one line between the typical price and the rows that move "
            "it, saying how far the suggestion sits from that typical price "
            "and on which side."
        )
    )
    suggested_price: int
    factors: list[PriceFactorOut] = Field(
        description="Largest effect first, at most five."
    )
    other_small_effects: PriceFactorOut | None = Field(
        default=None,
        description=(
            "Everything too small to list, multiplied into one row, or null "
            "when there was nothing left over."
        ),
    )
    combination_note: str
    limitation: str
    profile_note: str
    comparison: PriceComparisonOut


class ComparablesOut(BaseModel):
    """
    What mentors like this one charge: the summary, the spread, the rows.

    Two different lists of mentors, for two different questions.
    ``distribution`` is the comparison: an evenly spread sample of the whole
    match, which the summary and the histogram are both read from, and the
    one to plot or tabulate. ``items`` is a page of the match in whatever
    order was asked for, which is the right answer to "show me the dearest
    ten" and the wrong one to draw a market from, because the first page of a
    sort is one end of the market rather than the middle of it.
    """

    summary: ComparablesSummaryOut
    histogram: PriceHistogramOut
    distribution: PriceDistributionOut
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


class ActivityOut(BaseModel):
    """
    A mentor's own activity, month by month, as parallel arrays.

    Four lists of the same length, one entry per month, oldest first. Parallel
    arrays rather than a list of objects because every chart library takes
    them that way, and because it makes the one thing that matters about this
    response obvious: a month is one position in all four lists, so a gap in
    one of them is a gap and not a shift.

    **A null is not a zero.** ``booked_share_by_month`` and
    ``price_by_month`` are null for a month the platform has no such
    measurement for. A zero would say the mentor was booked for none of the
    time they offered, or charged nothing, and both are claims the platform
    cannot make. ``reviews_by_month`` is never null: a month inside the period
    a mentor has been on the platform with no reviews in it had none.

    **There is no rating over time.** The platform holds one rating per
    mentor, as it stands now, with no record of what it was in any earlier
    month, so a rating line would have to be invented.
    """

    has_history: bool = Field(
        description=(
            "False for a mentor with no activity recorded yet, which is every "
            "mentor who has just registered. The four lists are then empty."
        )
    )
    months: list[str] = Field(
        default_factory=list,
        description="Each month as its first day, oldest first.",
        examples=[["2026-07-01", "2026-08-01"]],
    )
    reviews_by_month: list[int] = Field(default_factory=list)
    booked_share_by_month: list[float | None] = Field(
        default_factory=list,
        description=(
            "The share of the time the mentor offered that was booked, from 0 "
            "to 1, or null for a month with no record of it."
        ),
    )
    price_by_month: list[int | None] = Field(
        default_factory=list,
        description=(
            f"What the mentor charged that month, in whole {mapping.CURRENCY}, "
            f"or null for a month with no record of it."
        ),
    )
    currency: str = Field(default=mapping.CURRENCY, examples=[mapping.CURRENCY])
    note: str = Field(
        description="One plain sentence saying what the period shows.",
        examples=["You have 23 reviews over the last 12 months."],
    )


class DashboardHeadlineOut(BaseModel):
    """
    The one line at the top of the mentor's page, and the figures behind it.

    Built for the mentor's main service, which is the first one they
    published. A page that opened with eight numbers and no sentence would
    leave the mentor to work out what they mean, and the sentence is the thing
    they came for: am I charging roughly what other people like me charge.

    ``sentence`` is written on the server, in plain words, so that the one
    statement the page makes about a mentor's price cannot be assembled
    differently by two different frontends. It carries no percentages and no
    model terms.
    """

    your_price: int | None = Field(
        default=None,
        description=(
            f"What the mentor charges for that service today, in whole "
            f"{mapping.CURRENCY}, or null if they have not set a price."
        ),
    )
    similar_typical: int | None = Field(
        default=None,
        description=(
            "What a typical comparable mentor charges: the median of the "
            "mentors this service is compared against. Null when there are "
            "none, or when this server has no comparison table."
        ),
    )
    position_vs_range: str | None = Field(
        default=None,
        description=(
            "Where the mentor's own price sits among comparable mentors: "
            '"below", "within" or "above" the range a typical one charges, '
            "which is the middle half of them. Null when either price is "
            "missing."
        ),
        examples=["within"],
    )
    sentence: str = Field(
        description="The same comparison in one plain sentence.",
        examples=[
            "You charge about the same as other one-to-one mentors in your field."
        ],
    )
    currency: str = Field(default=mapping.CURRENCY, examples=[mapping.CURRENCY])


class DemandComparisonOut(BaseModel):
    """
    How much of a mentor's offered time is taken, beside similar mentors.

    Only for a mentor the platform has measured. A new mentor has no such
    measurement, and a share invented for them would be the one number on the
    page that was never observed, so the field is null and the page shows
    nothing rather than a zero.

    ``position`` is one of above, below or about the same, and the sentence
    says the same thing in words, so no page has to carry the meaning in a
    colour. Both are advice: a mentor booked more than the mentors beside
    them may have a reason to stay where they are, and this says what the
    figures look like rather than what to do about them.
    """

    position: str = Field(description="above, below, or similar.", examples=["above"])
    booked_percent: float = Field(
        description="The share of this mentor's offered time that is taken.",
        examples=[62.0],
    )
    typical_booked_percent: float = Field(
        description="The same share for a typical comparable mentor.",
        examples=[48.0],
    )
    difference_points: float = Field(
        description=(
            "How far apart the two shares are, in percentage points, signed "
            "towards the mentor."
        ),
        examples=[14.0],
    )
    compared_with: int = Field(
        description="How many comparable mentors the typical share is from."
    )
    sentence: str = Field(description="The comparison in one plain sentence.")


class DashboardOut(BaseModel):
    """A mentor's own page: one block per service, plus their own totals."""

    mentor_id: int
    display_name: str
    average_rating: float | None = Field(
        default=None,
        description=(
            "The mentor's overall rating out of five, to one decimal place, "
            "or null when there is none. One figure, not a series: the "
            "platform records a mentor's rating as it stands rather than "
            "month by month, so there is nothing honest to draw over time."
        ),
        examples=[4.8],
    )
    headline: DashboardHeadlineOut = Field(
        description="The one line the page opens with, about the main service."
    )
    currency: str = Field(default=mapping.CURRENCY, examples=[mapping.CURRENCY])
    comparables_available: bool = Field(
        description=(
            "False when the comparison table was never prepared on this "
            "server, which is why the comparables and percentile fields are "
            "null."
        )
    )
    demand: DemandComparisonOut | None = Field(
        default=None,
        description=(
            "How booked this mentor is beside comparable mentors, or null "
            "when the platform has not measured it for them or there is "
            "nobody comparable to measure it against."
        ),
    )
    totals: DashboardTotalsOut
    services: list[DashboardServiceOut]


# Values the comparables endpoint accepts, published so the frontend can
# render the controls from the API rather than from its own copies.
SORT_FIELDS: tuple[str, ...] = comparables.SORT_FIELDS
ORDERS: tuple[str, ...] = comparables.ORDERS
