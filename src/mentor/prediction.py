"""
The prediction service: two models, one advisory price with a range.

A mentor who has just registered has no track record, so there is nothing for
a model to read beyond what they typed into the form. A mentor who has been
taking sessions for a year has a great deal more. Rather than impute a
track record for the first case, the system keeps two models and picks the one
whose inputs actually exist:

* **core**, eight inputs, every one of them available at registration: six
  from the form and two held constant by the mapping layer, which explains
  why. Used for a new mentor, and flagged ``low_confidence`` because a price
  inferred from a form alone is a weaker claim than one informed by what the
  mentor has actually done.
* **full**, those eight plus twenty-eight track-record inputs. Used once a
  mentor has a record. Measurably more accurate: see the metrics in
  ``model_info.json``.

Both are loaded once at startup. They are a few megabytes each and loading per
request would dominate the response time.

The pipelines are gitignored build outputs, produced by
``scripts/prepare_app_assets.py``. A missing one is an operational fault, not
a normal state, so it fails loudly at startup rather than at the first
request.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT
from src.mentor.mapping import COLUMN_MAX_MENTEES, CURRENCY

APP_ASSETS_DIR = PROJECT_ROOT / "app_assets"

CORE = "core"
FULL = "full"

ASSETS_MISSING_MESSAGE = (
    "The pricing models are not available on this server. They are build "
    "outputs rather than source, so they have to be prepared locally by "
    "running python scripts/prepare_app_assets.py before the API can serve a "
    "price."
)


class AssetsUnavailableError(RuntimeError):
    """The prepared models or their metadata could not be loaded."""


def per_mentee(session_price: int, max_mentees: int) -> int:
    """
    What one mentee pays towards a session priced at ``session_price``.

    The model prices the session, not the seat: a group of four is one
    booking at one price. A mentor comparing a group against one-to-one work
    needs the per-seat figure as well, so it is divided out here and rounded
    to whole currency units, the same precision the session price is shown
    at.
    """
    return int(round(session_price / max_mentees))


@dataclass(frozen=True)
class PriceRecommendation:
    """
    One advisory price, the range around it, and how it was produced.

    Six figures for one price. The three ``price_*`` ones are the session:
    what the mentor charges for the booking, whoever is in it. The three
    ``price_per_mentee_*`` ones are the same three divided by the number of
    seats, which is what a mentee pays and what makes a group comparable with
    one-to-one work. They are derived, not predicted.
    """

    recommended_price: int
    price_low: int
    price_high: int
    price_per_mentee: int
    price_per_mentee_low: int
    price_per_mentee_high: int
    model_used: str
    low_confidence: bool
    model_version: str
    currency: str = CURRENCY

    def as_dict(self) -> dict[str, Any]:
        return {
            "recommended_price": self.recommended_price,
            "price_low": self.price_low,
            "price_high": self.price_high,
            "price_per_mentee": self.price_per_mentee,
            "price_per_mentee_low": self.price_per_mentee_low,
            "price_per_mentee_high": self.price_per_mentee_high,
            "currency": self.currency,
            "model_used": self.model_used,
            "low_confidence": self.low_confidence,
            "model_version": self.model_version,
        }


@dataclass(frozen=True)
class PricingService:
    """
    The loaded models plus everything needed to turn a score into advice.

    Built by :func:`load_pricing_service`, which is the only place that reads
    the filesystem, so a test can construct one from stubs instead.
    """

    pipelines: dict[str, Any]
    model_info: dict[str, Any]
    ranges: dict[str, Any]
    columns: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def model_version(self) -> str:
        return str(self.model_info["model_version"])

    @property
    def trained_at(self) -> str:
        return str(self.model_info["trained_at"])

    @property
    def price_floor(self) -> float:
        return float(self.model_info["price_fences"]["lower"])

    @property
    def price_ceiling(self) -> float:
        return float(self.model_info["price_fences"]["upper"])

    def metrics(self, model_used: str) -> dict[str, Any]:
        return dict(self.model_info["models"][model_used]["metrics"])

    def clip(self, price: float) -> float:
        """Hold a price inside the fences the models were trained within."""
        return float(min(max(price, self.price_floor), self.price_ceiling))

    def predict(
        self,
        service_inputs: dict[str, Any],
        history: dict[str, Any] | None = None,
    ) -> PriceRecommendation:
        """
        Price one service, as a session total and as a per-mentee figure.

        ``service_inputs`` and ``history`` are model columns, not mentor
        answers: the translation belongs to :mod:`src.mentor.mapping`, and
        doing it here as well would put two spellings of each question in the
        codebase. Supplying ``history`` selects the full model and drops the
        low-confidence flag; leaving it out selects the core model.
        """
        model_used = CORE if history is None else FULL
        values = (
            dict(service_inputs)
            if history is None
            else {
                **service_inputs,
                **history,
            }
        )
        frame = self._input_frame(model_used, values)

        # The models were trained against log1p(price), so the inverse comes
        # first and every number after it is a price.
        predicted_log = float(self.pipelines[model_used].predict(frame)[0])
        point = self.clip(float(np.expm1(predicted_log)))

        band = self.ranges["models"][model_used]
        low = self.clip(point * float(band["low_multiplier"]))
        high = self.clip(point * float(band["high_multiplier"]))

        session = (int(round(point)), int(round(low)), int(round(high)))
        mentees = int(values[COLUMN_MAX_MENTEES])

        return PriceRecommendation(
            recommended_price=session[0],
            price_low=session[1],
            price_high=session[2],
            price_per_mentee=per_mentee(session[0], mentees),
            price_per_mentee_low=per_mentee(session[1], mentees),
            price_per_mentee_high=per_mentee(session[2], mentees),
            model_used=model_used,
            low_confidence=model_used == CORE,
            model_version=self.model_version,
        )

    def _input_frame(self, model_used: str, values: dict[str, Any]) -> pd.DataFrame:
        """
        One row, holding exactly the model's columns in the model's order.

        Column order matters: the fitted ColumnTransformer selects by name but
        validates the frame it is handed, and a row assembled from a dict
        would otherwise arrive in insertion order.
        """
        columns = self.columns[model_used]
        missing = [column for column in columns if column not in values]
        if missing:
            raise ValueError(
                f"the {model_used} model needs {len(columns)} inputs and "
                f"{len(missing)} were not supplied"
            )
        return pd.DataFrame([{column: values[column] for column in columns}])


def _read_json(path: Path, what: str) -> dict[str, Any]:
    if not path.exists():
        raise AssetsUnavailableError(f"{ASSETS_MISSING_MESSAGE}\nMissing: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise AssetsUnavailableError(f"{what} is not readable JSON: {path}") from error


def load_pricing_service(assets_dir: Path = APP_ASSETS_DIR) -> PricingService:
    """
    Load both pipelines and their metadata from ``assets_dir``.

    The column list in ``model_info.json`` is checked against each fitted
    pipeline. The two come from the same training run, so a disagreement means
    the assets folder is a mix of two runs, which would otherwise show up as a
    plausible but wrong price.
    """
    model_info = _read_json(assets_dir / "model_info.json", "the model metadata")
    ranges = _read_json(assets_dir / "ranges.json", "the price ranges")

    pipelines: dict[str, Any] = {}
    columns: dict[str, tuple[str, ...]] = {}
    for model_used in (CORE, FULL):
        try:
            spec = model_info["models"][model_used]
        except KeyError as error:
            raise AssetsUnavailableError(
                f"the model metadata has no entry for the {model_used} model"
            ) from error
        if model_used not in ranges.get("models", {}):
            raise AssetsUnavailableError(
                f"the price ranges file has no entry for the {model_used} model"
            )

        path = assets_dir / spec["file"]
        if not path.exists():
            raise AssetsUnavailableError(f"{ASSETS_MISSING_MESSAGE}\nMissing: {path}")
        pipeline = joblib.load(path)
        declared = tuple(str(column) for column in spec["input_columns"])
        fitted = tuple(
            str(column)
            for column in pipeline.named_steps["preprocess"].feature_names_in_
        )
        if declared != fitted:
            raise AssetsUnavailableError(
                f"the {model_used} model was fitted on {len(fitted)} columns "
                f"that do not match the {len(declared)} columns recorded in "
                f"model_info.json; rerun scripts/prepare_app_assets.py"
            )
        pipelines[model_used] = pipeline
        columns[model_used] = declared

    return PricingService(
        pipelines=pipelines, model_info=model_info, ranges=ranges, columns=columns
    )


@lru_cache(maxsize=1)
def get_pricing_service() -> PricingService:
    """
    The process-wide service, loaded on first use.

    Cached rather than built at import time so that importing the application
    does not read the filesystem, which matters for tests that run without
    prepared assets.
    """
    return load_pricing_service()
