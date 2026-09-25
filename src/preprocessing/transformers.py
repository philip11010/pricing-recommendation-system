"""
Custom scikit-learn transformers used by the preprocessing pipeline.

Each transformer learns its parameters in ``fit`` and only applies them in
``transform``, so statistics are always taken from the training data and
reused unchanged at prediction time.
"""

import numpy as np
from sklearn.base import BaseEstimator, OneToOneFeatureMixin, TransformerMixin
from sklearn.utils.validation import check_is_fitted

from src.config import IQR_MULTIPLIER


class IQRCapper(OneToOneFeatureMixin, TransformerMixin, BaseEstimator):
    """
    Cap each column to [Q1 - k * IQR, Q3 + k * IQR].

    Bounds are learned from the data passed to ``fit`` and applied as-is to
    any later data, so a test-set value is capped using training-set bounds.
    Missing values are ignored when learning bounds and passed through
    unchanged.

    Args:
        multiplier: The ``k`` in the bounds above. 1.5 is Tukey's convention.
    """

    def __init__(self, multiplier: float = IQR_MULTIPLIER):
        self.multiplier = multiplier

    def fit(self, X, y=None):
        if self.multiplier < 0:
            raise ValueError(f"multiplier must be non-negative, got {self.multiplier}")
        X = self._validate_data(X, dtype=np.float64, force_all_finite="allow-nan")
        q1, q3 = np.nanpercentile(X, [25, 75], axis=0)
        iqr = q3 - q1
        self.lower_ = q1 - self.multiplier * iqr
        self.upper_ = q3 + self.multiplier * iqr
        return self

    def transform(self, X):
        check_is_fitted(self, ["lower_", "upper_"])
        X = self._validate_data(
            X, dtype=np.float64, force_all_finite="allow-nan", reset=False
        )
        return np.clip(X, self.lower_, self.upper_)

    def inverse_transform(self, X):
        """
        Return X unchanged.

        Capping discards the original extreme values, so it cannot be undone;
        values inside the bounds are already their originals. Defined so the
        capper can sit in the target transformer, where model predictions are
        mapped back to the price scale through every step in reverse.
        """
        check_is_fitted(self, ["lower_", "upper_"])
        return self._validate_data(
            X, dtype=np.float64, force_all_finite="allow-nan", reset=False
        )
