"""
Tests for the record of what was asked of the models.

Three properties matter here and nothing else does.

**A call that scores a model leaves exactly one row.** One per call, not one
per model score: the preview scores the whole skill ladder to correct the
price, and a row per score would make the dashboard's call counts fiction.

**A log write can never hurt the caller.** The row is written after the
response, and the only correct answer to a write that fails is a warning line.
So one test breaks the writer deliberately and checks that the mentor still
gets their price, and the warning is checked too, because a failure that is
swallowed silently is a failure nobody will ever find.

**A row holds nothing personal.** The strongest form of that check is not a
list of column names: it is to register a mentor whose name, address and
profile text are distinctive strings, and then assert that none of those
strings appears anywhere in the stored row. A column added later that carries
one of them fails this test without anybody remembering to update it.
"""

from __future__ import annotations

import logging

import pytest
from sqlalchemy import inspect, select

from src.db.mentor_models import LOG_ENDPOINTS, RequestLog
from src.mentor import request_log
from src.mentor.request_log import PriceEvent

from .conftest import headers, register, registration

pytestmark = pytest.mark.app_assets


PREVIEW = {
    "field": "technology_software",
    "max_mentees": 2,
    "skills": ["cv_review", "interview_preparation"],
}


def rows(sessions) -> list[RequestLog]:
    """Every logged row, oldest first."""
    with sessions() as session:
        return list(session.scalars(select(RequestLog).order_by(RequestLog.id)))


def only_row(sessions) -> RequestLog:
    found = rows(sessions)
    assert len(found) == 1, f"expected one row, found {len(found)}"
    return found[0]


# ---------------------------------------------------------------------------
# One call, one row
# ---------------------------------------------------------------------------
def test_a_preview_is_logged_once(client, api_sessions):
    response = client.post("/preview", json=PREVIEW)
    assert response.status_code == 200

    row = only_row(api_sessions)
    assert row.endpoint == "preview"
    assert row.model_used == "core"
    assert row.field == "technology_software"
    assert row.group_size == 2
    assert row.skills_count == 2
    # No account behind the preview, so there is no mentor to name.
    assert row.mentor_id is None
    assert row.status_code == 200
    assert row.response_ms >= 0


def test_the_logged_price_is_the_price_the_caller_was_given(client, api_sessions):
    body = client.post("/preview", json=PREVIEW).json()

    row = only_row(api_sessions)
    assert row.recommended_price == body["session_price"]
    assert row.range_low == body["range_low"]
    assert row.range_high == body["range_high"]


def test_registration_is_logged_against_the_account_it_created(client, api_sessions):
    body = register(client, max_mentees=3)

    row = only_row(api_sessions)
    assert row.endpoint == "registration"
    assert row.mentor_id == body["mentor"]["id"]
    assert row.group_size == 3
    assert row.field == registration()["field"]
    assert row.status_code == 201
    assert row.recommended_price == body["recommendation"]["recommended_price"]


def test_adding_a_service_is_logged(client, api_sessions):
    body = register(client)
    mentor_id = body["mentor"]["id"]

    response = client.post(
        f"/mentors/{mentor_id}/services",
        json={
            "field": "law",
            "max_mentees": 4,
            "min_commitment": 1,
            "skills": ["cv_review"],
        },
        headers=headers(mentor_id),
    )
    assert response.status_code == 201

    logged = rows(api_sessions)
    assert [row.endpoint for row in logged] == ["registration", "service_added"]
    added = logged[-1]
    assert added.field == "law"
    assert added.group_size == 4
    assert added.skills_count == 1
    assert added.mentor_id == mentor_id


def test_recalculating_a_price_is_logged(client, api_sessions):
    body = register(client)
    mentor_id = body["mentor"]["id"]
    service_id = body["service"]["id"]

    response = client.post(
        f"/services/{service_id}/recommendations", headers=headers(mentor_id)
    )
    assert response.status_code == 201

    logged = rows(api_sessions)
    assert [row.endpoint for row in logged] == ["registration", "recalculation"]
    again = logged[-1]
    assert again.mentor_id == mentor_id
    assert again.field == registration()["field"]
    assert again.group_size == registration()["max_mentees"]


def test_every_logged_endpoint_is_one_the_table_allows(client, api_sessions):
    """
    The four names in the model are the four the application writes.

    A fifth written by an endpoint would be refused by the check constraint
    and swallowed by the writer, so the dashboard would quietly lose a path.
    """
    body = register(client)
    mentor_id = body["mentor"]["id"]
    client.post("/preview", json=PREVIEW)
    client.post(
        f"/mentors/{mentor_id}/services",
        json={"field": "law", "max_mentees": 1, "min_commitment": 1, "skills": []},
        headers=headers(mentor_id),
    )
    client.post(
        f"/services/{body['service']['id']}/recommendations",
        headers=headers(mentor_id),
    )

    written = {row.endpoint for row in rows(api_sessions)}
    assert written == set(LOG_ENDPOINTS)


# ---------------------------------------------------------------------------
# A call that did not get a price
# ---------------------------------------------------------------------------
def test_a_refused_preview_is_logged_with_no_price(client, api_sessions, monkeypatch):
    """
    The rate limit is the honest case of a call with a status and no price.

    Logged before the limit is tested on purpose: a dashboard that counted
    only the calls that succeeded would report a server under no load at the
    moment it was refusing everything.
    """
    from src.mentor import app as app_module

    monkeypatch.setattr(app_module.preview_limiter, "limit", 1)
    app_module.preview_limiter.forget()

    assert client.post("/preview", json=PREVIEW).status_code == 200
    assert client.post("/preview", json=PREVIEW).status_code == 429
    app_module.preview_limiter.forget()

    logged = rows(api_sessions)
    assert [row.status_code for row in logged] == [200, 429]
    refused = logged[-1]
    assert refused.model_used is None
    assert refused.recommended_price is None
    assert refused.range_low is None
    assert refused.range_high is None
    # What was asked is still recorded: the call happened.
    assert refused.field == "technology_software"
    assert refused.group_size == 2


def test_a_call_refused_before_the_handler_is_not_logged(
    client, modelless_client, api_sessions
):
    """
    Where the record starts, stated as a test rather than left to be found.

    A missing token and a server with no models are both refused by a
    dependency, so the handler that records the event never runs. There is
    nothing to record in either case: no field, no group size, not even a
    mentor id, because the body was never looked at. A row of nulls would
    put a call in the dashboard's counts that the service did no work for.

    The limit of the table is therefore: one row per call that reached a
    pricing handler. Calls turned away in front of one are the deployment's
    own problem and show up in its access log, not here.
    """
    assert client.post("/services/1/recommendations").status_code == 401
    assert modelless_client.post("/preview", json=PREVIEW).status_code == 503

    assert rows(api_sessions) == []


def test_a_call_for_someone_elses_service_is_logged_as_a_refusal(client, api_sessions):
    first = register(client)
    second = register(client, email="other@example.com")

    response = client.post(
        f"/services/{second['service']['id']}/recommendations",
        headers=headers(first["mentor"]["id"]),
    )
    assert response.status_code == 404

    refused = rows(api_sessions)[-1]
    assert refused.endpoint == "recalculation"
    assert refused.status_code == 404
    assert refused.mentor_id == first["mentor"]["id"]
    # Nothing is recorded about the service, because the caller was never
    # told anything about it either.
    assert refused.field is None
    assert refused.recommended_price is None


# ---------------------------------------------------------------------------
# A failed write costs the caller nothing
# ---------------------------------------------------------------------------
def test_a_logging_failure_does_not_break_the_call(
    client, api_sessions, monkeypatch, caplog
):
    def explode(*_args, **_kwargs):
        raise RuntimeError("the log table is on fire")

    monkeypatch.setattr(request_log, "RequestLog", explode)

    with caplog.at_level(logging.WARNING, logger="src.mentor.request_log"):
        response = client.post("/preview", json=PREVIEW)

    assert response.status_code == 200
    assert response.json()["session_price"] > 0
    assert rows(api_sessions) == []
    assert "could not record the preview request" in caplog.text


def test_a_broken_session_factory_does_not_break_the_call(client, caplog):
    """
    The other half of the same guarantee: the database itself is unreachable.

    Failing to open a session is a different failure from failing to write a
    row, and it happens in the more likely place: a connection pool that is
    exhausted or a database that has gone away.
    """

    def no_sessions():
        raise RuntimeError("no connection available")

    client.app.state.log_sessions = no_sessions
    try:
        with caplog.at_level(logging.WARNING, logger="src.mentor.request_log"):
            response = client.post("/preview", json=PREVIEW)
    finally:
        client.app.state.log_sessions = None

    assert response.status_code == 200
    assert "could not record the preview request" in caplog.text


def test_registering_still_works_when_the_log_cannot_be_written(
    client, monkeypatch, caplog
):
    """
    The write happens after the response, so the account is already created.

    This is the case worth stating plainly: a mentor who registers while the
    analytics table is broken gets an account, a service and a price.
    """
    monkeypatch.setattr(request_log, "RequestLog", lambda **_: 1 / 0)

    with caplog.at_level(logging.WARNING, logger="src.mentor.request_log"):
        body = register(client)

    assert body["recommendation"]["recommended_price"] > 0
    assert body["mentor"]["id"] > 0


# ---------------------------------------------------------------------------
# Nothing personal is stored
# ---------------------------------------------------------------------------
def test_no_column_in_the_table_can_hold_a_name_or_an_address():
    """
    The shape of the table, stated as the list it is allowed to be.

    A column added later that is not in this set fails here, which is the
    point: the restraint is on what the table may hold, not on what any one
    caller remembers to leave out.
    """
    allowed = {
        "id",
        "created_at",
        "endpoint",
        "model_used",
        "field",
        "group_size",
        "skills_count",
        "mentor_id",
        "recommended_price",
        "range_low",
        "range_high",
        "response_ms",
        "status_code",
    }

    assert set(inspect(RequestLog).columns.keys()) == allowed


def test_nothing_a_mentor_typed_reaches_the_log(client, api_sessions):
    """
    Registered with distinctive strings, and none of them is in the row.

    Stronger than checking column names, because it fails for a column that
    does not exist yet.
    """
    secrets = {
        "name": "Zephaniah Quillingsworth",
        "email": "zephaniah.quillingsworth@example.com",
        "headline": "Ornithologist turned staff engineer",
        "bio": "Sixteen years of herpetology and distributed systems.",
        "credentials": "Fellow of the Institute of Imaginary Things",
        "experience_summary": "Principal engineer at Vexillographers Limited",
    }
    register(client, **secrets)

    row = only_row(api_sessions)
    stored = " ".join(
        str(getattr(row, column)) for column in inspect(RequestLog).columns.keys()
    ).lower()
    for value in secrets.values():
        assert value.lower() not in stored


def test_the_event_a_handler_records_has_no_room_for_anything_personal():
    """
    The vocabulary an endpoint can log, as the dataclass's own field list.

    An endpoint cannot pass a name or an address through this: there is no
    field for one, so the attempt is a TypeError rather than a leak.
    """
    allowed = {
        "endpoint",
        "field",
        "group_size",
        "skills_count",
        "mentor_id",
        "model_used",
        "recommended_price",
        "range_low",
        "range_high",
    }

    assert set(PriceEvent.__dataclass_fields__) == allowed

    with pytest.raises(TypeError):
        PriceEvent(endpoint="preview", email="someone@example.com")


def test_no_network_address_is_stored_even_though_the_limiter_reads_one(
    client, api_sessions
):
    """
    The preview is rate limited per address, so the application does see one.

    That is exactly why this is worth a test of its own: the address is in
    the handler's own scope, two lines from the call that records the event,
    and the event has no field for it.
    """
    client.post("/preview", json=PREVIEW)

    row = only_row(api_sessions)
    columns = inspect(RequestLog).columns.keys()
    stored = " ".join(str(getattr(row, column)) for column in columns)
    assert "testclient" not in stored.lower()
    assert "127.0.0.1" not in stored
