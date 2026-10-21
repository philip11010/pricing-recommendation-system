"""Tests for target parsing, log transformation and capping."""

import warnings

import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline

from src.preprocessing import (
    build_preprocessor,
    build_target_transformer,
    parse_price,
    split_features_and_target,
    with_price_target,
)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$24.70", 24.70),
        ("$1,234.50", 1234.50),
        ("$52,850.00", 52850.0),
        (" $99.00 ", 99.0),
        (150, 150.0),
        (150.5, 150.5),
    ],
)
def test_parse_price_converts_to_float(raw, expected):
    result = parse_price(pd.Series([raw]))

    assert result.iloc[0] == pytest.approx(expected)
    assert result.dtype == np.float64


@pytest.mark.parametrize("raw", [np.nan, None, "", "N/A", "$"])
def test_parse_price_returns_nan_for_missing_or_unparseable(raw):
    result = parse_price(pd.Series([raw], dtype=object))

    assert np.isnan(result.iloc[0])


def test_parse_price_preserves_index():
    prices = pd.Series(["$10.00", "$20.00"], index=[7, 3])

    assert list(parse_price(prices).index) == [7, 3]


def test_split_features_and_target_drops_unpriced_rows():
    df = pd.DataFrame(
        {"accommodates": [2, 4, 6], "price": ["$100.00", np.nan, "$1,000.00"]}
    )

    X, y = split_features_and_target(df)

    assert list(y) == [100.0, 1000.0]
    assert list(X.index) == list(y.index) == [0, 2]
    assert "price" not in X.columns


# ---------------------------------------------------------------------------
# Log transform and capping
# ---------------------------------------------------------------------------
def test_target_transformer_applies_log1p():
    y = np.array([[10.0], [20.0], [30.0], [40.0], [50.0]])

    result = build_target_transformer().fit_transform(y)

    np.testing.assert_allclose(result, np.log1p(y))


def test_target_transformer_caps_on_log_scale():
    """
    Fences are learned on log price, so an extreme price is pulled back to
    exp(Q3 + 1.5 * IQR) of the logs, not to a dollar-scale fence.
    """
    y = np.array([[100.0], [150.0], [200.0], [250.0], [300.0], [1_000_000.0]])
    transformer = build_target_transformer().fit(y)
    upper = transformer.named_steps["cap"].upper_[0]

    result = transformer.transform(y)

    assert result[-1, 0] == pytest.approx(upper)
    np.testing.assert_allclose(result[:-1], np.log1p(y[:-1]))


def test_target_transformer_inverse_restores_uncapped_prices():
    y = np.array([[10.0], [20.0], [30.0], [40.0], [50.0]])
    transformer = build_target_transformer().fit(y)

    restored = transformer.inverse_transform(transformer.transform(y))

    np.testing.assert_allclose(restored, y)


# ---------------------------------------------------------------------------
# Wrapped regressor
# ---------------------------------------------------------------------------
def test_with_price_target_predicts_in_price_units():
    """Log price linear in x, so a linear model recovers price exactly."""
    X = np.arange(1, 41, dtype=float).reshape(-1, 1)
    y = np.expm1(3.0 + 0.05 * X.ravel())

    model = with_price_target(LinearRegression()).fit(X, y)

    np.testing.assert_allclose(model.predict(X), y, rtol=1e-6)


def test_with_price_target_trains_on_capped_target():
    """
    The regressor must see capped log prices. A model that predicts the
    maximum training target therefore predicts the cap, not the outlier.
    """
    X = np.zeros((6, 1))
    y = np.array([100.0, 150.0, 200.0, 250.0, 300.0, 1_000_000.0])

    model = with_price_target(DummyRegressor(strategy="quantile", quantile=1.0))
    model.fit(X, y)
    upper = model.transformer_.named_steps["cap"].upper_[0]

    assert model.predict(X[:1])[0] == pytest.approx(np.expm1(upper))
    assert model.predict(X[:1])[0] < 1_000_000.0


def test_with_price_target_fits_without_inverse_warning():
    """Capping is lossy by design; sklearn must not warn about it."""
    X = np.zeros((6, 1))
    y = np.array([100.0, 150.0, 200.0, 250.0, 300.0, 1_000_000.0])

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with_price_target(LinearRegression()).fit(X, y)


def test_full_pipeline_runs_in_grid_search_from_raw_prices():
    """
    End to end: raw "$" prices in, dollar-scale CV scores out, with both
    feature and target transformations refitted on every training fold.
    """
    rng = np.random.default_rng(0)
    n = 40
    accommodates = rng.integers(1, 8, n).astype(float)
    # Log price is linear in accommodates (about $75 to $450) with 2% noise.
    prices = np.exp(4.0 + 0.3 * accommodates + rng.normal(0, 0.02, n))
    df = pd.DataFrame(
        {
            "accommodates": accommodates,
            "number_of_reviews": rng.integers(0, 200, n).astype(float),
            "room_type": rng.choice(["Entire home/apt", "Private room"], n),
            "price": [f"${p:,.2f}" for p in prices],
        }
    )
    features = ["accommodates", "number_of_reviews", "room_type"]
    X, y = split_features_and_target(df)
    model = with_price_target(
        Pipeline(
            [
                ("preprocess", build_preprocessor(features)),
                ("model", LinearRegression()),
            ]
        )
    )
    search = GridSearchCV(
        model,
        {"regressor__preprocess__capped__cap__multiplier": [1.5, 3.0]},
        cv=4,
        scoring="neg_root_mean_squared_error",
    )

    search.fit(X, y)

    # 2% noise on prices up to ~$450 gives a dollar RMSE of a few dollars. A
    # log-scale RMSE would be ~0.02, so a score above 1 confirms dollar units.
    assert 1 < -search.best_score_ < 20
