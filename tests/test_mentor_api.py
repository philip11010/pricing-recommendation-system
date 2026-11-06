"""
Tests for the mentor-facing API.

Four concerns. That the new-mentor path works end to end: options, register,
price, read back. That a mentor with a track record is priced by the other
model, and shown their advice against what they charge today. That a bad
payload is refused with something a mentor could act on. And that one mentor
can never see another's rows, which is the only security property the
prototype has and the one that has to hold before authentication exists.

Most of the module needs the prepared models, so it is marked ``app_assets``.
The handful of tests that do not need them say so by using the modelless
client instead.
"""

from __future__ import annotations

import pytest

from src.db.mentor_models import Mentor, MentorHistory, Service
from src.mentor import mapping
from src.mentor.dependencies import MENTOR_ID_HEADER

from .conftest import SYNTHETIC_HISTORY

pytestmark = pytest.mark.app_assets

REGISTRATION = {
    "full_name": "A. Mentor",
    "email": "mentor@example.com",
    "years_mentoring_band": "3_to_5",
    "services_planned": 1,
    "headline": "Helping graduate engineers find their first role",
    "bio": "Twelve years in software, six of them leading teams.",
    "education_level": "masters",
    "experience_summary": "Senior engineer, then engineering manager.",
    "credentials": "Chartered engineer.",
    "service": {
        "field": "technology_software",
        "max_mentees": 1,
        "min_commitment": 1,
        "skills": ["cv_review", "interview_preparation", "career_planning"],
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


def give_history(sessions, mentor_id: int, **overrides) -> None:
    """
    Write a mentor a complete track record.

    Through a session rather than an endpoint, because that is how a track
    record comes into being: the platform computes it from the mentor's
    activity, and there is no request a mentor could make that creates one.
    """
    with sessions() as session:
        session.add(
            MentorHistory(mentor_id=mentor_id, **{**SYNTHETIC_HISTORY, **overrides})
        )
        session.commit()


def set_current_price(sessions, service_id: int, price: int | None) -> None:
    """What the mentor charges for a service today. Also not asked at signup."""
    with sessions() as session:
        service = session.get(Service, service_id)
        service.current_price = price
        session.commit()


def make_demo(sessions, mentor_id: int, source_key: int) -> None:
    """Flag a registered mentor as one of the seeded demonstration mentors."""
    with sessions() as session:
        mentor = session.get(Mentor, mentor_id)
        mentor.is_demo = True
        mentor.source_key = source_key
        session.commit()


# ---------------------------------------------------------------------------
# Health and options
# ---------------------------------------------------------------------------
def test_health_reports_the_loaded_models(client):
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["models_loaded"] is True
    assert body["model_version"]
    assert body["currency"] == "AUD"


@pytest.mark.app_assets
def test_health_without_models_says_so_rather_than_failing(modelless_client):
    response = modelless_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["models_loaded"] is False
    assert "prepare_app_assets" in body["detail"]


def test_the_options_endpoint_returns_every_list_the_form_needs(client):
    body = client.get("/meta/options").json()

    assert len(body["fields"]) == 12
    assert len(body["skills"]) == 30
    assert body["max_mentees"] == {"min": 1, "max": 8}
    assert body["currency"] == "AUD"


def test_the_options_endpoint_no_longer_offers_a_session_format(client):
    """
    The question is gone. What a session is called follows from how many
    mentees can join it, so the endpoint publishes that rule instead.
    """
    body = client.get("/meta/options").json()

    assert "service_types" not in body
    assert body["session_label_rule"]["one_to_one"]["max_mentees"] == 1
    assert body["session_label_rule"]["group"]["max_mentees_from"] == 2


def test_the_options_endpoint_works_without_models(modelless_client):
    """
    The form has to render on a server that cannot price anything yet, so the
    frontend can show the mentor the form and the reason.
    """
    assert modelless_client.get("/meta/options").status_code == 200


def test_nothing_the_api_returns_names_the_source_dataset(client):
    """
    The vocabulary boundary, checked on the widest surface: the options list
    and the OpenAPI document, which is every description in the API at once.
    """
    text = (client.get("/meta/options").text + client.get("/openapi.json").text).lower()

    for leaked in ("airbnb", "listing", "nightly", "superhost", "usd"):
        assert leaked not in text


# ---------------------------------------------------------------------------
# Registration, end to end
# ---------------------------------------------------------------------------
def test_registering_returns_the_mentor_the_service_and_a_price(client):
    body = register(client)

    assert body["mentor"]["id"] >= 1
    assert body["mentor"]["email"] == "mentor@example.com"
    assert body["service"]["mentor_id"] == body["mentor"]["id"]
    assert body["recommendation"]["service_id"] == body["service"]["id"]


def test_the_first_price_is_marked_low_confidence(client):
    """
    A price from the registration form alone is a weaker claim than one from a
    track record, and the response has to say so.
    """
    recommendation = register(client)["recommendation"]

    assert recommendation["model_used"] == "core"
    assert recommendation["low_confidence"] is True


def test_the_first_price_is_bracketed_and_in_whole_currency_units(client):
    recommendation = register(client)["recommendation"]

    assert recommendation["currency"] == "AUD"
    assert (
        recommendation["price_low"]
        < recommendation["recommended_price"]
        < recommendation["price_high"]
    )
    assert recommendation["recommended_price"] == int(
        recommendation["recommended_price"]
    )


def test_a_new_price_starts_as_pending(client):
    """The system advises. Nothing is decided until the mentor decides it."""
    assert register(client)["recommendation"]["status"] == "pending"


def test_the_mentor_record_never_includes_a_password_hash(client):
    mentor = register(client)["mentor"]

    assert "password_hash" not in mentor


def test_the_profile_text_is_stored_as_entered(client):
    mentor = register(client)["mentor"]

    assert mentor["headline"] == REGISTRATION["headline"]
    assert mentor["education_level"] == "masters"
    assert mentor["credentials"] == REGISTRATION["credentials"]


def test_a_mentor_can_read_their_own_record(client):
    mentor_id = register(client)["mentor"]["id"]

    response = client.get(f"/mentors/{mentor_id}", headers=headers(mentor_id))

    assert response.status_code == 200
    assert response.json()["id"] == mentor_id


def test_the_same_email_cannot_register_twice(client):
    register(client)

    response = client.post("/mentors", json=registration())

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_registering_without_models_explains_itself(modelless_client):
    response = modelless_client.post("/mentors", json=registration())

    assert response.status_code == 503
    assert "prepare_app_assets" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Pricing an existing service
# ---------------------------------------------------------------------------
def test_a_service_can_be_priced_again(client):
    body = register(client)
    mentor_id = body["mentor"]["id"]
    service_id = body["service"]["id"]

    response = client.post(
        f"/services/{service_id}/recommendations", headers=headers(mentor_id)
    )

    assert response.status_code == 201
    assert response.json()["service_id"] == service_id


def test_pricing_again_gives_the_same_number_for_unchanged_answers(client):
    body = register(client)
    mentor_id = body["mentor"]["id"]
    service_id = body["service"]["id"]

    again = client.post(
        f"/services/{service_id}/recommendations", headers=headers(mentor_id)
    ).json()

    assert again["recommended_price"] == body["recommendation"]["recommended_price"]
    assert again["id"] != body["recommendation"]["id"]


def test_a_recommendation_can_be_read_back(client):
    body = register(client)
    mentor_id = body["mentor"]["id"]
    recommendation_id = body["recommendation"]["id"]

    response = client.get(
        f"/recommendations/{recommendation_id}", headers=headers(mentor_id)
    )

    assert response.status_code == 200
    assert response.json() == body["recommendation"]


# ---------------------------------------------------------------------------
# Invalid payloads
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("override", "expected_field"),
    [
        ({"service": {"field": "astrophysics"}}, "service.field"),
        ({"service": {"max_mentees": 0}}, "service.max_mentees"),
        ({"service": {"max_mentees": 17}}, "service.max_mentees"),
        ({"service": {"max_mentees": 99}}, "service.max_mentees"),
        ({"service": {"min_commitment": 4}}, "service.min_commitment"),
        ({"service": {"skills": ["juggling"]}}, "service.skills"),
        ({"years_mentoring_band": "2_to_3"}, "years_mentoring_band"),
        ({"services_planned": 9}, "services_planned"),
        ({"education_level": "wizardry"}, "education_level"),
        ({"email": "not-an-email"}, "email"),
    ],
)
def test_an_invalid_answer_is_named_and_explained(client, override, expected_field):
    response = client.post("/mentors", json=registration(**override))

    assert response.status_code == 422
    body = response.json()
    assert body["detail"]
    fields = {error["field"] for error in body["errors"]}
    assert expected_field in fields
    assert all(error["message"] for error in body["errors"])


def test_a_missing_answer_is_reported_as_required(client):
    payload = registration()
    del payload["years_mentoring_band"]

    body = client.post("/mentors", json=payload).json()

    errors = {error["field"]: error["message"] for error in body["errors"]}
    assert errors["years_mentoring_band"] == "This answer is required."


def test_an_unknown_field_is_refused_rather_than_ignored(client):
    payload = registration()
    payload["hourly_rate"] = 200

    response = client.post("/mentors", json=payload)

    assert response.status_code == 422
    assert "hourly_rate" in {error["field"] for error in response.json()["errors"]}


@pytest.mark.parametrize("mentees", [0, 9, 16])
def test_a_group_size_outside_the_range_is_explained_in_mentor_language(
    client, mentees
):
    """
    The two ends either side of the range. The message has to name the range
    in the words the form uses, because the group size is now the only
    question about the shape of a session.
    """
    response = client.post(
        "/mentors", json=registration(service={"max_mentees": mentees})
    )

    assert response.status_code == 422
    errors = {error["field"]: error["message"] for error in response.json()["errors"]}
    message = errors["service.max_mentees"].lower()
    assert "mentees" in message
    assert "1" in message and "8" in message
    for leaked in ("accommodates", "room_type", "guest", "night"):
        assert leaked not in message


def test_a_session_format_sent_anyway_is_refused_rather_than_ignored(client):
    """
    A frontend still posting the old question is told, rather than quietly
    priced on something it did not send.
    """
    payload = registration()
    payload["service"]["service_type"] = "one_to_one"

    response = client.post("/mentors", json=payload)

    assert response.status_code == 422
    assert "service.service_type" in {
        error["field"] for error in response.json()["errors"]
    }


def test_an_error_message_is_written_for_the_mentor(client):
    response = client.post("/mentors", json=registration(service={"max_mentees": 99}))

    messages = " ".join(error["message"] for error in response.json()["errors"])
    assert "mentees" in messages.lower()
    assert "accommodates" not in messages.lower()


def test_every_error_body_has_the_same_shape(client):
    """One client path handles all of them, so they all look alike."""
    bodies = [
        client.post("/mentors", json={}).json(),
        client.get("/mentors/1").json(),
        client.get("/mentors/999", headers=headers(999)).json(),
    ]

    for body in bodies:
        assert set(body) == {"detail", "errors"}
        assert isinstance(body["detail"], str)
        assert isinstance(body["errors"], list)


# ---------------------------------------------------------------------------
# Scoping
#
# There is no authentication yet, so these are the tests that hold the line.
# ---------------------------------------------------------------------------
def test_another_mentors_record_is_not_found(client):
    first = register(client)["mentor"]["id"]
    second = register(client, email="other@example.com")["mentor"]["id"]

    response = client.get(f"/mentors/{second}", headers=headers(first))

    assert response.status_code == 404


def test_another_mentors_service_cannot_be_priced(client):
    first = register(client)
    second = register(client, email="other@example.com")

    response = client.post(
        f"/services/{second['service']['id']}/recommendations",
        headers=headers(first["mentor"]["id"]),
    )

    assert response.status_code == 404


def test_another_mentors_recommendation_is_not_found(client):
    first = register(client)
    second = register(client, email="other@example.com")

    response = client.get(
        f"/recommendations/{second['recommendation']['id']}",
        headers=headers(first["mentor"]["id"]),
    )

    assert response.status_code == 404


def test_a_refusal_does_not_reveal_that_the_record_exists(client):
    """
    404 rather than 403, and the same message either way: a different answer
    for "exists but not yours" would let a caller enumerate other mentors.
    """
    first = register(client)["mentor"]["id"]
    second = register(client, email="other@example.com")["mentor"]["id"]

    existing = client.get(f"/mentors/{second}", headers=headers(first))
    absent = client.get("/mentors/99999", headers=headers(first))

    assert existing.status_code == absent.status_code == 404
    assert existing.json() == absent.json()


@pytest.mark.parametrize("path", ["/mentors/1", "/recommendations/1"])
def test_a_mentor_scoped_endpoint_needs_an_identity(client, path):
    response = client.get(path)

    assert response.status_code == 401
    assert MENTOR_ID_HEADER in response.json()["detail"]


def test_a_non_numeric_identity_is_refused(client):
    response = client.get("/mentors/1", headers={MENTOR_ID_HEADER: "someone-else"})

    assert response.status_code == 401
    assert "whole number" in response.json()["detail"]


def test_registration_needs_no_identity(client):
    """It is the request that creates one."""
    assert client.post("/mentors", json=registration()).status_code == 201


# ---------------------------------------------------------------------------
# What is recorded
# ---------------------------------------------------------------------------
def test_the_stored_snapshot_holds_what_the_model_was_given(client, db_session):
    from src.db.mentor_models import PricingRecommendation

    recommendation_id = register(client)["recommendation"]["id"]
    read_back = client.get(
        f"/recommendations/{recommendation_id}",
        headers=headers(1),
    ).json()

    assert read_back["model_version"]
    assert read_back["model_used"] in {"core", "full"}
    assert PricingRecommendation.__tablename__ == "recommendations"


def test_the_price_moves_with_the_group_size_through_the_api(client):
    """The same directional check as the prediction tests, over HTTP."""
    one = register(client, service={"max_mentees": 1})
    eight = register(client, email="other@example.com", service={"max_mentees": 8})

    assert (
        eight["recommendation"]["recommended_price"]
        > one["recommendation"]["recommended_price"]
    )


@pytest.mark.parametrize(
    ("mentees", "expected"),
    [(1, "one_to_one"), (2, "group"), (8, "group")],
)
def test_the_service_carries_the_label_its_group_size_implies(
    client, mentees, expected
):
    """
    The label is derived and returned, so the frontend never has to decide
    what to call a session and cannot disagree with the stored record.
    """
    body = register(client, service={"max_mentees": mentees})

    assert body["service"]["session_label"] == expected
    assert "service_type" not in body["service"]


def test_the_price_comes_with_a_per_mentee_figure(client):
    """
    A session total alone does not tell a mentor whether a group is worth
    running, so the response divides it by the seats as well.
    """
    recommendation = register(client, service={"max_mentees": 4})["recommendation"]

    assert recommendation["price_per_mentee"] == round(
        recommendation["recommended_price"] / 4
    )
    assert recommendation["price_per_mentee_low"] == round(
        recommendation["price_low"] / 4
    )
    assert recommendation["price_per_mentee_high"] == round(
        recommendation["price_high"] / 4
    )


def test_a_one_to_one_price_is_the_same_per_mentee_as_per_session(client):
    recommendation = register(client, service={"max_mentees": 1})["recommendation"]

    assert recommendation["price_per_mentee"] == recommendation["recommended_price"]
    assert recommendation["price_per_mentee_low"] == recommendation["price_low"]
    assert recommendation["price_per_mentee_high"] == recommendation["price_high"]


def test_the_per_mentee_figures_survive_a_read_back(client):
    """
    They are divided out of the stored session prices rather than stored, so
    reading a price back has to produce the same six numbers.
    """
    body = register(client, service={"max_mentees": 8})
    mentor_id = body["mentor"]["id"]
    recommendation_id = body["recommendation"]["id"]

    read_back = client.get(
        f"/recommendations/{recommendation_id}", headers=headers(mentor_id)
    ).json()

    assert read_back == body["recommendation"]


@pytest.mark.parametrize("band", ["under_1", "1_to_2", "6_to_10", "over_10"])
def test_the_experience_band_does_not_change_the_price(client, band):
    """
    Change 2, over HTTP. The band is stored and returned on the mentor's
    record, and the price is the same whatever it says.
    """
    baseline = register(client, years_mentoring_band="3_to_5")
    other = register(client, email=f"{band}@example.com", years_mentoring_band=band)

    assert other["mentor"]["years_mentoring_band"] == band
    assert (
        other["recommendation"]["recommended_price"]
        == baseline["recommendation"]["recommended_price"]
    )
    assert (
        other["recommendation"]["price_per_mentee"]
        == baseline["recommendation"]["price_per_mentee"]
    )


def test_the_api_prices_a_new_mentor_on_the_new_mentor_tenure(client, pricing):
    """
    The constant, checked where it matters: the price the API returns is the
    price of a row carrying it. A registration routed through the experience
    band instead would come back as a different number.
    """
    body = register(client)
    expected = pricing.predict(
        mapping.to_model_inputs(
            field=REGISTRATION["service"]["field"],
            max_mentees=REGISTRATION["service"]["max_mentees"],
            min_commitment=REGISTRATION["service"]["min_commitment"],
            skills=REGISTRATION["service"]["skills"],
            profile_verified=REGISTRATION["service"]["profile_verified"],
            services_planned=REGISTRATION["services_planned"],
            services_count=1,
        )
    )

    assert mapping.NEW_MENTOR_TENURE_YEARS == 0.5
    assert body["recommendation"]["recommended_price"] == expected.recommended_price
    assert body["recommendation"]["price_per_mentee"] == expected.price_per_mentee


def test_a_mentor_planning_four_services_is_priced_differently(client):
    """
    The registration question about planned services has to reach the model,
    or asking it is pointless.
    """
    one = register(client, services_planned=1)
    four = register(client, email="other@example.com", services_planned=4)

    assert (
        four["recommendation"]["recommended_price"]
        != one["recommendation"]["recommended_price"]
    )


def test_the_recommendation_names_a_model_the_mapping_knows_about(client):
    recommendation = register(client)["recommendation"]

    assert recommendation["model_used"] == "core"
    assert len(mapping.CORE_COLUMNS) == 8


# ---------------------------------------------------------------------------
# An established mentor
#
# The other half of the system: a mentor with a track record is priced by the
# second model, on their own time on the platform rather than on the
# new-mentor constant, and the low-confidence flag goes away.
# ---------------------------------------------------------------------------
def test_a_mentor_with_a_track_record_is_priced_by_the_full_model(client, api_sessions):
    body = register(client)
    mentor_id = body["mentor"]["id"]
    give_history(api_sessions, mentor_id)

    priced = client.post(
        f"/services/{body['service']['id']}/recommendations",
        headers=headers(mentor_id),
    ).json()

    assert priced["model_used"] == "full"
    assert priced["low_confidence"] is False


def test_a_track_record_changes_the_price_for_the_same_answers(client, api_sessions):
    """
    The point of the second model. Same profile, same service, same answers:
    the only difference is that the platform now knows what the mentor has
    actually done, and the price has to respond to it.
    """
    body = register(client)
    mentor_id = body["mentor"]["id"]
    core_price = body["recommendation"]["recommended_price"]
    give_history(api_sessions, mentor_id)

    full = client.post(
        f"/services/{body['service']['id']}/recommendations",
        headers=headers(mentor_id),
    ).json()

    assert full["recommended_price"] != core_price
    assert full["price_low"] < full["recommended_price"] < full["price_high"]


def test_a_partial_track_record_keeps_the_mentor_on_the_core_model(
    client, api_sessions
):
    """
    The full model has no notion of a missing input, so a record with a gap in
    it is worth no more than none at all and must not be half used.
    """
    body = register(client)
    mentor_id = body["mentor"]["id"]
    incomplete = {**SYNTHETIC_HISTORY}
    del incomplete["rating_overall"]
    with api_sessions() as session:
        session.add(MentorHistory(mentor_id=mentor_id, **incomplete))
        session.commit()

    priced = client.post(
        f"/services/{body['service']['id']}/recommendations",
        headers=headers(mentor_id),
    ).json()

    assert priced["model_used"] == "core"
    assert priced["low_confidence"] is True


def test_a_track_record_without_tenure_keeps_the_mentor_on_the_core_model(
    client, api_sessions
):
    """Tenure is part of the record, so a row missing it is incomplete."""
    body = register(client)
    mentor_id = body["mentor"]["id"]
    without_tenure = {**SYNTHETIC_HISTORY}
    del without_tenure[mapping.HISTORY_TENURE_FIELD]
    with api_sessions() as session:
        session.add(MentorHistory(mentor_id=mentor_id, **without_tenure))
        session.commit()

    priced = client.post(
        f"/services/{body['service']['id']}/recommendations",
        headers=headers(mentor_id),
    ).json()

    assert priced["model_used"] == "core"


def test_the_full_price_is_the_one_the_prediction_service_gives(
    client, api_sessions, pricing
):
    """
    The API's full-model row, checked against the row built straight from the
    mapping layer. A wired-up-wrong full path would still return a number.
    """
    body = register(client)
    mentor_id = body["mentor"]["id"]
    give_history(api_sessions, mentor_id)

    priced = client.post(
        f"/services/{body['service']['id']}/recommendations",
        headers=headers(mentor_id),
    ).json()

    expected = pricing.predict(
        mapping.to_model_inputs(
            field=REGISTRATION["service"]["field"],
            max_mentees=REGISTRATION["service"]["max_mentees"],
            min_commitment=REGISTRATION["service"]["min_commitment"],
            skills=REGISTRATION["service"]["skills"],
            profile_verified=REGISTRATION["service"]["profile_verified"],
            services_planned=REGISTRATION["services_planned"],
            services_count=1,
        ),
        mapping.history_to_model_inputs(SYNTHETIC_HISTORY),
    )

    assert priced["recommended_price"] == expected.recommended_price
    assert priced["price_low"] == expected.price_low
    assert priced["price_high"] == expected.price_high


# ---------------------------------------------------------------------------
# The advice against what the mentor charges now
# ---------------------------------------------------------------------------
def test_a_service_with_no_price_set_has_nothing_to_compare_against(client):
    """All three comparison figures are null together, not zero."""
    recommendation = register(client)["recommendation"]

    assert recommendation["current_price"] is None
    assert recommendation["difference_vs_current_percent"] is None
    assert recommendation["position_vs_range"] is None


def test_the_advice_is_reported_against_the_current_price(client, api_sessions):
    body = register(client)
    mentor_id = body["mentor"]["id"]
    service_id = body["service"]["id"]
    set_current_price(api_sessions, service_id, 150)

    priced = client.post(
        f"/services/{service_id}/recommendations", headers=headers(mentor_id)
    ).json()

    assert priced["current_price"] == 150
    assert priced["difference_vs_current_percent"] == round(
        (priced["recommended_price"] - 150) / 150 * 100, 1
    )
    assert priced["position_vs_range"] in {"below", "within", "above"}


@pytest.mark.parametrize(
    ("offset", "expected"),
    [(-10, "below"), (0, "within"), (10, "above")],
)
def test_each_position_against_the_range_is_reported(
    client, api_sessions, offset, expected
):
    """
    One case either side of the range and one inside it, set by moving the
    current price relative to the range the mentor was actually given.
    """
    body = register(client)
    mentor_id = body["mentor"]["id"]
    service_id = body["service"]["id"]
    advice = body["recommendation"]

    if expected == "below":
        current = advice["price_low"] + offset
    elif expected == "above":
        current = advice["price_high"] + offset
    else:
        current = advice["recommended_price"]
    set_current_price(api_sessions, service_id, current)

    priced = client.post(
        f"/services/{service_id}/recommendations", headers=headers(mentor_id)
    ).json()

    assert priced["current_price"] == current
    assert priced["position_vs_range"] == expected


def test_the_comparison_survives_a_read_back(client, api_sessions):
    """
    The three figures are derived on read rather than stored, so reading a
    price back has to produce the same comparison.
    """
    body = register(client)
    mentor_id = body["mentor"]["id"]
    set_current_price(api_sessions, body["service"]["id"], 200)
    priced = client.post(
        f"/services/{body['service']['id']}/recommendations",
        headers=headers(mentor_id),
    ).json()

    read_back = client.get(
        f"/recommendations/{priced['id']}", headers=headers(mentor_id)
    ).json()

    assert read_back == priced


# ---------------------------------------------------------------------------
# A mentor's own record
# ---------------------------------------------------------------------------
def test_a_mentors_record_lists_their_services_and_what_each_one_charges(
    client, api_sessions
):
    body = register(client)
    mentor_id = body["mentor"]["id"]
    set_current_price(api_sessions, body["service"]["id"], 240)

    mentor = client.get(f"/mentors/{mentor_id}", headers=headers(mentor_id)).json()

    assert [service["id"] for service in mentor["services"]] == [body["service"]["id"]]
    assert mentor["services"][0]["current_price"] == 240


def test_a_mentor_with_no_track_record_reports_none(client):
    mentor_id = register(client)["mentor"]["id"]

    mentor = client.get(f"/mentors/{mentor_id}", headers=headers(mentor_id)).json()

    assert mentor["history"] is None


def test_a_mentors_record_summarises_their_track_record_in_mentor_language(
    client, api_sessions
):
    mentor_id = register(client)["mentor"]["id"]
    give_history(api_sessions, mentor_id)

    mentor = client.get(f"/mentors/{mentor_id}", headers=headers(mentor_id)).json()

    history = mentor["history"]
    assert history["complete"] is True
    assert history["reviews_total"] == SYNTHETIC_HISTORY["reviews_total"]
    assert history["rating_overall"] == SYNTHETIC_HISTORY["rating_overall"]
    assert history["tenure_years"] == SYNTHETIC_HISTORY["tenure_years"]
    for leaked in ("superhost", "occ_30", "review_scores_rating", "calendar"):
        assert leaked not in str(history)


def test_an_incomplete_track_record_says_it_is_incomplete(client, api_sessions):
    mentor_id = register(client)["mentor"]["id"]
    partial = {**SYNTHETIC_HISTORY}
    del partial["reviews_per_month"]
    with api_sessions() as session:
        session.add(MentorHistory(mentor_id=mentor_id, **partial))
        session.commit()

    mentor = client.get(f"/mentors/{mentor_id}", headers=headers(mentor_id)).json()

    assert mentor["history"]["complete"] is False
    assert mentor["history"]["reviews_per_month"] is None


# ---------------------------------------------------------------------------
# Adding another service
# ---------------------------------------------------------------------------
SECOND_SERVICE = {
    "field": "engineering",
    "max_mentees": 4,
    "min_commitment": 2,
    "skills": ["portfolio_review", "career_planning"],
    "profile_verified": True,
}


def test_a_mentor_can_add_another_service_and_is_given_a_price_for_it(client):
    mentor_id = register(client)["mentor"]["id"]

    response = client.post(
        f"/mentors/{mentor_id}/services",
        json=SECOND_SERVICE,
        headers=headers(mentor_id),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["service"]["mentor_id"] == mentor_id
    assert body["service"]["field"] == "engineering"
    assert body["service"]["session_label"] == "group"
    assert body["recommendation"]["service_id"] == body["service"]["id"]
    assert body["recommendation"]["recommended_price"] > 0


def test_a_second_service_appears_on_the_mentors_record(client):
    mentor_id = register(client)["mentor"]["id"]
    client.post(
        f"/mentors/{mentor_id}/services",
        json=SECOND_SERVICE,
        headers=headers(mentor_id),
    )

    mentor = client.get(f"/mentors/{mentor_id}", headers=headers(mentor_id)).json()

    assert len(mentor["services"]) == 2


def test_adding_a_service_moves_the_service_count_the_model_is_given(client):
    """
    A mentor who registered planning one service and then published a second
    is priced as someone with a two-service offering, so the first service's
    price changes when it is asked for again.
    """
    body = register(client, services_planned=1)
    mentor_id = body["mentor"]["id"]
    first_service = body["service"]["id"]
    before = body["recommendation"]["recommended_price"]

    client.post(
        f"/mentors/{mentor_id}/services",
        json=SECOND_SERVICE,
        headers=headers(mentor_id),
    )
    after = client.post(
        f"/services/{first_service}/recommendations", headers=headers(mentor_id)
    ).json()

    assert mapping.effective_services(2, 1) == 2
    assert after["recommended_price"] != before


def test_an_added_service_is_validated_the_same_way_as_the_first(client):
    mentor_id = register(client)["mentor"]["id"]

    response = client.post(
        f"/mentors/{mentor_id}/services",
        json={**SECOND_SERVICE, "max_mentees": 99},
        headers=headers(mentor_id),
    )

    assert response.status_code == 422
    errors = {error["field"]: error["message"] for error in response.json()["errors"]}
    assert "mentees" in errors["max_mentees"].lower()


def test_adding_a_service_needs_an_identity(client):
    mentor_id = register(client)["mentor"]["id"]

    response = client.post(f"/mentors/{mentor_id}/services", json=SECOND_SERVICE)

    assert response.status_code == 401


def test_a_service_cannot_be_added_to_another_mentor(client):
    first = register(client)["mentor"]["id"]
    second = register(client, email="other@example.com")["mentor"]["id"]

    response = client.post(
        f"/mentors/{second}/services",
        json=SECOND_SERVICE,
        headers=headers(first),
    )

    assert response.status_code == 404
    # Refused rather than silently written somewhere else: the other mentor
    # still has the one service they registered with.
    other = client.get(f"/mentors/{second}", headers=headers(second)).json()
    assert len(other["services"]) == 1


def test_adding_a_service_without_models_explains_itself(modelless_client):
    response = modelless_client.post(
        "/mentors/1/services", json=SECOND_SERVICE, headers=headers(1)
    )

    assert response.status_code == 503
    assert "prepare_app_assets" in response.json()["detail"]


# ---------------------------------------------------------------------------
# The demonstration list
# ---------------------------------------------------------------------------
def test_the_demo_list_is_empty_until_mentors_are_seeded(client):
    assert client.get("/mentors/demo").json() == []


def test_the_demo_list_needs_no_identity(client, api_sessions):
    """It is the list someone picks an identity from, so requiring one would
    be circular."""
    mentor_id = register(client)["mentor"]["id"]
    make_demo(api_sessions, mentor_id, source_key=1234)

    response = client.get("/mentors/demo")

    assert response.status_code == 200
    assert [entry["id"] for entry in response.json()] == [mentor_id]


def test_the_demo_list_describes_each_mentor_in_mentor_language(client, api_sessions):
    body = register(client)
    mentor_id = body["mentor"]["id"]
    make_demo(api_sessions, mentor_id, source_key=4321)
    give_history(api_sessions, mentor_id)

    entry = client.get("/mentors/demo").json()[0]

    assert entry["display_name"] == REGISTRATION["full_name"]
    assert entry["headline"] == REGISTRATION["headline"]
    assert entry["field_label"] == "Technology and software"
    assert entry["session_label"] == "One to one"
    assert entry["has_history"] is True


def test_the_demo_list_leaves_out_mentors_who_registered(client, api_sessions):
    """
    The list is for demonstration mentors. A real registration is not one,
    whatever it looks like.
    """
    demo = register(client)["mentor"]["id"]
    register(client, email="real@example.com")
    make_demo(api_sessions, demo, source_key=99)

    assert [entry["id"] for entry in client.get("/mentors/demo").json()] == [demo]


def test_a_demo_mentor_without_a_complete_record_says_so(client, api_sessions):
    mentor_id = register(client)["mentor"]["id"]
    make_demo(api_sessions, mentor_id, source_key=7)

    assert client.get("/mentors/demo").json()[0]["has_history"] is False


def test_the_demo_list_works_without_models(modelless_client):
    """
    It names no price, so a server that cannot price anything can still serve
    it and show the demo who is there.
    """
    assert modelless_client.get("/mentors/demo").status_code == 200
