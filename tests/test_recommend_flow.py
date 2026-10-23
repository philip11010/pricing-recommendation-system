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

from src.api.main import PROXY_BANNER, app, get_model
from src.db import Decision, Recommendation, get_engine, reset_engine
from src.models import train
from src.models.predict import (
    BEST_METADATA_FILENAME,
    BEST_MODEL_FILENAME,
    load_best_model,
)

FEATURES = ["accommodates", "number_of_reviews", "review_scores_rating", "room_type"]

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
                "input_columns": FEATURES,
                "categorical_choices": {
                    "room_type": ["Entire home/apt", "Private room"]
                },
                "numeric_ranges": {
                    "accommodates": {"min": 1.0, "max": 8.0},
                    "number_of_reviews": {"min": 0.0, "max": 50.0},
                    "review_scores_rating": {"min": 4.2, "max": 4.9},
                },
            }
        ),
        encoding="utf-8",
    )
    return load_best_model(store)


@pytest.fixture
def temp_database(tmp_path, monkeypatch):
    """Point the application at a throwaway SQLite file for one test."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'flow.db'}")
    # Prevent the lifespan from loading the developer's real artefact; the
    # model reaches the routes through a dependency override instead.
    monkeypatch.setattr("src.api.main.try_load_best_model", lambda *a, **k: None)
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
