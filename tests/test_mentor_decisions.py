"""
Tests for what the mentor decides, and for what the system reports about it.

This is the part of the system the word "advisory" is about. Everything before
it suggests a price; nothing before it sets one. So the tests that matter most
here are the ones about the difference between the three actions, because the
difference is the whole claim:

* an **accepted** price is the advised price, and a decision that says
  "accepted" while carrying a different number is refused rather than stored,
* a **modified** price is stored as modified and never as accepted, however
  close to the advice it is, because the record of how often mentors change
  the advice is the record of how good the advice was,
* a **rejected** decision may carry the mentor's own price or none.

A recommendation is answered once. The second attempt is a 409, and the test
for it is not about the status code: it is about there being no way to end up
with two answers to one question and no way to tell which one stands.

The dashboard tests are built on a hand-made sequence of decisions rather than
on whatever the models happen to return, so every figure in them can be
stated in the test rather than recomputed by it.
"""

from __future__ import annotations

import pytest

from src.db.mentor_models import PricingDecision, Service
from src.mentor import mapping
from src.mentor.dependencies import MENTOR_ID_HEADER

pytestmark = pytest.mark.app_assets

REGISTRATION = {
    "full_name": "A. Mentor",
    "email": "mentor@example.com",
    "years_mentoring_band": "3_to_5",
    "services_planned": 1,
    "headline": "Helping graduate engineers find their first role",
    "service": {
        "field": "technology_software",
        "max_mentees": 1,
        "min_commitment": 1,
        "skills": ["cv_review", "interview_preparation"],
        "profile_verified": True,
    },
}


def registration(**overrides):
    payload = {**REGISTRATION, **overrides}
    payload["service"] = {**REGISTRATION["service"], **overrides.get("service", {})}
    return payload


def register(client, **overrides):
    response = client.post("/mentors", json=registration(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def headers(mentor_id: int) -> dict[str, str]:
    return {MENTOR_ID_HEADER: str(mentor_id)}


def decide(client, mentor_id, recommendation_id, **payload):
    return client.post(
        f"/recommendations/{recommendation_id}/decision",
        json=payload,
        headers=headers(mentor_id),
    )


def price_again(client, mentor_id, service_id):
    response = client.post(
        f"/services/{service_id}/recommendations", headers=headers(mentor_id)
    )
    assert response.status_code == 201, response.text
    return response.json()


def current_price(client, mentor_id):
    return client.get(f"/mentors/{mentor_id}", headers=headers(mentor_id)).json()[
        "services"
    ][0]["current_price"]


@pytest.fixture
def registered(client):
    """A mentor with one service and one pending recommendation."""
    body = register(client)
    return body["mentor"]["id"], body["service"]["id"], body["recommendation"]


# ---------------------------------------------------------------------------
# Accepting
# ---------------------------------------------------------------------------
def test_accepting_settles_on_the_advised_price(client, registered):
    mentor_id, _, advice = registered

    response = decide(client, mentor_id, advice["id"], action="accepted")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["action"] == "accepted"
    assert body["final_price"] == advice["recommended_price"]
    assert body["currency"] == "AUD"
    assert body["recommendation_id"] == advice["id"]


def test_accepting_needs_no_price_of_its_own(client, registered):
    """
    The advised price is already in the system, so asking the frontend to send
    it back would be asking it to restate something it was told.
    """
    mentor_id, _, advice = registered

    body = decide(client, mentor_id, advice["id"], action="accepted").json()

    assert body["final_price"] == advice["recommended_price"]


def test_accepting_the_advised_price_explicitly_is_the_same_decision(
    client, registered
):
    mentor_id, _, advice = registered

    body = decide(
        client,
        mentor_id,
        advice["id"],
        action="accepted",
        final_price=advice["recommended_price"],
    ).json()

    assert body["final_price"] == advice["recommended_price"]


def test_accepting_a_different_price_is_refused_rather_than_recorded(
    client, registered
):
    """
    The row would otherwise say the mentor accepted a price they never saw.
    """
    mentor_id, _, advice = registered

    response = decide(
        client,
        mentor_id,
        advice["id"],
        action="accepted",
        final_price=advice["recommended_price"] + 100,
    )

    assert response.status_code == 422
    errors = {error["field"]: error["message"] for error in response.json()["errors"]}
    assert "modified" in errors["final_price"]
    assert current_price(client, mentor_id) is None


def test_accepting_updates_the_status_of_the_advice(client, registered):
    mentor_id, _, advice = registered
    decide(client, mentor_id, advice["id"], action="accepted")

    read_back = client.get(
        f"/recommendations/{advice['id']}", headers=headers(mentor_id)
    ).json()

    assert read_back["status"] == "accepted"


def test_accepting_sets_what_the_service_charges(client, registered):
    mentor_id, _, advice = registered
    assert current_price(client, mentor_id) is None

    decide(client, mentor_id, advice["id"], action="accepted")

    assert current_price(client, mentor_id) == advice["recommended_price"]


# ---------------------------------------------------------------------------
# Modifying
# ---------------------------------------------------------------------------
def test_modifying_records_the_mentors_own_price(client, registered):
    mentor_id, _, advice = registered
    chosen = advice["recommended_price"] + 60

    body = decide(
        client, mentor_id, advice["id"], action="modified", final_price=chosen
    ).json()

    assert body["action"] == "modified"
    assert body["final_price"] == chosen
    assert current_price(client, mentor_id) == chosen


def test_a_modification_is_never_stored_as_an_acceptance(client, registered):
    """
    The share of advice that gets changed is the clearest evidence the system
    will ever have about its own usefulness, so a modification that was filed
    as an acceptance would quietly flatter it.
    """
    mentor_id, _, advice = registered

    decide(
        client,
        mentor_id,
        advice["id"],
        action="modified",
        final_price=advice["recommended_price"] + 1,
    )

    read_back = client.get(
        f"/recommendations/{advice['id']}", headers=headers(mentor_id)
    ).json()
    assert read_back["status"] == "modified"


def test_modifying_without_a_price_is_refused(client, registered):
    mentor_id, _, advice = registered

    response = decide(client, mentor_id, advice["id"], action="modified")

    assert response.status_code == 422
    errors = {error["field"]: error["message"] for error in response.json()["errors"]}
    assert "charge" in errors["final_price"].lower()


def test_modifying_to_the_advised_price_is_refused(client, registered):
    """
    A modification equal to the advice is an acceptance, and storing it as a
    modification would misreport what the mentor did.
    """
    mentor_id, _, advice = registered

    response = decide(
        client,
        mentor_id,
        advice["id"],
        action="modified",
        final_price=advice["recommended_price"],
    )

    assert response.status_code == 422
    errors = {error["field"]: error["message"] for error in response.json()["errors"]}
    assert "accept" in errors["final_price"].lower()


@pytest.mark.parametrize("price", [0, -100, mapping.FINAL_PRICE_MAX + 1, 100_000])
def test_a_price_outside_the_bounds_is_refused(client, registered, price):
    """
    The box a mentor types their own price into is the one place a typo
    becomes a stored price and is then shown back to them as fact.
    """
    mentor_id, _, advice = registered

    response = decide(
        client, mentor_id, advice["id"], action="modified", final_price=price
    )

    assert response.status_code == 422
    assert "final_price" in {error["field"] for error in response.json()["errors"]}
    assert current_price(client, mentor_id) is None


@pytest.mark.parametrize("price", [mapping.FINAL_PRICE_MIN, mapping.FINAL_PRICE_MAX])
def test_the_ends_of_the_range_are_accepted(client, registered, price):
    mentor_id, _, advice = registered

    response = decide(
        client, mentor_id, advice["id"], action="modified", final_price=price
    )

    assert response.status_code == 201, response.text
    assert response.json()["final_price"] == price


@pytest.mark.parametrize("price", [320.5, "320", True, None])
def test_a_price_that_is_not_a_whole_number_is_refused(client, registered, price):
    mentor_id, _, advice = registered

    response = decide(
        client, mentor_id, advice["id"], action="modified", final_price=price
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Rejecting
# ---------------------------------------------------------------------------
def test_rejecting_without_a_price_records_the_refusal_alone(client, registered):
    mentor_id, _, advice = registered

    body = decide(client, mentor_id, advice["id"], action="rejected").json()

    assert body["action"] == "rejected"
    assert body["final_price"] is None
    assert current_price(client, mentor_id) is None


def test_rejecting_with_a_price_records_what_the_mentor_charges(client, registered):
    """
    The most useful thing a mentor who declines the advice can tell the
    system is the number they chose instead of it.
    """
    mentor_id, _, advice = registered

    body = decide(
        client, mentor_id, advice["id"], action="rejected", final_price=275
    ).json()

    assert body["action"] == "rejected"
    assert body["final_price"] == 275
    assert current_price(client, mentor_id) == 275


def test_a_bare_rejection_leaves_what_the_service_charges_alone(client, registered):
    """
    A mentor who already had a price and then declines new advice without
    naming one still charges what they charged.
    """
    mentor_id, service_id, first = registered
    decide(client, mentor_id, first["id"], action="accepted")
    settled = current_price(client, mentor_id)

    second = price_again(client, mentor_id, service_id)
    decide(client, mentor_id, second["id"], action="rejected")

    assert current_price(client, mentor_id) == settled


@pytest.mark.parametrize("price", [0, mapping.FINAL_PRICE_MAX + 1])
def test_a_rejection_price_is_bounded_too(client, registered, price):
    mentor_id, _, advice = registered

    response = decide(
        client, mentor_id, advice["id"], action="rejected", final_price=price
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# One answer per price
# ---------------------------------------------------------------------------
def test_a_recommendation_can_only_be_answered_once(client, registered):
    mentor_id, _, advice = registered
    assert decide(client, mentor_id, advice["id"], action="accepted").status_code == 201

    response = decide(client, mentor_id, advice["id"], action="rejected")

    assert response.status_code == 409
    assert "already answered" in response.json()["detail"]


def test_a_second_answer_changes_nothing(client, registered):
    """
    The 409 is not a formality: the refused answer must leave no trace, or the
    record would say one thing and the service another.
    """
    mentor_id, _, advice = registered
    decide(client, mentor_id, advice["id"], action="accepted")
    settled = current_price(client, mentor_id)

    decide(client, mentor_id, advice["id"], action="modified", final_price=999)

    assert current_price(client, mentor_id) == settled
    read_back = client.get(
        f"/recommendations/{advice['id']}", headers=headers(mentor_id)
    ).json()
    assert read_back["status"] == "accepted"


def test_a_fresh_price_can_be_answered_after_an_earlier_one(client, registered):
    """
    The way to decide again: ask for a new price and answer that. Each answer
    belongs to the advice it was given about.
    """
    mentor_id, service_id, first = registered
    decide(client, mentor_id, first["id"], action="accepted")

    second = price_again(client, mentor_id, service_id)
    response = decide(
        client, mentor_id, second["id"], action="modified", final_price=411
    )

    assert response.status_code == 201
    assert current_price(client, mentor_id) == 411


@pytest.mark.parametrize("action", ["accept", "ignored", "", "ACCEPTED"])
def test_an_unknown_action_is_refused(client, registered, action):
    mentor_id, _, advice = registered

    response = decide(client, mentor_id, advice["id"], action=action, final_price=300)

    assert response.status_code == 422
    assert "action" in {error["field"] for error in response.json()["errors"]}


def test_an_unknown_field_on_a_decision_is_refused(client, registered):
    mentor_id, _, advice = registered

    response = client.post(
        f"/recommendations/{advice['id']}/decision",
        json={"action": "accepted", "notes": "looks about right"},
        headers=headers(mentor_id),
    )

    assert response.status_code == 422
    assert "notes" in {error["field"] for error in response.json()["errors"]}


# ---------------------------------------------------------------------------
# Scoping
# ---------------------------------------------------------------------------
def test_another_mentors_price_cannot_be_answered(client):
    first = register(client)
    second = register(client, email="other@example.com")

    response = decide(
        client,
        first["mentor"]["id"],
        second["recommendation"]["id"],
        action="accepted",
    )

    assert response.status_code == 404


def test_another_mentors_price_is_not_changed_by_the_attempt(client, api_sessions):
    first = register(client)
    second = register(client, email="other@example.com")

    decide(
        client,
        first["mentor"]["id"],
        second["recommendation"]["id"],
        action="modified",
        final_price=4999,
    )

    with api_sessions() as session:
        service = session.get(Service, second["service"]["id"])
        assert service.current_price is None
        assert session.query(PricingDecision).count() == 0


def test_answering_needs_an_identity(client, registered):
    _, _, advice = registered

    response = client.post(
        f"/recommendations/{advice['id']}/decision", json={"action": "accepted"}
    )

    assert response.status_code == 401


def test_a_price_that_does_not_exist_is_not_found(client, registered):
    mentor_id, _, _ = registered

    response = decide(client, mentor_id, 99999, action="accepted")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------
def test_the_history_holds_every_price_newest_first(client, registered):
    mentor_id, service_id, first = registered
    second = price_again(client, mentor_id, service_id)
    third = price_again(client, mentor_id, service_id)

    body = client.get(
        f"/services/{service_id}/history", headers=headers(mentor_id)
    ).json()

    assert body["service_id"] == service_id
    assert body["count"] == 3
    assert [item["recommendation"]["id"] for item in body["items"]] == [
        third["id"],
        second["id"],
        first["id"],
    ]


def test_an_unanswered_price_has_no_decision(client, registered):
    mentor_id, service_id, _ = registered

    body = client.get(
        f"/services/{service_id}/history", headers=headers(mentor_id)
    ).json()

    assert body["items"][0]["decision"] is None
    assert body["items"][0]["recommendation"]["status"] == "pending"


def test_each_price_in_the_history_carries_what_came_of_it(client, registered):
    mentor_id, service_id, first = registered
    decide(client, mentor_id, first["id"], action="accepted")
    second = price_again(client, mentor_id, service_id)
    decide(client, mentor_id, second["id"], action="modified", final_price=500)
    third = price_again(client, mentor_id, service_id)
    decide(client, mentor_id, third["id"], action="rejected")

    items = client.get(
        f"/services/{service_id}/history", headers=headers(mentor_id)
    ).json()["items"]

    answers = [
        (item["decision"]["action"], item["decision"]["final_price"]) for item in items
    ]
    assert answers == [
        ("rejected", None),
        ("modified", 500),
        ("accepted", first["recommended_price"]),
    ]


def test_the_history_needs_no_models(client, registered, comparableless_client):
    """
    Every figure in it was stored when the price was given, so reading it back
    asks nothing of the models.
    """
    mentor_id, service_id, _ = registered

    body = client.get(f"/services/{service_id}/history", headers=headers(mentor_id))

    assert body.status_code == 200


def test_another_mentors_history_is_not_found(client):
    first = register(client)
    second = register(client, email="other@example.com")

    response = client.get(
        f"/services/{second['service']['id']}/history",
        headers=headers(first["mentor"]["id"]),
    )

    assert response.status_code == 404


def test_reading_the_history_needs_an_identity(client, registered):
    _, service_id, _ = registered

    assert client.get(f"/services/{service_id}/history").status_code == 401


# ---------------------------------------------------------------------------
# The dashboard, on a hand-built sequence
# ---------------------------------------------------------------------------
@pytest.fixture
def answered(client, registered):
    """
    One service with four prices answered in four different ways.

    Every figure the dashboard reports about it can be stated from this
    fixture: one accepted at the advice, one modified to the advice plus 100,
    one rejected at 200, and one left pending.
    """
    mentor_id, service_id, first = registered
    advised = first["recommended_price"]

    decide(client, mentor_id, first["id"], action="accepted")
    second = price_again(client, mentor_id, service_id)
    decide(
        client, mentor_id, second["id"], action="modified", final_price=advised + 100
    )
    third = price_again(client, mentor_id, service_id)
    decide(client, mentor_id, third["id"], action="rejected", final_price=200)
    price_again(client, mentor_id, service_id)

    return mentor_id, service_id, advised


def dashboard(client, mentor_id):
    response = client.get(f"/mentors/{mentor_id}/dashboard", headers=headers(mentor_id))
    assert response.status_code == 200, response.text
    return response.json()


def test_the_dashboard_describes_the_service_in_mentor_language(client, answered):
    mentor_id, service_id, _ = answered

    service = dashboard(client, mentor_id)["services"][0]

    assert service["service_id"] == service_id
    assert service["field_label"] == "Technology and software"
    assert service["session_label"] == "One to one"
    assert service["max_mentees"] == 1
    assert service["currency"] == "AUD"


def test_the_dashboard_counts_the_decisions_by_action(client, answered):
    mentor_id, _, _ = answered

    service = dashboard(client, mentor_id)["services"][0]

    assert service["decision_counts"] == {
        "accepted": 1,
        "modified": 1,
        "rejected": 1,
        "pending": 1,
    }


def test_the_dashboard_averages_the_difference_from_the_advice(client, answered):
    """
    Three answers named a price: the advice itself, the advice plus 100, and
    200. The average is of the three percentages, not of the three amounts.
    """
    mentor_id, _, advised = answered

    service = dashboard(client, mentor_id)["services"][0]

    expected = round((0 + 100 / advised * 100 + (200 - advised) / advised * 100) / 3, 1)
    assert service["average_difference_percent"] == expected


def test_a_mentor_who_has_answered_nothing_has_no_average(client, registered):
    mentor_id, _, _ = registered

    service = dashboard(client, mentor_id)["services"][0]

    assert service["average_difference_percent"] is None
    assert service["decision_counts"]["pending"] == 1


def test_the_dashboard_reports_the_latest_price_and_what_is_charged_now(
    client, answered
):
    mentor_id, service_id, _ = answered
    history = client.get(
        f"/services/{service_id}/history", headers=headers(mentor_id)
    ).json()
    newest = history["items"][0]["recommendation"]

    service = dashboard(client, mentor_id)["services"][0]

    assert service["latest_recommendation"]["id"] == newest["id"]
    # The last answer that named a price was the rejection at 200.
    assert service["current_price"] == 200


def test_the_dashboard_places_the_current_price_against_the_latest_range(
    client, answered
):
    mentor_id, _, _ = answered

    service = dashboard(client, mentor_id)["services"][0]
    latest = service["latest_recommendation"]

    assert service["position_vs_range"] in {"below", "within", "above"}
    if service["current_price"] < latest["price_low"]:
        assert service["position_vs_range"] == "below"
    elif service["current_price"] > latest["price_high"]:
        assert service["position_vs_range"] == "above"
    else:
        assert service["position_vs_range"] == "within"


def test_the_timeline_runs_oldest_first(client, answered):
    """
    The opposite order to the history, and for the opposite reason: this one
    is plotted against time, and a chart that starts at the right hand end
    reads backwards.
    """
    mentor_id, _, advised = answered

    timeline = dashboard(client, mentor_id)["services"][0]["timeline"]

    assert len(timeline) == 4
    assert [point["action"] for point in timeline] == [
        "accepted",
        "modified",
        "rejected",
        None,
    ]
    assert [point["final_price"] for point in timeline] == [
        advised,
        advised + 100,
        200,
        None,
    ]
    assert [point["generated_at"] for point in timeline] == sorted(
        point["generated_at"] for point in timeline
    )


def test_the_dashboard_reports_where_the_price_sits_among_comparable_mentors(
    client, answered
):
    mentor_id, _, _ = answered

    service = dashboard(client, mentor_id)["services"][0]

    assert service["comparables"]["count"] > 0
    assert service["comparables"]["match_description"]
    assert 0 <= service["price_percentile"] <= 100


def test_a_dashboard_on_a_server_without_the_table_still_answers(
    comparableless_client,
):
    """
    The comparison is one block of the page. Losing it must not take the rest
    of a mentor's own figures with it.
    """
    body = register(comparableless_client)
    mentor_id = body["mentor"]["id"]

    response = comparableless_client.get(
        f"/mentors/{mentor_id}/dashboard", headers=headers(mentor_id)
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["comparables_available"] is False
    service = payload["services"][0]
    assert service["comparables"] is None
    assert service["price_percentile"] is None
    assert service["latest_recommendation"] is not None


def test_the_dashboard_totals_cover_every_service(client, answered):
    mentor_id, _, _ = answered
    client.post(
        f"/mentors/{mentor_id}/services",
        json={
            "field": "engineering",
            "max_mentees": 4,
            "min_commitment": 2,
            "skills": ["career_planning"],
            "profile_verified": True,
        },
        headers=headers(mentor_id),
    )

    payload = dashboard(client, mentor_id)

    assert payload["mentor_id"] == mentor_id
    assert payload["display_name"] == REGISTRATION["full_name"]
    assert payload["totals"]["services"] == 2
    assert payload["totals"]["services_with_a_price"] == 1
    assert payload["totals"]["recommendations"] == 5
    assert payload["totals"]["decision_counts"] == {
        "accepted": 1,
        "modified": 1,
        "rejected": 1,
        "pending": 2,
    }
    assert len(payload["services"]) == 2


def test_the_dashboard_reports_no_earnings_or_income(client, answered):
    """
    The system has no bookings, so it has no volume, and any total in currency
    would be a price multiplied by a number nobody measured.
    """
    mentor_id, _, _ = answered

    text = client.get(
        f"/mentors/{mentor_id}/dashboard", headers=headers(mentor_id)
    ).text.lower()

    for forbidden in ("earning", "income", "revenue", "profit", "turnover", "payout"):
        assert forbidden not in text


def test_the_dashboard_names_nothing_from_the_source_dataset(client, answered):
    mentor_id, _, _ = answered

    text = client.get(
        f"/mentors/{mentor_id}/dashboard", headers=headers(mentor_id)
    ).text.lower()

    for leaked in ("airbnb", "listing", "host", "nightly", "superhost", "occ_"):
        assert leaked not in text


def test_another_mentors_dashboard_is_not_found(client):
    first = register(client)
    second = register(client, email="other@example.com")

    response = client.get(
        f"/mentors/{second['mentor']['id']}/dashboard",
        headers=headers(first["mentor"]["id"]),
    )

    assert response.status_code == 404


def test_reading_a_dashboard_needs_an_identity(client, registered):
    mentor_id, _, _ = registered

    assert client.get(f"/mentors/{mentor_id}/dashboard").status_code == 401
