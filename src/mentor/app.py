"""
The mentor-facing pricing API.

Six endpoints, covering the path a mentor takes the first time: read the form
options, register with a first service, receive an advisory price, and read it
back. A mentor with a track record is priced by the full model instead; that
path exists in the prediction service and is reached once the track-record
table is filled.

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
    load_pricing_service,
    per_mentee,
)
from src.mentor.schemas import (
    ErrorOut,
    HealthOut,
    MentorOut,
    MentorRegistration,
    OptionsOut,
    RecommendationOut,
    RegistrationOut,
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
weaker basis than a track record. Once a mentor has a record of completed
sessions and reviews, the same endpoints price them with a second, more
accurate model and the flag goes away.

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
    price is marked low confidence. Part 2 fills this table; until then there
    are no rows and this always returns None.
    """
    record = session.get(MentorHistory, mentor_id)
    if record is None:
        return None
    values = {name: getattr(record, name, None) for name in mapping.HISTORY_FIELDS}
    if any(value is None for value in values.values()):
        return None
    return mapping.history_to_model_inputs(values)


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


def as_recommendation(record: PricingRecommendation) -> RecommendationOut:
    """
    One stored recommendation, in the response shape.

    The per-mentee figures are divided out of the stored session prices
    rather than stored themselves. The group size they are divided by comes
    from the row's own input snapshot, not from the service as it stands now:
    a mentor who changes the number of seats afterwards must not change what
    an old price says each mentee was paying.
    """
    mentees = mapping.max_mentees_from_inputs(record.inputs_snapshot)
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
        mentor=MentorOut.model_validate(mentor),
        service=ServiceOut.model_validate(service),
        recommendation=as_recommendation(record),
    )


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
    return MentorOut.model_validate(mentor)


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
    return as_recommendation(record)


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
    return as_recommendation(record)
