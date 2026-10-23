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
    example_listing_values,
    example_values,
    form_sections,
    readable_errors,
)
from src.db import Decision, Recommendation, get_session, init_db
from src.models.predict import (
    MODEL_UNAVAILABLE_MESSAGE,
    LoadedModel,
    predict_price,
    try_load_best_model,
)
from src.models.report import comparison_rows, load_latest_report, raw_feature_ranking

API_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = API_DIR / "templates"
STATIC_DIR = API_DIR / "static"

HISTORY_LIMIT = 20

# The dashboard shows a short tail of decisions; /history shows the full page.
RECENT_LIMIT = 5

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
    app.state.report = load_latest_report()
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


def get_report(request: Request) -> dict[str, Any] | None:
    """
    The newest training report, or None if ``reports/`` holds none.

    Loaded at startup like the model. It supplies the model comparison and
    the feature importances that order the form, both of which are display
    concerns, so its absence degrades the page rather than breaking it.
    """
    return getattr(request.app.state, "report", None)


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


def page_context(
    request: Request,
    model: LoadedModel | None,
    report: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """
    Context shared by every page: the banner, the form fields, the model.

    The model comparison prefers the training report, which carries all three
    candidates with their tuned parameters. It falls back to the ``all_models``
    block in the model metadata, so the card still renders from the artefact
    alone when ``reports/`` is empty.
    """
    sections = (
        form_sections(model, raw_feature_ranking(report, model.input_columns))
        if model
        else {}
    )
    comparison = comparison_rows(report, model.model_name if model else None)
    if not comparison and model is not None:
        comparison = model.model_comparison

    defaults = example_values(model) if model else {}
    context: dict[str, Any] = {
        "banner": PROXY_BANNER,
        "model_loaded": model is not None,
        "model_name": model.model_name if model else None,
        "trained_at": model.trained_at if model else None,
        "form_primary": sections.get("primary", []),
        "form_more": sections.get("more", []),
        "values": defaults,
        # Handed to dashboard.js as JSON, for the Reset and Load example
        # buttons. Serialised here rather than in the template so the page
        # needs no inline script.
        "form_presets": json.dumps(
            {
                "defaults": defaults,
                "example": example_listing_values(model) if model else {},
            },
            sort_keys=True,
        ),
        "model_comparison": comparison if model is not None else [],
        "errors": [],
        "prediction": None,
        "confirmation": None,
        "recent": [],
    }
    context.update(extra)
    # Keyed by field for the inline messages beside each control. The first
    # error per field wins; the summary panel above the form lists them all,
    # including any that belong to no visible control.
    field_errors: dict[str, str] = {}
    for error in context.get("errors") or []:
        name = error.get("field")
        if name and name not in field_errors:
            field_errors[name] = error.get("message", "")
    context["field_errors"] = field_errors
    return context


def recent_recommendations(session: Session, limit: int) -> list[Recommendation]:
    """
    The most recent recommendations, newest first, with their decisions.

    Ordered by id as well as timestamp: two rows written in the same clock
    tick would otherwise come back in an arbitrary order.
    """
    statement = (
        select(Recommendation)
        .options(selectinload(Recommendation.decisions))
        .order_by(Recommendation.created_at.desc(), Recommendation.id.desc())
        .limit(limit)
    )
    return list(session.scalars(statement))


def model_unavailable(request: Request) -> HTMLResponse:
    """A 503 page explaining that no artefact has been trained yet."""
    return templates.TemplateResponse(
        request,
        "model_unavailable.html",
        page_context(request, None, None, message=MODEL_UNAVAILABLE_MESSAGE),
        status_code=503,
    )


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    model: LoadedModel | None = Depends(get_model),
    report: dict[str, Any] | None = Depends(get_report),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """
    Render the dashboard and its input form.

    Returns 200 even without a model, so the page can say what is missing.
    Only the prediction endpoint refuses to answer.
    """
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        page_context(
            request,
            model,
            report,
            recent=recent_recommendations(session, RECENT_LIMIT),
        ),
    )


@app.post("/recommend", response_class=HTMLResponse)
async def recommend(
    request: Request,
    model: LoadedModel | None = Depends(get_model),
    report: dict[str, Any] | None = Depends(get_report),
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
                request,
                model,
                report,
                values=submitted,
                errors=readable_errors(error),
                recent=recent_recommendations(session, RECENT_LIMIT),
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
                report,
                values=submitted,
                errors=[{"field": "", "label": "Model", "message": str(error)}],
                recent=recent_recommendations(session, RECENT_LIMIT),
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
            report,
            values=values,
            recent=recent_recommendations(session, RECENT_LIMIT),
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
    report: dict[str, Any] | None = Depends(get_report),
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
                request,
                model,
                report,
                values=submitted,
                errors=readable_errors(error),
                recent=recent_recommendations(session, RECENT_LIMIT),
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
                report,
                recent=recent_recommendations(session, RECENT_LIMIT),
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
            report,
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
    report: dict[str, Any] | None = Depends(get_report),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """The most recent recommendations, newest first, with their decisions."""
    return templates.TemplateResponse(
        request,
        "history.html",
        page_context(
            request,
            model,
            report,
            records=recent_recommendations(session, HISTORY_LIMIT),
            limit=HISTORY_LIMIT,
        ),
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
