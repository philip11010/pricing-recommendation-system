"""
Tests for the three things anybody may read: the directory, a profile, a price.

These are the only endpoints in the system served without a token, which
makes them the only ones where a field added by accident is a field published
to the internet. So the first concern of this module is what they do **not**
return: every test about the directory asserts the whole set of keys rather
than the presence of the ones it wants, because a test that checks for what it
expects cannot notice an email address arriving beside it.

The second concern is that a mentor who registered a minute ago is in the
directory on the same terms as a seeded demonstration mentor. That is the
property that makes the list a directory rather than a showcase.

The third is the live preview: the price beside a part-filled registration
form has to be the price the form will produce when it is submitted, it must
write nothing, and it has to be rate limited, because it is the one endpoint
with no account behind it and every call scores a model.

Most of the module needs the prepared models, because registering returns a
price and the preview is a price.
"""

from __future__ import annotations

import pytest

from src.db.mentor_models import Mentor, PricingRecommendation, Service
from src.mentor import mapping
from src.mentor.app import (
    DIRECTORY_DEFAULT_LIMIT,
    DIRECTORY_MAX_LIMIT,
    preview_limiter,
)

from .conftest import REGISTRATION, headers, register, registration

pytestmark = pytest.mark.app_assets

# Exactly what a card carries. Written out rather than derived from the
# response model, because the point of the assertion is to fail when somebody
# adds a field to that model.
CARD_KEYS = {
    "id",
    "display_name",
    "field_label",
    "service_name",
    "price",
    "max_mentees",
    "session_label",
    "verified",
    "review_count",
}

PROFILE_KEYS = CARD_KEYS | {
    "skills",
    "years_experience",
    "years_mentoring_band",
    "education_level",
    "education_label",
    "credentials",
}

PREVIEW = {
    "field": REGISTRATION["field"],
    "max_mentees": REGISTRATION["max_mentees"],
    "skills": REGISTRATION["skills"],
}


@pytest.fixture(autouse=True)
def forget_previous_previews():
    """
    Start every test with the preview counter empty.

    The limiter is one object for the process, so a test that did not reset it
    would be counting the calls of whatever ran before it.
    """
    preview_limiter.forget()
    yield
    preview_limiter.forget()


def preview(client, **overrides):
    return client.post("/preview", json={**PREVIEW, **overrides})


def set_verified(sessions, mentor_id: int, verified: bool = True) -> None:
    """
    Verify a mentor the way the script does.

    Through a session rather than an endpoint, because there is no endpoint: a
    mentor cannot tell the platform that the platform has checked them.
    """
    with sessions() as session:
        mentor = session.get(Mentor, mentor_id)
        mentor.verified = verified
        for service in mentor.services:
            service.profile_verified = verified
        session.commit()


def give_price(sessions, service_id: int, price: int) -> None:
    with sessions() as session:
        session.get(Service, service_id).current_price = price
        session.commit()


# ---------------------------------------------------------------------------
# The directory
# ---------------------------------------------------------------------------
def test_the_directory_is_empty_until_somebody_registers(client):
    body = client.get("/mentors").json()

    assert body == {
        "total": 0,
        "limit": DIRECTORY_DEFAULT_LIMIT,
        "offset": 0,
        "items": [],
    }


def test_the_directory_needs_no_token(client):
    register(client)

    assert client.get("/mentors").status_code == 200


def test_a_mentor_who_just_registered_is_listed(client):
    """
    The property that makes this a directory rather than a showcase. A new
    mentor appears immediately, with their verification shown as what it is.
    """
    body = register(client)

    listed = client.get("/mentors").json()

    assert listed["total"] == 1
    (card,) = listed["items"]
    assert card["id"] == body["mentor"]["id"]
    assert card["display_name"] == REGISTRATION["name"]
    assert card["verified"] is False


def test_a_card_carries_nothing_but_the_nine_fields(client):
    """
    The assertion this module exists for: the whole key set, not the keys a
    test happens to want. Anything added to the card is a field published to
    anybody who asks.
    """
    register(client)

    (card,) = client.get("/mentors").json()["items"]

    assert set(card) == CARD_KEYS


@pytest.mark.parametrize(
    "private",
    ["email", "password_hash", "password", "is_demo", "source_key", "bio", "headline"],
)
def test_a_card_never_carries_a_private_field(client, private):
    register(client)

    (card,) = client.get("/mentors").json()["items"]

    assert private not in card


def test_a_card_names_no_model_input(client):
    """
    The vocabulary boundary on the widest surface the system has. None of the
    eight figures a price is worked out from belongs on a public card.
    """
    register(client)

    text = client.get("/mentors").text.lower()

    for leaked in (
        "accommodates",
        "room_type",
        "neighbourhood",
        "host_identity_verified",
        "tenure",
        "superhost",
        "airbnb",
        "listing",
        "night",
    ):
        assert leaked not in text


def test_a_card_describes_the_mentors_main_service(client):
    body = register(client, field="law", max_mentees=4)

    (card,) = client.get("/mentors").json()["items"]

    assert card["field_label"] == "Law"
    assert card["service_name"] == mapping.service_name("law", 4)
    assert card["max_mentees"] == 4
    assert card["session_label"] == "group"
    assert card["id"] == body["mentor"]["id"]


def test_a_mentor_with_several_services_is_listed_once(client):
    """
    One card per mentor, about the first service they published, rather than
    one card per service.
    """
    mentor_id = register(client)["mentor"]["id"]
    client.post(
        f"/mentors/{mentor_id}/services",
        json={"field": "law", "max_mentees": 4, "min_commitment": 1, "skills": []},
        headers=headers(mentor_id),
    )

    listed = client.get("/mentors").json()

    assert listed["total"] == 1
    assert listed["items"][0]["field_label"] == "Technology and software"


def test_a_card_reports_no_price_until_the_mentor_settles_on_one(client, api_sessions):
    """
    A mentor who has only been advised a price has not set one, and showing
    advice as their price would put a number on their card they never chose.
    """
    body = register(client)

    (card,) = client.get("/mentors").json()["items"]
    assert card["price"] is None

    give_price(api_sessions, body["service"]["id"], 275)
    (card,) = client.get("/mentors").json()["items"]
    assert card["price"] == 275


def test_a_card_reports_a_verified_mentor_as_verified(client, api_sessions):
    mentor_id = register(client)["mentor"]["id"]
    set_verified(api_sessions, mentor_id)

    (card,) = client.get("/mentors").json()["items"]

    assert card["verified"] is True


def test_a_card_counts_the_mentors_reviews_or_says_none(client, api_sessions):
    from src.db.mentor_models import MentorHistory

    from .conftest import SYNTHETIC_HISTORY

    mentor_id = register(client)["mentor"]["id"]
    (card,) = client.get("/mentors").json()["items"]
    assert card["review_count"] == 0

    with api_sessions() as session:
        session.add(MentorHistory(mentor_id=mentor_id, **SYNTHETIC_HISTORY))
        session.commit()

    (card,) = client.get("/mentors").json()["items"]
    assert card["review_count"] == SYNTHETIC_HISTORY["reviews_total"]


def test_the_directory_lists_the_newest_mentor_first(client):
    first = register(client)["mentor"]["id"]
    second = register(client, email="second@example.com")["mentor"]["id"]
    third = register(client, email="third@example.com")["mentor"]["id"]

    listed = client.get("/mentors").json()["items"]

    assert [card["id"] for card in listed] == [third, second, first]


def test_the_directory_can_be_filtered_by_field(client):
    register(client, field="law")
    register(client, email="other@example.com", field="engineering")

    listed = client.get("/mentors", params={"field": "law"}).json()

    assert listed["total"] == 1
    assert listed["items"][0]["field_label"] == "Law"


@pytest.mark.parametrize(("group", "mentees"), [("one_to_one", 1), ("group", 6)])
def test_the_directory_can_be_filtered_by_session_type(client, group, mentees):
    register(client, max_mentees=1)
    register(client, email="other@example.com", max_mentees=6)

    listed = client.get("/mentors", params={"group": group}).json()

    assert listed["total"] == 1
    assert listed["items"][0]["max_mentees"] == mentees
    assert listed["items"][0]["session_label"] == group


def test_the_two_filters_apply_together(client):
    register(client, field="law", max_mentees=1)
    register(client, email="b@example.com", field="law", max_mentees=6)
    register(client, email="c@example.com", field="engineering", max_mentees=1)

    listed = client.get(
        "/mentors", params={"field": "law", "group": "one_to_one"}
    ).json()

    assert listed["total"] == 1
    assert listed["items"][0]["field_label"] == "Law"
    assert listed["items"][0]["max_mentees"] == 1


@pytest.mark.parametrize(
    "params",
    [
        {"field": "astrophysics"},
        {"group": "seminar"},
        {"limit": 0},
        {"limit": DIRECTORY_MAX_LIMIT + 1},
        {"offset": -1},
    ],
)
def test_a_filter_the_directory_cannot_honour_is_refused(client, params):
    assert client.get("/mentors", params=params).status_code == 422


def test_the_directory_pages_and_reports_the_whole_count(client):
    for index in range(3):
        register(client, email=f"mentor{index}@example.com")

    first = client.get("/mentors", params={"limit": 2, "offset": 0}).json()
    second = client.get("/mentors", params={"limit": 2, "offset": 2}).json()

    assert first["total"] == second["total"] == 3
    assert len(first["items"]) == 2
    assert len(second["items"]) == 1
    assert {card["id"] for card in first["items"]}.isdisjoint(
        card["id"] for card in second["items"]
    )


def test_the_directory_works_on_a_server_that_cannot_price(modelless_client):
    """
    It names a price the mentor set rather than one a model worked out, so a
    server with no models can still serve the list.
    """
    assert modelless_client.get("/mentors").status_code == 200


# ---------------------------------------------------------------------------
# One mentor's public profile
# ---------------------------------------------------------------------------
def test_a_public_profile_is_the_card_plus_what_the_mentor_said(client):
    mentor_id = register(client)["mentor"]["id"]

    body = client.get(f"/mentors/{mentor_id}/public").json()

    assert set(body) == PROFILE_KEYS
    assert body["id"] == mentor_id
    assert body["years_experience"] == REGISTRATION["years_experience"]
    assert body["years_mentoring_band"] == "6_to_10"
    assert body["education_level"] == "masters"
    assert body["education_label"] == "Master's degree"
    assert body["credentials"] == REGISTRATION["credentials"]


def test_a_public_profile_lists_the_skills_with_their_labels(client):
    mentor_id = register(client)["mentor"]["id"]

    body = client.get(f"/mentors/{mentor_id}/public").json()

    assert [skill["id"] for skill in body["skills"]] == REGISTRATION["skills"]
    assert all(skill["label"] for skill in body["skills"])
    assert body["skills"][0]["label"] == mapping.SKILLS[REGISTRATION["skills"][0]]


def test_a_public_profile_leaves_out_what_the_mentor_did_not_answer(client):
    payload = registration()
    for optional in ("years_experience", "education_level", "credentials"):
        del payload[optional]

    created = client.post("/auth/register", json=payload).json()
    body = client.get(f"/mentors/{created['mentor']['id']}/public").json()

    assert body["years_experience"] is None
    assert body["years_mentoring_band"] is None
    assert body["education_level"] is None
    assert body["education_label"] is None
    assert body["credentials"] is None


def test_a_public_profile_needs_no_token(client):
    mentor_id = register(client)["mentor"]["id"]

    assert client.get(f"/mentors/{mentor_id}/public").status_code == 200


@pytest.mark.parametrize("private", ["email", "password_hash", "is_demo", "source_key"])
def test_a_public_profile_never_carries_a_private_field(client, private):
    mentor_id = register(client)["mentor"]["id"]

    body = client.get(f"/mentors/{mentor_id}/public").json()

    assert private not in body


def test_a_profile_nobody_has_is_not_found(client):
    assert client.get("/mentors/99999/public").status_code == 404


# ---------------------------------------------------------------------------
# The live preview
# ---------------------------------------------------------------------------
def test_a_preview_prices_three_answers(client):
    response = preview(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_price"] > 0
    assert body["range_low"] < body["session_price"] < body["range_high"]
    assert body["currency"] == "AUD"
    assert body["low_confidence"] is True


def test_a_preview_needs_no_token(client):
    assert preview(client).status_code == 200


def test_a_preview_is_the_price_the_form_will_produce(client):
    """
    The property the whole feature rests on. A preview that differed from the
    price registration goes on to give would be worse than no preview: the
    mentor would watch one number and be given another.
    """
    previewed = preview(client).json()

    registered = register(client)["recommendation"]

    assert previewed["session_price"] == registered["recommended_price"]
    assert previewed["range_low"] == registered["price_low"]
    assert previewed["range_high"] == registered["price_high"]
    assert previewed["per_person_price"] == registered["price_per_mentee"]


def test_a_preview_divides_a_group_price_by_the_seats(client):
    body = preview(client, max_mentees=4).json()

    assert body["per_person_price"] == round(body["session_price"] / 4)


def test_a_preview_of_a_single_mentee_is_the_same_either_way(client):
    body = preview(client, max_mentees=1).json()

    assert body["per_person_price"] == body["session_price"]


def test_a_larger_group_previews_higher(client):
    one = preview(client, max_mentees=1).json()
    eight = preview(client, max_mentees=8).json()

    assert eight["session_price"] > one["session_price"]


def test_a_preview_writes_nothing(client, api_sessions):
    """
    There is no mentor to write it against, and a preview is not advice the
    mentor has been offered: the record of what was advised and what they did
    about it starts at registration.
    """
    for mentees in (1, 2, 4):
        assert preview(client, max_mentees=mentees).status_code == 200

    with api_sessions() as session:
        assert session.query(Mentor).count() == 0
        assert session.query(Service).count() == 0
        assert session.query(PricingRecommendation).count() == 0


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"field": "astrophysics"}, "field"),
        ({"max_mentees": 0}, "max_mentees"),
        ({"max_mentees": 9}, "max_mentees"),
        ({"max_mentees": True}, "max_mentees"),
        ({"skills": ["juggling"]}, "skills"),
    ],
)
def test_a_preview_validates_its_answers_the_way_registration_does(
    client, override, field
):
    response = preview(client, **override)

    assert response.status_code == 422
    assert field in {error["field"] for error in response.json()["errors"]}


def test_a_preview_refuses_an_answer_the_form_does_not_send(client):
    response = client.post("/preview", json={**PREVIEW, "years_experience": 7})

    assert response.status_code == 422


def test_a_preview_on_a_server_that_cannot_price_explains_itself(modelless_client):
    response = modelless_client.post("/preview", json=PREVIEW)

    assert response.status_code == 503
    assert "prepare_app_assets" in response.json()["detail"]


def test_too_many_previews_from_one_caller_are_refused(client, monkeypatch):
    """
    The limit, tested with a small one rather than by making sixty calls. What
    is being checked is that the counter refuses rather than where it is set.
    """
    monkeypatch.setattr(preview_limiter, "limit", 2)

    assert preview(client).status_code == 200
    assert preview(client).status_code == 200
    refused = preview(client)

    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) >= 1
    assert refused.json()["detail"]


def test_the_preview_limit_is_a_minute_of_calls(client):
    """
    The configured limit, named here so changing it is a decision rather than
    an accident. Sixty a minute is faster than anybody fills in a form.
    """
    assert preview_limiter.limit == 60
    assert preview_limiter.window == 60.0
