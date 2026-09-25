"""
Target variable preparation: price parsing, log transformation and capping.

The raw price column is a string such as "$1,234.00". It is parsed to a float
once, before the train/test split. The log transform and outlier capping are
fitted estimators, so they are learned from training data only and reapplied
unchanged to every CV fold and at prediction time.

Capping happens on the log scale. Raw prices are so right-skewed that Tukey
fences on the dollar scale would cap about 8% of Sydney listings at roughly
$860, leaving the model unable to predict anything above that. On the log
scale the distribution is close to symmetric and the fences cap about 5% of
listings across both tails.
"""

import numpy as np
import pandas as pd
from sklearn.base import RegressorMixin
from sklearn.compose import TransformedTargetRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer

from src.config import TARGET_VARIABLE
from src.preprocessing.transformers import IQRCapper


def parse_price(prices: pd.Series) -> pd.Series:
    """
    Convert price strings such as "$1,234.00" to floats.

    Values that are already numeric pass through. Missing or unparseable
    values become NaN rather than raising, so they can be dropped explicitly.
    """
    cleaned = prices.astype(str).str.replace(r"[$,\s]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce").astype(np.float64)


def split_features_and_target(
    df: pd.DataFrame, target: str = TARGET_VARIABLE
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Parse the target and separate it from the features.

    Rows without a usable price are dropped. In the Inside Airbnb snapshot
    these are mostly inactive listings (zero availability for the year), so
    this is an exclusion rule to report, not random missingness to impute.

    Returns:
        ``(X, y)`` with matching indexes. ``X`` still contains every other
        column; the preprocessor selects the configured features.
    """
    y = parse_price(df[target])
    keep = y.notna()
    return df.loc[keep].drop(columns=target), y.loc[keep]


def build_target_transformer() -> Pipeline:
    """
    Unfitted transformer mapping price to capped log price.

    ``log1p`` rather than ``log`` so a zero price cannot produce -inf.
    """
    return Pipeline(
        [
            (
                "log",
                FunctionTransformer(
                    np.log1p, inverse_func=np.expm1, check_inverse=False
                ),
            ),
            ("cap", IQRCapper()),
        ]
    )


def with_price_target(regressor: RegressorMixin) -> TransformedTargetRegressor:
    """
    Wrap a regressor so it trains on capped log price but predicts in the
    original price units.

    ``regressor`` is normally the ``Pipeline`` of preprocessor and model, so
    that GridSearchCV refits both the feature and target transformations on
    each training fold. Tuned parameters are then addressed as
    ``regressor__<step>__<param>``.

    ``check_inverse`` is disabled because capping is deliberately lossy:
    capped prices do not round-trip to their original values.
    """
    return TransformedTargetRegressor(
        regressor=regressor,
        transformer=build_target_transformer(),
        check_inverse=False,
    )
