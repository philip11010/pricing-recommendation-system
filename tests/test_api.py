"""Tests for the FastAPI dashboard serving layer."""

from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

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
def client() -> TestClient:
    return TestClient(app)


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


def test_action_controls_are_styled_identically(action_buttons):
    # No action may carry extra classes, inline styles or other emphasis.
    assert {b.get("class") for b in action_buttons} == {"action-btn"}
    assert all("style" not in b for b in action_buttons)
    assert all("autofocus" not in b for b in action_buttons)


def test_dashboard_renders_placeholder_price(dashboard_response):
    assert "2,500" in dashboard_response.text


def test_stylesheet_is_served(client, dashboard_response):
    assert "/static/css/dashboard.css" in dashboard_response.text
    response = client.get("/static/css/dashboard.css")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
