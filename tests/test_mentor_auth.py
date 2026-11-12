"""
Tests for authentication: registering, signing in, and who may read what.

Five concerns, in the order they matter.

**Registering is the only way an account comes into being**, and it has to
refuse what it cannot use: an address already registered, a password too short
to be worth hashing, a group size outside the supported range, a skill that is
not on the list.

**Signing in must not answer a question nobody asked.** A wrong password and
an address nobody has registered give the same answer, byte for byte. Either
one differing would turn the sign-in form into a way of finding out who is on
the platform.

**A token has to be a proof rather than a claim.** A tampered one, an expired
one and a missing one are all refused, and the mentor-scoped routes are
enumerated from the application itself rather than listed by hand, so a route
added later without a token check fails this module instead of passing
unnoticed.

**One mentor can never read another's anything.** The property the prototype
held with a trusted header, now held with a signed token, and tested across
every mentor-scoped shape of record: a service, a price, the comparison, the
history and the dashboard.

**A production server without a signing key must not start.** It would issue
tokens anyone could forge while answering /health perfectly happily.

The module needs the prepared models, because registering returns a price.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.db.mentor_models import Mentor, Service
from src.mentor import security
from src.mentor.dependencies import get_current_mentor_id

from .conftest import REGISTRATION, headers, register, registration

pytestmark = pytest.mark.app_assets

OTHER = {"email": "other@example.com"}


def login(client, **overrides):
    """Sign in with the registered mentor's credentials, or an override."""
    body = {
        "email": REGISTRATION["email"],
        "password": REGISTRATION["password"],
        **overrides,
    }
    return client.post("/auth/login", json=body)


def token_of(client, **overrides) -> str:
    """Register one mentor and return the token they are given."""
    return register(client, **overrides)["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {security.AUTH_HEADER: f"Bearer {token}"}


# ---------------------------------------------------------------------------
# The mentor-scoped routes, read off the application
#
# Enumerated rather than listed, so a route added later without a token check
# is a failure here rather than a hole nobody notices. The paths are built
# from the route templates with 1 for every id, which is enough: what is being
# checked is that the request never reaches the handler at all.
# ---------------------------------------------------------------------------
def needs_a_token(route) -> bool:
    """Whether a route depends on the identity function, however deeply."""

    def search(dependant) -> bool:
        if dependant.call is get_current_mentor_id:
            return True
        return any(search(nested) for nested in dependant.dependencies)

    dependant = getattr(route, "dependant", None)
    return dependant is not None and search(dependant)


def protected_routes() -> list[tuple[str, str]]:
    from src.mentor.app import app

    found = []
    for route in app.routes:
        if not needs_a_token(route):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            path = route.path
            for name in route.param_convertors:
                path = path.replace(f"{{{name}}}", "1")
            found.append((method, path))
    return found


PROTECTED = protected_routes()


def test_the_application_has_mentor_scoped_routes_to_check():
    """A guard on the enumeration above: an empty list would pass silently."""
    assert len(PROTECTED) >= 7


# ---------------------------------------------------------------------------
# Registering
# ---------------------------------------------------------------------------
def test_registering_returns_a_token_the_mentor_the_service_and_a_price(client):
    body = register(client)

    assert body["token_type"] == "bearer"
    assert body["expires_in"] == security.token_lifetime_seconds()
    assert security.read_access_token(body["access_token"]) == body["mentor"]["id"]
    assert body["service"]["id"] >= 1
    assert body["recommendation"]["recommended_price"] > 0


def test_the_token_registration_returns_works_straight_away(client):
    """
    The point of returning it: the frontend does not have to sign in again
    immediately after registering.
    """
    body = register(client)

    me = client.get("/auth/me", headers=bearer(body["access_token"]))

    assert me.status_code == 200
    assert me.json()["id"] == body["mentor"]["id"]


def test_a_new_mentor_is_not_verified(client):
    """
    Verification is what the platform says about a mentor after a person has
    looked. Nothing on the form can set it.
    """
    body = register(client)

    assert body["mentor"]["verified"] is False


def test_a_new_mentor_cannot_claim_to_be_verified(client):
    """The field is not on the form, so sending it is refused, not ignored."""
    response = client.post("/auth/register", json=registration(verified=True))

    assert response.status_code == 422
    assert "verified" in {error["field"] for error in response.json()["errors"]}


def test_the_password_is_never_returned_or_stored_as_typed(client, api_sessions):
    body = register(client)

    assert "password" not in body["mentor"]
    assert "password_hash" not in body["mentor"]
    with api_sessions() as session:
        stored = session.get(Mentor, body["mentor"]["id"]).password_hash
    assert stored and REGISTRATION["password"] not in stored
    assert stored.startswith("$argon2")


def test_the_same_address_cannot_register_twice(client):
    register(client)

    response = client.post("/auth/register", json=registration())

    assert response.status_code == 409


def test_the_same_address_in_different_capitals_cannot_register_twice(client):
    """
    Addresses are lowercased before they are stored, so these are one
    address however they were typed.
    """
    register(client)

    response = client.post(
        "/auth/register", json=registration(email="Mentor@Example.COM")
    )

    assert response.status_code == 409


def test_an_address_is_stored_lowercased_and_trimmed(client):
    body = register(client, email="  MENTOR@Example.com  ")

    assert body["mentor"]["email"] == "mentor@example.com"


@pytest.mark.parametrize("password", ["", "short", "x" * 7, "y" * 129])
def test_a_password_the_hasher_will_not_take_is_refused(client, password):
    response = client.post("/auth/register", json=registration(password=password))

    assert response.status_code == 422
    assert "password" in {error["field"] for error in response.json()["errors"]}


@pytest.mark.parametrize("mentees", [0, 9, 99])
def test_a_group_size_outside_the_supported_range_is_refused(client, mentees):
    response = client.post("/auth/register", json=registration(max_mentees=mentees))

    assert response.status_code == 422
    errors = {error["field"]: error["message"] for error in response.json()["errors"]}
    assert "8" in errors["max_mentees"]


def test_a_skill_that_is_not_on_the_list_is_refused(client):
    response = client.post(
        "/auth/register", json=registration(skills=["cv_review", "juggling"])
    )

    assert response.status_code == 422
    errors = {error["field"]: error["message"] for error in response.json()["errors"]}
    assert "juggling" in errors["skills"]


def test_nothing_is_written_when_registration_is_refused(client, api_sessions):
    client.post("/auth/register", json=registration(password="short"))

    with api_sessions() as session:
        assert session.query(Mentor).count() == 0


# ---------------------------------------------------------------------------
# Signing in
# ---------------------------------------------------------------------------
def test_signing_in_returns_a_token_and_the_mentor(client):
    mentor_id = register(client)["mentor"]["id"]

    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["mentor"]["id"] == mentor_id
    assert security.read_access_token(body["access_token"]) == mentor_id


def test_signing_in_ignores_the_capitals_in_the_address(client):
    register(client)

    assert login(client, email="MENTOR@example.com").status_code == 200


def test_a_wrong_password_and_an_unknown_address_are_indistinguishable(client):
    """
    The test this module exists for. Two different answers here would turn
    the sign-in form into a way of finding out who has an account.
    """
    register(client)

    wrong_password = login(client, password="not-the-right-password")
    unknown_address = login(client, email="nobody@example.com")

    assert wrong_password.status_code == unknown_address.status_code == 401
    assert wrong_password.json() == unknown_address.json()


def test_a_failed_sign_in_says_nothing_about_which_half_was_wrong(client):
    register(client)

    detail = login(client, password="not-the-right-password").json()["detail"]

    assert "password" in detail.lower()
    for leaked in ("no such", "not registered", "unknown", "exists"):
        assert leaked not in detail.lower()


def test_an_account_with_no_password_cannot_be_signed_in_to(client, api_sessions):
    """
    The column is nullable, so a row seeded before passwords existed has no
    hash. It is refused like any wrong password rather than treated as a
    blank one.
    """
    body = register(client)
    with api_sessions() as session:
        mentor = session.get(Mentor, body["mentor"]["id"])
        mentor.password_hash = None
        session.commit()

    assert login(client).status_code == 401


def test_signing_in_needs_no_token(client):
    register(client)

    assert login(client).status_code == 200


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_every_mentor_scoped_route_refuses_a_request_with_no_token(
    client, method, path
):
    response = client.request(method, path)

    assert response.status_code == 401, (method, path)
    assert response.headers.get("www-authenticate") == "Bearer"


def tampered(token: str) -> str:
    """
    One character of the signature changed, away from its end.

    Not the last character: a 32 byte signature is 43 base64url characters,
    which is 258 bits, so the final character carries two bits that decoding
    discards. Four different last characters therefore decode to the same
    signature, and a test that changed only that one would pass most of the
    time and fail the rest, which is worse than not testing it.
    """
    index = len(token) - 20
    replacement = "a" if token[index] != "a" else "b"
    return token[:index] + replacement + token[index + 1 :]


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_every_mentor_scoped_route_refuses_a_tampered_token(client, method, path):
    """
    A real token with its signature altered, on every mentor-scoped route
    rather than on the ones somebody remembered to check.
    """
    response = client.request(
        method, path, headers=bearer(tampered(security.create_access_token(1)))
    )

    assert response.status_code == 401, (method, path)


def test_an_expired_token_is_refused(client):
    mentor_id = register(client)["mentor"]["id"]
    expired = security.create_access_token(
        mentor_id,
        issued_at=datetime.now(UTC) - timedelta(days=30),
        ttl=timedelta(days=7),
    )

    response = client.get("/auth/me", headers=bearer(expired))

    assert response.status_code == 401


def test_a_token_signed_with_another_key_is_refused(client, monkeypatch):
    """
    What a forged token actually looks like: the right shape, the right
    claims, the wrong key.
    """
    mentor_id = register(client)["mentor"]["id"]
    import jwt

    forged = jwt.encode(
        {
            "sub": str(mentor_id),
            "exp": int((datetime.now(UTC) + timedelta(days=1)).timestamp()),
        },
        "a-key-this-server-has-never-heard-of",
        algorithm=security.ALGORITHM,
    )

    assert client.get("/auth/me", headers=bearer(forged)).status_code == 401


def test_an_unsigned_token_is_refused(client):
    """
    The classic attack on a careless implementation: a token that says it is
    not signed. The library is given one algorithm and refuses anything else.
    """
    import jwt

    unsigned = jwt.encode({"sub": "1"}, key="", algorithm="none")

    assert client.get("/auth/me", headers=bearer(unsigned)).status_code == 401


@pytest.mark.parametrize(
    "value",
    ["", "   ", "Token abc", "Bearer", "Bearer ", "abc", "Basic abc"],
)
def test_an_authorization_header_that_is_not_a_bearer_token_is_refused(client, value):
    assert (
        client.get("/auth/me", headers={security.AUTH_HEADER: value}).status_code == 401
    )


def test_the_scheme_may_be_written_in_any_capitals(client):
    """The specification says the scheme is case-insensitive, so it is."""
    token = token_of(client)

    response = client.get("/auth/me", headers={security.AUTH_HEADER: f"bEaReR {token}"})

    assert response.status_code == 200


def test_a_token_for_a_mentor_who_no_longer_exists_is_refused(client):
    """
    An identity that cannot be established is 401 rather than 404: there is
    no record being asked for yet, only a caller who cannot be placed.
    """
    response = client.get("/auth/me", headers=headers(99999))

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# One mentor, one mentor's records
# ---------------------------------------------------------------------------
@pytest.fixture
def two_mentors(client):
    """Two registered mentors, each with a service and a price of their own."""
    return register(client), register(client, **OTHER)


def test_a_mentor_cannot_read_another_mentors_service(client, two_mentors):
    first, second = two_mentors

    response = client.get(
        f"/services/{second['service']['id']}",
        headers=headers(first["mentor"]["id"]),
    )

    assert response.status_code == 404


def test_a_mentor_cannot_read_another_mentors_recommendation(client, two_mentors):
    first, second = two_mentors

    response = client.get(
        f"/recommendations/{second['recommendation']['id']}",
        headers=headers(first["mentor"]["id"]),
    )

    assert response.status_code == 404


def test_a_mentor_cannot_read_another_mentors_comparables(client, two_mentors):
    first, second = two_mentors

    response = client.get(
        f"/services/{second['service']['id']}/comparables",
        headers=headers(first["mentor"]["id"]),
    )

    assert response.status_code == 404


def test_a_mentor_cannot_read_another_mentors_history(client, two_mentors):
    first, second = two_mentors

    response = client.get(
        f"/services/{second['service']['id']}/history",
        headers=headers(first["mentor"]["id"]),
    )

    assert response.status_code == 404


def test_a_mentor_cannot_read_another_mentors_dashboard(client, two_mentors):
    first, second = two_mentors

    response = client.get(
        f"/mentors/{second['mentor']['id']}/dashboard",
        headers=headers(first["mentor"]["id"]),
    )

    assert response.status_code == 404


def test_a_mentor_cannot_decide_another_mentors_price(client, two_mentors):
    first, second = two_mentors

    response = client.post(
        f"/recommendations/{second['recommendation']['id']}/decision",
        json={"action": "accepted"},
        headers=headers(first["mentor"]["id"]),
    )

    assert response.status_code == 404


def test_a_refusal_looks_the_same_whether_the_record_exists(client, two_mentors):
    first, second = two_mentors
    mine = headers(first["mentor"]["id"])

    theirs = client.get(f"/services/{second['service']['id']}", headers=mine)
    absent = client.get("/services/99999", headers=mine)

    assert theirs.status_code == absent.status_code == 404
    assert theirs.json() == absent.json()


# ---------------------------------------------------------------------------
# Editing the mentor's own profile
# ---------------------------------------------------------------------------
def test_a_mentor_can_edit_their_name_and_optional_profile_fields(client):
    body = register(client)
    mentor_id = body["mentor"]["id"]

    response = client.patch(
        "/mentors/me",
        json={
            "name": "A. Different Mentor",
            "years_experience": 12,
            "education_level": "doctorate",
            "credentials": "Fellow of something.",
        },
        headers=headers(mentor_id),
    )

    assert response.status_code == 200, response.text
    mentor = response.json()
    assert mentor["full_name"] == "A. Different Mentor"
    assert mentor["years_experience"] == 12
    assert mentor["years_mentoring_band"] == "over_10"
    assert mentor["education_level"] == "doctorate"
    assert mentor["credentials"] == "Fellow of something."


def test_an_edit_leaves_out_what_it_does_not_mention(client):
    body = register(client)
    mentor_id = body["mentor"]["id"]

    mentor = client.patch(
        "/mentors/me", json={"credentials": "Updated."}, headers=headers(mentor_id)
    ).json()

    assert mentor["full_name"] == REGISTRATION["name"]
    assert mentor["years_experience"] == REGISTRATION["years_experience"]
    assert mentor["credentials"] == "Updated."


def test_an_edit_can_clear_an_optional_field(client):
    mentor_id = register(client)["mentor"]["id"]

    mentor = client.patch(
        "/mentors/me",
        json={"years_experience": None, "credentials": None},
        headers=headers(mentor_id),
    ).json()

    assert mentor["years_experience"] is None
    assert mentor["years_mentoring_band"] is None
    assert mentor["credentials"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"email": "new@example.com"},
        {"verified": True},
        {"is_demo": True},
        {"password": "another-long-password"},
        {"max_mentees": 8},
    ],
)
def test_an_edit_cannot_reach_anything_settled_elsewhere(client, body):
    """
    The address they sign in with, their verification and anything about a
    service each have a reason to be settled somewhere else, and a
    general-purpose profile edit that could reach them would make those
    reasons unenforceable.
    """
    mentor_id = register(client)["mentor"]["id"]

    response = client.patch("/mentors/me", json=body, headers=headers(mentor_id))

    assert response.status_code == 422


def test_an_edit_does_not_change_the_price(client):
    """None of these fields is a model input, so no price may move."""
    body = register(client)
    mentor_id = body["mentor"]["id"]
    before = body["recommendation"]["recommended_price"]

    client.patch(
        "/mentors/me", json={"years_experience": 40}, headers=headers(mentor_id)
    )
    after = client.post(
        f"/services/{body['service']['id']}/recommendations",
        headers=headers(mentor_id),
    ).json()

    assert after["recommended_price"] == before


def test_editing_a_profile_needs_a_token(client):
    assert client.patch("/mentors/me", json={"name": "Nobody"}).status_code == 401


# ---------------------------------------------------------------------------
# The signing key
# ---------------------------------------------------------------------------
@pytest.fixture
def forget_the_key():
    """Restore the process key afterwards, whatever the test did to it."""
    yield
    security.reset_secret_key()


def test_production_refuses_to_run_without_a_signing_key():
    with pytest.raises(security.InsecureConfigurationError) as error:
        security.secret_key_for("production", None)

    assert security.SECRET_KEY_VARIABLE in str(error.value)


def test_production_refuses_a_key_too_short_to_be_one():
    short = "x" * (security.SECRET_KEY_MIN_LENGTH - 1)

    with pytest.raises(security.InsecureConfigurationError):
        security.secret_key_for("production", short)


def test_production_accepts_a_key_of_the_stated_length():
    key = "x" * security.SECRET_KEY_MIN_LENGTH

    assert security.secret_key_for("production", key) == key


def test_a_development_server_generates_a_key_and_says_so(caplog):
    with caplog.at_level("WARNING"):
        generated = security.secret_key_for("development", None)

    assert len(generated) >= security.SECRET_KEY_MIN_LENGTH
    assert security.SECRET_KEY_VARIABLE in caplog.text
    # The key itself is never logged. Only the fact that there was none.
    assert generated not in caplog.text


def test_a_configured_key_is_used_whatever_the_environment():
    key = "y" * security.SECRET_KEY_MIN_LENGTH

    assert security.secret_key_for("", key) == key
    assert security.secret_key_for("development", key) == key


def test_a_production_server_without_a_key_does_not_start(
    monkeypatch, tmp_path, forget_the_key
):
    """
    The refusal where it counts: at startup, rather than on the first request
    that needs a token. A server that boots without a key answers /health
    perfectly happily while handing out tokens anyone could forge.
    """
    from src.mentor.app import app

    monkeypatch.setattr(security, "ENV_FILE", tmp_path / "absent.env")
    monkeypatch.setenv(security.ENVIRONMENT_VARIABLE, "production")
    monkeypatch.delenv(security.SECRET_KEY_VARIABLE, raising=False)
    security.reset_secret_key()

    with pytest.raises(security.InsecureConfigurationError):
        with TestClient(app):
            pass


def test_a_production_server_with_a_key_starts(monkeypatch, tmp_path, forget_the_key):
    from src.mentor.app import app

    monkeypatch.setattr(security, "ENV_FILE", tmp_path / "absent.env")
    monkeypatch.setenv(security.ENVIRONMENT_VARIABLE, "production")
    monkeypatch.setenv(
        security.SECRET_KEY_VARIABLE, "z" * security.SECRET_KEY_MIN_LENGTH
    )
    security.reset_secret_key()

    with TestClient(app) as started:
        assert started.get("/health").status_code == 200


# ---------------------------------------------------------------------------
# Verifying a mentor
#
# The script is the only thing that sets the flag, so what it does to the two
# columns that carry the same claim is worth a test of its own.
# ---------------------------------------------------------------------------
@pytest.fixture
def script_db(tmp_path, monkeypatch):
    """A database the script's own engine will find, with one mentor in it."""
    from sqlalchemy.orm import sessionmaker

    from src.db import Base, create_db_engine

    url = f"sqlite:///{tmp_path / 'verify.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_db_engine(url)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        mentor = Mentor(
            full_name="A. Mentor",
            email="mentor@example.com",
            password_hash=security.hash_password("a-long-enough-password"),
        )
        mentor.services.append(
            Service(
                session_label="one_to_one",
                field="technology_software",
                max_mentees=1,
                min_commitment=1,
                skills=["cv_review"],
                profile_verified=False,
            )
        )
        session.add(mentor)
        session.commit()
    yield sessions
    engine.dispose()


def test_the_script_verifies_a_mentor_and_their_services(script_db):
    from scripts import verify_mentor

    assert verify_mentor.main(["mentor@example.com"]) == 0

    with script_db() as session:
        mentor = session.scalar(select(Mentor))
        assert mentor.verified is True
        assert all(service.profile_verified for service in mentor.services)


def test_the_script_takes_a_verification_back(script_db):
    from scripts import verify_mentor

    assert verify_mentor.main(["mentor@example.com"]) == 0
    assert verify_mentor.main(["mentor@example.com", "--revoke"]) == 0

    with script_db() as session:
        mentor = session.scalar(select(Mentor))
        assert mentor.verified is False
        assert not any(service.profile_verified for service in mentor.services)


def test_the_script_matches_the_address_without_case(script_db):
    from scripts import verify_mentor

    assert verify_mentor.main(["MENTOR@Example.com"]) == 0

    with script_db() as session:
        assert session.scalar(select(Mentor)).verified is True


def test_the_script_fails_on_an_address_nobody_registered(script_db, capsys):
    from scripts import verify_mentor

    assert verify_mentor.main(["nobody@example.com"]) == 1

    error = capsys.readouterr().err
    assert "no mentor" in error
    # The address is not echoed back, because the script's output is the sort
    # of thing that ends up in a terminal history or a screenshot.
    assert "nobody@example.com" not in error
