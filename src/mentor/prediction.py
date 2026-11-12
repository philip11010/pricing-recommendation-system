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
* **full**, those eight plus twenty-eight track-record inputs, and the
  mentor's real tenure in place of the constant the core path uses. Used once
  a mentor has a complete record. Measurably more accurate: see the metrics in
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
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT
from src.mentor.mapping import (
    COLUMN_MAX_MENTEES,
    COLUMN_SKILLS,
    CURRENCY,
    MAX_MENTEES_MAX,
    MAX_MENTEES_MIN,
    SKILL_COUNT,
    SKILL_WEIGHT,
    ModelColumnsMismatchError,
    check_model_columns,
)

APP_ASSETS_DIR = PROJECT_ROOT / "app_assets"

CORE = "core"
FULL = "full"

# ---------------------------------------------------------------------------
# The monotone envelope
#
# Two of the answers behind a price are ones a mentor can only raise by
# offering more: how many skills the service covers, and how many mentees can
# join a session. Neither is something a mentor can do more of and reasonably
# be told to charge less for.
#
# The models disagree. Breadth of offering reaches them as one number, and the
# shape they learned for it is not monotone: over some stretches of the range
# a wider offering scores slightly lower than a narrower one. The same is true
# of group size in places. Both are artefacts of what the training data
# happens to hold rather than rules anybody would defend, and they surface as
# a mentor ticking one more skill, or adding one more seat, and watching their
# suggested price fall.
#
# So a price is read off an envelope rather than off the single point the
# model returns. For one profile the service scores every combination of a
# group size up to the one asked for and a skill count up to the one chosen,
# in a single call, and takes the largest. The price at a given pair is
# therefore the best the model says about that profile at that pair or at any
# smaller one, which is non-decreasing in both by construction. Plateaus are
# expected and are the honest answer: they say the model sees no further gain,
# not that there is a loss.
#
# Because the range either side is worked out from the enveloped price rather
# than from the raw one, neither end of it can fall as a skill is ticked or a
# seat is added either.
#
# Three things this deliberately is not. It is not a retrain: the fitted
# pipelines are untouched and the correction lives in the service that reads
# them. It is not a per-skill weighting: a model is given the count and
# nothing else about which skills were chosen, so there is no evidence in the
# system for one skill being worth more than another. And it is not symmetric:
# it can only raise a price relative to the raw model, never lower one, which
# is a bias worth stating wherever these prices are reported.
#
# The fewest skills a service may offer is zero. A mentor may publish a
# service before choosing what to put in it, so zero is a real answer and the
# envelope starts there.
# ---------------------------------------------------------------------------
SKILL_COUNT_MIN = 0

ASSETS_MISSING_MESSAGE = (
    "The pricing models are not available on this server. They are build "
    "outputs rather than source, so they have to be prepared locally by "
    "running python scripts/prepare_app_assets.py before the API can serve a "
    "price."
)


class AssetsUnavailableError(RuntimeError):
    """The prepared models or their metadata could not be loaded."""


# Where the price a mentor charges today sits relative to the range the
# system advises. Three words rather than a number, because that is the whole
# of what the comparison supports: the range is a pair of residual quantiles,
# so "19 per cent into the band" would read as a precision it does not have.
POSITION_BELOW = "below"
POSITION_WITHIN = "within"
POSITION_ABOVE = "above"

POSITIONS: tuple[str, ...] = (POSITION_BELOW, POSITION_WITHIN, POSITION_ABOVE)


def position_vs_range(current_price: int, price_low: int, price_high: int) -> str:
    """
    Whether ``current_price`` falls below, within or above the advised range.

    Both ends count as within. A mentor charging exactly the low end is
    charging something the system advised, and telling them they are below it
    would be wrong.
    """
    if current_price < price_low:
        return POSITION_BELOW
    if current_price > price_high:
        return POSITION_ABOVE
    return POSITION_WITHIN


def difference_vs_current_percent(recommended_price: int, current_price: int) -> float:
    """
    How far the advice is from what the mentor charges, as a percentage of it.

    Positive means the advice is higher than the current price. Expressed
    against the current price rather than the advice because that is the
    number the mentor is being asked to change: "20 per cent more than you
    charge now" is the sentence this supports.

    One decimal place. The prices either side of it are whole currency units
    and the model behind them has an RMSE in the hundreds, so a second
    decimal would be noise rendered as detail.
    """
    if current_price <= 0:
        raise ValueError("a current price has to be a positive amount")
    return round((recommended_price - current_price) / current_price * 100, 1)


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

        A track record carries the tenure column as well as the twenty-eight
        it adds, so merging it over the service row is what replaces the
        new-mentor tenure constant with the mentor's own time on the platform.
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
        return self.predict_many([values], model_used)[0]

    def skill_count(self, values: dict[str, Any]) -> int:
        """
        How many skills the breadth-of-offering value in ``values`` stands for.

        The inverse of what the mapping layer wrote into the row, rounded
        because the column is a number, and held inside the list the form
        offers, so a stored row written by something other than this
        application cannot ask for an envelope running past the end of it.
        """
        try:
            raw = float(values[COLUMN_SKILLS])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "the row does not say how many skills the service offers"
            ) from error
        counted = int(round(raw / SKILL_WEIGHT))
        return int(min(max(counted, SKILL_COUNT_MIN), SKILL_COUNT))

    def group_size(self, values: dict[str, Any]) -> int:
        """How many mentees the session in ``values`` is for, inside the form's range."""
        try:
            raw = float(values[COLUMN_MAX_MENTEES])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "the row does not say how many mentees the session is for"
            ) from error
        return int(min(max(int(round(raw)), MAX_MENTEES_MIN), MAX_MENTEES_MAX))

    def envelope_rows(self, values: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Every smaller-or-equal service this profile is priced against.

        One row per combination of a group size from the smallest the form
        offers up to the one asked for, and a skill count from none up to the
        one chosen. The row itself is always in the list, as the largest pair.
        """
        mentees = self.group_size(values)
        count = self.skill_count(values)
        return [
            {
                **values,
                COLUMN_MAX_MENTEES: size,
                COLUMN_SKILLS: step * SKILL_WEIGHT,
            }
            for size in range(MAX_MENTEES_MIN, mentees + 1)
            for step in range(SKILL_COUNT_MIN, count + 1)
        ]

    def raw_prices_by_skill_count(
        self, values: dict[str, Any], model_used: str
    ) -> list[float]:
        """
        What the model says about one profile at every count up to its own.

        The uncorrected ladder at this profile's own group size, clipped to
        the fences and nothing else. It is public because it is what the
        envelope is an envelope *of*: a test that shows the model dipping has
        to be able to see the dip, and a second copy of this loop written
        inside a test would be measuring something other than what the service
        reads.
        """
        count = self.skill_count(values)
        ladder = [
            {**values, COLUMN_SKILLS: step * SKILL_WEIGHT}
            for step in range(SKILL_COUNT_MIN, count + 1)
        ]
        return self._raw_prices(ladder, model_used)

    def _raw_prices(
        self, rows: Sequence[dict[str, Any]], model_used: str
    ) -> list[float]:
        """Every row scored in one call, as a price inside the fences."""
        frame = self._input_frame(model_used, rows)

        # The models were trained against log1p(price), so the inverse comes
        # first and every number after it is a price.
        predicted_log = np.asarray(
            self.pipelines[model_used].predict(frame), dtype=float
        )
        return [self.clip(float(price)) for price in np.expm1(predicted_log)]

    def predict_many(
        self, rows: Sequence[dict[str, Any]], model_used: str
    ) -> list[PriceRecommendation]:
        """
        Price many rows in one pass, through the same arithmetic as one.

        :meth:`predict` is a call to this with a single row, rather than the
        other way round. Anything that has to score a large number of rows,
        such as the demonstration seed script choosing between candidates,
        would otherwise either pay for one model call per row or carry its own
        copy of the clipping and the range, and a second copy of that
        arithmetic is a second answer waiting to disagree with this one.

        This is the one place a price is decided, which is what makes
        registration, the live preview, adding a service and asking for a
        fresh price agree: all four arrive here. Each row is expanded into the
        envelope described at the top of this module, every expansion is
        scored in one call, and the row's price is the largest price in its
        own envelope. The range either side is then worked out from that
        price rather than from the raw one, so neither end of it can fall as a
        skill is ticked or a seat is added either.
        """
        if not rows:
            return []

        envelopes = [self.envelope_rows(values) for values in rows]
        prices = self._raw_prices(
            [row for envelope in envelopes for row in envelope], model_used
        )

        band = self.ranges["models"][model_used]
        low_multiplier = float(band["low_multiplier"])
        high_multiplier = float(band["high_multiplier"])

        advice = []
        read = 0
        for values, envelope in zip(rows, envelopes, strict=True):
            point = max(prices[read : read + len(envelope)])
            read += len(envelope)
            session = (
                int(round(point)),
                int(round(self.clip(point * low_multiplier))),
                int(round(self.clip(point * high_multiplier))),
            )
            mentees = int(values[COLUMN_MAX_MENTEES])
            advice.append(
                PriceRecommendation(
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
            )
        return advice

    def _input_frame(
        self, model_used: str, rows: Sequence[dict[str, Any]]
    ) -> pd.DataFrame:
        """
        The rows, holding exactly the model's columns in the model's order.

        Column order matters: the fitted ColumnTransformer selects by name but
        validates the frame it is handed, and a row assembled from a dict
        would otherwise arrive in insertion order.
        """
        columns = self.columns[model_used]
        missing = [column for column in columns if column not in rows[0]]
        if missing:
            raise ValueError(
                f"the {model_used} model needs {len(columns)} inputs and "
                f"{len(missing)} were not supplied"
            )
        return pd.DataFrame(
            [{column: values[column] for column in columns} for values in rows]
        )


def _read_json(path: Path, what: str) -> dict[str, Any]:
    if not path.exists():
        raise AssetsUnavailableError(f"{ASSETS_MISSING_MESSAGE}\nMissing: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise AssetsUnavailableError(f"{what} is not readable JSON: {path}") from error


def read_price_fences(assets_dir: Path = APP_ASSETS_DIR) -> tuple[float, float]:
    """
    The price fences the models were trained within, without loading them.

    A build script that only needs to know the range the models can be
    trusted over should not pay for two gradient-boosted pipelines to find
    out. Reading the metadata keeps the fences single-sourced either way: the
    number in the file is the number the application clips to.
    """
    model_info = _read_json(assets_dir / "model_info.json", "the model metadata")
    try:
        fences = model_info["price_fences"]
        return float(fences["lower"]), float(fences["upper"])
    except (KeyError, TypeError, ValueError) as error:
        raise AssetsUnavailableError(
            f"the model metadata does not record the price fences: "
            f"{assets_dir / 'model_info.json'}"
        ) from error


def load_pricing_service(assets_dir: Path = APP_ASSETS_DIR) -> PricingService:
    """
    Load both pipelines and their metadata from ``assets_dir``.

    Two checks before anything is served. The column list in
    ``model_info.json`` is checked against each fitted pipeline: the two come
    from the same training run, so a disagreement means the assets folder is a
    mix of two runs. Then both lists are checked against
    :mod:`src.mentor.mapping`, which is what assembles the rows: a retrained
    model that renames or reorders a column would otherwise be handed values
    under the wrong headings and would answer with a plausible but wrong price
    rather than an error.
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

    try:
        check_model_columns(columns[CORE], columns[FULL])
    except ModelColumnsMismatchError as error:
        raise AssetsUnavailableError(
            f"{error}; either rerun scripts/prepare_app_assets.py against the "
            f"training run this application was written for, or update the "
            f"column names in src/mentor/mapping.py to the retrained model's"
        ) from error

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
