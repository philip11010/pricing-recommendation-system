"""
The operations dashboard: six read-only endpoints under /admin.

What this is for. Everything else in this API answers a question about one
mentor. These six answer questions about the service itself: how much it is
being asked to do, which model is answering, how long it takes, what it has
been advising, and how the two models scored on the rows they were held back
from. None of that can be read off the mentor-facing endpoints, and until the
request log existed none of it was recorded at all.

Four rules hold across the whole module.

**Read only.** Six GETs, no bodies, no writes. An administration page that can
change a mentor's price or verify an account would make the advisory design a
claim rather than a property of the system, and nothing here needs to.

**One gate.** Every endpoint depends on
:func:`src.mentor.dependencies.require_admin`, declared once on the router so
a new endpoint cannot be added without it. 401 with no usable token, 403 for a
signed-in account that is not an administrator.

**Nothing personal leaves.** No name, no address, no free text, and no mentor
id: the aggregates are counts and the activity list is the request log without
its one identifier. An administrator reading this page learns what the service
did, not who it did it for. The one place that could leak by accident is
/admin/models, which reads a training report that holds the internal column
names of the models, so it returns a whitelist of named fields and never the
document it read them from.

**Aggregated in Python, deliberately.** Grouping by day, medians and the 95th
percentile are all computed here rather than in SQL. SQLite has no percentile
function and the two backends spell date truncation differently, so a portable
SQL version would be two dialects of a query to save pulling a few thousand
integers over a connection on a page one person opens. The row counts this
reads are bounded by the window: thirty days of the log, and the stored
recommendations.

**Gaps are filled.** The daily and weekly series return every day and every
week in the window, including the ones with nothing in them. A chart drawn
from only the days that had traffic draws a continuous line across a
three-day outage.
"""

from __future__ import annotations

import json
import logging
import statistics
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.config import PROJECT_ROOT
from src.db import get_session
from src.db.mentor_models import (
    DECISION_ACTIONS,
    LOG_ENDPOINTS,
    Mentor,
    PricingDecision,
    PricingRecommendation,
    RequestLog,
    Service,
)
from src.mentor import mapping
from src.mentor.admin_schemas import (
    AdminEvent,
    AdminModelCard,
    AdminModelsOut,
    AdminOutputsOut,
    AdminRecentOut,
    AdminSignupsOut,
    AdminSummaryOut,
    AdminUsageOut,
    DecisionCounts,
    FieldOutputs,
    HistogramBucket,
    LabelledCount,
    LatencyDay,
    ModelMetric,
    ModelShare,
    RangeWidths,
    SignupWeek,
    UsageDay,
)
from src.mentor.dependencies import require_admin
from src.mentor.prediction import APP_ASSETS_DIR, CORE, FULL

logger = logging.getLogger(__name__)

# How far back each series reaches. Thirty days of calls is a month of
# operation, which is long enough to see a pattern and short enough to draw
# as one bar per day on a phone. Twelve weeks of sign-ups is a quarter, which
# is the shortest window in which a weekly count means anything.
USAGE_DAYS = 30
SIGNUP_WEEKS = 12

# How many events the activity table holds. Fifty is a screenful that can be
# scrolled rather than paged, and the dashboard has the aggregates for
# anything longer.
RECENT_DEFAULT = 50
RECENT_MAX = 200

# Where the held-out scores are read from. Git-ignored, because it is an
# output of a local training run, so a fresh clone legitimately has none.
MODEL_REPORT = PROJECT_ROOT / "reports" / "model_results.json"

# The deployed build output, read for the file names and the dates only.
MODEL_INFO = APP_ASSETS_DIR / "model_info.json"

ENDPOINT_LABELS: dict[str, str] = {
    "preview": "Registration preview",
    "registration": "Registration",
    "service_added": "Service added",
    "recalculation": "Price recalculated",
}

MODEL_LABELS: dict[str, str] = {CORE: "Core model", FULL: "Full model"}

MODEL_INPUT_NOTES: dict[str, str] = {
    CORE: (
        "Eight profile inputs, every one of them available the moment a "
        "mentor registers. Used for a mentor with no track record, and the "
        "price it gives is marked low confidence."
    ),
    FULL: (
        "The same eight profile inputs plus twenty-eight track record "
        "inputs, and the mentor's own time on the platform in place of the "
        "constant the core model is given. Used once a mentor has a complete "
        "record."
    ),
}

# Which feature set in the training report each deployed model was fitted on.
MODEL_FEATURE_SETS: dict[str, str] = {CORE: "core", FULL: "full"}

# ---------------------------------------------------------------------------
# The whitelist
#
# The training report is a long document that holds, among much else, the
# internal column names the models were fitted on. Those names belong to the
# training data and never appear in anything the application serves, so this
# endpoint names the five figures it will return and reads nothing else. A
# field added to the report later is not served by accident, and a field
# renamed in it shows up as a missing metric rather than as a leak.
#
# Each entry is: the id the response uses, the label the page prints, the key
# in the report, and the scale, which says what the figure is measured in and
# which direction is better. A figure without its direction is one a reader
# can only guess at.
# ---------------------------------------------------------------------------
METRIC_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    (
        "r2",
        "R squared",
        "r2_typical",
        "0 to 1, higher is better",
    ),
    (
        "rmse_log",
        "Log RMSE",
        "rmse_log_typical",
        "log price units, lower is better",
    ),
    (
        "mae",
        "MAE",
        "mae_aud_typical",
        f"{mapping.CURRENCY}, lower is better",
    ),
    (
        "rmse",
        "RMSE",
        "rmse_aud_typical",
        f"{mapping.CURRENCY}, lower is better",
    ),
    (
        "cv_rmse_log",
        "Cross-validated log RMSE",
        "cv_rmse_log_mean",
        "log price units, lower is better, mean of 10 folds",
    ),
)

MEASURED_ON = "the held-out typical test rows, which no model was fitted on"

CROSS_VALIDATION = (
    "10-fold cross-validation on the training rows, the same folds for every "
    "model, scored on the log of the price"
)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    # Declared on the router rather than on each endpoint, so an endpoint
    # added later is behind the gate whether or not whoever added it
    # remembered to say so.
    dependencies=[Depends(require_admin)],
    responses={
        401: {"description": "No usable access token was sent."},
        403: {"description": "The account is signed in and is not an administrator."},
    },
)


# ---------------------------------------------------------------------------
# Small shared arithmetic
# ---------------------------------------------------------------------------
def percent(part: int, whole: int) -> float | None:
    """``part`` as a percentage of ``whole``, or None when there is no whole."""
    if whole <= 0:
        return None
    return round(part * 100 / whole, 1)


def median_int(values: list[int]) -> int | None:
    """The median of some integers, rounded, or None for an empty list."""
    if not values:
        return None
    return int(round(statistics.median(values)))


def percentile_int(values: list[int], share: float) -> int | None:
    """
    A percentile by nearest rank, which is the honest method on few points.

    Nearest rank rather than interpolated: an interpolated 95th percentile of
    four measurements is a number between two of them that nothing measured,
    and this page reports days that may hold four calls. The rank method
    returns one of the observations, so the figure is always a duration the
    service actually took.
    """
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, min(len(ordered), -(-int(len(ordered) * share * 100) // 100)))
    return ordered[rank - 1]


def field_label_of(field: str | None) -> str | None:
    """
    The label for a stored field id, falling back to the id itself.

    A stored id that the mapping no longer knows is a renamed field rather
    than a reason for this page to fail, and an administrator reading an old
    row is better served by the raw id than by a 500.
    """
    if field is None:
        return None
    try:
        return mapping.field_label(field)
    except Exception:  # noqa: BLE001 - a renamed field id, see the docstring
        return field


def bucket_step(spread: int) -> int:
    """
    A readable bar width for a histogram of that spread.

    The smallest step from a fixed ladder that keeps the chart under about a
    dozen bars. A step chosen as spread divided by a bar count gives widths
    like 37, and a reader cannot hold "300 to 337" in their head.
    """
    for step in (10, 25, 50, 100, 200, 250, 500, 1000):
        if spread <= step * 12:
            return step
    return 2000


def histogram(values: list[int]) -> list[HistogramBucket]:
    """
    Values as half-open buckets, ``low`` included and ``high`` excluded.

    Every bucket between the lowest and the highest value is returned, empty
    ones included, so a gap in the middle of the distribution is drawn as a
    gap rather than closed up.
    """
    if not values:
        return []
    step = bucket_step(max(values) - min(values))
    lowest = (min(values) // step) * step
    highest = (max(values) // step) * step + step
    counts = Counter(((value - lowest) // step) for value in values)
    return [
        HistogramBucket(
            low=lowest + index * step,
            high=lowest + (index + 1) * step,
            count=counts.get(index, 0),
        )
        for index in range((highest - lowest) // step)
    ]


def day_of(moment: datetime) -> date:
    """
    Which UTC day a timestamp falls in.

    UTC and not a local day, because the application stores UTC and a series
    bucketed by the server's local day would shift under it twice a year.
    """
    return moment.astimezone(UTC).date()


def week_of(moment: datetime) -> date:
    """The Monday of the UTC week a timestamp falls in."""
    day = day_of(moment)
    return day - timedelta(days=day.weekday())


def decision_counts(by_action: dict[str, int], pending: int = 0) -> DecisionCounts:
    """
    The three actions, their total, and the share that were accepted.

    The rate is null rather than zero when nobody has decided anything: a
    platform whose advice nobody has answered has no acceptance rate, and a
    zero would read as advice that everyone rejected.
    """
    counts = {action: int(by_action.get(action, 0)) for action in DECISION_ACTIONS}
    total = sum(counts.values())
    return DecisionCounts(
        **counts,
        total=total,
        acceptance_rate_percent=percent(counts["accepted"], total),
        pending=pending,
    )


def count_of(session: Session, model: Any, *where) -> int:
    """One scalar count, as a plain integer."""
    statement = select(func.count()).select_from(model)
    if where:
        statement = statement.where(*where)
    return int(session.scalar(statement) or 0)


def decisions_by_action(session: Session) -> dict[str, int]:
    """How many decisions of each kind have been recorded."""
    rows = session.execute(
        select(PricingDecision.action, func.count()).group_by(PricingDecision.action)
    ).all()
    return {str(action): int(total) for action, total in rows}


# ---------------------------------------------------------------------------
# /admin/summary
# ---------------------------------------------------------------------------
@router.get(
    "/summary",
    response_model=AdminSummaryOut,
    summary="The counts the dashboard opens with",
)
async def read_summary(session: Session = Depends(get_session)) -> AdminSummaryOut:
    """
    How much is on the platform, and how busy it has been.

    "Accounts" is every row and "mentors" is every account that is not an
    administrator, because an administrator account exists to read this page
    and is not somebody the platform prices. The demonstration mentors are
    counted separately for the same reason: they are real rows that went
    through the real flow, and a reader deciding whether the platform has ten
    mentors or none needs to know which of the two they are looking at.
    """
    pending = count_of(
        session, PricingRecommendation, PricingRecommendation.status == "pending"
    )
    durations = [
        int(value)
        for value in session.scalars(select(RequestLog.response_ms)).all()
        if value is not None
    ]
    since = datetime.now(UTC) - timedelta(hours=24)

    return AdminSummaryOut(
        accounts=count_of(session, Mentor),
        mentors=count_of(session, Mentor, Mentor.is_admin.is_(False)),
        verified_mentors=count_of(
            session, Mentor, Mentor.is_admin.is_(False), Mentor.verified.is_(True)
        ),
        demo_mentors=count_of(session, Mentor, Mentor.is_demo.is_(True)),
        services=count_of(session, Service),
        recommendations=count_of(session, PricingRecommendation),
        decisions=decision_counts(decisions_by_action(session), pending=pending),
        requests_last_24h=count_of(session, RequestLog, RequestLog.created_at >= since),
        median_response_ms=median_int(durations),
        logged_requests=len(durations),
    )


# ---------------------------------------------------------------------------
# /admin/usage
# ---------------------------------------------------------------------------
@router.get(
    "/usage",
    response_model=AdminUsageOut,
    summary="Calls per day, by path, and how long they took",
)
async def read_usage(
    days: int = Query(
        default=USAGE_DAYS,
        ge=1,
        le=365,
        description="How many days back the daily series reaches.",
    ),
    session: Session = Depends(get_session),
) -> AdminUsageOut:
    """
    What the service has been asked to do, over the window and in total.

    The daily series is split by which model answered, and carries a third
    count for the calls that reached no model at all: a refused preview, or a
    request for a record that was not the caller's. Leaving those out would
    show a quiet server at the moment it was refusing everything, and folding
    them into either model would attribute work to a model that did none.

    ``by_endpoint`` and ``model_share`` are over the same window as the
    series, not over all time, so every figure on the page is about the same
    stretch of days.
    """
    today = datetime.now(UTC).date()
    first = today - timedelta(days=days - 1)
    window = [first + timedelta(days=offset) for offset in range(days)]

    rows = session.execute(
        select(
            RequestLog.created_at,
            RequestLog.endpoint,
            RequestLog.model_used,
            RequestLog.response_ms,
        ).where(
            RequestLog.created_at >= datetime.combine(first, datetime.min.time(), UTC)
        )
    ).all()

    per_day: dict[date, Counter[str]] = defaultdict(Counter)
    latencies: dict[date, list[int]] = defaultdict(list)
    endpoints: Counter[str] = Counter()
    models: Counter[str] = Counter()

    for created_at, endpoint, model_used, response_ms in rows:
        day = day_of(created_at)
        if day < first or day > today:
            continue
        key = model_used if model_used in (CORE, FULL) else "no_model"
        per_day[day][key] += 1
        latencies[day].append(int(response_ms))
        endpoints[str(endpoint)] += 1
        models[key] += 1

    total = sum(models.values())

    return AdminUsageOut(
        days=days,
        per_day=[
            UsageDay(
                day=day,
                core=per_day[day].get(CORE, 0),
                full=per_day[day].get(FULL, 0),
                no_model=per_day[day].get("no_model", 0),
                total=sum(per_day[day].values()),
            )
            for day in window
        ],
        by_endpoint=[
            LabelledCount(
                id=endpoint,
                label=ENDPOINT_LABELS.get(endpoint, endpoint),
                count=endpoints.get(endpoint, 0),
            )
            for endpoint in LOG_ENDPOINTS
        ],
        # Only the days that had calls. A median of nothing is not zero
        # milliseconds, and a line plotted through zeros on the quiet days
        # would say the service answered instantly on the days it answered
        # nothing at all.
        latency_per_day=[
            LatencyDay(
                day=day,
                median_ms=median_int(latencies[day]) or 0,
                p95_ms=percentile_int(latencies[day], 0.95) or 0,
                requests=len(latencies[day]),
            )
            for day in window
            if latencies[day]
        ],
        model_share=ModelShare(
            core=models.get(CORE, 0),
            full=models.get(FULL, 0),
            no_model=models.get("no_model", 0),
            total=total,
            core_percent=percent(models.get(CORE, 0), total),
            full_percent=percent(models.get(FULL, 0), total),
        ),
    )


# ---------------------------------------------------------------------------
# /admin/outputs
# ---------------------------------------------------------------------------
@router.get(
    "/outputs",
    response_model=AdminOutputsOut,
    summary="What the models advised, and what mentors did about it",
)
async def read_outputs(session: Session = Depends(get_session)) -> AdminOutputsOut:
    """
    The distribution of the advice itself.

    Built from the stored recommendations rather than from the request log,
    and that choice is the whole shape of this endpoint: a recommendation is
    advice a mentor was offered and can answer, while a preview is a figure
    on a form that nobody has submitted. Counting previews here would let a
    page being filled in slowly move the distribution of what the platform
    advises.

    The range widths are reported beside the prices because the range is what
    a mentor acts within. A range half as wide as the price is a different
    statement from one a tenth as wide, and nothing else on the dashboard
    would show it.
    """
    rows = session.execute(
        select(
            PricingRecommendation.recommended_price,
            PricingRecommendation.price_low,
            PricingRecommendation.price_high,
            Service.field,
        ).join(Service, Service.id == PricingRecommendation.service_id)
    ).all()

    prices = [int(price) for price, _, _, _ in rows]
    widths = [int(high) - int(low) for _, low, high, _ in rows]
    width_shares = [
        (int(high) - int(low)) * 100 / int(price)
        for price, low, high, _ in rows
        if int(price) > 0
    ]

    by_field: dict[str, list[int]] = defaultdict(list)
    for price, _, _, field in rows:
        by_field[str(field)].append(int(price))

    pending = count_of(
        session, PricingRecommendation, PricingRecommendation.status == "pending"
    )

    return AdminOutputsOut(
        recommendations=len(rows),
        currency=mapping.CURRENCY,
        price_buckets=histogram(prices),
        median_price=median_int(prices),
        by_field=sorted(
            (
                FieldOutputs(
                    id=field,
                    label=field_label_of(field) or field,
                    count=len(found),
                    median_price=median_int(found),
                )
                for field, found in by_field.items()
            ),
            key=lambda item: (-item.count, item.label),
        ),
        decisions=decision_counts(decisions_by_action(session), pending=pending),
        range_widths=RangeWidths(
            median=median_int(widths),
            median_percent_of_price=(
                round(statistics.median(width_shares), 1) if width_shares else None
            ),
            buckets=histogram(widths),
        ),
    )


# ---------------------------------------------------------------------------
# /admin/signups
# ---------------------------------------------------------------------------
@router.get(
    "/signups",
    response_model=AdminSignupsOut,
    summary="New accounts per week, verified against not",
)
async def read_signups(
    weeks: int = Query(
        default=SIGNUP_WEEKS,
        ge=1,
        le=104,
        description="How many weeks back the series reaches.",
    ),
    session: Session = Depends(get_session),
) -> AdminSignupsOut:
    """
    How many mentors joined, and how many of them have been checked.

    Administrator accounts are left out of every figure here. An
    administrator is created by a script run by whoever administers the
    deployment, so counting one as a sign-up would put a line on the chart for
    an act of configuration.

    Weekly rather than daily, because a sign-up series on a platform this size
    is mostly zeros at daily resolution and a week is the shortest bucket in
    which the count says anything. The verified split is as the accounts stand
    now rather than as they stood that week: the platform records that a
    mentor was checked and not when, so a historical split would be invented.
    """
    today = datetime.now(UTC).date()
    this_week = today - timedelta(days=today.weekday())
    window = [
        this_week - timedelta(weeks=offset) for offset in range(weeks - 1, -1, -1)
    ]

    rows = session.execute(
        select(Mentor.created_at, Mentor.verified).where(Mentor.is_admin.is_(False))
    ).all()

    per_week: dict[date, Counter[str]] = defaultdict(Counter)
    verified = 0
    for created_at, is_verified in rows:
        if is_verified:
            verified += 1
        per_week[week_of(created_at)]["verified" if is_verified else "unverified"] += 1

    return AdminSignupsOut(
        weeks=weeks,
        per_week=[
            SignupWeek(
                week=week,
                accounts=sum(per_week[week].values()),
                verified=per_week[week].get("verified", 0),
                unverified=per_week[week].get("unverified", 0),
            )
            for week in window
        ],
        accounts=len(rows),
        verified=verified,
        unverified=len(rows) - verified,
    )


# ---------------------------------------------------------------------------
# /admin/models
# ---------------------------------------------------------------------------
def read_json_file(path: Path, what: str) -> dict[str, Any] | None:
    """
    One JSON document, or None with a warning line.

    Both documents this endpoint reads are git-ignored outputs of a local
    build, so a missing one is the normal state of a fresh clone rather than a
    fault. A malformed one is a fault, and it is reported the same way,
    because the correct behaviour for this page is identical either way: say
    the scores are not available and serve the rest.
    """
    try:
        with path.open(encoding="utf-8") as handle:
            loaded = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("could not read %s at %s: %s", what, path, error)
        return None
    return loaded if isinstance(loaded, dict) else None


def metrics_from(record: Any) -> list[ModelMetric]:
    """
    The five whitelisted scores, each with the scale it is measured on.

    A key the report does not carry is skipped rather than sent as zero: a
    missing score is a report from a different version of the training
    script, and a zero R squared is a claim about the model.
    """
    if not isinstance(record, dict):
        return []
    found: list[ModelMetric] = []
    for metric_id, label, key, scale in METRIC_FIELDS:
        value = record.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            found.append(
                ModelMetric(
                    id=metric_id,
                    label=label,
                    # Six places keeps a log RMSE readable and an R squared
                    # exact. The page decides how many to print.
                    value=round(float(value), 6),
                    scale=scale,
                )
            )
    return found


def deployed_files() -> dict[str, dict[str, Any]]:
    """
    The file name and fit date of each deployed model, and nothing else.

    Read straight from the build output rather than through the loaded
    pricing service, so this page still names the files on a server whose
    models failed to load, which is exactly when somebody is looking at it.

    Two keys are taken from each entry. The same document also holds the
    models' internal input column names, which belong to the training data
    and appear nowhere this application serves, so nothing else is read out
    of it.
    """
    info = read_json_file(MODEL_INFO, "the deployed model metadata")
    models = info.get("models") if isinstance(info, dict) else None
    if not isinstance(models, dict):
        return {}
    found: dict[str, dict[str, Any]] = {}
    for name in (CORE, FULL):
        record = models.get(name)
        if not isinstance(record, dict):
            continue
        found[name] = {
            # The name of the file and not the path it sits at: the path is
            # where this deployment keeps its build output, which is nothing
            # an administration page needs to publish.
            "file": Path(str(record.get("file", ""))).name or None,
            "created_at": record.get("trained_at"),
        }
    return found


@router.get(
    "/models",
    response_model=AdminModelsOut,
    summary="The held-out scores of the two deployed models",
)
async def read_models() -> AdminModelsOut:
    """
    How well each model did on rows it was never fitted on.

    Five figures per model, each labelled with its scale, because an
    operations page is read by somebody who did not run the training: "0.54"
    is not a score until it is named as R squared on a 0 to 1 scale where
    higher is better, and "0.33" is not a score until it is named as a log
    RMSE where lower is better.

    Both documents behind this are git-ignored build outputs. A fresh clone
    has neither, and this endpoint then answers with the two cards, what each
    model is given, and ``report_available: false``: the honest statement that
    the scores were not measured on this machine, rather than an error page or
    a figure somebody typed in.
    """
    report = read_json_file(MODEL_REPORT, "the training report")
    winners = report.get("winners") if isinstance(report, dict) else None
    winners = winners if isinstance(winners, dict) else {}
    files = deployed_files()

    cards: list[AdminModelCard] = []
    for name in (CORE, FULL):
        record = winners.get(MODEL_FEATURE_SETS[name])
        algorithm = record.get("model") if isinstance(record, dict) else None
        deployed = files.get(name, {})
        cards.append(
            AdminModelCard(
                id=name,
                label=MODEL_LABELS[name],
                algorithm=str(algorithm) if isinstance(algorithm, str) else None,
                inputs_note=MODEL_INPUT_NOTES[name],
                file=deployed.get("file"),
                created_at=deployed.get("created_at"),
                metrics=metrics_from(record),
            )
        )

    return AdminModelsOut(
        measured_on=MEASURED_ON,
        cross_validation=CROSS_VALIDATION,
        currency=mapping.CURRENCY,
        report_available=any(card.metrics for card in cards),
        models=cards,
    )


# ---------------------------------------------------------------------------
# /admin/recent
# ---------------------------------------------------------------------------
@router.get(
    "/recent",
    response_model=AdminRecentOut,
    summary="The latest logged calls, newest first",
)
async def read_recent(
    limit: int = Query(
        default=RECENT_DEFAULT,
        ge=1,
        le=RECENT_MAX,
        description="How many events to return.",
    ),
    session: Session = Depends(get_session),
) -> AdminRecentOut:
    """
    The last calls the service answered, as a table.

    The mentor id is on the stored row and is left out of the response. The
    table is read to see what the service is doing, and the account behind a
    call adds nothing to that while turning a page of figures into a page
    about people.
    """
    rows = session.scalars(
        select(RequestLog).order_by(RequestLog.id.desc()).limit(limit)
    ).all()

    return AdminRecentOut(
        limit=limit,
        currency=mapping.CURRENCY,
        events=[
            AdminEvent(
                id=row.id,
                created_at=row.created_at,
                endpoint=row.endpoint,
                endpoint_label=ENDPOINT_LABELS.get(row.endpoint, row.endpoint),
                model_used=row.model_used,
                field=row.field,
                field_label=field_label_of(row.field),
                group_size=row.group_size,
                recommended_price=row.recommended_price,
                response_ms=row.response_ms,
                status_code=row.status_code,
            )
            for row in rows
        ],
    )
