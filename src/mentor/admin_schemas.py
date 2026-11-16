"""
Response shapes for the operations dashboard under /admin.

Kept apart from :mod:`src.mentor.schemas`, which holds the mentor-facing
surface, for one reason that is worth stating: these two sets of shapes have
different audiences and different rules, and mixing them makes it easy to
answer a mentor with a figure about the service or to answer an administrator
with somebody's name. Nothing here is ever returned to a mentor, and nothing
here carries a name, an address, free text or a mentor id.

Every one of these is a response model, so there is no ``StrictModel`` base
and no validator: /admin is read only. Six GET endpoints and no body anywhere.

Each number that is not a count carries its own unit, because an operations
page is read by somebody who did not write it. A metric arrives with the scale
it is measured on rather than a bare figure: "0.54" means nothing until it is
labelled as R squared on a 0 to 1 scale where higher is better.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminModel(BaseModel):
    """Base for every shape here: read only, and built from plain values."""

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------
class LabelledCount(AdminModel):
    """One category and how many rows fell in it."""

    id: str = Field(description="The stored id, as the database holds it.")
    label: str = Field(description="What to print for it.")
    count: int


class HistogramBucket(AdminModel):
    """
    One bar of a histogram, as a half-open interval.

    ``low`` is included and ``high`` is not, so the buckets tile the range
    without a value falling in two of them. Stated here rather than left to
    be inferred, because a reader deciding whether a price of exactly 200 is
    in the 100 to 200 bucket or the 200 to 300 one has no other way to know.
    """

    low: int
    high: int
    count: int


class DecisionCounts(AdminModel):
    """
    What mentors did with the advice they were given.

    ``acceptance_rate_percent`` is accepted over all three, and it is null
    rather than zero when nobody has decided anything yet: a platform with no
    decisions has no acceptance rate, and a zero would read as advice that
    everybody rejected.
    """

    accepted: int = 0
    modified: int = 0
    rejected: int = 0
    total: int = 0
    acceptance_rate_percent: float | None = None
    pending: int = Field(
        default=0,
        description="Recommendations nobody has answered yet.",
    )


# ---------------------------------------------------------------------------
# /admin/summary
# ---------------------------------------------------------------------------
class AdminSummaryOut(AdminModel):
    """The figures the dashboard opens with."""

    accounts: int = Field(description="Every row in the accounts table.")
    mentors: int = Field(
        description=(
            "Accounts that are mentors, which is every account that is not "
            "an administrator. An administrator account exists to read this "
            "page and is not somebody the platform prices."
        )
    )
    verified_mentors: int
    demo_mentors: int = Field(
        description=(
            "Mentors created by the demonstration seed script. Reported "
            "separately so the other counts can be read for what they are."
        )
    )
    services: int
    recommendations: int
    decisions: DecisionCounts
    requests_last_24h: int = Field(
        description="Logged pricing calls with a timestamp in the last 24 hours."
    )
    median_response_ms: int | None = Field(
        default=None,
        description=(
            "The median duration of every logged pricing call, in "
            "milliseconds, or null while none has been logged. Over the whole "
            "log rather than the last day, so the figure does not disappear "
            "on a quiet day."
        ),
    )
    logged_requests: int = Field(
        description="Every row in the request log, which the median is over."
    )


# ---------------------------------------------------------------------------
# /admin/usage
# ---------------------------------------------------------------------------
class UsageDay(AdminModel):
    """One day of calls, split by which model answered."""

    day: date
    core: int = 0
    full: int = 0
    no_model: int = Field(
        default=0,
        description=(
            "Calls that were answered before a model was reached: a refused "
            "preview, or a request for a record that was not the caller's."
        ),
    )
    total: int = 0


class LatencyDay(AdminModel):
    """How long the calls on one day took."""

    day: date
    median_ms: int
    p95_ms: int = Field(
        description=(
            "The 95th percentile, by nearest rank on that day's own calls. On "
            "a day with few calls it is close to the slowest one, which is "
            "what makes requests worth reporting beside it."
        )
    )
    requests: int


class ModelShare(AdminModel):
    """How the whole log divides between the two models."""

    core: int = 0
    full: int = 0
    no_model: int = 0
    total: int = 0
    core_percent: float | None = None
    full_percent: float | None = None


class AdminUsageOut(AdminModel):
    """Calls over time, by path, and how long they took."""

    days: int = Field(description="How many days back the series covers.")
    per_day: list[UsageDay] = Field(default_factory=list)
    by_endpoint: list[LabelledCount] = Field(default_factory=list)
    latency_per_day: list[LatencyDay] = Field(default_factory=list)
    model_share: ModelShare


# ---------------------------------------------------------------------------
# /admin/outputs
# ---------------------------------------------------------------------------
class FieldOutputs(AdminModel):
    """What was advised in one field."""

    id: str
    label: str
    count: int
    median_price: int | None = None


class RangeWidths(AdminModel):
    """
    How wide the range around a price is.

    Worth a section of its own because the range is the part of the advice a
    mentor acts within: a range half as wide as the price is a different
    statement from one a tenth as wide, and the dashboard has no other place
    that would show it.
    """

    median: int | None = None
    median_percent_of_price: float | None = None
    buckets: list[HistogramBucket] = Field(default_factory=list)


class AdminOutputsOut(AdminModel):
    """What the models actually advised."""

    recommendations: int
    currency: str
    price_buckets: list[HistogramBucket] = Field(
        default_factory=list,
        description=(
            "The distribution of advised prices. Built from the stored "
            "recommendations rather than from the request log, because a "
            "recommendation is advice a mentor was offered and a preview is a "
            "figure on a form nobody has submitted."
        ),
    )
    median_price: int | None = None
    by_field: list[FieldOutputs] = Field(default_factory=list)
    decisions: DecisionCounts
    range_widths: RangeWidths


# ---------------------------------------------------------------------------
# /admin/signups
# ---------------------------------------------------------------------------
class SignupWeek(AdminModel):
    """One week of new accounts, by whether they have been checked."""

    week: date = Field(description="The Monday the week starts on.")
    accounts: int = 0
    verified: int = 0
    unverified: int = 0


class AdminSignupsOut(AdminModel):
    """New accounts over time."""

    weeks: int = Field(description="How many weeks the series covers.")
    per_week: list[SignupWeek] = Field(default_factory=list)
    accounts: int
    verified: int
    unverified: int


# ---------------------------------------------------------------------------
# /admin/models
# ---------------------------------------------------------------------------
class ModelMetric(AdminModel):
    """
    One held-out score, with the scale it is measured on.

    The scale is a field rather than a sentence in the docs, because the page
    prints it beside the figure. A number whose direction is not stated is a
    number a reader can only guess at: a lower RMSE is better and a higher R
    squared is better, and nothing about either figure says so.
    """

    id: str
    label: str
    value: float
    scale: str = Field(
        description="What the figure is measured in, and which way is better."
    )


class AdminModelCard(AdminModel):
    """One deployed model, its inputs and its scores."""

    id: str = Field(description='Either "core" or "full".')
    label: str
    algorithm: str | None = None
    inputs_note: str = Field(
        description="What this model is given, in words, for the page to print."
    )
    file: str | None = Field(
        default=None, description="The file name the application loads it from."
    )
    created_at: datetime | None = Field(
        default=None, description="When the deployed file was fitted."
    )
    metrics: list[ModelMetric] = Field(default_factory=list)


class AdminModelsOut(AdminModel):
    """The two deployed models, as the report and the build output describe them."""

    measured_on: str = Field(
        description="Which rows every score on this page was measured on."
    )
    cross_validation: str = Field(
        description="How the cross-validated figure was produced, in one line."
    )
    currency: str
    report_available: bool = Field(
        description=(
            "False when the training report is not on this machine, which is "
            "the normal state of a fresh clone: the report is a git-ignored "
            "output of a local training run. The cards then carry the file "
            "names and no scores, rather than an error."
        )
    )
    models: list[AdminModelCard] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# /admin/recent
# ---------------------------------------------------------------------------
class AdminEvent(AdminModel):
    """
    One logged call, as the activity table prints it.

    The mentor id is in the table and deliberately not in this shape. A
    recent-activity list is read to see what the service is doing, and the
    account behind a call adds nothing to that while turning a page of
    figures into a page about people.
    """

    id: int
    created_at: datetime
    endpoint: str
    endpoint_label: str
    model_used: str | None = None
    field: str | None = None
    field_label: str | None = None
    group_size: int | None = None
    recommended_price: int | None = None
    response_ms: int
    status_code: int


class AdminRecentOut(AdminModel):
    """The latest calls, newest first."""

    limit: int
    currency: str
    events: list[AdminEvent] = Field(default_factory=list)
