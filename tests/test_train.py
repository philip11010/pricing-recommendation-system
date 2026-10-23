"""
Tests for the training entry point.

Everything here runs on a small synthetic frame with a tiny grid and 2 folds.
The real dataset is deliberately not touched: these tests check that the
plumbing is correct (target round-trip, pipeline wiring, artefact and report
output), not that the models are accurate.
"""

import json

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline

from src import config
from src.models import train
from src.preprocessing import NO_REVIEWS_FLAG

FEATURES = [
    "accommodates",
    "bedrooms",
    "number_of_reviews",
    "review_scores_rating",
    "reviews_per_month",
    "availability_30",
    "room_type",
    NO_REVIEWS_FLAG,
]


@pytest.fixture
def synthetic():
    """
    120 synthetic listings with a price that genuinely depends on the
    features, so a fitted model is not degenerate. A quarter of the rows have
    no reviews, with the review columns missing as they are in the real data.
    """
    rng = np.random.default_rng(config.RANDOM_SEED)
    n = 120
    accommodates = rng.integers(1, 9, n).astype(float)
    bedrooms = np.ceil(accommodates / 2)
    reviews = rng.integers(0, 80, n).astype(float)
    unreviewed = rng.random(n) < 0.25
    reviews[unreviewed] = 0.0

    rating = np.where(unreviewed, np.nan, rng.uniform(3.5, 5.0, n))
    per_month = np.where(unreviewed, np.nan, rng.uniform(0.1, 5.0, n))

    price = (
        60.0
        + 35.0 * accommodates
        + 0.4 * reviews
        + 20.0 * np.nan_to_num(rating, nan=0.0)
        + rng.normal(0, 15, n)
    ).clip(min=20.0)

    X = pd.DataFrame(
        {
            "accommodates": accommodates,
            "bedrooms": bedrooms,
            "number_of_reviews": reviews,
            "review_scores_rating": rating,
            "reviews_per_month": per_month,
            "availability_30": rng.integers(0, 31, n).astype(float),
            "room_type": rng.choice(["Entire home/apt", "Private room"], n),
            # A column outside FEATURES, to confirm it is dropped.
            "host_name": ["someone"] * n,
        }
    )
    return X, pd.Series(price, name="price")


@pytest.fixture
def tiny_specs():
    """One cheap model with a two-point grid, so the suite stays fast."""
    return [
        train.ModelSpec(
            key="ridge",
            label="Linear Regression (Ridge)",
            estimator=Ridge(random_state=config.RANDOM_SEED),
            param_grid={"model__alpha": [0.1, 1.0]},
        )
    ]


# ---------------------------------------------------------------------------
# Dollar conversion
# ---------------------------------------------------------------------------
def test_dollar_conversion_round_trips():
    prices = np.array([1.74, 100.0, 291.0, 52850.0])

    np.testing.assert_allclose(train.to_dollars(train.to_log_price(prices)), prices)


def test_log_price_matches_numpy_log():
    prices = pd.Series([10.0, 250.0])

    np.testing.assert_allclose(train.to_log_price(prices), np.log([10.0, 250.0]))


def test_to_dollars_matches_numpy_exp():
    logs = np.array([0.0, 1.0, np.log(250.0)])

    np.testing.assert_allclose(train.to_dollars(logs), [1.0, np.e, 250.0])


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_log_price_rejects_non_positive_prices(bad):
    with pytest.raises(ValueError, match="strictly positive"):
        train.to_log_price(np.array([100.0, bad]))


def test_dollar_conversion_is_not_a_linear_rescale():
    """
    Guards against someone replacing exp with a shift. The gap between two
    log values must grow multiplicatively, not additively.
    """
    low = train.to_dollars(np.array([np.log(100.0), np.log(200.0)]))
    high = train.to_dollars(np.array([np.log(1000.0), np.log(2000.0)]))

    assert high[1] - high[0] == pytest.approx(10 * (low[1] - low[0]))


# ---------------------------------------------------------------------------
# Pipeline construction
# ---------------------------------------------------------------------------
def test_pipeline_has_reviews_step_before_preprocessing():
    pipeline = train.build_model_pipeline(Ridge(), FEATURES)

    assert list(pipeline.named_steps) == ["reviews", "preprocess", "model"]


def test_pipeline_fits_and_predicts_on_synthetic_data(synthetic):
    X, y = synthetic
    pipeline = train.build_model_pipeline(Ridge(), FEATURES)

    pipeline.fit(X, train.to_log_price(y))
    predictions = train.to_dollars(pipeline.predict(X))

    assert predictions.shape == (len(X),)
    assert np.isfinite(predictions).all()
    assert (predictions > 0).all()


def test_pipeline_can_predict_for_an_unreviewed_listing(synthetic):
    """
    The case the no-reviews fix exists for: a listing with every review
    column missing must still get a finite price out of the pipeline.
    """
    X, y = synthetic
    pipeline = train.build_model_pipeline(Ridge(), FEATURES).fit(
        X, train.to_log_price(y)
    )
    unreviewed = X.assign(
        number_of_reviews=0.0, review_scores_rating=np.nan, reviews_per_month=np.nan
    ).head(1)

    prediction = train.to_dollars(pipeline.predict(unreviewed))[0]

    assert np.isfinite(prediction)
    assert prediction > 0


def test_pipeline_drops_columns_outside_the_feature_list(synthetic):
    X, _ = synthetic
    pipeline = train.build_model_pipeline(Ridge(), FEATURES)

    pipeline.fit(X, np.zeros(len(X)))
    encoded = pipeline.named_steps["preprocess"].get_feature_names_out()

    assert "host_name" not in encoded


def test_full_feature_set_builds_a_pipeline():
    pipeline = train.build_model_pipeline(Ridge(), config.full_feature_set())

    configured = [
        column
        for _, _, columns in pipeline.named_steps["preprocess"].transformers
        for column in columns
    ]
    assert sorted(configured) == sorted(config.full_feature_set())


# ---------------------------------------------------------------------------
# Model specs
# ---------------------------------------------------------------------------
def test_three_candidate_models_are_configured():
    keys = [spec.key for spec in train.model_specs()]

    assert keys == ["ridge", "random_forest", "xgboost"]


def test_ridge_grid_matches_the_specification():
    ridge = next(spec for spec in train.model_specs() if spec.key == "ridge")

    assert ridge.param_grid["model__alpha"] == [0.01, 0.1, 1, 10, 100]
    assert ridge.n_candidates == 5


def test_xgboost_uses_the_histogram_tree_method():
    xgb = next(spec for spec in train.model_specs() if spec.key == "xgboost")

    assert xgb.estimator.get_params()["tree_method"] == "hist"


def test_every_spec_is_seeded_for_reproducibility():
    for spec in train.model_specs():
        assert spec.estimator.get_params()["random_state"] == config.RANDOM_SEED


def test_grids_stay_small_enough_for_the_target_machine():
    """8 GB of RAM: keep the total number of fits bounded."""
    total = sum(spec.n_candidates for spec in train.model_specs()) * config.CV_FOLDS

    assert total <= 250


# ---------------------------------------------------------------------------
# Tuning and evaluation
# ---------------------------------------------------------------------------
def test_tune_returns_a_fitted_search_with_a_chosen_parameter(synthetic, tiny_specs):
    X, y = synthetic

    search = train.tune(tiny_specs[0], FEATURES, X, train.to_log_price(y), cv_folds=2)

    assert search.best_params_["model__alpha"] in (0.1, 1.0)
    assert isinstance(search.best_estimator_, Pipeline)


def test_evaluate_reports_every_required_metric(synthetic, tiny_specs):
    X, y = synthetic
    search = train.tune(
        tiny_specs[0], FEATURES, X.iloc[:90], train.to_log_price(y.iloc[:90]), 2
    )

    metrics = train.evaluate(search, X.iloc[90:], y.iloc[90:])

    assert set(metrics) == {
        "rmse_dollars",
        "mae_dollars",
        "r2_dollars",
        "rmse_log",
        "cv_rmse_log_mean",
        "cv_rmse_log_std",
    }
    assert all(np.isfinite(value) for value in metrics.values())


def test_evaluate_dollar_metrics_are_computed_on_the_dollar_scale(
    synthetic, tiny_specs
):
    """
    The metrics must describe dollars, not log dollars. Recomputing them by
    hand from the converted predictions has to reproduce the reported values.
    """
    X, y = synthetic
    search = train.tune(
        tiny_specs[0], FEATURES, X.iloc[:90], train.to_log_price(y.iloc[:90]), 2
    )
    X_test, y_test = X.iloc[90:], y.iloc[90:]

    metrics = train.evaluate(search, X_test, y_test)

    predicted = train.to_dollars(search.predict(X_test))
    expected_rmse = np.sqrt(np.mean((predicted - y_test.to_numpy()) ** 2))
    expected_mae = np.mean(np.abs(predicted - y_test.to_numpy()))
    assert metrics["rmse_dollars"] == pytest.approx(expected_rmse)
    assert metrics["mae_dollars"] == pytest.approx(expected_mae)
    # A dollar error is far larger in magnitude than a log error, so a report
    # that mixed the two up would be obvious here.
    assert metrics["rmse_dollars"] > metrics["rmse_log"]


def test_evaluate_log_rmse_matches_the_log_scale_residuals(synthetic, tiny_specs):
    X, y = synthetic
    search = train.tune(
        tiny_specs[0], FEATURES, X.iloc[:90], train.to_log_price(y.iloc[:90]), 2
    )
    X_test, y_test = X.iloc[90:], y.iloc[90:]

    metrics = train.evaluate(search, X_test, y_test)

    residuals = search.predict(X_test) - train.to_log_price(y_test)
    assert metrics["rmse_log"] == pytest.approx(np.sqrt(np.mean(residuals**2)))


def test_tree_importances_are_returned_against_encoded_names(synthetic):
    from sklearn.ensemble import RandomForestRegressor

    X, y = synthetic
    spec = train.ModelSpec(
        key="rf",
        label="Random Forest",
        estimator=RandomForestRegressor(
            n_estimators=10, random_state=config.RANDOM_SEED
        ),
        param_grid={"model__max_depth": [3]},
    )
    search = train.tune(spec, FEATURES, X, train.to_log_price(y), cv_folds=2)

    importances = train.top_feature_importances(search, top_n=5)

    assert len(importances) == 5
    encoded = set(train.preprocessed_feature_names(search))
    assert all(item["feature"] in encoded for item in importances)
    values = [item["importance"] for item in importances]
    assert values == sorted(values, reverse=True)


def test_importances_are_none_for_a_linear_model(synthetic, tiny_specs):
    X, y = synthetic
    search = train.tune(tiny_specs[0], FEATURES, X, train.to_log_price(y), cv_folds=2)

    assert train.top_feature_importances(search) is None


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------
@pytest.fixture
def experiment(synthetic, tiny_specs, tmp_path):
    X, y = synthetic
    report = train.run_experiment(
        X,
        y,
        features=FEATURES,
        specs=tiny_specs,
        cv_folds=2,
        model_dir=tmp_path / "models_store",
        report_dir=tmp_path / "reports",
    )
    return report, tmp_path


def test_run_experiment_saves_one_artefact_per_model(experiment):
    _, tmp_path = experiment

    assert (tmp_path / "models_store" / "ridge.joblib").exists()


def test_run_experiment_saves_the_best_model_and_its_metadata(experiment):
    _, tmp_path = experiment

    assert (tmp_path / "models_store" / "best_model.joblib").exists()
    assert (tmp_path / "models_store" / "best_model_metadata.json").exists()


def test_saved_best_model_loads_and_predicts(experiment, synthetic):
    _, tmp_path = experiment
    X, _ = synthetic

    model = joblib.load(tmp_path / "models_store" / "best_model.joblib")
    predictions = train.to_dollars(model.predict(X.head(5)))

    assert predictions.shape == (5,)
    assert np.isfinite(predictions).all()


def test_metadata_records_the_required_provenance_fields(experiment):
    _, tmp_path = experiment

    metadata = json.loads(
        (tmp_path / "models_store" / "best_model_metadata.json").read_text(
            encoding="utf-8"
        )
    )

    assert metadata["data_source"] == "Inside Airbnb Sydney (proxy)"
    assert metadata["target"] == "log(price)"
    assert metadata["model_name"] == "Linear Regression (Ridge)"
    assert metadata["trained_at"]
    assert metadata["feature_names"]
    assert "rmse_dollars" in metadata["metrics"]


def test_metadata_feature_names_are_the_encoded_columns(experiment):
    _, tmp_path = experiment

    metadata = json.loads(
        (tmp_path / "models_store" / "best_model_metadata.json").read_text(
            encoding="utf-8"
        )
    )

    assert NO_REVIEWS_FLAG in metadata["feature_names"]
    assert "room_type" not in metadata["feature_names"]  # one-hot encoded away


def test_run_experiment_writes_both_report_formats(experiment):
    _, tmp_path = experiment
    reports = tmp_path / "reports"

    assert len(list(reports.glob("training_report_*.json"))) == 1
    assert len(list(reports.glob("training_report_*.md"))) == 1


def test_report_filenames_are_timestamped(synthetic, tiny_specs, tmp_path):
    from datetime import datetime

    X, y = synthetic
    train.run_experiment(
        X,
        y,
        features=FEATURES,
        specs=tiny_specs,
        cv_folds=2,
        model_dir=tmp_path / "models_store",
        report_dir=tmp_path / "reports",
        timestamp=datetime(2026, 1, 2, 3, 4, 5),
    )

    assert (tmp_path / "reports" / "training_report_20260102_030405.md").exists()


def test_report_records_the_split_and_cv_settings(experiment):
    report, _ = experiment

    assert report["cv_folds"] == 2
    assert report["random_seed"] == config.RANDOM_SEED
    assert report["test_size"] == config.TEST_SIZE
    assert report["rows_train"] + report["rows_test"] == report["rows_total"]


def test_report_names_a_best_model_and_a_cv_ranking(experiment):
    report, _ = experiment

    assert report["best_model"] == "Linear Regression (Ridge)"
    assert report["cv_ranking"] == ["Linear Regression (Ridge)"]
    assert report["selection_metric"] == "rmse_dollars"


def test_report_discloses_test_set_selection_as_a_limitation(experiment):
    report, _ = experiment

    assert any("test-set RMSE" in note for note in report["limitations"])


def test_markdown_report_contains_the_comparison_table(experiment):
    _, tmp_path = experiment

    text = next((tmp_path / "reports").glob("*.md")).read_text(encoding="utf-8")

    assert "## Comparison" in text
    assert "Test RMSE ($)" in text
    assert "Linear Regression (Ridge)" in text
    assert "## Limitations" in text


def test_markdown_report_includes_tree_importances(synthetic, tmp_path):
    from sklearn.ensemble import RandomForestRegressor

    X, y = synthetic
    specs = [
        train.ModelSpec(
            key="random_forest",
            label="Random Forest",
            estimator=RandomForestRegressor(
                n_estimators=10, random_state=config.RANDOM_SEED
            ),
            param_grid={"model__max_depth": [3]},
        )
    ]

    train.run_experiment(
        X,
        y,
        features=FEATURES,
        specs=specs,
        cv_folds=2,
        model_dir=tmp_path / "models_store",
        report_dir=tmp_path / "reports",
    )

    text = next((tmp_path / "reports").glob("*.md")).read_text(encoding="utf-8")
    assert "Feature importances" in text
    assert "| Rank | Feature | Importance |" in text


def test_report_json_is_serialisable_without_numpy_scalars(experiment):
    report, tmp_path = experiment

    raw = next((tmp_path / "reports").glob("*.json")).read_text(encoding="utf-8")

    assert json.loads(raw)["best_model"] == report["best_model"]


def test_run_experiment_does_not_write_into_the_repository(experiment):
    """The fixture redirects both output directories, so nothing leaks."""
    report, tmp_path = experiment

    assert str(tmp_path) not in str(config.MODEL_STORE_DIR)
    assert report["results"][0]["artefact"] == "ridge.joblib"
