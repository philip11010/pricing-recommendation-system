"""
Tests for the prediction service.

A synthetic pipeline and metadata stand in for the trained artefact, so these
tests pass on a fresh clone with no ``models_store/`` contents. The tests that
need the real artefact are marked and skipped when it is absent.
"""

import json

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import Ridge

from src.config import MODEL_STORE_DIR
from src.models import train
from src.models.predict import (
    BEST_METADATA_FILENAME,
    BEST_MODEL_FILENAME,
    LoadedModel,
    ModelUnavailableError,
    build_input_frame,
    load_best_model,
    predict_price,
    try_load_best_model,
)

FEATURES = ["accommodates", "number_of_reviews", "review_scores_rating", "room_type"]


@pytest.fixture
def fake_store(tmp_path):
    """
    A ``models_store`` directory holding a real fitted pipeline and the
    metadata the training run would have written beside it.
    """
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

    store = tmp_path / "models_store"
    store.mkdir()
    joblib.dump(pipeline, store / BEST_MODEL_FILENAME)
    (store / BEST_METADATA_FILENAME).write_text(
        json.dumps(
            {
                "model_name": "Linear Regression (Ridge)",
                "data_source": "Inside Airbnb Sydney (proxy)",
                "target": "log(price)",
                "trained_at": "2026-01-01T00:00:00",
                "metrics": {"rmse_dollars": 100.0},
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
    return store


@pytest.fixture
def model(fake_store) -> LoadedModel:
    return load_best_model(fake_store)


VALID = {
    "accommodates": 4.0,
    "number_of_reviews": 20.0,
    "review_scores_rating": 4.8,
    "room_type": "Entire home/apt",
}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def test_load_reads_the_pipeline_and_its_metadata(model):
    assert model.model_name == "Linear Regression (Ridge)"
    assert model.data_source == "Inside Airbnb Sydney (proxy)"
    assert model.target == "log(price)"
    assert model.input_columns == FEATURES


def test_load_exposes_the_training_categories_and_ranges(model):
    assert model.categorical_choices["room_type"] == [
        "Entire home/apt",
        "Private room",
    ]
    assert model.numeric_ranges["accommodates"] == {"min": 1.0, "max": 8.0}


def test_load_raises_when_the_model_file_is_missing(fake_store):
    (fake_store / BEST_MODEL_FILENAME).unlink()

    with pytest.raises(ModelUnavailableError, match="src.models.train"):
        load_best_model(fake_store)


def test_load_raises_when_the_metadata_is_missing(fake_store):
    (fake_store / BEST_METADATA_FILENAME).unlink()

    with pytest.raises(ModelUnavailableError):
        load_best_model(fake_store)


def test_load_raises_on_an_empty_directory(tmp_path):
    with pytest.raises(ModelUnavailableError):
        load_best_model(tmp_path)


def test_load_raises_on_corrupt_metadata(fake_store):
    (fake_store / BEST_METADATA_FILENAME).write_text("{not json", encoding="utf-8")

    with pytest.raises(ModelUnavailableError, match="Loading failed"):
        load_best_model(fake_store)


def test_load_refuses_metadata_without_input_columns(fake_store):
    """
    Without the column list the pipeline's expected column order is unknown,
    and a prediction built from a guess would be quietly wrong.
    """
    path = fake_store / BEST_METADATA_FILENAME
    metadata = json.loads(path.read_text(encoding="utf-8"))
    del metadata["input_columns"]
    path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ModelUnavailableError, match="input_columns"):
        load_best_model(fake_store)


def test_try_load_returns_none_instead_of_raising(tmp_path):
    assert try_load_best_model(tmp_path) is None


def test_try_load_returns_the_model_when_present(fake_store):
    assert try_load_best_model(fake_store) is not None


# ---------------------------------------------------------------------------
# Input frame
# ---------------------------------------------------------------------------
def test_input_frame_uses_the_training_column_order(model):
    frame = build_input_frame(model, VALID)

    assert list(frame.columns) == FEATURES
    assert len(frame) == 1


def test_input_frame_order_is_independent_of_the_caller(model):
    """A dict in a different order must not produce a different frame."""
    reversed_values = dict(reversed(list(VALID.items())))

    frame = build_input_frame(model, reversed_values)

    assert list(frame.columns) == FEATURES


def test_input_frame_fills_an_omitted_column_with_nan(model):
    frame = build_input_frame(model, {k: v for k, v in VALID.items() if k != "beds"})

    assert frame.shape == (1, len(FEATURES))


def test_input_frame_drops_keys_that_are_not_input_columns(model):
    frame = build_input_frame(model, {**VALID, "host_name": "someone"})

    assert "host_name" not in frame.columns


def test_omitted_review_score_becomes_nan(model):
    values = {k: v for k, v in VALID.items() if k != "review_scores_rating"}

    frame = build_input_frame(model, values)

    assert pd.isna(frame.loc[0, "review_scores_rating"])


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------
def test_predict_returns_a_positive_price_rounded_to_cents(model):
    price = predict_price(model, VALID)

    assert price > 0
    assert price == round(price, 2)


def test_predict_converts_from_the_log_scale_with_exp(model):
    """
    The reported price must be exp of the pipeline's own output, not the raw
    log value.
    """
    frame = build_input_frame(model, VALID)
    log_prediction = float(model.pipeline.predict(frame)[0])

    price = predict_price(model, VALID)

    assert price == pytest.approx(round(float(np.exp(log_prediction)), 2))


def test_predict_is_deterministic(model):
    assert predict_price(model, VALID) == predict_price(model, VALID)


def test_predict_handles_a_listing_with_no_reviews(model):
    """Blank review scores are valid input, not missing input."""
    values = {
        **VALID,
        "number_of_reviews": 0.0,
        "review_scores_rating": None,
    }

    price = predict_price(model, values)

    assert price > 0


def test_a_bigger_listing_is_not_cheaper(model):
    """
    A sanity check on the wiring rather than on the model: the synthetic
    training data is monotone in accommodates, so the fitted pipeline must be
    too. A column-order bug would scramble this.
    """
    small = predict_price(model, {**VALID, "accommodates": 1.0})
    large = predict_price(model, {**VALID, "accommodates": 8.0})

    assert large > small


def test_predict_rejects_a_non_finite_model_output(model):
    class Broken:
        def predict(self, frame):
            return np.array([np.inf])

    broken = LoadedModel(pipeline=Broken(), metadata=model.metadata)

    with pytest.raises(ValueError, match="unusable price"):
        predict_price(broken, VALID)


# ---------------------------------------------------------------------------
# The real artefact, when one has been trained
# ---------------------------------------------------------------------------
real_artefact = pytest.mark.skipif(
    not (MODEL_STORE_DIR / BEST_MODEL_FILENAME).exists(),
    reason="no trained model; run python -m src.models.train",
)


@real_artefact
def test_the_saved_artefact_loads_and_predicts():
    model = load_best_model()
    values = {column: 1.0 for column in model.input_columns}
    values.update(
        {column: choices[0] for column, choices in model.categorical_choices.items()}
    )
    for column, bounds in model.numeric_ranges.items():
        values[column] = (bounds["min"] + bounds["max"]) / 2

    price = predict_price(model, values)

    assert price > 0


@real_artefact
def test_the_saved_metadata_describes_the_configured_feature_set():
    from src import config
    from src.models.train import DERIVED_FEATURES

    model = load_best_model()

    expected = [f for f in config.full_feature_set() if f not in DERIVED_FEATURES]
    assert model.input_columns == expected
