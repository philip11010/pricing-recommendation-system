"""
The mentor-facing pricing API.

Nine endpoints, covering two paths. A mentor registering for the first time
reads the form options, registers with a first service, receives an advisory
price and reads it back. A mentor who already has a track record is priced by
the full model on the same endpoints, and their advice is shown against what
they charge today.

The price is advice. Nothing here sets a mentor's price: a recommendation is
stored with status "pending" and stays that way until the mentor answers it,
which is the next part of the work.

Both models are loaded once, at startup. A server without prepared models
still answers ``/health`` and ``/meta/options``, and says plainly on those
endpoints that it cannot price anything, rather than failing on the first
mentor who tries to register.

Run locally with:

    uvicorn src.mentor.app:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db import get_session
from src.db.mentor_models import (
    Mentor,
    MentorHistory,
    PricingRecommendation,
    Service,
)
from src.mentor import mapping
from src.mentor.dependencies import get_current_mentor_id
from src.mentor.prediction import (
    ASSETS_MISSING_MESSAGE,
    AssetsUnavailableError,
    PricingService,
    difference_vs_current_percent,
    load_pricing_service,
    per_mentee,
    position_vs_range,
)
from src.mentor.schemas import (
    DemoMentorOut,
    ErrorOut,
    HealthOut,
    HistorySummaryOut,
    MentorOut,
    MentorRegistration,
    OptionsOut,
    RecommendationOut,
    RegistrationOut,
    ServiceCreatedOut,
    ServiceInput,
    ServiceOut,
)

logger = logging.getLogger(__name__)

# Returned whenever a mentor asks for something that is not theirs, as well as
# for something that does not exist. The two cases are deliberately
# indistinguishable: a different answer for "exists but not yours" would let a
# caller enumerate other mentors' rows.
NOT_FOUND_MESSAGE = "That record does not exist."

EMAIL_TAKEN_MESSAGE = (
    "An account already exists for that email address. Sign in instead, or "
    "register with a different address."
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

Identity is a placeholder: send the mentor's id in the `X-Mentor-Id` header.
There is no authentication yet. A mentor can only ever read their own records,
and a request for someone else's returns 404.
"""

TAGS: list[dict[str, Any]] = [
    {"name": "service", "description": "Liveness and form options."},
    {"name": "mentors", "description": "Registration and a mentor's own record."},
    {"name": "pricing", "description": "Advisory prices for a mentor's services."},
    {
        "name": "demo",
        "description": "Mentors seeded so there is something to demonstrate.",
    },
]

ERROR_RESPONSE = {"model": ErrorOut}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Load both models before the first request, or record why they are missing.

    A missing model is an operational fault rather than a normal state, but
    refusing to boot would also take down the endpoints that could explain it.
    So the failure is held and reported by /health and by any endpoint that
    needs a price.
    """
    try:
        app.state.pricing = load_pricing_service()
        app.state.pricing_error = None
    except AssetsUnavailableError as error:
        app.state.pricing = None
        app.state.pricing_error = str(error)
        logger.warning("pricing models unavailable: %s", error)
    yield


app = FastAPI(
    title="Mentor Session Pricing",
    description=DESCRIPTION,
    version="1.0.0",
    openapi_tags=TAGS,
    lifespan=lifespan,
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
        years_mentoring_band=mentor.years_mentoring_band,
        services_planned=mentor.services_planned,
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

    # The mentor's experience band is not passed in: it is profile text, and
    # the mapping layer has no parameter for it. See the note at the top of
    # that module.
    service_inputs = mapping.to_model_inputs(
        field=service.field,
        max_mentees=service.max_mentees,
        min_commitment=service.min_commitment,
        skills=list(service.skills or []),
        profile_verified=bool(service.profile_verified),
        services_planned=mentor.services_planned,
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
    record: PricingRecommendation, current_price: int | None = None
) -> RecommendationOut:
    """
    One stored recommendation, in the response shape.

    The per-mentee figures are divided out of the stored session prices
    rather than stored themselves. The group size they are divided by comes
    from the row's own input snapshot, not from the service as it stands now:
    a mentor who changes the number of seats afterwards must not change what
    an old price says each mentee was paying.

    ``current_price`` is read from the service as it stands now, and that is
    the right way round: the comparison answers "what should I charge instead
    of what I charge today", so it has to be against today's price rather than
    against whatever was set when the advice was given.
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
        model_used=record.model_used,
        low_confidence=record.low_confidence,
        model_version=record.model_version,
        status=record.status,
        generated_at=record.generated_at,
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
    if pricing is None:
        return HealthOut(
            status="ok",
            models_loaded=False,
            model_version=None,
            trained_at=None,
            detail=ASSETS_MISSING_MESSAGE,
        )
    return HealthOut(
        status="ok",
        models_loaded=True,
        model_version=pricing.model_version,
        trained_at=pricing.trained_at,
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
@app.post(
    "/mentors",
    tags=["mentors"],
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
    Register and return the first price in one call.

    One call rather than three because a mentor who has just filled in the
    form is waiting for the number: asking the frontend to chain three
    requests would show them an empty service first.

    No identity header: this is the request that creates the identity.
    """
    mentor = Mentor(
        full_name=payload.full_name,
        email=payload.email,
        headline=payload.headline,
        bio=payload.bio,
        education_level=payload.education_level,
        experience_summary=payload.experience_summary,
        credentials=payload.credentials,
        years_mentoring_band=payload.years_mentoring_band,
        services_planned=payload.services_planned,
    )
    service = Service(
        session_label=mapping.session_label(payload.service.max_mentees),
        field=payload.service.field,
        max_mentees=payload.service.max_mentees,
        min_commitment=payload.service.min_commitment,
        skills=list(payload.service.skills),
        profile_verified=payload.service.profile_verified,
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
        mentor=as_mentor(mentor),
        service=ServiceOut.model_validate(service),
        recommendation=as_recommendation(record, service.current_price),
    )


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
        profile_verified=payload.profile_verified,
    )
    session.add(service)
    session.commit()
    session.refresh(service)

    record = recommend_for_service(session, pricing, service, mentor)
    return ServiceCreatedOut(
        service=ServiceOut.model_validate(service),
        recommendation=as_recommendation(record, service.current_price),
    )


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
    """One of the mentor's own recommendations, scoped through its service."""
    record = owned_recommendation(session, recommendation_id, current_mentor_id)
    return as_recommendation(record, record.service.current_price)
