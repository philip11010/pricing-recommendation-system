"""
Tests for browser access to the mentor-facing API.

The web application runs on its own origin and calls this API from the
browser, which means every call is a cross-origin one and the browser refuses
them unless the API says otherwise. Two things are checked here: that the list
of permitted origins is read the way it is documented, and that the identity
header actually survives a preflight, because that is the one header the
frontend cannot do without and the one a default configuration leaves out.

The middleware is installed once, at import, with whatever the environment
said then. So the parsing is tested through the function and the behaviour
through the default origins, rather than by setting the variable and hoping
the application rereads it.
"""

from __future__ import annotations

from src.mentor.app import (
    ALLOWED_ORIGINS_VARIABLE,
    DEFAULT_ALLOWED_ORIGINS,
    allowed_origins,
)
from src.mentor.security import AUTH_HEADER

LOCAL_ORIGIN = "http://localhost:3000"
FOREIGN_ORIGIN = "https://somewhere-else.example.com"


def test_origins_default_to_the_local_development_server(monkeypatch) -> None:
    monkeypatch.delenv(ALLOWED_ORIGINS_VARIABLE, raising=False)
    assert allowed_origins() == list(DEFAULT_ALLOWED_ORIGINS)


def test_origins_are_read_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv(
        ALLOWED_ORIGINS_VARIABLE,
        "https://mentors.example.com, https://staging.example.com",
    )
    assert allowed_origins() == [
        "https://mentors.example.com",
        "https://staging.example.com",
    ]


def test_a_trailing_slash_is_stripped() -> None:
    """An origin is a scheme, a host and a port, and matches as a string."""
    assert allowed_origins("http://localhost:3000/") == [LOCAL_ORIGIN]


def test_a_blank_setting_falls_back_rather_than_allowing_nothing() -> None:
    assert allowed_origins("") == list(DEFAULT_ALLOWED_ORIGINS)
    assert allowed_origins("  ,  ") == list(DEFAULT_ALLOWED_ORIGINS)


def test_a_preflight_allows_the_authorization_header(modelless_client) -> None:
    """
    The header the frontend sends on every mentor-scoped request.

    A preflight that does not list it is the failure mode this test exists
    for: the browser sends the access token on the real request, the preflight
    never approved it, and the call is refused before the API sees it.
    """
    response = modelless_client.options(
        "/mentors/1",
        headers={
            "Origin": LOCAL_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": AUTH_HEADER,
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == LOCAL_ORIGIN
    allowed = response.headers["access-control-allow-headers"].lower()
    assert AUTH_HEADER.lower() in allowed
    assert "content-type" in allowed


def test_a_preflight_no_longer_allows_the_old_identity_header(
    modelless_client,
) -> None:
    """
    The prototype's trusted header is gone, and so is the browser's
    permission to send it. A frontend still setting it is told by the
    preflight rather than having its requests quietly ignored.
    """
    response = modelless_client.options(
        "/mentors/1",
        headers={
            "Origin": LOCAL_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Mentor-Id",
        },
    )

    assert (
        "x-mentor-id"
        not in response.headers.get("access-control-allow-headers", "").lower()
    )


def test_a_preflight_allows_editing_the_mentors_own_profile(modelless_client) -> None:
    """PATCH is the third method the frontend uses, so it has to be listed."""
    response = modelless_client.options(
        "/mentors/me",
        headers={
            "Origin": LOCAL_ORIGIN,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": AUTH_HEADER,
        },
    )

    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]


def test_a_permitted_origin_may_read_the_response(modelless_client) -> None:
    response = modelless_client.get("/meta/options", headers={"Origin": LOCAL_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == LOCAL_ORIGIN


def test_an_unlisted_origin_is_not_granted_access(modelless_client) -> None:
    """
    The response still arrives; what is missing is the browser's permission.

    CORS is enforced in the browser rather than by the server refusing to
    answer, so what this asserts is the absence of the header that would let a
    page on another origin read the body.
    """
    response = modelless_client.get("/meta/options", headers={"Origin": FOREIGN_ORIGIN})

    assert "access-control-allow-origin" not in response.headers
