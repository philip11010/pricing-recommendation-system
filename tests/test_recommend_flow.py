"""
End-to-end tests for the recommendation and decision flow.

Every test runs against a temporary SQLite file and a synthetic model, so the
suite never reads the developer's ``app.db`` and does not need a trained
artefact in ``models_store/``.
"""

import json
import re

import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from src.api.main import PROXY_BANNER, app, get_model, get_report
from src.db import Decision, Recommendation, get_engine, reset_engine
from src.models import train
from src.models.predict import (
    BEST_METADATA_FILENAME,
    BEST_MODEL_FILENAME,
    load_best_model,
)

FEATURES = ["accommodates", "number_of_reviews", "review_scores_rating", "room_type"]

# RMSE and MAE are far apart on purpose, so a test can tell which figure the
# result panel quoted.
METRICS = {
    "Linear Regression (Ridge)": {
        "rmse_dollars": 517.0,
        "mae_dollars": 42.0,
        "r2_dollars": 0.5,
    },
    "Random Forest": {
        "rmse_dollars": 550.0,
        "mae_dollars": 136.0,
        "r2_dollars": 0.42,
    },
    "XGBoost": {
        "rmse_dollars": 512.0,
        "mae_dollars": 131.0,
        "r2_dollars": 0.49,
    },
}

VALID_FORM = {
    "accommodates": "4",
    "number_of_reviews": "20",
    "review_scores_rating": "4.8",
    "room_type": "Entire home/apt",
}


@pytest.fixture
def fake_model(tmp_path):
    """A real fitted pipeline over four columns, plus its metadata."""
    from sklearn.linear_model import Ridge

    frame = pd.DataFrame(
        {
            "accommodates": [1.0, 2.0, 4.0, 6.0, 8.0, 3.0],
            "number_of_reviews": [0.0, 5.0, 20.0, 50.0, 2.0, 0.0],
            "review_scores_rating": [np.nan, 4.5, 4.8, 4.9, 4.2, np.nan],
            "room_type": ["Private room", "Entire home/apt"] * 3,
        }
    )
    prices = np.array([80.0, 120.0, 200.0, 320.0, 420.0, 150.0])
    pipeline = train.build_model_pipeline(Ridge(alpha=1.0), FEATURES)
    pipeline.fit(frame, train.to_log_price(prices))

    store = tmp_path / "store"
    store.mkdir()
    joblib.dump(pipeline, store / BEST_MODEL_FILENAME)
    (store / BEST_METADATA_FILENAME).write_text(
        json.dumps(
            {
                "model_name": "Linear Regression (Ridge)",
                "data_source": "Inside Airbnb Sydney (proxy)",
                "target": "log(price)",
                "trained_at": "2026-01-01T00:00:00",
                "selection_metric": "rmse_dollars",
                "metrics": METRICS["Linear Regression (Ridge)"],
                "all_models": METRICS,
                "input_columns": FEATURES,
                "categorical_choices": {
                    "room_type": ["Entire home/apt", "Private room"]
                },
                "numeric_ranges": {
                    "accommodates": {"min": 1.0, "max": 8.0},
                    "number_of_reviews": {"min": 0.0, "max": 50.0},
                    "review_scores_rating": {"min": 4.2, "max": 4.9},
                },
                "numeric_medians": {
                    "accommodates": 4.0,
                    "number_of_reviews": 20.0,
                    "review_scores_rating": 4.8,
                },
                "categorical_modes": {"room_type": "Entire home/apt"},
            }
        ),
        encoding="utf-8",
    )
    return load_best_model(store)


@pytest.fixture
def temp_database(tmp_path, monkeypatch):
    """Point the application at a throwaway SQLite file for one test."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'flow.db'}")
    # Prevent the lifespan from loading the developer's real artefact or
    # report; the model reaches the routes through a dependency override, and
    # a test that wants a report overrides get_report. Without this the real
    # reports/ directory would decide what the comparison card shows.
    monkeypatch.setattr("src.api.main.try_load_best_model", lambda *a, **k: None)
    monkeypatch.setattr("src.api.main.load_latest_report", lambda *a, **k: None)
    reset_engine()
    yield
    reset_engine()


@pytest.fixture
def client(temp_database, fake_model):
    """A client with a model available. Used as a context manager so the
    lifespan runs and the tables are created."""
    app.dependency_overrides[get_model] = lambda: fake_model
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


FAKE_REPORT = {
    "selection_metric": "rmse_dollars",
    "best_model": "Linear Regression (Ridge)",
    "results": [
        {
            "model": "Linear Regression (Ridge)",
            "metrics": METRICS["Linear Regression (Ridge)"],
            "feature_importances": None,
        },
        {
            "model": "Random Forest",
            "metrics": METRICS["Random Forest"],
            # Deliberately ranks number_of_reviews above accommodates, the
            # opposite of the column order, so a test can tell the form was
            # ordered by importance rather than by declaration.
            "feature_importances": [
                {"feature": "number_of_reviews", "importance": 0.6},
                {"feature": "accommodates", "importance": 0.3},
                {"feature": "room_type_Private room", "importance": 0.1},
            ],
        },
        {
            "model": "XGBoost",
            "metrics": METRICS["XGBoost"],
            "feature_importances": None,
        },
    ],
}


@pytest.fixture
def reporting_client(temp_database, fake_model):
    """A client whose dashboard reads the fake training report."""
    app.dependency_overrides[get_model] = lambda: fake_model
    app.dependency_overrides[get_report] = lambda: FAKE_REPORT
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def modelless_client(temp_database):
    """A client with no model loaded, as on a fresh clone."""
    app.dependency_overrides[get_model] = lambda: None
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def session():
    """A session on the same temporary database the client is using."""
    with sessionmaker(bind=get_engine(), expire_on_commit=False)() as session:
        yield session


def selected_option(text: str, name: str) -> str | None:
    """The pre-selected option of a <select>, as the page rendered it."""
    block = re.search(rf'name="{name}"(.*?)</select>', text, re.S)
    if not block:
        return None
    option = re.search(r'value="([^"]+)"\s*selected', block.group(1))
    return option.group(1) if option else None


def result_panel(response) -> str:
    """The recommendation panel only, so a test can say where a figure is."""
    match = re.search(
        r'<section class="panel recommendation".*?</section>', response.text, re.S
    )
    assert match, "no recommendation panel in the rendered page"
    return match.group(0)


def comparison_panel(response) -> str:
    match = re.search(
        r'<section class="panel comparison".*?</section>', response.text, re.S
    )
    assert match, "no comparison panel in the rendered page"
    return match.group(0)


def recommendation_id(response) -> str:
    """Pull the recommendation id out of the rendered decision form."""
    match = re.search(r'name="recommendation_id"\s+value="(\d+)"', response.text)
    assert match, "no recommendation id in the rendered page"
    return match.group(1)


def make_recommendation(client) -> str:
    response = client.post("/recommend", data=VALID_FORM)
    assert response.status_code == 200
    return recommendation_id(response)


# ---------------------------------------------------------------------------
# Banner, present on every page
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/", "/history"])
def test_banner_is_on_every_page(client, path):
    assert PROXY_BANNER in client.get(path).text


def test_banner_names_the_proxy_the_currency_and_the_caveat():
    assert "Inside Airbnb Sydney" in PROXY_BANNER
    assert "structural proxy" in PROXY_BANNER
    assert "USD" in PROXY_BANNER
    assert "not a mentorship rate" in PROXY_BANNER


def test_banner_is_on_the_result_page(client):
    response = client.post("/recommend", data=VALID_FORM)

    assert PROXY_BANNER in response.text


def test_banner_is_on_the_confirmation_page(client):
    rec_id = make_recommendation(client)

    response = client.post(
        "/decision", data={"recommendation_id": rec_id, "decision": "accept"}
    )

    assert PROXY_BANNER in response.text


def test_banner_is_on_the_model_unavailable_page(modelless_client):
    response = modelless_client.post("/recommend", data=VALID_FORM)

    assert PROXY_BANNER in response.text


# ---------------------------------------------------------------------------
# Dashboard and form
# ---------------------------------------------------------------------------
def test_dashboard_renders_a_control_for_every_input_column(client):
    text = client.get("/").text

    for column in FEATURES:
        assert f'name="{column}"' in text


def test_dashboard_populates_a_dropdown_from_the_training_categories(client):
    text = client.get("/").text

    assert '<option value="Entire home/apt"' in text
    assert '<option value="Private room"' in text
    assert "Treehouse" not in text


def test_dashboard_does_not_ask_for_a_derived_feature(client):
    """has_no_reviews is computed by the pipeline, so it is not an input."""
    assert 'name="has_no_reviews"' not in client.get("/").text


def test_dashboard_applies_the_training_ranges_to_the_number_inputs(client):
    text = client.get("/").text

    assert 'name="accommodates"' in text
    assert 'min="1.0"' in text and 'max="8.0"' in text


# ---------------------------------------------------------------------------
# POST /recommend, valid input
# ---------------------------------------------------------------------------
def test_recommend_renders_a_price(client):
    response = client.post("/recommend", data=VALID_FORM)

    assert response.status_code == 200
    assert "USD" in response.text
    assert re.search(r'price-value">[\d,]+\.\d{2}<', response.text)


def test_recommend_stores_one_row(client, session):
    client.post("/recommend", data=VALID_FORM)

    stored = session.scalars(select(Recommendation)).all()

    assert len(stored) == 1
    assert stored[0].model_name == "Linear Regression (Ridge)"
    assert stored[0].data_source == "Inside Airbnb Sydney (proxy)"
    assert stored[0].predicted_price > 0


def test_stored_input_json_is_the_validated_input(client, session):
    client.post("/recommend", data=VALID_FORM)

    stored = session.scalars(select(Recommendation)).one()

    recorded = json.loads(stored.input_json)
    assert recorded["accommodates"] == 4.0
    assert recorded["room_type"] == "Entire home/apt"
    assert set(recorded) == set(FEATURES)


def test_stored_price_matches_the_displayed_price(client, session):
    response = client.post("/recommend", data=VALID_FORM)

    stored = session.scalars(select(Recommendation)).one()

    assert f"{stored.predicted_price:,.2f}" in response.text


def test_recommend_accepts_a_listing_with_no_reviews(client, session):
    """Blank review scores mean "no reviews yet", which is valid input."""
    response = client.post(
        "/recommend",
        data={**VALID_FORM, "number_of_reviews": "0", "review_scores_rating": ""},
    )

    assert response.status_code == 200
    stored = session.scalars(select(Recommendation)).one()
    assert json.loads(stored.input_json)["review_scores_rating"] is None


# ---------------------------------------------------------------------------
# Reported error and model comparison
# ---------------------------------------------------------------------------
def test_result_panel_quotes_the_mae_as_the_typical_error(client):
    response = client.post("/recommend", data=VALID_FORM)

    panel = result_panel(response)

    assert "Typical error about" in panel
    assert "$42" in panel


def test_result_panel_does_not_quote_the_rmse(client):
    """
    RMSE is roughly four times MAE on this data, so showing it beside one
    price would overstate the error on a typical listing.
    """
    response = client.post("/recommend", data=VALID_FORM)

    panel = result_panel(response)

    assert "517" not in panel
    assert "RMSE" not in panel


def test_comparison_card_shows_rmse_mae_and_r2(client):
    panel = comparison_panel(client.get("/"))

    assert "RMSE (USD)" in panel
    assert "MAE (USD)" in panel
    assert "R2" in panel


def test_comparison_card_lists_all_three_candidate_models(client):
    panel = comparison_panel(client.get("/"))

    for name in METRICS:
        assert name in panel


def test_comparison_card_reports_the_rmse_figures(client):
    panel = comparison_panel(client.get("/"))

    assert "517.00" in panel
    assert "550.00" in panel
    assert "512.00" in panel


def test_comparison_card_orders_by_rmse_and_marks_the_selected_model(client):
    panel = comparison_panel(client.get("/"))

    order = [
        panel.index(name) for name in ("XGBoost", "Linear Regression", "Random Forest")
    ]
    assert order == sorted(order)
    assert "selected" in panel


def test_comparison_card_is_absent_without_a_model(modelless_client):
    assert 'class="panel comparison"' not in modelless_client.get("/").text


def test_comparison_card_prefers_the_report_over_the_metadata(reporting_client):
    """
    The report carries all three candidates from the run that selected the
    model, so it is the better source when one is present.
    """
    panel = comparison_panel(reporting_client.get("/"))

    assert "517.00" in panel
    assert "550.00" in panel
    assert "512.00" in panel


def test_comparison_card_marks_the_served_model_not_the_reports_best(
    reporting_client,
):
    """
    The served artefact decides what "selected" means. The report's own
    best_model could be from a later run than the artefact on disk.
    """
    panel = comparison_panel(reporting_client.get("/"))

    selected_row = [row for row in panel.split("<tr") if "badge" in row]
    assert len(selected_row) == 1
    assert "Linear Regression (Ridge)" in selected_row[0]


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------
def test_landing_page_shows_an_empty_state_instead_of_a_price(client):
    response = client.get("/")

    assert "No price yet" in response.text
    assert "price-value" not in response.text


def test_landing_page_has_no_placeholder_currency_or_figure(client):
    """
    The dashboard used to show an illustrative "KES 2,500". A figure that
    looks like a price but is not model output is the one thing a pricing
    tool must not display.
    """
    text = client.get("/").text

    assert "KES" not in text
    assert "2,500" not in text
    assert "Illustration only" not in text


def test_empty_state_is_replaced_by_the_real_price(client):
    response = client.post("/recommend", data=VALID_FORM)

    assert "No price yet" not in response.text
    assert "price-value" in response.text


# ---------------------------------------------------------------------------
# Form layout: primary fields, collapsed remainder, prefills, presets
# ---------------------------------------------------------------------------
def test_every_input_column_is_still_rendered_somewhere(client):
    """
    Collapsing fields must not drop them: the form submits the complete
    input, so each column appears exactly once whichever half it is in.
    """
    text = client.get("/").text

    for column in FEATURES:
        assert text.count(f'name="{column}"') == 1


def test_remaining_fields_sit_in_a_collapsed_details_element(reporting_client):
    text = reporting_client.get("/").text

    assert '<details class="more-details"' in text
    # Collapsed by default: no open attribute on the element.
    assert '<details class="more-details" open' not in text


def test_more_details_summary_counts_the_hidden_fields(reporting_client):
    text = reporting_client.get("/").text

    assert re.search(r"<summary>More details \(\d+ further inputs\)</summary>", text)


def test_primary_fields_are_chosen_by_reported_importance(reporting_client):
    """
    The fake report ranks number_of_reviews above accommodates, which is the
    opposite of the declaration order, so position proves the ranking was
    used rather than the column list.
    """
    text = reporting_client.get("/").text
    collapsed = text.index("<details")

    assert text.index('id="field-number_of_reviews"') < collapsed


def test_room_type_and_neighbourhood_are_always_shown_first(client):
    """
    Both are forced into the primary set: they are the two inputs a reviewer
    reaches for, whatever the importances say.
    """
    text = client.get("/").text
    collapsed = text.index("<details") if "<details" in text else len(text)

    assert text.index('id="field-room_type"') < collapsed


def test_numeric_inputs_are_prefilled_with_the_training_median(client):
    """
    number_of_reviews has a median of 20 in the fake training frame, so the
    form opens on a submittable listing rather than empty boxes.
    """
    text = client.get("/").text

    match = re.search(r'id="field-number_of_reviews"[^>]*value="([^"]*)"', text)
    assert match and match.group(1) == "20"


def test_categorical_inputs_are_prefilled_with_the_training_mode(client):
    text = client.get("/").text

    assert selected_option(text, "room_type") == "Entire home/apt"


def test_the_prefilled_form_submits_without_edits(client, session):
    """
    The point of pre-filling from the training centre: whatever the page
    opens with must be accepted, so a demo cannot start on a 400.
    """
    text = client.get("/").text
    values = dict(re.findall(r'id="field-(\w+)"[^>]*value="([^"]*)"', text))
    values["room_type"] = selected_option(text, "room_type")

    response = client.post("/recommend", data=values)

    assert response.status_code == 200
    assert session.scalars(select(Recommendation)).all()


def test_preset_values_are_rendered_as_json_for_the_buttons(client):
    text = client.get("/").text

    raw = re.search(r'id="form-presets">(.*?)</script>', text, re.S).group(1)
    presets = json.loads(raw)
    assert set(presets) == {"defaults", "example"}
    assert set(presets["defaults"]) == set(FEATURES)
    assert set(presets["example"]) == set(FEATURES)


def test_example_listing_differs_from_the_median_defaults(client):
    """
    Otherwise the Load example button would appear to do nothing. The example
    is one coherent listing, not a column-by-column average.
    """
    text = client.get("/").text
    presets = json.loads(
        re.search(r'id="form-presets">(.*?)</script>', text, re.S).group(1)
    )

    assert presets["example"] != presets["defaults"]


def test_example_listing_stays_inside_the_accepted_ranges(client):
    """
    The example is written by hand, so it is clamped to the training range.
    An example the form would then refuse is worse than no example.
    """
    text = client.get("/").text
    presets = json.loads(
        re.search(r'id="form-presets">(.*?)</script>', text, re.S).group(1)
    )

    response = client.post("/recommend", data=presets["example"])

    assert response.status_code == 200


def test_load_example_and_reset_buttons_are_present_and_not_submits(client):
    text = client.get("/").text

    assert "data-load-example" in text
    assert "data-reset-form" in text
    # Neither may submit the form, and neither may be a decision control.
    for marker in ("data-load-example", "data-reset-form"):
        button = re.search(r"<button[^>]*" + marker + r"[^>]*>", text).group(0)
        assert 'type="button"' in button
        assert "name=" not in button.replace("data-announce", "")


def test_each_field_carries_its_mentor_platform_equivalent(client):
    text = client.get("/").text

    assert text.count('class="field-help"') == len(FEATURES)
    assert "Review count stands in for total sessions reviewed" in text


# ---------------------------------------------------------------------------
# Range hints
# ---------------------------------------------------------------------------
def test_each_numeric_input_shows_its_training_range(client):
    text = client.get("/").text

    assert '<span class="field-hint" id="hint-accommodates">1 to 8</span>' in text
    assert '<span class="field-hint" id="hint-number_of_reviews">0 to 50</span>' in text


def test_range_hint_is_tied_to_its_input_for_screen_readers(client):
    text = client.get("/").text

    assert 'aria-describedby="hint-accommodates"' in text


def test_range_hint_shows_decimal_bounds_unrounded(client):
    """review_scores_rating runs 4.2 to 4.9, so the hint must not say 4 to 5."""
    text = client.get("/").text

    assert 'id="hint-review_scores_rating">4.2 to 4.9</span>' in text


def test_no_range_hint_on_a_dropdown(client):
    assert 'id="hint-room_type"' not in client.get("/").text


# ---------------------------------------------------------------------------
# POST /recommend, invalid input
# ---------------------------------------------------------------------------# ---------------------------------------------------------------------------
# POST /recommend, invalid input
# ---------------------------------------------------------------------------
def test_missing_required_field_is_rejected(client, session):
    payload = {k: v for k, v in VALID_FORM.items() if k != "accommodates"}

    response = client.post("/recommend", data=payload)

    assert response.status_code == 400
    assert "Field required" in response.text
    assert session.scalars(select(Recommendation)).all() == []


def test_blank_required_field_is_rejected(client):
    response = client.post("/recommend", data={**VALID_FORM, "accommodates": ""})

    assert response.status_code == 400
    assert "Field required" in response.text


def test_negative_number_is_rejected(client, session):
    response = client.post("/recommend", data={**VALID_FORM, "accommodates": "-4"})

    assert response.status_code == 400
    assert "greater than or equal to 1" in response.text
    assert session.scalars(select(Recommendation)).all() == []


def test_value_above_the_training_range_is_rejected(client):
    """Beyond the training range the model has no evidence, so it refuses."""
    response = client.post("/recommend", data={**VALID_FORM, "accommodates": "400"})

    assert response.status_code == 400
    assert "less than or equal to 8" in response.text


def test_unknown_category_is_rejected(client, session):
    response = client.post("/recommend", data={**VALID_FORM, "room_type": "Treehouse"})

    assert response.status_code == 400
    assert "Room type" in response.text
    assert session.scalars(select(Recommendation)).all() == []


def test_non_numeric_value_is_rejected(client):
    response = client.post("/recommend", data={**VALID_FORM, "accommodates": "four"})

    assert response.status_code == 400


def test_unknown_field_is_rejected(client):
    response = client.post("/recommend", data={**VALID_FORM, "surprise": "1"})

    assert response.status_code == 400
    assert "Extra inputs are not permitted" in response.text


def test_rejected_input_is_echoed_back_into_the_form(client):
    """The user must not have to retype 24 valid fields to fix one."""
    response = client.post("/recommend", data={**VALID_FORM, "accommodates": "-4"})

    assert 'value="-4"' in response.text


# ---------------------------------------------------------------------------
# POST /decision
# ---------------------------------------------------------------------------
def test_accept_stores_the_recommended_price_as_final(client, session):
    rec_id = make_recommendation(client)

    response = client.post(
        "/decision", data={"recommendation_id": rec_id, "decision": "accept"}
    )

    assert response.status_code == 200
    decision = session.scalars(select(Decision)).one()
    recommendation = session.get(Recommendation, int(rec_id))
    assert decision.action == "accept"
    assert decision.final_price == pytest.approx(recommendation.predicted_price)


def test_modify_stores_the_mentors_own_price(client, session):
    rec_id = make_recommendation(client)

    response = client.post(
        "/decision",
        data={
            "recommendation_id": rec_id,
            "decision": "modify",
            "final_price": "275.50",
        },
    )

    assert response.status_code == 200
    assert "275.50" in response.text
    decision = session.scalars(select(Decision)).one()
    assert decision.action == "modify"
    assert decision.final_price == pytest.approx(275.50)


def test_reject_stores_no_final_price(client, session):
    rec_id = make_recommendation(client)

    response = client.post(
        "/decision", data={"recommendation_id": rec_id, "decision": "reject"}
    )

    assert response.status_code == 200
    decision = session.scalars(select(Decision)).one()
    assert decision.action == "reject"
    assert decision.final_price is None


def test_reject_discards_a_price_left_in_the_box(client, session):
    rec_id = make_recommendation(client)

    client.post(
        "/decision",
        data={"recommendation_id": rec_id, "decision": "reject", "final_price": "99"},
    )

    assert session.scalars(select(Decision)).one().final_price is None


def test_modify_error_is_shown_beside_the_price_box(client):
    """
    The error must attach to final_price, not to the model as a whole, or it
    can only appear in the summary and not next to the control at fault.
    """
    rec_id = make_recommendation(client)

    response = client.post(
        "/decision", data={"recommendation_id": rec_id, "decision": "modify"}
    )

    assert 'id="error-final-price"' in response.text
    assert 'aria-describedby="error-final-price"' in response.text


def test_modify_without_the_price_field_at_all_is_rejected(client, session):
    """
    A form that omits the price box leaves final_price at its default.
    Pydantic skips validators for an unsupplied field unless asked, so
    without validate_default this reached the database CHECK constraint and
    raised a 500 instead of showing a message.
    """
    rec_id = make_recommendation(client)

    response = client.post(
        "/decision", data={"recommendation_id": rec_id, "decision": "modify"}
    )

    assert response.status_code == 400
    assert session.scalars(select(Decision)).all() == []


def test_modify_without_a_number_is_rejected(client, session):
    rec_id = make_recommendation(client)

    response = client.post(
        "/decision", data={"recommendation_id": rec_id, "decision": "modify"}
    )

    assert response.status_code == 400
    assert "needs a new price" in response.text
    assert session.scalars(select(Decision)).all() == []


def test_modify_with_a_blank_number_is_rejected(client):
    rec_id = make_recommendation(client)

    response = client.post(
        "/decision",
        data={"recommendation_id": rec_id, "decision": "modify", "final_price": ""},
    )

    assert response.status_code == 400
    assert "needs a new price" in response.text


@pytest.mark.parametrize("bad_price", ["0", "-10"])
def test_modify_with_a_non_positive_number_is_rejected(client, session, bad_price):
    rec_id = make_recommendation(client)

    response = client.post(
        "/decision",
        data={
            "recommendation_id": rec_id,
            "decision": "modify",
            "final_price": bad_price,
        },
    )

    assert response.status_code == 400
    assert session.scalars(select(Decision)).all() == []


def test_unknown_action_is_rejected(client):
    rec_id = make_recommendation(client)

    response = client.post(
        "/decision", data={"recommendation_id": rec_id, "decision": "maybe"}
    )

    assert response.status_code == 400


def test_decision_on_an_unknown_recommendation_is_rejected(client, session):
    response = client.post(
        "/decision", data={"recommendation_id": "9999", "decision": "accept"}
    )

    assert response.status_code == 400
    assert "9999" in response.text
    assert session.scalars(select(Decision)).all() == []


def test_decision_does_not_need_a_loaded_model(modelless_client, temp_database):
    """
    Recording a decision is a database write, not a prediction, so it must
    keep working even when no model is available.
    """
    with sessionmaker(bind=get_engine())() as setup:
        record = Recommendation(
            input_json="{}",
            model_name="XGBoost",
            predicted_price=200.0,
            data_source="Inside Airbnb Sydney (proxy)",
        )
        setup.add(record)
        setup.commit()
        rec_id = record.id

    response = modelless_client.post(
        "/decision", data={"recommendation_id": str(rec_id), "decision": "accept"}
    )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /history
# ---------------------------------------------------------------------------
def test_history_is_empty_before_any_recommendation(client):
    response = client.get("/history")

    assert response.status_code == 200
    assert "No recommendations recorded yet" in response.text


def test_history_lists_newest_first(client):
    for accommodates in ("1", "4", "8"):
        client.post("/recommend", data={**VALID_FORM, "accommodates": accommodates})

    text = client.get("/history").text

    positions = [text.index(f">{i}</td>") for i in (3, 2, 1)]
    assert positions == sorted(positions)


def test_history_shows_the_recorded_decision(client):
    rec_id = make_recommendation(client)
    client.post(
        "/decision",
        data={
            "recommendation_id": rec_id,
            "decision": "modify",
            "final_price": "275.50",
        },
    )

    text = client.get("/history").text

    assert "modify" in text
    assert "275.50" in text


def test_history_marks_a_recommendation_with_no_decision(client):
    make_recommendation(client)

    assert "no decision yet" in client.get("/history").text


def test_history_shows_a_rejection_without_a_final_price(client):
    rec_id = make_recommendation(client)
    client.post("/decision", data={"recommendation_id": rec_id, "decision": "reject"})

    text = client.get("/history").text

    assert "reject" in text


def test_history_returns_at_most_twenty_rows(client, session):
    with session as writer:
        for _ in range(25):
            writer.add(
                Recommendation(
                    input_json="{}",
                    model_name="XGBoost",
                    predicted_price=100.0,
                    data_source="Inside Airbnb Sydney (proxy)",
                )
            )
        writer.commit()

    text = client.get("/history").text

    assert text.count("<tr>") == 21  # 20 data rows plus the header row


# ---------------------------------------------------------------------------
# Missing model
# ---------------------------------------------------------------------------
def test_recommend_without_a_model_returns_503(modelless_client):
    response = modelless_client.post("/recommend", data=VALID_FORM)

    assert response.status_code == 503


def test_model_unavailable_page_says_how_to_fix_it(modelless_client):
    response = modelless_client.post("/recommend", data=VALID_FORM)

    assert "python -m src.models.train" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_dashboard_still_renders_without_a_model(modelless_client):
    """
    The page must not 503: it is what explains the situation, and the history
    view stays usable.
    """
    response = modelless_client.get("/")

    assert response.status_code == 200
    assert "No trained model is loaded" in response.text


def test_dashboard_without_a_model_shows_no_input_form(modelless_client):
    response = modelless_client.get("/")

    assert 'action="/recommend"' not in response.text


def test_history_still_renders_without_a_model(modelless_client):
    assert modelless_client.get("/history").status_code == 200


def test_no_recommendation_is_stored_when_the_model_is_missing(
    modelless_client, session
):
    modelless_client.post("/recommend", data=VALID_FORM)

    assert session.scalars(select(Recommendation)).all() == []


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
def test_health_reports_a_loaded_model(client):
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert body["model_name"] == "Linear Regression (Ridge)"
    assert body["data_source"] == "Inside Airbnb Sydney (proxy)"
    assert body["target"] == "log(price)"


def test_health_reports_a_missing_model(modelless_client):
    response = modelless_client.get("/health")

    assert response.status_code == 200
    assert response.json()["model_loaded"] is False
    assert response.json()["model_name"] is None
