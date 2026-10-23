"""
Prediction service: load the selected pipeline and turn one input into a price.

The artefact written by ``src.models.train`` is a complete scikit-learn
``Pipeline``, so nothing here repeats any preprocessing. The only work is to
present one row in the column order the pipeline was fitted on, and to undo
the log transform the model was trained against.

Loading is explicit rather than lazy, so the application can decide what to
do about a missing artefact at startup instead of failing on the first
request. ``models_store/`` is gitignored, so a fresh clone has no model until
``python -m src.models.train`` has been run; that is a normal state, not a
bug, and :class:`ModelUnavailableError` describes it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.config import MODEL_STORE_DIR
from src.models.train import (
    BEST_METADATA_FILENAME,
    BEST_MODEL_FILENAME,
    DATA_SOURCE,
    TARGET_DESCRIPTION,
)

# Shown to the user when the artefact is absent. Phrased as an instruction,
# because the fix is a command the project owner can run.
MODEL_UNAVAILABLE_MESSAGE = (
    "No trained model is available. Model artefacts are not committed to the "
    "repository, so they must be produced locally by running "
    "python -m src.models.train before the prediction flow can be used."
)


class ModelUnavailableError(RuntimeError):
    """Raised when the saved pipeline or its metadata cannot be loaded."""


@dataclass(frozen=True)
class LoadedModel:
    """
    A fitted pipeline together with the metadata describing its input.

    The metadata is what lets the serving layer build its form and validate
    against the training data without hard-coding anything the training run
    already recorded.
    """

    pipeline: Any
    metadata: dict[str, Any]

    @property
    def model_name(self) -> str:
        return str(self.metadata.get("model_name", "unknown"))

    @property
    def input_columns(self) -> list[str]:
        """Raw columns the caller must supply, in training order."""
        return [str(column) for column in self.metadata.get("input_columns", [])]

    @property
    def categorical_choices(self) -> dict[str, list[str]]:
        choices = self.metadata.get("categorical_choices", {})
        return {str(k): [str(v) for v in values] for k, values in choices.items()}

    @property
    def numeric_ranges(self) -> dict[str, dict[str, float]]:
        ranges = self.metadata.get("numeric_ranges", {})
        return {
            str(column): {"min": float(bounds["min"]), "max": float(bounds["max"])}
            for column, bounds in ranges.items()
        }

    @property
    def numeric_medians(self) -> dict[str, float]:
        """
        Training-split median per numeric column, for pre-filling the form.

        Empty for metadata written before the serving layer, so a caller must
        treat an absent column as "no default available" rather than assuming
        zero.
        """
        medians = self.metadata.get("numeric_medians", {})
        return {str(column): float(value) for column, value in medians.items()}

    @property
    def categorical_modes(self) -> dict[str, str]:
        """Most common training value per categorical column."""
        modes = self.metadata.get("categorical_modes", {})
        return {str(column): str(value) for column, value in modes.items()}

    @property
    def data_source(self) -> str:
        return str(self.metadata.get("data_source", DATA_SOURCE))

    @property
    def target(self) -> str:
        return str(self.metadata.get("target", TARGET_DESCRIPTION))

    @property
    def trained_at(self) -> str:
        return str(self.metadata.get("trained_at", "unknown"))

    @property
    def metrics(self) -> dict[str, float]:
        metrics = self.metadata.get("metrics", {})
        return {str(k): float(v) for k, v in metrics.items()}

    @property
    def typical_error_dollars(self) -> float | None:
        """
        Test-set MAE, the figure to quote as the error on one prediction.

        MAE is the mean of the absolute errors, so "about this much out" is a
        fair reading of it. RMSE squares the errors first, which on this data
        makes it roughly four times larger: a handful of listings up to
        $52,850 dominate it, and a log-scale model never predicts those. RMSE
        is the right criterion for ranking models against each other, and the
        wrong number to hand a user as the expected miss on their own price.
        """
        mae = self.metrics.get("mae_dollars")
        return float(mae) if mae is not None else None

    @property
    def model_comparison(self) -> list[dict[str, Any]]:
        """
        Every candidate model with its test metrics, best first.

        Read from the ``all_models`` block the training run recorded, so the
        comparison shown is the one that selected this model. Ordered by the
        selection metric, which is dollar RMSE.
        """
        all_models = self.metadata.get("all_models", {})
        selection_metric = str(self.metadata.get("selection_metric", "rmse_dollars"))

        rows = [
            {
                "model_name": str(name),
                "rmse_dollars": float(metrics.get("rmse_dollars", float("nan"))),
                "mae_dollars": float(metrics.get("mae_dollars", float("nan"))),
                "r2_dollars": float(metrics.get("r2_dollars", float("nan"))),
                "is_selected": str(name) == self.model_name,
            }
            for name, metrics in all_models.items()
        ]
        return sorted(rows, key=lambda row: row.get(selection_metric, float("inf")))


def load_best_model(model_dir: Path = MODEL_STORE_DIR) -> LoadedModel:
    """
    Load ``best_model.joblib`` and its metadata from ``model_dir``.

    Raises:
        ModelUnavailableError: If either file is missing, unreadable, or the
            metadata does not describe the pipeline's input columns. A
            metadata file without ``input_columns`` predates the serving
            layer, and a prediction built from guessed column order would be
            silently wrong, so it is refused rather than worked around.
    """
    model_path = model_dir / BEST_MODEL_FILENAME
    metadata_path = model_dir / BEST_METADATA_FILENAME

    for path in (model_path, metadata_path):
        if not path.exists():
            raise ModelUnavailableError(f"{MODEL_UNAVAILABLE_MESSAGE} Missing: {path}")

    try:
        pipeline = joblib.load(model_path)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as error:  # corrupt artefact, version mismatch, bad JSON
        raise ModelUnavailableError(
            f"{MODEL_UNAVAILABLE_MESSAGE} Loading failed: {error}"
        ) from error

    loaded = LoadedModel(pipeline=pipeline, metadata=metadata)
    if not loaded.input_columns:
        raise ModelUnavailableError(
            f"{metadata_path} does not list input_columns, so the column order "
            "the pipeline expects is unknown. Re-run python -m src.models.train."
        )
    return loaded


def try_load_best_model(model_dir: Path = MODEL_STORE_DIR) -> LoadedModel | None:
    """
    Load the model, or return None if it is unavailable.

    Used at startup so the application still boots, serves its health check
    and explains itself when no model has been trained yet.
    """
    try:
        return load_best_model(model_dir)
    except ModelUnavailableError:
        return None


def build_input_frame(model: LoadedModel, values: dict[str, Any]) -> pd.DataFrame:
    """
    Build the one-row frame the pipeline expects.

    Columns are taken from the metadata, in training order. A value the caller
    omitted becomes NaN, which the pipeline's imputers handle exactly as they
    did during training. Keys that are not input columns are dropped: the
    pipeline would ignore them anyway, and passing them through would make the
    frame's column order depend on the caller.
    """
    row = {column: values.get(column, np.nan) for column in model.input_columns}
    return pd.DataFrame([row], columns=model.input_columns)


def predict_price(model: LoadedModel, values: dict[str, Any]) -> float:
    """
    Predict one advisory price, in dollars, rounded to 2 decimals.

    The pipeline predicts on the log scale it was trained on, so the result is
    converted back with ``exp``.

    Raises:
        ValueError: If the pipeline returns a non-finite or non-positive
            price. That cannot be shown to a user as advice, and it means the
            input is far outside anything the model was fitted on.
    """
    frame = build_input_frame(model, values)
    log_price = float(np.asarray(model.pipeline.predict(frame), dtype=float)[0])
    price = float(np.exp(log_price))

    if not np.isfinite(price) or price <= 0:
        raise ValueError(
            f"model produced an unusable price ({price!r}) from log value "
            f"{log_price!r}"
        )
    return round(price, 2)
