"""
FastAPI application: the serving layer for the mentor pricing dashboard.

Corresponds to the FastAPI Application component in Chapter 4. The model is
loaded once at startup rather than per request, because the artefact is a
fitted pipeline of a few megabytes and loading it on every call would dominate
the response time.

Model artefacts are gitignored, so a fresh clone has no model until
``python -m src.models.train`` has been run. That is a normal state: the
dashboard still renders and explains itself, ``/health`` reports
``model_loaded: false``, and the prediction endpoint answers 503 rather than
crashing.

Run locally with:
    uvicorn src.api.main:app --reload

Endpoints are declared ``async`` so the dynamic form can be read with
``await request.form()``: the field names come from the trained model, so they
cannot be declared as function parameters. The database work inside them is
synchronous, which is acceptable here because every query is a local SQLite
read or a single-row insert. A remote database would need a threadpool or an
async driver.
"""

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.api.schema import (
    DecisionRequest,
    build_request_model,
    clean_form_values,
    example_values,
    grouped_field_specs,
    readable_errors,
)
from src.db import Decision, Recommendation, get_session, init_db
from src.models.predict import (
    MODEL_UNAVAILABLE_MESSAGE,
    LoadedModel,
    predict_price,
    try_load_best_model,
)

API_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = API_DIR / "templates"
STATIC_DIR = API_DIR / "static"

HISTORY_LIMIT = 20

# Shown on every page. The proxy dataset is the single most important caveat
# about this prototype, so it is part of the layout rather than a footnote.
PROXY_BANNER = (
    "Prototype trained on Inside Airbnb Sydney listings as a structural proxy "
    "for mentor pricing. Output is a Sydney nightly price in USD, not a "
    "mentorship rate."
)

# Invalid form input re-renders the page with the errors shown, so the status
# is 400 rather than FastAPI's 422: the request body was read and understood,
# and the response is a page, not a validation document.
INVALID_INPUT_STATUS = 400


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Create the tables and load the model once, before serving any request.

    A missing artefact is recorded rather than raised, so the application
    boots and can explain the situation.
    """
    init_db()
    app.state.model = try_load_best_model()
    app.state.request_model = None
    app.state.request_model_for = None
    yield


app = FastAPI(title="Mentor Pricing Recommendation", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def get_model(request: Request) -> LoadedModel | None:
    """
    The pipeline loaded at startup, or None if there is no artefact.

    A dependency rather than a direct attribute read so a test can substitute
    a model, or the absence of one, without touching the filesystem.
    """
    return getattr(request.app.state, "model", None)


def get_request_model(
    request: Request, model: LoadedModel | None = Depends(get_model)
) -> type[BaseModel] | None:
    """
    The Pydantic model validating prediction input, built from ``model``.

    Cached on application state, keyed on the model object it was built from.
    Building it means running ``create_model`` over 25 fields, which is not
    worth repeating per request, but it must be rebuilt if the model itself is
    substituted, as a test does.
    """
    if model is None:
        return None
    cached = getattr(request.app.state, "request_model", None)
    if (
        cached is None
        or getattr(request.app.state, "request_model_for", None) is not model
    ):
        cached = build_request_model(model)
        request.app.state.request_model = cached
        request.app.state.request_model_for = model
    return cached


# ---------------------------------------------------------------------------
# Placeholder context
#
# Stands in for a real mentor record. The platform dataset has not been
# received, so the profile, performance and demand panels still show fixed
# values. There is deliberately no placeholder price: the only figure the
# dashboard shows is model output, in USD. Before a prediction exists the
# panel shows an empty state instead.
# ---------------------------------------------------------------------------
PLACEHOLDER_DASHBOARD: dict = {
    "profile": {
        "name": "Placeholder Mentor",
        "specialisation": "Data Science",
        "experience_years": 6,
        "education": "MSc Computer Science",
        "certifications": 2,
    },
    "performance": {
        "rating": 4.7,
        "reviews": 38,
        "completion_rate": 0.96,
        "repeat_booking_rate": 0.41,
    },
    "demand": {
        "profile_views_30d": 312,
        "booking_requests_30d": 17,
        "skill_demand_trend": "Rising",
    },
}


def page_context(
    request: Request, model: LoadedModel | None, **extra: Any
) -> dict[str, Any]:
    """Context shared by every page: the banner, the form fields, the model."""
    context: dict[str, Any] = {
        **PLACEHOLDER_DASHBOARD,
        "banner": PROXY_BANNER,
        "model_loaded": model is not None,
        "model_name": model.model_name if model else None,
        "trained_at": model.trained_at if model else None,
        "field_groups": grouped_field_specs(model) if model else [],
        "values": example_values(model) if model else {},
        "model_comparison": model.model_comparison if model else [],
        "errors": [],
        "prediction": None,
        "confirmation": None,
    }
    context.update(extra)
    return context


def model_unavailable(request: Request) -> HTMLResponse:
    """A 503 page explaining that no artefact has been trained yet."""
    return templates.TemplateResponse(
        request,
        "model_unavailable.html",
        page_context(request, None, message=MODEL_UNAVAILABLE_MESSAGE),
        status_code=503,
    )


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request, model: LoadedModel | None = Depends(get_model)
) -> HTMLResponse:
    """
    Render the dashboard and its input form.

    Returns 200 even without a model, so the page can say what is missing.
    Only the prediction endpoint refuses to answer.
    """
    return templates.TemplateResponse(
        request, "dashboard.html", page_context(request, model)
    )


@app.post("/recommend", response_class=HTMLResponse)
async def recommend(
    request: Request,
    model: LoadedModel | None = Depends(get_model),
    request_model: type[BaseModel] | None = Depends(get_request_model),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """
    Validate the submitted form, predict a price, store it and re-render.

    The stored row holds the validated input rather than the raw form, so what
    is recorded is exactly what the model was given.
    """
    if model is None or request_model is None:
        return model_unavailable(request)

    submitted = dict((await request.form()).items())

    try:
        validated = request_model(**clean_form_values(submitted))
    except ValidationError as error:
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            page_context(
                request, model, values=submitted, errors=readable_errors(error)
            ),
            status_code=INVALID_INPUT_STATUS,
        )

    values = validated.model_dump()
    try:
        price = predict_price(model, values)
    except ValueError as error:
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            page_context(
                request,
                model,
                values=submitted,
                errors=[{"field": "", "label": "Model", "message": str(error)}],
            ),
            status_code=INVALID_INPUT_STATUS,
        )

    record = Recommendation(
        input_json=json.dumps(values, sort_keys=True),
        model_name=model.model_name,
        predicted_price=price,
        data_source=model.data_source,
    )
    session.add(record)
    session.commit()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        page_context(
            request,
            model,
            values=values,
            prediction={
                "id": record.id,
                "price": price,
                "model_name": model.model_name,
                "data_source": model.data_source,
                # MAE, not RMSE: see LoadedModel.typical_error_dollars.
                "typical_error": model.typical_error_dollars,
            },
        ),
    )


@app.post("/decision", response_class=HTMLResponse)
async def decide(
    request: Request,
    model: LoadedModel | None = Depends(get_model),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """
    Record whether the mentor accepted, modified or rejected the price.

    "accept" stores the recommended price as the final one, so the row says
    what the mentor settled on without a join. "reject" stores no price: the
    mentor declined the advice and did not say what they charge instead.
    """
    submitted = dict((await request.form()).items())

    try:
        decision = DecisionRequest(**clean_form_values(submitted))
    except ValidationError as error:
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            page_context(
                request, model, values=submitted, errors=readable_errors(error)
            ),
            status_code=INVALID_INPUT_STATUS,
        )

    recommendation = session.get(Recommendation, decision.recommendation_id)
    if recommendation is None:
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            page_context(
                request,
                model,
                errors=[
                    {
                        "field": "recommendation_id",
                        "label": "Recommendation",
                        "message": (
                            f"No recommendation with id "
                            f"{decision.recommendation_id} exists."
                        ),
                    }
                ],
            ),
            status_code=INVALID_INPUT_STATUS,
        )

    final_price = decision.final_price
    if decision.decision == "accept":
        final_price = recommendation.predicted_price

    record = Decision(
        recommendation_id=recommendation.id,
        action=decision.decision,
        final_price=final_price,
    )
    session.add(record)
    session.commit()

    return templates.TemplateResponse(
        request,
        "confirmation.html",
        page_context(
            request,
            model,
            confirmation={
                "action": record.action,
                "final_price": record.final_price,
                "recommended_price": recommendation.predicted_price,
                "recommendation_id": recommendation.id,
            },
        ),
    )


@app.get("/history", response_class=HTMLResponse)
async def history(
    request: Request,
    model: LoadedModel | None = Depends(get_model),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """
    The most recent recommendations, newest first, with their decisions.

    Ordered by id as well as timestamp: two rows written in the same clock
    tick would otherwise come back in an arbitrary order.
    """
    statement = (
        select(Recommendation)
        .options(selectinload(Recommendation.decisions))
        .order_by(Recommendation.created_at.desc(), Recommendation.id.desc())
        .limit(HISTORY_LIMIT)
    )
    records = list(session.scalars(statement))

    return templates.TemplateResponse(
        request,
        "history.html",
        page_context(request, model, records=records, limit=HISTORY_LIMIT),
    )


@app.get("/health")
async def health(model: LoadedModel | None = Depends(get_model)) -> JSONResponse:
    """
    Liveness plus whether a model is loaded.

    Always 200: the application is answering, which is what a health check
    asks. ``model_loaded`` is the field that says whether it can predict.
    """
    return JSONResponse(
        {
            "status": "ok",
            "model_loaded": model is not None,
            "model_name": model.model_name if model else None,
            "data_source": model.data_source if model else None,
            "target": model.target if model else None,
            "trained_at": model.trained_at if model else None,
        }
    )
