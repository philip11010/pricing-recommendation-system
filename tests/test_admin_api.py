"""
Tests for the operations dashboard under /admin.

Three things are checked, in this order of importance.

**Who may read it.** Every endpoint is tried three ways: with no token, with a
mentor's token and with an administrator's. Anonymous is 401, a mentor is 403,
and the difference between the two matters because it is what a frontend acts
on: 401 means sign in and 403 means signing in again will not help. The
endpoints are enumerated from the router rather than listed by hand, so an
endpoint added later is covered without anybody remembering to add it here.

**That it answers on an empty database.** An administration page that only
works once there is data is one nobody can set up, and the shapes it returns
on nothing are the empty states the interface draws.

**That nothing personal comes out.** The same approach as the request log
tests: register a mentor whose details are distinctive strings and assert that
none of them appears anywhere in any admin response, whatever the shape.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from src.db.mentor_models import Mentor
from src.mentor.admin import router as admin_router

from .conftest import headers, register

pytestmark = pytest.mark.app_assets


# Every GET the router exposes, read from the router itself so an endpoint
# added later is behind the same three checks without being listed twice.
ADMIN_PATHS: list[str] = sorted(
    route.path
    for route in admin_router.routes
    if "GET" in getattr(route, "methods", set())
)

PREVIEW = {
    "field": "technology_software",
    "max_mentees": 2,
    "skills": ["cv_review", "interview_preparation"],
}


@pytest.fixture
def admin(client, api_sessions) -> dict:
    """
    An administrator account, and the headers to call /admin with.

    Written straight into the table, the way the seed script does it, because
    there is no endpoint that grants the flag and that is the point of it.
    """
    with api_sessions() as session:
        account = Mentor(
            full_name="Platform administrator",
            email="admin@example.com",
            password_hash="not-a-real-hash",
            is_admin=True,
        )
        session.add(account)
        session.commit()
        session.refresh(account)
        account_id = account.id
    return {"id": account_id, "headers": headers(account_id)}


def seeded(client, api_sessions) -> dict:
    """
    One mentor who went the whole way through the flow, plus a preview.

    Everything on the dashboard is built from rows the application wrote, so
    the fixture for a populated database is the application being used rather
    than inserts: a registration, a second service, a recalculated price, a
    decision and a preview. That is also what makes the counts worth
    asserting, because a hand-written row could be shaped to pass.
    """
    body = register(client)
    mentor_id = body["mentor"]["id"]
    token = headers(mentor_id)

    client.post("/preview", json=PREVIEW)
    client.post(
        f"/mentors/{mentor_id}/services",
        json={"field": "law", "max_mentees": 4, "min_commitment": 1, "skills": []},
        headers=token,
    )
    again = client.post(
        f"/services/{body['service']['id']}/recommendations", headers=token
    ).json()
    decided = client.post(
        f"/recommendations/{again['id']}/decision",
        json={"action": "accepted"},
        headers=token,
    )
    assert decided.status_code == 201, decided.text
    return body


# ---------------------------------------------------------------------------
# Who may read it
# ---------------------------------------------------------------------------
def test_there_are_six_admin_endpoints():
    """
    The set of paths, stated once, so the guard tests below cover them all.

    A seventh endpoint changes this number, which is the prompt to decide
    whether it belongs on this surface at all.
    """
    assert ADMIN_PATHS == [
        "/admin/models",
        "/admin/outputs",
        "/admin/recent",
        "/admin/signups",
        "/admin/summary",
        "/admin/usage",
    ]


@pytest.mark.parametrize("path", ADMIN_PATHS)
def test_an_anonymous_caller_gets_401(client, path):
    response = client.get(path)

    assert response.status_code == 401
    # The scheme is named, which is what a 401 means rather than suggests.
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("path", ADMIN_PATHS)
def test_a_mentor_gets_403(client, path):
    """
    A signed-in mentor is refused with 403 and not 404.

    The rest of the API answers 404 for a record that is not the caller's,
    because 404 does not confirm that somebody else's record exists. /admin
    is a fixed set of paths with nothing per-account about it, so there is
    nothing for a 404 to conceal and 403 is the accurate answer: you are
    signed in, and signing in again will not help.
    """
    body = register(client)

    response = client.get(path, headers=headers(body["mentor"]["id"]))

    assert response.status_code == 403
    assert "cannot read" in response.json()["detail"]


@pytest.mark.parametrize("path", ADMIN_PATHS)
def test_an_administrator_is_let_in(client, admin, path):
    assert client.get(path, headers=admin["headers"]).status_code == 200


@pytest.mark.parametrize("path", ADMIN_PATHS)
def test_a_token_for_an_account_that_no_longer_exists_is_401(
    client, api_sessions, admin, path
):
    """
    A valid token naming a deleted account is an identity, not a record.

    401 rather than 403, because the question "is this account allowed here"
    cannot be asked of an account that is not there.
    """
    with api_sessions() as session:
        session.delete(session.get(Mentor, admin["id"]))
        session.commit()

    assert client.get(path, headers=admin["headers"]).status_code == 401


def test_revoking_the_flag_takes_effect_on_the_next_call(client, api_sessions, admin):
    """
    The flag is read from the account per request, not carried in the token.

    So taking it away stops the next call rather than waiting seven days for
    an access token to expire.
    """
    assert client.get("/admin/summary", headers=admin["headers"]).status_code == 200

    with api_sessions() as session:
        account = session.get(Mentor, admin["id"])
        account.is_admin = False
        session.commit()

    assert client.get("/admin/summary", headers=admin["headers"]).status_code == 403


def test_nothing_a_mentor_sends_can_set_the_flag(client):
    """
    Registration cannot make an administrator, however the body is written.

    The request bodies forbid unknown fields, so the attempt is a 422 rather
    than a quietly ignored key: a field that was silently dropped would be
    one that a later version of the schema might start reading.
    """
    response = client.post(
        "/auth/register",
        json={
            **{
                "name": "A. Mentor",
                "email": "sneaky@example.com",
                "password": "a-long-enough-password",
                "field": "technology_software",
                "max_mentees": 1,
                "min_commitment": 1,
                "skills": ["cv_review"],
            },
            "is_admin": True,
        },
    )

    assert response.status_code == 422


def test_the_mentor_response_reports_the_flag(client, admin):
    """
    /auth/me carries is_admin, which is what the frontend draws the link from.

    This is not a formality. The response is assembled field by field rather
    than validated off the row, so a field left out of that assembly takes
    the schema's default of false, and the symptom is an administrator who
    cannot find their own pages while the API answers every /admin request
    perfectly happily. That is exactly what happened, and this is the test
    that would have caught it.
    """
    body = client.get("/auth/me", headers=admin["headers"]).json()

    assert body["is_admin"] is True


def test_the_public_profile_never_reports_the_flag(client, api_sessions, admin):
    """
    Who administers the platform is not on anybody's public profile.

    The public shapes are built field by field from a chosen list, and this
    asserts that the administrator flag is not on that list: it says nothing
    a mentee has any use for and names the account worth attacking.
    """
    body = register(client)
    mentor_id = body["mentor"]["id"]

    public = client.get(f"/mentors/{mentor_id}/public").json()
    assert "is_admin" not in public

    directory = client.get("/mentors").json()
    assert all("is_admin" not in card for card in directory["items"])


def test_an_account_is_not_an_administrator_by_default(client, api_sessions):
    body = register(client)

    with api_sessions() as session:
        account = session.get(Mentor, body["mentor"]["id"])
        assert account.is_admin is False
    assert body["mentor"]["is_admin"] is False


# ---------------------------------------------------------------------------
# An empty database
# ---------------------------------------------------------------------------
def test_summary_on_an_empty_database(client, admin):
    body = client.get("/admin/summary", headers=admin["headers"]).json()

    # The administrator is an account and is not a mentor: it exists to read
    # this page and is not somebody the platform prices.
    assert body["accounts"] == 1
    assert body["mentors"] == 0
    assert body["verified_mentors"] == 0
    assert body["services"] == 0
    assert body["recommendations"] == 0
    assert body["decisions"]["total"] == 0
    # No decisions means no acceptance rate. A zero would read as advice
    # everybody rejected.
    assert body["decisions"]["acceptance_rate_percent"] is None
    assert body["requests_last_24h"] == 0
    assert body["median_response_ms"] is None


def test_usage_on_an_empty_database_still_returns_the_whole_window(client, admin):
    """
    Every day in the window, including the empty ones.

    A chart drawn from only the days that had traffic draws a continuous line
    across an outage, so the series is filled here rather than in the
    interface.
    """
    body = client.get("/admin/usage", headers=admin["headers"]).json()

    assert body["days"] == 30
    assert len(body["per_day"]) == 30
    assert all(day["total"] == 0 for day in body["per_day"])
    # Days with no calls have no median, so they are absent rather than zero.
    assert body["latency_per_day"] == []
    assert body["model_share"]["total"] == 0
    assert body["model_share"]["core_percent"] is None
    # Every path is listed at zero, so the breakdown is a chart rather than
    # an empty space that might be a loading state.
    assert len(body["by_endpoint"]) == 4
    assert all(item["count"] == 0 for item in body["by_endpoint"])


def test_outputs_on_an_empty_database(client, admin):
    body = client.get("/admin/outputs", headers=admin["headers"]).json()

    assert body["recommendations"] == 0
    assert body["price_buckets"] == []
    assert body["median_price"] is None
    assert body["by_field"] == []
    assert body["range_widths"]["median"] is None
    assert body["currency"] == "AUD"


def test_signups_on_an_empty_database(client, admin):
    body = client.get("/admin/signups", headers=admin["headers"]).json()

    assert body["weeks"] == 12
    assert len(body["per_week"]) == 12
    # The administrator is not a sign-up: it was created by a script run by
    # whoever administers the deployment.
    assert body["accounts"] == 0
    assert all(week["accounts"] == 0 for week in body["per_week"])


def test_recent_on_an_empty_database(client, admin):
    body = client.get("/admin/recent", headers=admin["headers"]).json()

    assert body["limit"] == 50
    assert body["events"] == []


def test_models_answers_even_with_no_training_report(client, admin, monkeypatch):
    """
    A fresh clone has no training report, and the page still renders.

    The report is a git-ignored output of a local training run, so this is the
    normal state rather than a fault: the two cards arrive with what each
    model is given and no scores, and ``report_available`` says so.
    """
    from src.mentor import admin as admin_module

    monkeypatch.setattr(
        admin_module, "MODEL_REPORT", admin_module.PROJECT_ROOT / "no-such-report.json"
    )

    body = client.get("/admin/models", headers=admin["headers"]).json()

    assert body["report_available"] is False
    assert [card["id"] for card in body["models"]] == ["core", "full"]
    assert all(card["metrics"] == [] for card in body["models"])
    assert all(card["inputs_note"] for card in body["models"])


# ---------------------------------------------------------------------------
# A database with rows in it
# ---------------------------------------------------------------------------
def test_summary_counts_what_the_flow_wrote(client, api_sessions, admin):
    seeded(client, api_sessions)

    body = client.get("/admin/summary", headers=admin["headers"]).json()

    assert body["accounts"] == 2
    assert body["mentors"] == 1
    assert body["services"] == 2
    # Registration, the added service and the recalculation.
    assert body["recommendations"] == 3
    assert body["decisions"]["accepted"] == 1
    assert body["decisions"]["total"] == 1
    assert body["decisions"]["acceptance_rate_percent"] == 100.0
    assert body["decisions"]["pending"] == 2
    # Registration, preview, service added, recalculation.
    assert body["requests_last_24h"] == 4
    assert body["logged_requests"] == 4
    assert body["median_response_ms"] >= 0


def test_usage_splits_the_days_by_model_and_lists_every_path(
    client, api_sessions, admin
):
    seeded(client, api_sessions)

    body = client.get("/admin/usage", headers=admin["headers"]).json()

    today = body["per_day"][-1]
    assert today["total"] == 4
    assert today["core"] == 4
    assert today["full"] == 0
    assert today["no_model"] == 0

    counts = {item["id"]: item["count"] for item in body["by_endpoint"]}
    assert counts == {
        "preview": 1,
        "registration": 1,
        "service_added": 1,
        "recalculation": 1,
    }

    assert body["model_share"]["core"] == 4
    assert body["model_share"]["core_percent"] == 100.0
    assert len(body["latency_per_day"]) == 1
    assert body["latency_per_day"][0]["requests"] == 4
    assert (
        body["latency_per_day"][0]["p95_ms"] >= body["latency_per_day"][0]["median_ms"]
    )


def test_usage_counts_a_refused_call_against_no_model(client, admin, monkeypatch):
    """
    A refused preview is a call the service did work for and priced nothing.

    Folding it into either model would attribute work to a model that did
    none, and leaving it out would show a quiet server at the moment it was
    refusing everything.
    """
    from src.mentor import app as app_module

    monkeypatch.setattr(app_module.preview_limiter, "limit", 1)
    app_module.preview_limiter.forget()
    assert client.post("/preview", json=PREVIEW).status_code == 200
    assert client.post("/preview", json=PREVIEW).status_code == 429
    app_module.preview_limiter.forget()

    body = client.get("/admin/usage", headers=admin["headers"]).json()

    assert body["model_share"] == {
        "core": 1,
        "full": 0,
        "no_model": 1,
        "total": 2,
        "core_percent": 50.0,
        "full_percent": 0.0,
    }


def test_outputs_describes_the_advice_that_was_stored(client, api_sessions, admin):
    seeded(client, api_sessions)

    body = client.get("/admin/outputs", headers=admin["headers"]).json()

    assert body["recommendations"] == 3
    assert body["median_price"] > 0
    assert sum(bucket["count"] for bucket in body["price_buckets"]) == 3
    # Half-open buckets, so no price can fall in two of them.
    assert all(bucket["high"] > bucket["low"] for bucket in body["price_buckets"])
    fields = {item["id"]: item["count"] for item in body["by_field"]}
    assert fields == {"technology_software": 2, "law": 1}
    assert body["decisions"]["accepted"] == 1
    assert body["range_widths"]["median"] > 0
    assert body["range_widths"]["median_percent_of_price"] > 0


def test_outputs_ignores_previews(client, admin):
    """
    A preview is a figure on a form nobody submitted, not advice.

    Counting previews in the distribution of what the platform advises would
    let a form being filled in slowly move it.
    """
    for _ in range(3):
        client.post("/preview", json=PREVIEW)

    body = client.get("/admin/outputs", headers=admin["headers"]).json()

    assert body["recommendations"] == 0
    assert body["price_buckets"] == []


def test_signups_counts_accounts_and_splits_them_by_verification(
    client, api_sessions, admin
):
    register(client)
    register(client, email="second@example.com")
    with api_sessions() as session:
        first = session.scalars(
            select(Mentor).where(Mentor.email == "mentor@example.com")
        ).one()
        first.verified = True
        session.commit()

    body = client.get("/admin/signups", headers=admin["headers"]).json()

    assert body["accounts"] == 2
    assert body["verified"] == 1
    assert body["unverified"] == 1
    this_week = body["per_week"][-1]
    assert this_week["accounts"] == 2
    assert this_week["verified"] == 1
    assert this_week["unverified"] == 1


def test_recent_returns_the_newest_calls_first(client, api_sessions, admin):
    seeded(client, api_sessions)

    body = client.get("/admin/recent", headers=admin["headers"]).json()

    assert [event["endpoint"] for event in body["events"]] == [
        "recalculation",
        "service_added",
        "preview",
        "registration",
    ]
    first = body["events"][0]
    assert first["endpoint_label"] == "Price recalculated"
    assert first["model_used"] == "core"
    assert first["field_label"] == "Technology and software"
    assert first["status_code"] == 201
    assert first["response_ms"] >= 0


def test_recent_honours_its_limit(client, api_sessions, admin):
    for _ in range(4):
        client.post("/preview", json=PREVIEW)

    body = client.get("/admin/recent?limit=2", headers=admin["headers"]).json()

    assert body["limit"] == 2
    assert len(body["events"]) == 2


def test_models_reports_five_labelled_scores_for_each_model(client, admin):
    """
    Skipped rather than failed when the training report is not on the machine.

    The report is a local build output, so a clone without one is a normal
    state; what this test is for is the shape when it is present.
    """
    from src.mentor import admin as admin_module

    if not admin_module.MODEL_REPORT.exists():
        pytest.skip(
            "reports/model_results.json is a local training output; run "
            "scripts/train_experiments.py to produce it"
        )

    body = client.get("/admin/models", headers=admin["headers"]).json()

    assert body["report_available"] is True
    assert body["currency"] == "AUD"
    assert "held-out" in body["measured_on"]
    assert "10-fold" in body["cross_validation"]

    for card in body["models"]:
        ids = [metric["id"] for metric in card["metrics"]]
        assert ids == ["r2", "rmse_log", "mae", "rmse", "cv_rmse_log"]
        # Every figure carries the scale it is measured on and which way is
        # better, because a bare number is one a reader can only guess at.
        assert all(metric["scale"] for metric in card["metrics"])
        assert all(metric["label"] for metric in card["metrics"])
        assert card["algorithm"] == "XGBoost"


def test_models_returns_the_deployed_file_names_and_dates(client, admin):
    """
    The file an administrator would find on disk, and when it was fitted.

    The path it sits at is not returned: where this deployment keeps its
    build output is not something an administration page needs to publish.
    """
    body = client.get("/admin/models", headers=admin["headers"]).json()

    files = {card["id"]: card["file"] for card in body["models"]}
    assert files == {"core": "core.joblib", "full": "full.joblib"}
    assert all(card["created_at"] for card in body["models"])


def test_models_never_returns_the_raw_report(client, admin):
    """
    The whitelist, checked against the thing it exists to hold back.

    The training report names the internal columns the models were fitted
    on. Those names belong to the training data and appear nowhere this
    application serves, so this asserts that none of them is in the response
    and that the response has only the keys the schema declares.
    """
    from src.mentor import admin as admin_module

    if not admin_module.MODEL_REPORT.exists():
        pytest.skip("reports/model_results.json is a local training output")

    body = client.get("/admin/models", headers=admin["headers"]).json()
    served = json.dumps(body).lower()

    report = json.loads(admin_module.MODEL_REPORT.read_text(encoding="utf-8"))
    for column in report["feature_sets"]["full"]:
        assert column.lower() not in served
    for key in ("dataset", "scope", "split", "fences", "importances", "grids"):
        assert key not in body
        assert str(report.get(key, "")).lower()[:40] not in served or not report.get(
            key
        )


# ---------------------------------------------------------------------------
# Nothing personal comes out
# ---------------------------------------------------------------------------
def test_no_admin_response_carries_anything_a_mentor_typed(client, admin):
    """
    Registered with distinctive strings, and none of them is in any response.

    Stronger than checking field names, because it fails for a field that
    does not exist yet, and it covers all six endpoints at once.
    """
    secrets_sent = {
        "name": "Zephaniah Quillingsworth",
        "email": "zephaniah.quillingsworth@example.com",
        "headline": "Ornithologist turned staff engineer",
        "bio": "Sixteen years of herpetology and distributed systems.",
        "credentials": "Fellow of the Institute of Imaginary Things",
        "experience_summary": "Principal engineer at Vexillographers Limited",
    }
    register(client, **secrets_sent)

    for path in ADMIN_PATHS:
        served = json.dumps(client.get(path, headers=admin["headers"]).json()).lower()
        for value in secrets_sent.values():
            assert value.lower() not in served, f"{value} leaked from {path}"


def test_the_activity_table_carries_no_mentor_id(client, api_sessions, admin):
    """
    The stored row names the account; the response does not.

    A recent-activity list is read to see what the service is doing, and the
    account behind a call adds nothing to that while turning a page of
    figures into a page about people.
    """
    seeded(client, api_sessions)

    body = client.get("/admin/recent", headers=admin["headers"]).json()

    assert body["events"]
    for event in body["events"]:
        assert "mentor_id" not in event
        assert "mentor" not in event
