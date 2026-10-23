"""
Reading the training reports the serving layer displays.

``src.models.train`` writes a timestamped JSON report per run. Two things in
it are worth showing on the dashboard:

- the comparison of all three candidate models, which is what justifies the
  model being served rather than one of the others;
- the tree feature importances, used to decide which inputs the form shows
  first, so a demo is not 20 numeric boxes deep before anything interesting.

Both are presentation concerns, so a missing or unreadable report degrades to
an empty result rather than an error: ``reports/`` is gitignored, and the app
must still serve predictions on a checkout that has none.

Importances in the report are per encoded column, so ``room_type`` appears as
``room_type_Private room`` and the like. :func:`raw_feature_ranking` folds
those back onto the raw input columns the form actually asks for.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import REPORTS_DIR

REPORT_GLOB = "training_report_*.json"


def latest_report_path(report_dir: Path = REPORTS_DIR) -> Path | None:
    """
    The newest report file, or None if there is none.

    Chosen by filename rather than modification time: the names carry a
    sortable ``YYYYmmdd_HHMMSS`` stamp, and a file copied between machines
    keeps its name but not its mtime.
    """
    if not report_dir.is_dir():
        return None
    reports = sorted(report_dir.glob(REPORT_GLOB))
    return reports[-1] if reports else None


def load_latest_report(report_dir: Path = REPORTS_DIR) -> dict[str, Any] | None:
    """
    Parse the newest report, or return None if absent or unreadable.

    A malformed report is a display problem, not a reason to refuse to serve,
    so it is treated the same as a missing one.
    """
    path = latest_report_path(report_dir)
    if path is None:
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return report if isinstance(report, dict) else None


def comparison_rows(
    report: dict[str, Any] | None, selected_model: str | None = None
) -> list[dict[str, Any]]:
    """
    One row per candidate model, ordered by the report's selection metric.

    Args:
        report: A parsed report, or None.
        selected_model: Name of the model being served, marked in the output.
            Defaults to the report's own best model.

    Returns:
        ``[{"model_name", "rmse_dollars", "mae_dollars", "r2_dollars",
        "is_selected"}, ...]``, empty if the report has no results.
    """
    if not report:
        return []

    results = report.get("results") or []
    metric = str(report.get("selection_metric", "rmse_dollars"))
    selected = selected_model or report.get("best_model")

    rows = []
    for result in results:
        metrics = result.get("metrics") or {}
        name = str(result.get("model", ""))
        rows.append(
            {
                "model_name": name,
                "rmse_dollars": _as_float(metrics.get("rmse_dollars")),
                "mae_dollars": _as_float(metrics.get("mae_dollars")),
                "r2_dollars": _as_float(metrics.get("r2_dollars")),
                "is_selected": name == selected,
            }
        )
    return sorted(rows, key=lambda row: row[metric] if metric in row else float("inf"))


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def raw_feature_ranking(
    report: dict[str, Any] | None, input_columns: list[str]
) -> list[str]:
    """
    Input columns ordered by how much the tree models relied on them.

    Importances from every model that reports them are summed, after each
    model's are normalised to sum to 1. Using both trees rather than only the
    selected one gives a steadier ordering and better coverage: the report
    keeps the top 15 encoded columns per model, and the two models' top 15
    overlap only partly.

    One-hot levels are folded back onto their source column, so the total for
    ``neighbourhood_cleansed`` is the sum over its levels. That is the right
    comparison for a form, where the user picks one value for the whole
    column.

    Returns:
        Columns in descending order of importance. Columns the report says
        nothing about are omitted, so the caller decides what to do with the
        remainder.
    """
    if not report:
        return []

    totals: dict[str, float] = {}
    for result in report.get("results") or []:
        importances = result.get("feature_importances")
        if not importances:
            continue
        scale = sum(abs(_as_float(item.get("importance"))) for item in importances)
        if not scale:
            continue
        for item in importances:
            column = _source_column(str(item.get("feature", "")), input_columns)
            if column is None:
                continue
            share = abs(_as_float(item.get("importance"))) / scale
            totals[column] = totals.get(column, 0.0) + share

    return sorted(totals, key=lambda column: (-totals[column], column))


def _source_column(encoded: str, input_columns: list[str]) -> str | None:
    """
    Map an encoded column name back to the input column it came from.

    An exact match wins, so ``number_of_reviews`` is never mistaken for a
    one-hot level of something else. Otherwise the longest ``column_`` prefix
    wins, which resolves a one-hot level whose own value contains an
    underscore.
    """
    if encoded in input_columns:
        return encoded
    candidates = [
        column for column in input_columns if encoded.startswith(f"{column}_")
    ]
    return max(candidates, key=len) if candidates else None
