"""
The mentor-facing pricing API.

A mentor registering for the first time reads the form options, registers with
a first service, receives an advisory price and reads it back. A mentor who
already has a track record is priced by the full model on the same endpoints,
and their advice is shown against what they charge today.

Around that sit the three things that make a price usable rather than merely
correct:

* **Who it is compared against.** A number alone is one a mentor has no way to
  judge, so every service can be shown what mentors like them charge, matched
  on field and group size and widening until there are enough of them to say
  anything. See :mod:`src.mentor.comparables`.
* **What the mentor decided.** The price is advice, and the record of whether
  it was taken is the record of whether it was any good. A recommendation is
  stored "pending" and stays that way until the mentor answers it, once.
* **What that adds up to.** The dashboard reports, per service, what was
  advised, what the mentor settled on, how far apart those were, and where
  their price sits among comparable mentors. No earnings and no income: the
  system has no bookings to count, so it reports what it knows.

Both models and the comparison table are loaded once, at startup. A server
without them still answers ``/health`` and ``/meta/options``, and says plainly
on the endpoints that need them what has not been prepared, rather than
failing on the first mentor who tries to register.

Run locally with:

    uvicorn src.mentor.app:app --reload
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db import get_session
from src.db.mentor_models import (
    Mentor,
    MentorActivity,
    MentorHistory,
    PricingDecision,
    PricingRecommendation,
    Service,
)
from src.mentor import comparables as comparables_module
from src.mentor import mapping, security
from src.mentor.dependencies import get_current_mentor_id, unauthorized
from src.mentor.prediction import (
    ASSETS_MISSING_MESSAGE,
    POSITION_ABOVE,
    POSITION_BELOW,
    POSITION_WITHIN,
    AssetsUnavailableError,
    PricingService,
    difference_vs_current_percent,
    load_pricing_service,
    per_mentee,
    position_vs_range,
)
from src.mentor.rate_limit import RateLimiter
from src.mentor.schemas import (
    ActivityOut,
    ComparableItemOut,
    ComparablesOut,
    ComparablesSummaryOut,
    DashboardHeadlineOut,
    DashboardOut,
    DashboardServiceOut,
    DashboardTotalsOut,
    DecisionCountsOut,
    DecisionInput,
    DecisionOut,
    DemoMentorOut,
    ErrorOut,
    HealthOut,
    HistorySummaryOut,
    LoginOut,
    MentorCardOut,
    MentorDirectoryOut,
    MentorLogin,
    MentorOut,
    MentorRegistration,
    MentorUpdate,
    OptionsOut,
    PreviewInput,
    PreviewOut,
    PriceDistributionOut,
    PriceHistogramOut,
    PublicMentorOut,
    RecommendationHistoryOut,
    RecommendationOut,
    RegistrationOut,
    ServiceCreatedOut,
    ServiceHistoryOut,
    ServiceInput,
    ServiceOut,
    SkillOut,
    TimelinePointOut,
)

logger = logging.getLogger(__name__)

# Returned whenever a mentor asks for something that is not theirs, as well as
# for something that does not exist. The two cases are deliberately
# indistinguishable: a different answer for "exists but not yours" would let a
# caller enumerate other mentors' rows.
NOT_FOUND_MESSAGE = "That record does not exist."

# Deliberately neutral. "That address is already registered" would confirm
# an account exists to anyone who typed the address, so the message names no
# address and says the same thing whoever reads it.
EMAIL_TAKEN_MESSAGE = (
    "That email address cannot be used to register. Sign in instead, or "
    "register with a different address."
)

# One message for a wrong password and for an address nobody has registered.
# Two messages would answer "is this person on the platform".
SIGN_IN_FAILED_MESSAGE = "That email address and password do not match an account."

ALREADY_DECIDED_MESSAGE = (
    "You have already answered this price. Ask for a fresh price if you want "
    "to decide again, and answer that one instead."
)

# The paging limits on the comparable mentors list. The default is a screenful
# and the maximum is what a frontend can plot without paging, since the
# histogram beside the list already describes the whole distribution.
DEFAULT_LIMIT = 20
MAX_LIMIT = 200

# The paging limits on the public directory. Twenty-four is a screenful of
# cards in three, four or six columns, and a hundred is as many as one request
# is worth: a list that long is being scraped rather than read.
DIRECTORY_DEFAULT_LIMIT = 24
DIRECTORY_MAX_LIMIT = 100

# How often one address may ask for a preview price. Sixty a minute is about
# one a second, which is faster than anybody fills in a form and slower than a
# page in a loop.
PREVIEW_RATE_LIMIT = 60
PREVIEW_RATE_WINDOW_SECONDS = 60.0

preview_limiter = RateLimiter(
    limit=PREVIEW_RATE_LIMIT, window=PREVIEW_RATE_WINDOW_SECONDS
)

PREVIEW_RATE_LIMIT_MESSAGE = (
    "That is more price previews than this server will work out at once. Wait "
    "a moment and try again."
)

DESCRIPTION = """
Advisory session pricing for mentors.

Every price this API returns is advice. The mentor may accept it, change it or
ignore it; the system never sets a price on their behalf.

A newly registered mentor is priced from what they entered on the registration
form. Those prices are marked `low_confidence`, because a form alone is a
weaker basis than a track record. Once a mentor has a complete record of
completed sessions and reviews, the same endpoints price them with a second,
more accurate model, their own time on the platform replaces the constant the
first model is given, and the flag goes away.

A service that records what the mentor charges today gets its advice compared
against it: `current_price`, `difference_vs_current_percent`, and
`position_vs_range`, which says whether what they charge is below, within or
above the advised range. All three are null for a service with no price set.

Every price comes with two sets of figures. `recommended_price`, `price_low`
and `price_high` are the session: one booking, one price, however many
mentees are in it. The three `price_per_mentee` figures are those divided by
the number of seats, which is what one mentee pays.

How long a mentor has been mentoring is asked and shown on their profile, and
does not affect the price.

Every service can also be compared with mentors like them. The comparison is
matched on field and group size, widens in steps until it has enough mentors
to generalise from, and reports which level it used, because "mentors in any
field" is a weaker statement than "mentors in your field". It carries no ids
of any kind: it is a distribution, not a list of other people's accounts.

A mentor answers a price once, with `accepted`, `modified` or `rejected`.
Accepting settles on the advised price; modifying requires a different price;
rejecting may name the mentor's own price or none. Whatever price they settle
on becomes what the service charges, and the dashboard reports how far their
decisions have sat from the advice.

Nothing in this API reports earnings or income. There are no bookings in the
system, so there is no volume to turn a price into a total, and a figure
presented as income would be invented.

A mentor registers with an email address and a password and is given an access
token. Every request about their own records carries it as
`Authorization: Bearer <token>`. A mentor can only ever read their own
records, and a request for someone else's returns 404 rather than 403, because
403 would confirm that the other record exists.

Signing out is the client discarding the token. The server keeps no session,
so there is nothing for it to end.
"""

TAGS: list[dict[str, Any]] = [
    {"name": "service", "description": "Liveness and form options."},
    {
        "name": "auth",
        "description": "Registering, signing in, and who the caller is.",
    },
    {"name": "mentors", "description": "A mentor's own record."},
    {"name": "pricing", "description": "Advisory prices for a mentor's services."},
    {
        "name": "comparables",
        "description": "What mentors like this one charge.",
    },
    {
        "name": "decisions",
        "description": "What the mentor did about a price, and the record of it.",
    },
    {
        "name": "directory",
        "description": "The public list of mentors, and one mentor's profile.",
    },
    {
        "name": "demo",
        "description": "Mentors seeded so there is something to demonstrate.",
    },
]

ERROR_RESPONSE = {"model": ErrorOut}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Settle the signing key, then load the models and the comparison table.

    The signing key comes first and is the one thing here that can stop the
    server from starting. A production deployment without one would issue
    access tokens that anyone could forge while looking perfectly healthy, so
    it refuses to boot instead. Outside production a key is generated and one
    warning line says so.

    A missing build output is different: it is an operational fault rather
    than an unsafe state, and refusing to boot would also take down the
    endpoints that could explain it. So each failure is held and reported by
    /health and by the endpoints that need that particular thing. The two are
    independent: a server can price perfectly well with no comparison table,
    and the only thing it cannot do is say what other mentors charge.
    """
    security.get_secret_key()

    try:
        app.state.pricing = load_pricing_service()
        app.state.pricing_error = None
    except AssetsUnavailableError as error:
        app.state.pricing = None
        app.state.pricing_error = str(error)
        logger.warning("pricing models unavailable: %s", error)

    try:
        app.state.comparables = comparables_module.load_comparables()
        app.state.comparables_error = None
    except comparables_module.ComparablesUnavailableError as error:
        app.state.comparables = None
        app.state.comparables_error = str(error)
        logger.warning("comparable mentors unavailable: %s", error)
    yield


app = FastAPI(
    title="Mentor Session Pricing",
    description=DESCRIPTION,
    version="1.0.0",
    openapi_tags=TAGS,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Browser access
# ---------------------------------------------------------------------------
# The mentor-facing web application is served from its own origin and talks to
# this API from the browser, so the browser needs to be told that this API
# accepts those requests. The list is configuration rather than a constant:
# development runs on a local port and a deployment will not.
ALLOWED_ORIGINS_VARIABLE = "ALLOWED_ORIGINS"

# The two addresses a local Next.js development server answers on. Both are
# listed because an origin is matched as a string and the two are different
# strings, so a developer who opens one of them should not have to discover
# that only the other works.
DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)

# Only the two the frontend sends. "*" would also work and is what most
# examples use, but naming them documents what the client is expected to
# send, and the authorization header is the one the frontend cannot do
# without: a preflight that leaves it out means every signed-in request is
# refused by the browser before this API sees it.
ALLOWED_REQUEST_HEADERS: tuple[str, ...] = ("Content-Type", security.AUTH_HEADER)


def allowed_origins(raw: str | None = None) -> list[str]:
    """
    The origins a browser may call this API from.

    Read from ``ALLOWED_ORIGINS`` as a comma-separated list, falling back to
    the local development server. An empty or blank setting falls back too,
    rather than allowing nothing: a variable set to an empty string is far
    more likely to be a deployment mistake than a decision to lock every
    browser out, and the failure it produces is a page of requests that are
    refused with no explanation in the response body.

    A trailing slash is stripped. An origin is a scheme, a host and a port and
    nothing else, and ``http://localhost:3000/`` never matches anything.
    """
    value = os.environ.get(ALLOWED_ORIGINS_VARIABLE) if raw is None else raw
    if value is None:
        return list(DEFAULT_ALLOWED_ORIGINS)
    origins = [part.strip().rstrip("/") for part in value.split(",")]
    origins = [origin for origin in origins if origin]
    return origins or list(DEFAULT_ALLOWED_ORIGINS)


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    # No cookies. The access token travels in a header the frontend sets
    # itself, so there are no credentials for a browser to attach on its own,
    # and a request the mentor did not make cannot carry their identity.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=list(ALLOWED_REQUEST_HEADERS),
    max_age=600,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    """
    Turn Pydantic's report into one the mentor can act on.

    FastAPI's default body nests a location tuple and a machine-readable error
    type. What the frontend needs is a field name it can attach a message to,
    and a sentence to show. The messages themselves come from the validators
    in src.mentor.mapping, so they are already written for a mentor.
    """
    errors = []
    for detail in error.errors():
        location = [str(part) for part in detail.get("loc", ()) if part != "body"]
        message = str(detail.get("msg", "")).removeprefix("Value error, ")
        if detail.get("type") == "missing":
            message = "This answer is required."
        elif detail.get("type") == "extra_forbidden":
            message = "This is not a field the registration form sends."
        errors.append({"field": ".".join(location), "message": message})

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Some of the answers need changing before a price can be "
            "worked out.",
            "errors": errors,
        },
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, error: HTTPException) -> JSONResponse:
    """Give every error the same body shape, so one client path handles all."""
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": str(error.detail), "errors": []},
        headers=getattr(error, "headers", None),
    )


@app.exception_handler(mapping.MentorInputError)
async def mentor_input_error_handler(
    request: Request, error: mapping.MentorInputError
) -> JSONResponse:
    """
    A mapping rule rejected an answer outside the Pydantic pass.

    Reachable when a value is read back from the database and no longer
    satisfies the current rules, which is what happens after an option list
    changes under rows that were written before it.
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": error.message,
            "errors": [{"field": error.field, "message": error.message}],
        },
    )


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
def get_pricing(request: Request) -> PricingService:
    """
    The loaded models, or 503 explaining that they were never prepared.

    A dependency rather than a module-level lookup so a test can supply a
    service without touching the filesystem.
    """
    pricing = getattr(request.app.state, "pricing", None)
    if pricing is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ASSETS_MISSING_MESSAGE,
        )
    return pricing


def optional_comparables(
    request: Request,
) -> comparables_module.ComparablesTable | None:
    """
    The comparison table if this server has one, or None.

    For the dashboard, which has plenty to report without it and should not
    fail entirely because one block of it would be empty.
    """
    return getattr(request.app.state, "comparables", None)


def get_comparables(request: Request) -> comparables_module.ComparablesTable:
    """
    The comparison table, or 503 explaining what was never prepared.

    Separate from :func:`get_pricing` because the two are independent: a
    server with models and no comparison table can still price every service,
    and should say exactly which of the two is missing.
    """
    table = optional_comparables(request)
    if table is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=comparables_module.COMPARABLES_MISSING_MESSAGE,
        )
    return table


def owned_service(session: Session, service_id: int, mentor_id: int) -> Service:
    """
    One of this mentor's services, or 404.

    The ownership test is in the ``where`` clause rather than an ``if`` after
    the fetch. That is the point: a query that cannot return another mentor's
    row cannot be followed by a forgotten check.
    """
    service = session.scalar(
        select(Service).where(Service.id == service_id, Service.mentor_id == mentor_id)
    )
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_MESSAGE
        )
    return service


def owned_recommendation(
    session: Session, recommendation_id: int, mentor_id: int
) -> PricingRecommendation:
    """One of this mentor's recommendations, or 404. Scoped through its service."""
    recommendation = session.scalar(
        select(PricingRecommendation)
        .join(Service, Service.id == PricingRecommendation.service_id)
        .where(
            PricingRecommendation.id == recommendation_id,
            Service.mentor_id == mentor_id,
        )
    )
    if recommendation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_MESSAGE
        )
    return recommendation


def comparables_for(
    table: comparables_module.ComparablesTable, service: Service, mentor: Mentor
) -> comparables_module.ComparableSet:
    """
    The mentors one service is compared against.

    The mentor's own source record is excluded. Only a seeded demonstration
    mentor has one, and for them it matters: they were built from a row of the
    same population, so a comparison that included it would place them against
    themselves and report their own price as exactly typical.
    """
    return table.match(
        field=service.field,
        max_mentees=service.max_mentees,
        exclude_key=mentor.source_key,
    )


def final_price_of(decision: PricingDecision | None) -> int | None:
    """
    The price a decision settled on, as whole currency units.

    The column is Numeric for a reason that predates this part of the system,
    so what comes back is a Decimal and has to be narrowed. Everything written
    through the API is already whole: see mapping.validate_final_price.
    """
    if decision is None or decision.final_price is None:
        return None
    return int(round(float(decision.final_price)))


def as_decision(decision: PricingDecision) -> DecisionOut:
    """One stored decision, in the response shape."""
    return DecisionOut(
        id=decision.id,
        recommendation_id=decision.recommendation_id,
        action=decision.action,
        final_price=final_price_of(decision),
        currency=mapping.CURRENCY,
        decided_at=decision.decided_at,
    )


def count_decisions(records: list[PricingRecommendation]) -> DecisionCountsOut:
    """
    How the mentor answered these recommendations, counted by action.

    A recommendation nobody has answered counts as pending rather than being
    left out, because the share of advice that was acted on at all is part of
    what these counts are for.
    """
    counts = {"accepted": 0, "modified": 0, "rejected": 0, "pending": 0}
    for record in records:
        decision = record.decision
        counts[decision.action if decision is not None else "pending"] += 1
    return DecisionCountsOut(**counts)


def average_difference_percent(
    records: list[PricingRecommendation],
) -> float | None:
    """
    How far the prices the mentor settled on sat from the prices advised.

    Averaged over the decisions that named a price, as a percentage of the
    advice in each case rather than of the total: a 10 per cent change on a
    150 session and a 10 per cent change on a 900 one are the same decision
    about the advice, and averaging the amounts would let the larger session
    speak for both.

    Null rather than zero when the mentor has settled on no prices yet. Zero
    is a real answer here, and it means they have taken the advice exactly.
    """
    differences = [
        (final - record.recommended_price) / record.recommended_price * 100
        for record in records
        if (final := final_price_of(record.decision)) is not None
    ]
    if not differences:
        return None
    # One decimal place, the same precision difference_vs_current_percent
    # reports a single comparison at, and for the same reason: the prices
    # either side are whole units and the model behind them has an RMSE in
    # the hundreds.
    return round(sum(differences) / len(differences), 1)


def complete_history(session: Session, mentor_id: int) -> dict[str, Any] | None:
    """
    The mentor's track record as model columns, or None if it is not usable.

    The full model has no notion of a missing input, so a partial record is no
    better than none: an incomplete row means the core model is used and the
    price is marked low confidence. A mentor who has never taken a session has
    no row at all, which is the same answer.

    The translated row carries the tenure column as well as the twenty-eight
    track-record ones, so merging it over a core row is what replaces the
    new-mentor tenure constant with the mentor's own time on the platform.
    """
    record = session.get(MentorHistory, mentor_id)
    if record is None or not record.is_complete:
        return None
    return mapping.history_to_model_inputs(record.stored_values())


def as_history_summary(record: MentorHistory) -> HistorySummaryOut:
    """
    One track record as the figures a mentor is shown on their own page.

    ``complete`` comes first because it is the one that explains the rest of
    the response: a record that is not complete is why a price is still
    marked low confidence.
    """
    summary = {
        name: getattr(record, name)
        for name in HistorySummaryOut.model_fields
        if name not in ("complete",)
    }
    return HistorySummaryOut(complete=record.is_complete, **summary)


def as_mentor(mentor: Mentor) -> MentorOut:
    """
    A mentor's record, with their services and a summary of their history.

    Built here rather than validated straight off the ORM object, because the
    history on the response is a summary in mentor language and the row behind
    it holds twenty-nine quantities that exist for a model to read.
    """
    return MentorOut(
        id=mentor.id,
        full_name=mentor.full_name,
        email=mentor.email,
        headline=mentor.headline,
        bio=mentor.bio,
        education_level=mentor.education_level,
        experience_summary=mentor.experience_summary,
        credentials=mentor.credentials,
        years_experience=mentor.years_experience,
        years_mentoring_band=mentor.years_mentoring_band,
        verified=bool(mentor.verified),
        is_demo=bool(mentor.is_demo),
        services=[ServiceOut.model_validate(service) for service in mentor.services],
        history=(
            as_history_summary(mentor.history) if mentor.history is not None else None
        ),
        created_at=mentor.created_at,
    )


def recommend_for_service(
    session: Session, pricing: PricingService, service: Service, mentor: Mentor
) -> PricingRecommendation:
    """
    Price one service and store the advice.

    The stored snapshot is the model's input rather than the mentor's answers,
    because that is what has to be read back to explain a price: the answers
    can be edited afterwards, and the row would then describe a price that was
    never given.
    """
    services_count = int(
        session.scalar(
            select(func.count())
            .select_from(Service)
            .where(Service.mentor_id == mentor.id)
        )
        or 0
    )

    # The mentor's years of experience are not passed in: they are profile
    # text, and the mapping layer has no parameter for them. See the note at
    # the top of that module.
    service_inputs = mapping.to_model_inputs(
        field=service.field,
        max_mentees=service.max_mentees,
        min_commitment=service.min_commitment,
        skills=list(service.skills or []),
        profile_verified=bool(service.profile_verified),
        services_count=services_count,
    )
    history = complete_history(session, mentor.id)
    advice = pricing.predict(service_inputs, history)

    record = PricingRecommendation(
        service_id=service.id,
        model_used=advice.model_used,
        recommended_price=advice.recommended_price,
        price_low=advice.price_low,
        price_high=advice.price_high,
        low_confidence=advice.low_confidence,
        inputs_snapshot={**service_inputs, **(history or {})},
        model_version=advice.model_version,
        status="pending",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def as_recommendation(
    record: PricingRecommendation,
    current_price: int | None = None,
    *,
    with_decision: bool = False,
) -> RecommendationOut:
    """
    One stored recommendation, in the response shape.

    The per-mentee figures are divided out of the stored session prices
    rather than stored themselves. The group size they are divided by comes
    from the row's own input snapshot, not from the service as it stands now:
    a mentor who changes the number of seats afterwards must not change what
    an old price says each mentee was paying. The size of session the price
    was for, and what that size is called, are read from the same snapshot for
    the same reason.

    ``current_price`` is read from the service as it stands now, and that is
    the right way round: the comparison answers "what should I charge instead
    of what I charge today", so it has to be against today's price rather than
    against whatever was set when the advice was given.

    ``with_decision`` includes the mentor's answer on the price itself. Off by
    default, because the responses that list prices report the decision beside
    each one, and reporting it in both places would put the same row in a
    response twice.
    """
    mentees = mapping.max_mentees_from_inputs(record.inputs_snapshot)
    comparison: dict[str, Any] = {}
    if current_price is not None and current_price > 0:
        comparison = {
            "current_price": int(current_price),
            "difference_vs_current_percent": difference_vs_current_percent(
                record.recommended_price, int(current_price)
            ),
            "position_vs_range": position_vs_range(
                int(current_price), record.price_low, record.price_high
            ),
        }
    return RecommendationOut(
        id=record.id,
        service_id=record.service_id,
        recommended_price=record.recommended_price,
        price_low=record.price_low,
        price_high=record.price_high,
        price_per_mentee=per_mentee(record.recommended_price, mentees),
        price_per_mentee_low=per_mentee(record.price_low, mentees),
        price_per_mentee_high=per_mentee(record.price_high, mentees),
        currency=mapping.CURRENCY,
        max_mentees=mentees,
        session_label=mapping.session_label(mentees),
        model_used=record.model_used,
        low_confidence=record.low_confidence,
        model_version=record.model_version,
        status=record.status,
        generated_at=record.generated_at,
        decision=(
            as_decision(record.decision)
            if with_decision and record.decision is not None
            else None
        ),
        **comparison,
    )


# ---------------------------------------------------------------------------
# Service endpoints
# ---------------------------------------------------------------------------
@app.get(
    "/health",
    tags=["service"],
    response_model=HealthOut,
    summary="Liveness, and whether a price can be produced",
)
async def health(request: Request) -> HealthOut:
    """
    Always 200 while the application is answering.

    ``models_loaded`` is the field that says whether it can price anything.
    """
    pricing = getattr(request.app.state, "pricing", None)
    table = optional_comparables(request)
    if pricing is None:
        return HealthOut(
            status="ok",
            models_loaded=False,
            comparables_loaded=table is not None,
            model_version=None,
            trained_at=None,
            detail=ASSETS_MISSING_MESSAGE,
        )
    return HealthOut(
        status="ok",
        models_loaded=True,
        comparables_loaded=table is not None,
        model_version=pricing.model_version,
        trained_at=pricing.trained_at,
        detail=(
            None
            if table is not None
            else comparables_module.COMPARABLES_MISSING_MESSAGE
        ),
    )


@app.get(
    "/meta/options",
    tags=["service"],
    response_model=OptionsOut,
    summary="Every option list the registration form needs",
)
async def options() -> OptionsOut:
    """
    The ids and labels for every choice on the form.

    The frontend renders from this rather than from its own copies, so the
    options a mentor sees and the values the API accepts are the same list.
    """
    return OptionsOut(**mapping.get_form_options())


# ---------------------------------------------------------------------------
# Mentors
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# The public directory
#
# The one part of this API that answers anybody at all, which is why what it
# returns was chosen field by field rather than trimmed from a mentor's
# record. See MentorCardOut.
# ---------------------------------------------------------------------------
def review_count_of(mentor: Mentor) -> int:
    """
    How many reviews a mentor has, or zero.

    Zero rather than null for a mentor with no record yet, because the
    directory shows it as a count and "no reviews yet" and "zero reviews" are
    the same thing to someone reading a card.
    """
    record = mentor.history
    if record is None or record.reviews_total is None:
        return 0
    return int(record.reviews_total)


def average_rating_of(mentor: Mentor) -> float | None:
    """
    What mentees rate this mentor overall, out of five, or null.

    Null rather than zero, and the opposite choice to the review count above,
    because the two numbers read differently. "No reviews yet" and "zero
    reviews" say the same thing; a rating of zero says the mentor was rated
    and rated badly, which is not what an absent rating means. A frontend
    shows nothing at all in that case.

    One decimal place, because that is the precision the figure deserves: a
    rating carried to several decimals invites a mentor to read a difference
    that no mentee intended. Anything outside the scale is dropped rather
    than clamped, since a value off the scale means the record is wrong
    rather than extreme.

    One figure, never a series. The platform records a mentor's rating as it
    stands now, so a rating drawn month by month would be invented.
    """
    record = mentor.history
    if record is None or record.rating_overall is None:
        return None
    value = float(record.rating_overall)
    if not 0.0 <= value <= 5.0:
        return None
    return round(value, 1)


def mentor_card(mentor: Mentor, service: Service) -> dict[str, Any]:
    """
    One mentor and their main service, as the directory shows them.

    Assembled here rather than validated off the ORM objects, because every
    field is either renamed, derived or deliberately left out, and a response
    model built from the row would mean a new private column appearing in a
    public response by default.
    """
    return {
        "id": mentor.id,
        "display_name": mentor.full_name,
        "field_label": mapping.field_label(service.field),
        "service_name": mapping.service_name(service.field, service.max_mentees),
        "price": service.current_price,
        "max_mentees": service.max_mentees,
        "session_label": service.session_label,
        "verified": bool(mentor.verified),
        "review_count": review_count_of(mentor),
        "average_rating": average_rating_of(mentor),
    }


def main_service_of(session: Session, mentor_id: int) -> Service | None:
    """
    The service a mentor's card is about: the first one they published.

    The first rather than the cheapest or the newest, because it is the one
    they described at registration and the one they are most likely to think
    of as what they do.
    """
    return session.scalar(
        select(Service)
        .where(Service.mentor_id == mentor_id)
        .order_by(Service.id)
        .limit(1)
    )


def directory_query(field: str | None, group: str | None):
    """
    The mentors the directory lists, each with their main service.

    One row per mentor, joined to the lowest service id they own, so a mentor
    with four services appears once rather than four times. A mentor with no
    service at all does not appear: there would be nothing on their card to
    show and no price to compare, and the only way to have none is to have
    deleted one, since registration creates one.

    Newest first. A directory ordered by id would bury every mentor who joins
    later, and the point of this list is that a mentor who registered a minute
    ago is in it on the same terms as a seeded one.
    """
    main = (
        select(Service.mentor_id, func.min(Service.id).label("service_id"))
        .group_by(Service.mentor_id)
        .subquery()
    )
    query = (
        select(Mentor, Service)
        .join(main, main.c.mentor_id == Mentor.id)
        .join(Service, Service.id == main.c.service_id)
    )
    if field is not None:
        query = query.where(Service.field == mapping.validate_field(field))
    if group is not None:
        query = query.where(Service.session_label == validate_group(group))
    return query.order_by(Mentor.created_at.desc(), Mentor.id.desc())


def validate_group(value: Any) -> str:
    """Which of the two sizes of session a directory filter asked for."""
    if value not in mapping.SESSION_LABELS:
        allowed = ", ".join(mapping.SESSION_LABELS)
        raise mapping.MentorInputError(
            "group", f"Mentors can be filtered by session type: {allowed}."
        )
    return str(value)


@app.get(
    "/mentors",
    tags=["directory"],
    response_model=MentorDirectoryOut,
    responses={422: ERROR_RESPONSE},
    summary="The public list of mentors",
)
async def read_directory(
    field: str | None = Query(
        default=None,
        description="Only mentors in this field, from /meta/options.",
        examples=["technology_software"],
    ),
    group: str | None = Query(
        default=None,
        description=(
            'Only one-to-one sessions ("one_to_one") or only group sessions '
            '("group").'
        ),
        examples=["one_to_one"],
    ),
    limit: int = Query(default=DIRECTORY_DEFAULT_LIMIT, ge=1, le=DIRECTORY_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> MentorDirectoryOut:
    """
    Every mentor on the platform, newest first, as cards.

    No token: this is the list a mentee reads before they have an account,
    and the one a mentor sees their own profile appear on. A mentor who
    registered a minute ago is listed on exactly the same terms as a seeded
    demonstration mentor, with their verification shown as what it is, which
    is false until somebody has checked them.

    ``total`` counts every mentor the filters match rather than the ones on
    this page, so a frontend can say how many there are without asking for all
    of them.
    """
    query = directory_query(field, group)
    total = int(session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = session.execute(query.limit(limit).offset(offset)).all()
    return MentorDirectoryOut(
        total=total,
        limit=limit,
        offset=offset,
        items=[
            MentorCardOut(**mentor_card(mentor, service)) for mentor, service in rows
        ],
    )


@app.get(
    "/mentors/{mentor_id}/public",
    tags=["directory"],
    response_model=PublicMentorOut,
    responses={404: ERROR_RESPONSE},
    summary="One mentor's public profile",
)
async def read_public_profile(
    mentor_id: int, session: Session = Depends(get_session)
) -> PublicMentorOut:
    """
    The card a mentee clicked on, with what the mentor chose to say.

    The same fields as the directory plus the skills they offer and the three
    optional profile fields, each null where the mentor left it blank. Nothing
    private: no address, no verification of anyone else's, and none of the
    figures a model reads.

    A mentor with no service is reported as missing rather than as a profile
    with nothing in it, which is the same answer the directory gives by
    leaving them out.
    """
    mentor = session.get(Mentor, mentor_id)
    service = main_service_of(session, mentor_id) if mentor is not None else None
    if mentor is None or service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_MESSAGE
        )
    return PublicMentorOut(
        **mentor_card(mentor, service),
        skills=[
            SkillOut(id=skill, label=mapping.SKILLS[skill])
            for skill in (service.skills or [])
            if skill in mapping.SKILLS
        ],
        years_experience=mentor.years_experience,
        years_mentoring_band=mentor.years_mentoring_band,
        education_level=mentor.education_level,
        education_label=(
            mapping.EDUCATION_LEVELS.get(mentor.education_level)
            if mentor.education_level
            else None
        ),
        credentials=mentor.credentials,
    )


# ---------------------------------------------------------------------------
# The live preview
# ---------------------------------------------------------------------------
@app.post(
    "/preview",
    tags=["pricing"],
    response_model=PreviewOut,
    responses={422: ERROR_RESPONSE, 429: ERROR_RESPONSE, 503: ERROR_RESPONSE},
    summary="Price a part-filled registration form, without storing anything",
)
async def preview_price(
    payload: PreviewInput,
    request: Request,
    pricing: PricingService = Depends(get_pricing),
) -> PreviewOut:
    """
    What the form will say, while it is still being filled in.

    The same three answers, the same validation and the same model as
    registration, so the number a mentor watches while they type is the number
    they are given when they submit. The two other answers registration needs
    are the ones it does not ask: a new account is unverified, and a mentor
    being priced has one service.

    **Nothing is written.** There is no mentor to write it against, and a
    preview is not advice anybody has been offered: the record of what the
    system advised and what the mentor did about it starts at registration.

    Rate limited per address, because this is the one endpoint with no account
    behind it and every call scores a model. See src.mentor.rate_limit for
    exactly how little that limit claims to be.
    """
    caller = request.client.host if request.client else "unknown"
    if not preview_limiter.allow(caller):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=PREVIEW_RATE_LIMIT_MESSAGE,
            headers={"Retry-After": str(preview_limiter.retry_after(caller))},
        )

    advice = pricing.predict(
        mapping.to_model_inputs(
            field=payload.field,
            max_mentees=payload.max_mentees,
            min_commitment=mapping.MIN_COMMITMENT_DEFAULT,
            skills=list(payload.skills),
            profile_verified=False,
            services_count=1,
        )
    )
    return PreviewOut(
        session_price=advice.recommended_price,
        per_person_price=advice.price_per_mentee,
        range_low=advice.price_low,
        range_high=advice.price_high,
        low_confidence=advice.low_confidence,
    )


def issued_token(mentor_id: int) -> dict[str, Any]:
    """The token fields of a response, built in one place for both endpoints."""
    return {
        "access_token": security.create_access_token(mentor_id),
        "token_type": security.TOKEN_TYPE,
        "expires_in": security.token_lifetime_seconds(),
    }


def mentor_by_email(session: Session, email: str) -> Mentor | None:
    """
    The account registered to one address, matched without case.

    Addresses are lowercased before they are stored, so the comparison is
    already like for like. It is lowercased on both sides anyway, because a
    row written by something other than this application is the case the
    unique index on the lowercased column exists for, and a sign-in that
    could not find such a row would be a confusing way to discover it.
    """
    return session.scalar(
        select(Mentor).where(
            func.lower(Mentor.email) == security.normalise_email(email)
        )
    )


def signed_in_mentor(
    session: Session = Depends(get_session),
    current_mentor_id: int = Depends(get_current_mentor_id),
) -> Mentor:
    """
    The mentor the token belongs to, or 401.

    A token that is perfectly valid but names a mentor who no longer exists is
    not a request for a missing record: it is an identity that cannot be
    established, which is what 401 means. That is the one case where a signed
    request answers 401 rather than 404.
    """
    mentor = session.get(Mentor, current_mentor_id)
    if mentor is None:
        raise unauthorized()
    return mentor


@app.post(
    "/auth/register",
    tags=["auth"],
    response_model=RegistrationOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: ERROR_RESPONSE, 422: ERROR_RESPONSE, 503: ERROR_RESPONSE},
    summary="Register a mentor, their first service, and price it",
)
async def register_mentor(
    payload: MentorRegistration,
    session: Session = Depends(get_session),
    pricing: PricingService = Depends(get_pricing),
) -> RegistrationOut:
    """
    Register, sign in and return the first price in one call.

    One call rather than four because a mentor who has just filled in the form
    is waiting for the number: asking the frontend to chain the account, the
    profile, the service and the price would show them an empty service
    first, and would leave a mentor whose connection dropped halfway with an
    account and nothing in it.

    No token on this request: this is the request that creates the identity,
    and the response carries the token for every request after it.

    The account starts unverified. Verification is a statement the platform
    makes about a mentor after a person has looked, so nothing a mentor sends
    can set it, including on this endpoint.
    """
    mentor = Mentor(
        full_name=payload.name,
        email=payload.email,
        password_hash=security.hash_password(payload.password),
        verified=False,
        headline=payload.headline,
        bio=payload.bio,
        education_level=payload.education_level,
        experience_summary=payload.experience_summary,
        credentials=payload.credentials,
        years_experience=payload.years_experience,
        years_mentoring_band=(
            mapping.years_mentoring_band_for_experience(payload.years_experience)
            if payload.years_experience is not None
            else None
        ),
    )
    service = Service(
        session_label=mapping.session_label(payload.max_mentees),
        field=payload.field,
        max_mentees=payload.max_mentees,
        min_commitment=payload.min_commitment,
        skills=list(payload.skills),
        # Follows the account rather than the form. A new mentor is
        # unverified, and this column is what the model is given for it.
        profile_verified=False,
    )
    mentor.services.append(service)
    session.add(mentor)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=EMAIL_TAKEN_MESSAGE
        ) from None
    session.refresh(mentor)
    session.refresh(service)

    record = recommend_for_service(session, pricing, service, mentor)
    return RegistrationOut(
        **issued_token(mentor.id),
        mentor=as_mentor(mentor),
        service=ServiceOut.model_validate(service),
        recommendation=as_recommendation(record, service.current_price),
    )


@app.post(
    "/auth/login",
    tags=["auth"],
    response_model=LoginOut,
    responses={401: ERROR_RESPONSE, 422: ERROR_RESPONSE},
    summary="Sign in with an email address and a password",
)
async def login(
    payload: MentorLogin,
    session: Session = Depends(get_session),
) -> LoginOut:
    """
    Exchange a password for an access token.

    An address nobody has registered and a wrong password give the same
    answer, and take about the same time to give it: the unknown case is
    verified against a hash no password matches rather than returning
    immediately. Either answer would otherwise tell a caller which addresses
    have accounts on the platform, which is a question they did not ask and
    are not entitled to.
    """
    mentor = mentor_by_email(session, payload.email)
    password_hash = mentor.password_hash if mentor is not None else None
    if not security.verify_password(payload.password, password_hash):
        raise unauthorized(SIGN_IN_FAILED_MESSAGE)
    return LoginOut(**issued_token(mentor.id), mentor=as_mentor(mentor))


@app.get(
    "/auth/me",
    tags=["auth"],
    response_model=MentorOut,
    responses={401: ERROR_RESPONSE},
    summary="The mentor the current token belongs to",
)
async def read_me(mentor: Mentor = Depends(signed_in_mentor)) -> MentorOut:
    """
    Who the caller is, according to the token they sent.

    What the frontend calls on a page load to decide whether it is signed in,
    and the endpoint that says a token has expired.

    **There is no sign-out endpoint.** The token is signed rather than stored,
    so the server holds no session to end: signing out is the client
    discarding the token, after which no request carries an identity at all. A
    token that has already been issued stays valid until it expires, which is
    why it expires in seven days.
    """
    return as_mentor(mentor)


@app.patch(
    "/mentors/me",
    tags=["mentors"],
    response_model=MentorOut,
    responses={401: ERROR_RESPONSE, 422: ERROR_RESPONSE},
    summary="Edit the mentor's own name and optional profile fields",
)
async def update_me(
    payload: MentorUpdate,
    session: Session = Depends(get_session),
    mentor: Mentor = Depends(signed_in_mentor),
) -> MentorOut:
    """
    Change the mentor's name, years of experience, education or credentials.

    Those four and nothing else. The address they sign in with, their
    verification and everything about a service are each settled somewhere
    with a reason of its own, and a general-purpose profile edit that could
    reach them would make those reasons unenforceable.

    A field that was not sent is left alone. A field sent as null is cleared,
    which is how a mentor removes something they would rather not show. The
    experience band shown on their profile follows the number of years, so
    clearing the years clears the band with it rather than leaving a band
    behind that no longer describes anything.

    None of these fields reaches a model, so a price never changes because of
    an edit here.
    """
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        if changes["name"] is None:
            raise mapping.MentorInputError(
                "name", "Enter the name to show on your profile."
            )
        mentor.full_name = changes["name"]
    if "years_experience" in changes:
        years = changes["years_experience"]
        mentor.years_experience = years
        mentor.years_mentoring_band = (
            mapping.years_mentoring_band_for_experience(years)
            if years is not None
            else None
        )
    if "education_level" in changes:
        mentor.education_level = changes["education_level"]
    if "credentials" in changes:
        mentor.credentials = changes["credentials"]

    session.commit()
    session.refresh(mentor)
    return as_mentor(mentor)


# Declared before /mentors/{mentor_id}, because routes are matched in the
# order they are added and "demo" would otherwise be read as a mentor id.
@app.get(
    "/mentors/demo",
    tags=["demo"],
    response_model=list[DemoMentorOut],
    summary="The mentors seeded for the demonstration",
)
async def read_demo_mentors(
    session: Session = Depends(get_session),
) -> list[DemoMentorOut]:
    """
    Every mentor created by ``scripts/seed_demo_mentors.py``.

    No identity header: this is the list someone picks an identity *from*, so
    requiring one would be circular. It carries nothing a mentee could not
    already read on a mentor's public profile.

    The mentors are fictional and so is everything about them except the shape
    of the record, which comes from the dataset the models were trained on.
    """
    mentors = session.scalars(
        select(Mentor).where(Mentor.is_demo.is_(True)).order_by(Mentor.id)
    ).all()

    listed = []
    for mentor in mentors:
        service = mentor.services[0] if mentor.services else None
        listed.append(
            DemoMentorOut(
                id=mentor.id,
                display_name=mentor.full_name,
                headline=mentor.headline,
                field_label=(
                    mapping.field_label(service.field) if service is not None else ""
                ),
                session_label=(
                    mapping.SESSION_LABELS[service.session_label]
                    if service is not None
                    else ""
                ),
                has_history=(mentor.history is not None and mentor.history.is_complete),
            )
        )
    return listed


@app.get(
    "/mentors/{mentor_id}",
    tags=["mentors"],
    response_model=MentorOut,
    responses={401: ERROR_RESPONSE, 404: ERROR_RESPONSE},
    summary="A mentor's own record",
)
async def read_mentor(
    mentor_id: int,
    session: Session = Depends(get_session),
    current_mentor_id: int = Depends(get_current_mentor_id),
) -> MentorOut:
    """
    The mentor's own record, and only their own.

    Includes every service with what it currently charges, and, for a mentor
    who has one, a summary of their track record in mentor language.

    Asking for another mentor's id returns 404 rather than 403: 403 would
    confirm that the other mentor exists.
    """
    mentor = session.scalar(
        select(Mentor).where(Mentor.id == mentor_id, Mentor.id == current_mentor_id)
    )
    if mentor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_MESSAGE
        )
    return as_mentor(mentor)


@app.post(
    "/mentors/{mentor_id}/services",
    tags=["mentors"],
    response_model=ServiceCreatedOut,
    status_code=status.HTTP_201_CREATED,
    responses={401: ERROR_RESPONSE, 404: ERROR_RESPONSE, 503: ERROR_RESPONSE},
    summary="Add another service, and price it",
)
async def add_service(
    mentor_id: int,
    payload: ServiceInput,
    session: Session = Depends(get_session),
    current_mentor_id: int = Depends(get_current_mentor_id),
    pricing: PricingService = Depends(get_pricing),
) -> ServiceCreatedOut:
    """
    A second or later service for a mentor who already exists.

    The same questions, the same validation and the same mapping as the
    service asked for at registration: there is one description of a service
    in the system, not one for the first and another for the rest.

    Adding a service moves the service count the model is given, so the price
    this returns is not necessarily the price the same answers would have got
    as a first service. That is the intended behaviour rather than a quirk:
    see ``mapping.effective_services``.
    """
    mentor = session.scalar(
        select(Mentor).where(Mentor.id == mentor_id, Mentor.id == current_mentor_id)
    )
    if mentor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_MESSAGE
        )

    service = Service(
        mentor_id=mentor.id,
        session_label=mapping.session_label(payload.max_mentees),
        field=payload.field,
        max_mentees=payload.max_mentees,
        min_commitment=payload.min_commitment,
        skills=list(payload.skills),
        # From the account, not from the body. See ServiceInput.
        profile_verified=bool(mentor.verified),
    )
    session.add(service)
    session.commit()
    session.refresh(service)

    record = recommend_for_service(session, pricing, service, mentor)
    return ServiceCreatedOut(
        service=ServiceOut.model_validate(service),
        recommendation=as_recommendation(record, service.current_price),
    )


@app.get(
    "/services/{service_id}",
    tags=["mentors"],
    response_model=ServiceOut,
    responses={401: ERROR_RESPONSE, 404: ERROR_RESPONSE},
    summary="One of the mentor's own services",
)
async def read_service(
    service_id: int,
    session: Session = Depends(get_session),
    current_mentor_id: int = Depends(get_current_mentor_id),
) -> ServiceOut:
    """
    One service, with what it currently charges.

    The mentor's own record already lists every service they have, so this is
    for a page about one of them: a frontend that has a service id and would
    otherwise fetch the whole mentor to render a single service.
    """
    service = owned_service(session, service_id, current_mentor_id)
    return ServiceOut.model_validate(service)


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------
@app.post(
    "/services/{service_id}/recommendations",
    tags=["pricing"],
    response_model=RecommendationOut,
    status_code=status.HTTP_201_CREATED,
    responses={401: ERROR_RESPONSE, 404: ERROR_RESPONSE, 503: ERROR_RESPONSE},
    summary="Price one of the mentor's services again",
)
async def create_recommendation(
    service_id: int,
    session: Session = Depends(get_session),
    current_mentor_id: int = Depends(get_current_mentor_id),
    pricing: PricingService = Depends(get_pricing),
) -> RecommendationOut:
    """
    Produce a fresh price for a service the mentor already has.

    Each call stores a new row rather than replacing the last one. The history
    of what the system advised is the record of whether its advice was any
    good, so it is kept.
    """
    service = owned_service(session, service_id, current_mentor_id)
    mentor = session.get(Mentor, current_mentor_id)
    if mentor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_MESSAGE
        )
    record = recommend_for_service(session, pricing, service, mentor)
    return as_recommendation(record, service.current_price)


@app.get(
    "/recommendations/{recommendation_id}",
    tags=["pricing"],
    response_model=RecommendationOut,
    responses={401: ERROR_RESPONSE, 404: ERROR_RESPONSE},
    summary="Read back one advisory price",
)
async def read_recommendation(
    recommendation_id: int,
    session: Session = Depends(get_session),
    current_mentor_id: int = Depends(get_current_mentor_id),
) -> RecommendationOut:
    """
    One of the mentor's own recommendations, scoped through its service.

    Carries the mentor's decision when they have answered this price, so a
    frontend showing one price does not have to ask a second time to find out
    whether it still stands.
    """
    record = owned_recommendation(session, recommendation_id, current_mentor_id)
    return as_recommendation(record, record.service.current_price, with_decision=True)


# ---------------------------------------------------------------------------
# Comparable mentors
# ---------------------------------------------------------------------------
@app.get(
    "/services/{service_id}/comparables",
    tags=["comparables"],
    response_model=ComparablesOut,
    responses={401: ERROR_RESPONSE, 404: ERROR_RESPONSE, 503: ERROR_RESPONSE},
    summary="What mentors like this one charge",
)
async def read_comparables(
    service_id: int,
    sort: str = Query(
        default=comparables_module.SORT_PRICE,
        description="Sort the mentors by price or by rating.",
        examples=["price"],
    ),
    order: str = Query(
        default=comparables_module.ORDER_ASCENDING,
        description="Sort ascending or descending.",
        examples=["asc"],
    ),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    current_mentor_id: int = Depends(get_current_mentor_id),
    table: comparables_module.ComparablesTable = Depends(get_comparables),
) -> ComparablesOut:
    """
    The mentors this service is compared against, and what they charge.

    The same endpoint for a mentor who registered a minute ago and one who has
    been taking sessions for a year: the comparison is drawn from the field
    and the group size, which both of them have, and does not depend on either
    one having a track record.

    ``summary`` describes the whole match and ``histogram`` the whole spread,
    so paging through ``items`` never changes what the mentor is told about
    the market. The figures stay put while they scroll.
    """
    service = owned_service(session, service_id, current_mentor_id)
    mentor = session.get(Mentor, current_mentor_id)
    if mentor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_MESSAGE
        )

    found = comparables_for(table, service, mentor)
    ordered = comparables_module.sorted_items(found, sort, order)
    page = ordered.iloc[offset : offset + limit]

    return ComparablesOut(
        summary=ComparablesSummaryOut(**comparables_module.summarise(found)),
        histogram=PriceHistogramOut(**comparables_module.histogram(found)),
        distribution=PriceDistributionOut(**comparables_module.distribution(found)),
        items=[
            ComparableItemOut(**comparables_module.as_item(row))
            for _, row in page.iterrows()
        ],
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------
def settle_on_price(
    record: PricingRecommendation, payload: DecisionInput
) -> int | None:
    """
    The price a decision settles on, or None for a rejection that names none.

    The three actions are checked against the recommendation here rather than
    in the request schema, because two of the three rules need the advised
    price and the schema has never seen it. Each refusal names ``final_price``
    and says what to send instead, because that is the one answer the mentor
    can change.
    """
    advised = record.recommended_price
    price = payload.final_price

    if payload.action == "accepted":
        # Accepting means taking the advised price. A different number sent
        # alongside "accepted" is refused rather than stored, because the row
        # would then say the mentor accepted a price they never saw.
        if price is not None and price != advised:
            raise mapping.MentorInputError(
                "final_price",
                f"Accepting the advice means charging the advised "
                f"{advised:,} {mapping.CURRENCY}. To charge "
                f"{price:,} instead, send that as a modified price.",
            )
        return mapping.validate_final_price(advised)

    if payload.action == "modified":
        if price is None:
            raise mapping.MentorInputError(
                "final_price",
                "Say what you will charge instead of the advised price.",
            )
        if price == advised:
            raise mapping.MentorInputError(
                "final_price",
                f"That is the advised price. Accept the advice instead of "
                f"modifying it to the same {advised:,} {mapping.CURRENCY}.",
            )
        return price

    # Rejected. A mentor who declines the advice may say what they charge
    # instead, which is the most useful thing they could tell the system, or
    # may simply decline and say nothing.
    return price


@app.post(
    "/recommendations/{recommendation_id}/decision",
    tags=["decisions"],
    response_model=DecisionOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: ERROR_RESPONSE,
        404: ERROR_RESPONSE,
        409: ERROR_RESPONSE,
        422: ERROR_RESPONSE,
    },
    summary="Answer one advisory price",
)
async def decide(
    recommendation_id: int,
    payload: DecisionInput,
    session: Session = Depends(get_session),
    current_mentor_id: int = Depends(get_current_mentor_id),
) -> DecisionOut:
    """
    Record what the mentor decided, once.

    This is the endpoint the whole system is advisory for. Up to here nothing
    has set a price: the recommendation is stored "pending" and the service
    charges whatever it charged before. The mentor's answer is what moves it,
    and the answer is stored as its own row rather than written over the
    advice, so what the system suggested and what the mentor chose are both
    still readable afterwards.

    A second answer to the same recommendation returns 409. The mentor can ask
    for a fresh price whenever they like and answer that one instead; two
    answers to one question would leave no way to tell which stands.
    """
    record = owned_recommendation(session, recommendation_id, current_mentor_id)
    if record.decision is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=ALREADY_DECIDED_MESSAGE
        )

    final_price = settle_on_price(record, payload)
    decision = PricingDecision(
        recommendation_id=record.id,
        action=payload.action,
        final_price=final_price,
    )
    record.status = payload.action
    if final_price is not None:
        # Whatever the mentor settled on is what the service charges now,
        # including a price they named while rejecting the advice. The point
        # of asking is to know what they actually charge.
        record.service.current_price = final_price

    session.add(decision)
    try:
        session.commit()
    except IntegrityError:
        # The unique index caught a second answer that arrived between the
        # check above and this commit.
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=ALREADY_DECIDED_MESSAGE
        ) from None
    session.refresh(decision)
    return as_decision(decision)


@app.get(
    "/services/{service_id}/history",
    tags=["decisions"],
    response_model=ServiceHistoryOut,
    responses={401: ERROR_RESPONSE, 404: ERROR_RESPONSE},
    summary="Every price this service has been given, and what came of it",
)
async def read_service_history(
    service_id: int,
    session: Session = Depends(get_session),
    current_mentor_id: int = Depends(get_current_mentor_id),
) -> ServiceHistoryOut:
    """
    The record of what was advised and what the mentor did about it.

    Newest first, because the question a mentor opens this with is almost
    always "what was I last told". The older rows are the record of whether
    the advice has been worth taking, which is the only evidence the system
    will ever have about itself.

    No models needed: every figure here was stored when the price was given.
    """
    service = owned_service(session, service_id, current_mentor_id)
    records = sorted(
        service.recommendations, key=lambda record: record.id, reverse=True
    )
    return ServiceHistoryOut(
        service_id=service.id,
        count=len(records),
        items=[
            RecommendationHistoryOut(
                recommendation=as_recommendation(record, service.current_price),
                decision=(
                    as_decision(record.decision)
                    if record.decision is not None
                    else None
                ),
            )
            for record in records
        ],
    )


# ---------------------------------------------------------------------------
# A mentor's activity over time
# ---------------------------------------------------------------------------
NO_ACTIVITY_NOTE = (
    "There is nothing to show here yet. This is where your sessions and "
    "reviews will appear once you have been mentoring on the platform."
)

# How many months at each end are compared to say whether something is picking
# up. A quarter: one month against one month is a fluctuation rather than a
# direction, and half the period against the other half describes a year ago
# as though it were news.
TREND_MONTHS = 3


def direction_of(values: list[float]) -> str:
    """
    Whether a series ends higher than it started, in one word.

    The last few months against the first few, rather than the last value
    against the first: a mentor who had a quiet August has not had a bad year,
    and a sentence that said so would be wrong the following month.

    "about the same" is deliberately wide. These are small counts, and a
    sentence claiming a rise on the strength of one extra review would be a
    sentence about noise.
    """
    if len(values) < 2:
        return "about the same"
    window = min(TREND_MONTHS, len(values) // 2) or 1
    start = sum(values[:window]) / window
    end = sum(values[-window:]) / window
    if start == 0:
        return "more" if end > 0 else "about the same"
    change = (end - start) / start
    if change > 0.2:
        return "more"
    if change < -0.2:
        return "less"
    return "about the same"


def activity_note(rows: list[MentorActivity]) -> str:
    """
    One plain sentence about the period, from whatever it has in it.

    Written here rather than in a frontend, so the one statement the platform
    makes about a mentor's own figures is one statement. It describes the
    measure it actually has: the price when the platform has a price per
    month, and otherwise the reviews, which it always has. It never describes
    a measure that is missing, and it claims no direction from a single month.
    """
    if not rows:
        return NO_ACTIVITY_NOTE

    months = len(rows)
    prices = [float(row.price) for row in rows if row.price is not None]
    if len(prices) >= 2:
        moved = direction_of(prices)
        if moved == "about the same":
            return (
                f"Your price has stayed about the same over the last "
                f"{months} months."
            )
        word = "gone up" if moved == "more" else "come down"
        return f"Your price has {word} over the last {months} months."

    reviews = [float(row.reviews_count) for row in rows]
    total = int(sum(reviews))
    if total == 0:
        return (
            f"You have had no reviews in the last {months} months, so there "
            f"is nothing in this period to read a trend from."
        )
    moved = direction_of(reviews)
    if moved == "about the same":
        return (
            f"You have {total} reviews over the last {months} months, at "
            f"about a steady rate."
        )
    word = "picking up" if moved == "more" else "slowing down"
    return (
        f"You have {total} reviews over the last {months} months, and recent "
        f"months are {word}."
    )


@app.get(
    "/mentors/{mentor_id}/activity",
    tags=["mentors"],
    response_model=ActivityOut,
    responses={401: ERROR_RESPONSE, 404: ERROR_RESPONSE},
    summary="A mentor's own activity, month by month",
)
async def read_activity(
    mentor_id: int,
    session: Session = Depends(get_session),
    current_mentor_id: int = Depends(get_current_mentor_id),
) -> ActivityOut:
    """
    What the mentor has done, month by month, and one sentence about it.

    Their own and only their own: another mentor's activity returns 404, like
    every other mentor-scoped record. It is not on the public directory at
    all, because how busy somebody has been is theirs to share.

    A mentor with nothing recorded yet, which is every mentor who has just
    registered, gets ``has_history: false``, four empty lists and a sentence
    saying what will appear here. Not an error: having no history is the
    ordinary state of a new account rather than a missing record.

    Where a measurement does not exist for a month, the entry is null rather
    than zero. See ActivityOut: a zero would be a claim the platform cannot
    make, and the two are not the same thing to a mentor reading a chart.
    """
    mentor = session.scalar(
        select(Mentor).where(Mentor.id == mentor_id, Mentor.id == current_mentor_id)
    )
    if mentor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_MESSAGE
        )

    rows = list(
        session.scalars(
            select(MentorActivity)
            .where(MentorActivity.mentor_id == mentor.id)
            .order_by(MentorActivity.month)
        )
    )
    return ActivityOut(
        has_history=bool(rows),
        months=[row.month.isoformat() for row in rows],
        reviews_by_month=[int(row.reviews_count) for row in rows],
        booked_share_by_month=[
            float(row.booked_share) if row.booked_share is not None else None
            for row in rows
        ],
        price_by_month=[
            int(row.price) if row.price is not None else None for row in rows
        ],
        note=activity_note(rows),
    )


# ---------------------------------------------------------------------------
# The dashboard
# ---------------------------------------------------------------------------
def dashboard_service(
    service: Service,
    mentor: Mentor,
    table: comparables_module.ComparablesTable | None,
) -> DashboardServiceOut:
    """
    One service, with everything the mentor's own page says about it.

    The timeline runs oldest first, the opposite of the history endpoint, and
    for the opposite reason: this one is plotted against time, and a chart
    that starts at the right hand end reads backwards.
    """
    records = sorted(service.recommendations, key=lambda record: record.id)
    latest = records[-1] if records else None

    found = comparables_for(table, service, mentor) if table is not None else None
    percentile = (
        comparables_module.price_percentile(found, service.current_price)
        if found is not None
        else None
    )

    position = None
    if latest is not None and service.current_price:
        position = position_vs_range(
            int(service.current_price), latest.price_low, latest.price_high
        )

    return DashboardServiceOut(
        service_id=service.id,
        field_label=mapping.field_label(service.field),
        session_label=mapping.SESSION_LABELS[service.session_label],
        max_mentees=service.max_mentees,
        current_price=service.current_price,
        currency=mapping.CURRENCY,
        latest_recommendation=(
            as_recommendation(latest, service.current_price)
            if latest is not None
            else None
        ),
        position_vs_range=position,
        price_percentile=percentile,
        decision_counts=count_decisions(records),
        average_difference_percent=average_difference_percent(records),
        timeline=[
            TimelinePointOut(
                generated_at=record.generated_at,
                recommended_price=record.recommended_price,
                final_price=final_price_of(record.decision),
                action=record.decision.action if record.decision is not None else None,
            )
            for record in records
        ],
        comparables=(
            ComparablesSummaryOut(**comparables_module.summarise(found))
            if found is not None
            else None
        ),
    )


# ---------------------------------------------------------------------------
# The one sentence the dashboard opens with
#
# Written here, on the server, so that the single statement the platform makes
# about a mentor's price is one statement rather than one per frontend. Plain
# words, no percentages and no model terms: a mentor opening their page wants
# to know whether they are charging roughly what people like them charge, and
# every number behind the sentence is reported beside it for anyone who wants
# the figures.
# ---------------------------------------------------------------------------
NO_SERVICE_SENTENCE = "Add a service to see how your price compares with other mentors."

NO_COMPARISON_SENTENCE = (
    "There are not enough other mentors to compare your price with yet."
)

NO_PRICE_SENTENCE = "You have not set a price for this service yet."

TYPICAL_SENTENCE = "Other {phrase} charge about {price:,} {currency} for a session."

SAME_SENTENCE = "You charge about the same as other {phrase}."
LESS_SENTENCE = "You charge less than most other {phrase}."
MORE_SENTENCE = "You charge more than most other {phrase}."


def comparison_phrase(found: comparables_module.ComparableSet, service: Service) -> str:
    """
    Who the sentence is comparing the mentor with, in words.

    Three phrasings for the three levels the match can reach, because the
    sentence has to stay true: a comparison that had to widen to every field
    cannot be described as "in your field", and one that widened to every
    group size cannot be described as one-to-one or group.
    """
    session_word = (
        "one-to-one" if service.session_label == mapping.LABEL_ONE_TO_ONE else "group"
    )
    if found.match_level == comparables_module.MATCH_SAME_FIELD_AND_SIZE:
        return f"{session_word} mentors in your field"
    if found.match_level == comparables_module.MATCH_SAME_FIELD:
        return "mentors in your field"
    return f"{session_word} mentors on the platform"


def headline_of(
    mentor: Mentor,
    service: Service | None,
    table: comparables_module.ComparablesTable | None,
) -> DashboardHeadlineOut:
    """
    The mentor's price, a typical comparable price, and the sentence between.

    ``position_vs_range`` here is against the middle half of comparable
    mentors rather than against the advised range: the question this block
    answers is how the mentor compares with other people, and the quartiles
    are the range a typical one of them charges. The advised range is reported
    per service, on the recommendation itself, where it belongs.
    """
    if service is None:
        return DashboardHeadlineOut(sentence=NO_SERVICE_SENTENCE)

    found = comparables_for(table, service, mentor) if table is not None else None
    summary = comparables_module.summarise(found) if found is not None else None
    typical = summary["median_price"] if summary else None
    price = service.current_price

    if typical is None or found is None or found.count == 0:
        return DashboardHeadlineOut(
            your_price=price,
            sentence=(NO_PRICE_SENTENCE if not price else NO_COMPARISON_SENTENCE),
        )

    phrase = comparison_phrase(found, service)
    if not price:
        return DashboardHeadlineOut(
            similar_typical=typical,
            sentence=(
                f"{NO_PRICE_SENTENCE} "
                + TYPICAL_SENTENCE.format(
                    phrase=phrase, price=typical, currency=mapping.CURRENCY
                )
            ),
        )

    low = summary["p25_price"] or typical
    high = summary["p75_price"] or typical
    position = position_vs_range(int(price), int(low), int(high))
    sentence = {
        POSITION_BELOW: LESS_SENTENCE,
        POSITION_WITHIN: SAME_SENTENCE,
        POSITION_ABOVE: MORE_SENTENCE,
    }[position].format(phrase=phrase)

    return DashboardHeadlineOut(
        your_price=int(price),
        similar_typical=typical,
        position_vs_range=position,
        sentence=sentence,
    )


@app.get(
    "/mentors/{mentor_id}/dashboard",
    tags=["mentors"],
    response_model=DashboardOut,
    responses={401: ERROR_RESPONSE, 404: ERROR_RESPONSE},
    summary="A mentor's own page: advice, decisions and where they sit",
)
async def read_dashboard(
    mentor_id: int,
    session: Session = Depends(get_session),
    current_mentor_id: int = Depends(get_current_mentor_id),
    table: comparables_module.ComparablesTable | None = Depends(optional_comparables),
) -> DashboardOut:
    """
    Everything the mentor's own page shows, in one request.

    One request rather than several because the page is a page: a frontend
    chaining a call per service would render it in pieces, and the mentor
    would watch their own figures arrive one at a time.

    **No earnings and no income anywhere.** The system has no bookings, so it
    has no volume, and any total in currency would be a price multiplied by a
    number nobody measured. What it reports instead is what it knows: what the
    mentor charges, what was advised, how far their decisions have sat from
    the advice, and where their price falls among comparable mentors.

    ``headline`` is the one line the page opens with, about the mentor's main
    service: what they charge, what a typical comparable mentor charges, and
    one plain sentence saying which side of that they are on.

    A server with no comparison table still answers. ``comparables_available``
    says so, the fields that need it are null, and the headline sentence says
    there is nothing to compare with rather than claiming anything.
    """
    mentor = session.scalar(
        select(Mentor).where(Mentor.id == mentor_id, Mentor.id == current_mentor_id)
    )
    if mentor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_MESSAGE
        )

    services = [
        dashboard_service(service, mentor, table) for service in mentor.services
    ]
    every_record = [
        record for service in mentor.services for record in service.recommendations
    ]

    return DashboardOut(
        mentor_id=mentor.id,
        display_name=mentor.full_name,
        average_rating=average_rating_of(mentor),
        headline=headline_of(
            mentor, mentor.services[0] if mentor.services else None, table
        ),
        currency=mapping.CURRENCY,
        comparables_available=table is not None,
        totals=DashboardTotalsOut(
            services=len(mentor.services),
            services_with_a_price=sum(
                1 for service in mentor.services if service.current_price
            ),
            recommendations=len(every_record),
            decision_counts=count_decisions(every_record),
            average_difference_percent=average_difference_percent(every_record),
        ),
        services=services,
    )
