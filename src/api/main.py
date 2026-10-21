"""
FastAPI application: the serving layer for the mentor pricing dashboard.

Corresponds to the FastAPI Application component in Chapter 4. At this stage
the dashboard is rendered with placeholder data so the serving layer (routing,
templating, static files) can be verified before any model is wired in.

Run locally with:
    uvicorn src.api.main:app --reload
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

API_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = API_DIR / "templates"
STATIC_DIR = API_DIR / "static"

app = FastAPI(title="Mentor Pricing Recommendation")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ---------------------------------------------------------------------------
# Placeholder data
#
# Stands in for a real mentor record and model output until the ML Model
# component is connected. Grouped by the input variable categories so the
# eventual wiring maps one-to-one onto the template.
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
    "recommendation": {
        "currency": "KES",
        "price": 2500,
        "current_price": 2200,
    },
    "demand": {
        "profile_views_30d": 312,
        "booking_requests_30d": 17,
        "skill_demand_trend": "Rising",
    },
}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    """Render the mentor dashboard with placeholder data."""
    return templates.TemplateResponse(request, "dashboard.html", PLACEHOLDER_DASHBOARD)
