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

from src.mentor import mapping

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

    @field_validator("max_mentees")
    @classmethod
    def _check_max_mentees(cls, value: int) -> int:
        return mapping.validate_max_mentees(value)

    @field_validator("min_commitment")
    @classmethod
    def _check_min_commitment(cls, value: int) -> int:
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

    @field_validator("services_planned")
    @classmethod
    def _check_services_planned(cls, value: int) -> int:
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
    """Liveness, plus whether a price can actually be produced."""

    status: str = Field(examples=["ok"])
    models_loaded: bool
    model_version: str | None
    trained_at: str | None
    currency: str = mapping.CURRENCY
    detail: str | None = Field(
        default=None, description="Why the models are unavailable, when they are."
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
