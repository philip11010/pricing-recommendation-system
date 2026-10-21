"""
Data Preprocessing component.

Builds a single scikit-learn ``ColumnTransformer`` covering imputation,
outlier capping, scaling and encoding. Because every step is a fitted
estimator, the object fitted on training data is the same object that
transforms prediction-time data, so the two can never drift apart.

To keep the test set and each CV validation fold unseen during fitting, wrap
the preprocessor and the model in one ``Pipeline`` and pass that to
``GridSearchCV``, rather than transforming the full dataset up front::

    Pipeline([("preprocess", build_preprocessor(features)), ("model", model)])

The target is handled separately by ``with_price_target`` in
``src.preprocessing.target``.
"""

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder

from src.config import CAPPED_FEATURES, CATEGORICAL_FEATURES
from src.preprocessing.transformers import IQRCapper


def split_feature_types(
    features: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """
    Split a feature list into capped continuous, uncapped continuous and
    categorical columns, preserving the input order within each group.

    Returns:
        ``(capped, uncapped, categorical)``
    """
    categorical = [f for f in features if f in CATEGORICAL_FEATURES]
    capped = [f for f in features if f in CAPPED_FEATURES]
    uncapped = [f for f in features if f not in categorical + capped]
    return capped, uncapped, categorical


def build_preprocessor(features: list[str]) -> ColumnTransformer:
    """
    Build an unfitted preprocessor for the given feature list.

    - Capped continuous (skewed counts): median imputation, IQR capping,
      Min-Max scaling
    - Other continuous: median imputation, Min-Max scaling
    - Categorical: mode imputation, one-hot encoding with the first category
      of each feature dropped as the reference level. Without the drop, each
      one-hot block sums to the intercept column, and LinearRegression finds
      huge offsetting coefficients that explode on any row whose block is all
      zeros. Categories not seen during fitting are encoded as all zeros,
      i.e. treated as the reference level, and scikit-learn warns.

    Columns not in ``features`` (e.g. the target or IDs) are dropped.

    Args:
        features: Columns to use, typically ``baseline_feature_set()`` or
            ``full_feature_set()`` from ``src.config``.
    """
    capped, uncapped, categorical = split_feature_types(features)

    capped_steps = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("cap", IQRCapper()),
            ("scale", MinMaxScaler()),
        ]
    )
    uncapped_steps = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", MinMaxScaler()),
        ]
    )
    categorical_steps = Pipeline(
        [
            ("impute", SimpleImputer(strategy="most_frequent")),
            (
                "encode",
                OneHotEncoder(
                    drop="first", handle_unknown="ignore", sparse_output=False
                ),
            ),
        ]
    )

    branches = [
        ("capped", capped_steps, capped),
        ("uncapped", uncapped_steps, uncapped),
        ("categorical", categorical_steps, categorical),
    ]
    return ColumnTransformer(
        [branch for branch in branches if branch[2]],
        remainder="drop",
        verbose_feature_names_out=False,
    )
