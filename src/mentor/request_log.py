"""
Recording what was asked of the models, without making anybody wait for it.

The operations dashboard needs to know how often each pricing path is called,
which model answered, how long it took and whether it succeeded. None of that
can be read back from the tables the flow already writes: a preview stores
nothing at all, and a stored recommendation carries no timing and no status.

Three rules shape everything in this module.

**A log write never delays the caller.** The row is written in a background
task attached to the response, which Starlette runs after the body has been
sent, in a worker thread. The mentor has their price before the row exists.

**A log write never fails the caller.** :func:`write` catches every exception
and turns it into one warning line. A dashboard with a gap in it is a far
smaller fault than a mentor who cannot get a price because an analytics table
is full, locked or missing.

**A log row carries nothing personal.** The event an endpoint records is a
field id, two counts, an optional mentor id and the model's own output. There
is no name, no address, no free text, no network address and no request body,
and the dataclass below is the whole vocabulary: a caller cannot add a field
to it by passing one.

Why an event on the request rather than a call at the end of each endpoint:
the two things worth recording that an endpoint does not know are the status
code and how long the whole request took. An endpoint that raises never
reaches its own last line, so it could not log its own failure. So the
endpoint records what it knows as it goes, and the middleware in
:mod:`src.mentor.app` adds the duration and the status code once the response
exists.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from starlette.background import BackgroundTask, BackgroundTasks

from src.db.mentor_models import RequestLog
from src.db.session import get_session_factory

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from fastapi import FastAPI, Request
    from sqlalchemy.orm import Session, sessionmaker
    from starlette.responses import Response

logger = logging.getLogger(__name__)

# Where the request stashes its event. One attribute name, used by the
# endpoints and by the middleware, so neither has to guess.
STATE_ATTRIBUTE = "price_event"

# Set on app.state to point the writer at a different database. The tests use
# it, because they override the session dependency rather than the engine, and
# a background writer that reached for the process-wide engine would write to
# whatever DATABASE_URL happens to name on the machine running them.
SESSIONS_ATTRIBUTE = "log_sessions"


@dataclass(frozen=True)
class PriceEvent:
    """
    What one call asked of a model, and what it got back.

    Frozen, and replaced rather than mutated, so that a half-filled event
    cannot be observed: an endpoint records what it knows on entry and
    records a complete one again once the model has answered.

    Every field except ``endpoint`` is optional, because a call that was
    refused before it reached a model still produced a status code and a
    duration worth recording, and inventing the rest would be worse than
    leaving it out.
    """

    endpoint: str
    field: str | None = None
    group_size: int | None = None
    skills_count: int | None = None
    mentor_id: int | None = None
    model_used: str | None = None
    recommended_price: int | None = None
    range_low: int | None = None
    range_high: int | None = None


def record(request: Request, event: PriceEvent) -> None:
    """Attach an event to this request, replacing any earlier one."""
    setattr(request.state, STATE_ATTRIBUTE, event)


def event_of(request: Request) -> PriceEvent | None:
    """The event this request recorded, or None if it recorded none."""
    return getattr(request.state, STATE_ATTRIBUTE, None)


def note_advice(request: Request, advice: Any) -> None:
    """
    Add the model's answer to the event this request already recorded.

    Takes anything with the four attributes a price has, which is both the
    :class:`~src.mentor.prediction.PriceRecommendation` the preview returns
    and the stored row the other three paths produce. A request with no event
    is left alone rather than given one, because an event with no endpoint is
    not a row this table can hold.
    """
    event = event_of(request)
    if event is None:
        return
    record(
        request,
        replace(
            event,
            model_used=getattr(advice, "model_used", None),
            recommended_price=_whole(getattr(advice, "recommended_price", None)),
            range_low=_whole(getattr(advice, "price_low", None)),
            range_high=_whole(getattr(advice, "price_high", None)),
        ),
    )


def note_mentor(request: Request, mentor_id: int | None) -> None:
    """
    Name the mentor this request turned out to belong to.

    Registration is the one path that cannot record the id on entry, because
    the account does not exist until the request is half over.
    """
    event = event_of(request)
    if event is None:
        return
    record(request, replace(event, mentor_id=mentor_id))


def _whole(value: Any) -> int | None:
    """A price as the whole number the table stores, or None."""
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def sessions_for(app: FastAPI) -> sessionmaker[Session]:
    """
    The session factory the writer should use for this application.

    ``app.state.log_sessions`` when something has set one, and the
    process-wide factory otherwise. Resolved here rather than at import, so a
    test that points it elsewhere is obeyed by the next request and not only
    by the next process.
    """
    factory = getattr(app.state, SESSIONS_ATTRIBUTE, None)
    return factory if factory is not None else get_session_factory()


def write(
    event: PriceEvent,
    response_ms: int,
    status_code: int,
    sessions: sessionmaker[Session],
) -> None:
    """
    Write one row, and swallow anything that goes wrong doing it.

    The bare ``except Exception`` is the point of the function rather than a
    shortcut around a known failure. This runs after the caller has their
    answer, so there is nobody left to report a failure to and nothing useful
    to do about one: a table that is missing, locked, full or at the end of a
    dropped connection must cost the service a warning line and no more.
    """
    try:
        with sessions() as session:
            session.add(
                RequestLog(
                    endpoint=event.endpoint,
                    model_used=event.model_used,
                    field=event.field,
                    group_size=event.group_size,
                    skills_count=event.skills_count,
                    mentor_id=event.mentor_id,
                    recommended_price=event.recommended_price,
                    range_low=event.range_low,
                    range_high=event.range_high,
                    response_ms=max(0, int(response_ms)),
                    status_code=int(status_code),
                )
            )
            session.commit()
    except Exception as error:  # noqa: BLE001 - see the docstring
        logger.warning(
            "could not record the %s request in request_logs: %s",
            event.endpoint,
            error,
        )


def started() -> float:
    """A monotonic reading, for measuring how long a request took."""
    return time.perf_counter()


def elapsed_ms(since: float) -> int:
    """Whole milliseconds since ``since``, never negative."""
    return max(0, int(round((time.perf_counter() - since) * 1000)))


def attach(
    response: Response,
    task: BackgroundTask,
) -> None:
    """
    Run ``task`` after this response has been sent, keeping any already set.

    No endpoint in this application sets a background task of its own today.
    Composing rather than overwriting means that one which does later gets
    logged as well instead of silently losing its own task.
    """
    existing = response.background
    response.background = (
        task if existing is None else BackgroundTasks([existing, task])
    )
