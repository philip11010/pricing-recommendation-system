"""Tests for the FastAPI dashboard serving layer."""

import os
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, get_model
from src.db import reset_engine

ACTIONS = ("accept", "modify", "reject")


class _ButtonCollector(HTMLParser):
    """Collect the attributes of every <button> element in a document."""

    def __init__(self) -> None:
        super().__init__()
        self.buttons: list[dict[str, str | None]] = []

    def handle_starttag(self, tag, attrs):
        if tag == "button":
            self.buttons.append(dict(attrs))


@pytest.fixture(scope="module")
def client(tmp_path_factory) -> TestClient:
    """
    A client against a throwaway database, with the lifespan run.

    The model is forced absent so these tests describe the serving layer
    alone and pass on a checkout with no trained artefact.
    """
    database = tmp_path_factory.mktemp("api") / "api.db"
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{database}"
    app.dependency_overrides[get_model] = lambda: None
    reset_engine()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    reset_engine()
    if previous is None:
        del os.environ["DATABASE_URL"]
    else:
        os.environ["DATABASE_URL"] = previous


@pytest.fixture(scope="module")
def dashboard_response(client):
    return client.get("/")


@pytest.fixture(scope="module")
def action_buttons(dashboard_response) -> list[dict[str, str | None]]:
    parser = _ButtonCollector()
    parser.feed(dashboard_response.text)
    return [b for b in parser.buttons if b.get("name") == "decision"]


def test_dashboard_returns_200_html(dashboard_response):
    assert dashboard_response.status_code == 200
    assert dashboard_response.headers["content-type"].startswith("text/html")


def test_dashboard_contains_three_action_controls(action_buttons):
    assert sorted(b["value"] for b in action_buttons) == sorted(ACTIONS)


def test_action_controls_are_real_buttons_of_equal_size(action_buttons):
    """
    The design brief gives Accept, Modify and Reject different visual weight
    (primary, secondary, ghost). What must not differ: all three are real
    submit buttons, all carry the shared .action-btn sizing class, and none
    is pre-selected or styled inline. Reject stays as reachable as Accept.
    """
    assert len(action_buttons) == 3
    assert all(b.get("type") == "submit" for b in action_buttons)
    assert all("action-btn" in (b.get("class") or "").split() for b in action_buttons)
    assert all("style" not in b for b in action_buttons)
    assert all("autofocus" not in b for b in action_buttons)


def test_no_action_is_hidden_or_disabled_relative_to_the_others(action_buttons):
    """A ghost button must still be a button, not a hidden one."""
    assert all("hidden" not in b for b in action_buttons)
    assert len({"disabled" in b for b in action_buttons}) == 1


def test_dashboard_shows_an_empty_state_before_any_recommendation(dashboard_response):
    """
    Nothing on the landing page may look like a price. The dashboard used to
    show a greyed-out illustrative figure here, which is the one thing a
    pricing tool must not do.
    """
    assert "No price yet" in dashboard_response.text
    assert "price-value" not in dashboard_response.text


def test_stylesheet_is_served(client, dashboard_response):
    assert "/static/css/dashboard.css" in dashboard_response.text
    response = client.get("/static/css/dashboard.css")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
