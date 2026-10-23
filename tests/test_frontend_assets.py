"""
Tests for the front-end contract the demo depends on.

Two things here are requirements rather than preferences:

- The demo must work with no network, so no template or stylesheet may
  reference an external origin.
- Every control must be reachable and labelled, because the dashboard is the
  artefact that gets demonstrated.

These read the files on disk rather than a rendered page, so they hold for
every template including the ones a test never renders.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import STATIC_DIR, TEMPLATES_DIR, app, get_model
from src.db import reset_engine

TEMPLATES = sorted(TEMPLATES_DIR.glob("*.html"))
STYLESHEET = STATIC_DIR / "css" / "dashboard.css"
SCRIPT = STATIC_DIR / "js" / "dashboard.js"

# http(s) references, which would need the network, and protocol-relative
# ones, which are the same thing with the scheme left off.
EXTERNAL_URL = re.compile(r"""(?:https?:)?//(?!\s)[\w.-]+\.\w""")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'assets.db'}")
    monkeypatch.setattr("src.api.main.try_load_best_model", lambda *a, **k: None)
    monkeypatch.setattr("src.api.main.load_latest_report", lambda *a, **k: None)
    app.dependency_overrides[get_model] = lambda: None
    reset_engine()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    reset_engine()


def _closing_brace(text: str) -> int:
    """Index just past the brace that closes the first block in ``text``."""
    depth = 0
    for index, character in enumerate(text):
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
    raise AssertionError("unbalanced braces in the stylesheet")


def source_lines(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    return list(enumerate(text.splitlines(), start=1))


# ---------------------------------------------------------------------------
# Offline: nothing may be fetched from another origin
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_template_references_no_external_origin(template):
    offending = [
        (number, line)
        for number, line in source_lines(template)
        if EXTERNAL_URL.search(line)
    ]

    assert offending == []


def test_stylesheet_references_no_external_origin():
    """
    No @import of a webfont and no CDN. The type stack is the host platform's
    UI font, which needs no download.
    """
    offending = [
        (number, line)
        for number, line in source_lines(STYLESHEET)
        if EXTERNAL_URL.search(line)
    ]

    assert offending == []


def test_stylesheet_loads_no_font_files():
    css = STYLESHEET.read_text(encoding="utf-8")

    assert "@import" not in css
    assert "@font-face" not in css


def test_script_makes_no_network_calls():
    js = SCRIPT.read_text(encoding="utf-8")

    for forbidden in ("fetch(", "XMLHttpRequest", "import(", "WebSocket"):
        assert forbidden not in js


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_template_has_no_inline_script_or_style_block(template):
    """
    Inline code cannot be cached or audited, and the preset values are handed
    over as JSON data instead. A JSON block is data, not executable script.
    """
    text = template.read_text(encoding="utf-8")

    assert "<style" not in text
    for opening in re.findall(r"<script[^>]*>", text):
        assert 'src="' in opening or 'type="application/json"' in opening


def test_every_asset_the_page_links_is_served(client):
    text = client.get("/").text

    paths = set(re.findall(r'(?:href|src)="[^"]*?(/static/[^"]+)"', text))
    assert paths, "the page links no static assets"
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path


# ---------------------------------------------------------------------------
# Theming and the design tokens the stylesheet is built on
# ---------------------------------------------------------------------------
def test_light_is_the_default_and_dark_comes_from_the_media_query():
    css = STYLESHEET.read_text(encoding="utf-8")

    assert "color-scheme: light" in css
    assert "@media (prefers-color-scheme: dark)" in css
    assert css.index(":root {") < css.index("@media (prefers-color-scheme: dark)")


def test_dark_theme_redefines_every_colour_token():
    """
    A token defined only in the light block would keep its light value in
    dark mode, which is how a dashboard ends up with white panels at night.
    """
    css = STYLESHEET.read_text(encoding="utf-8")
    light, dark = css.split("@media (prefers-color-scheme: dark)", 1)
    dark = dark[: _closing_brace(dark)]

    colour_token = re.compile(r"(--[\w-]+):\s*(#[0-9a-fA-F]{3,8}|rgba?\()")
    light_tokens = {name for name, _ in colour_token.findall(light)}
    dark_tokens = {name for name, _ in colour_token.findall(dark)}

    assert light_tokens - dark_tokens == set()


def test_spacing_tokens_follow_an_eight_pixel_grid():
    css = STYLESHEET.read_text(encoding="utf-8")

    sizes = [int(v) for v in re.findall(r"--space-\d:\s*(\d+)px", css)]
    assert sizes
    # 4px is the only half-step the scale allows.
    assert all(size % 8 == 0 or size == 4 for size in sizes)


def test_a_single_accent_hue_is_used():
    """One accent, so nothing competes with the price and the primary action."""
    css = STYLESHEET.read_text(encoding="utf-8")

    accents = re.findall(r"--accent[\w-]*:", css)
    assert len(set(accents)) <= 4


def test_touch_targets_meet_the_minimum_height():
    css = STYLESHEET.read_text(encoding="utf-8")

    heights = [int(v) for v in re.findall(r"min-height:\s*(\d+)px", css)]
    assert 44 in heights


def test_mobile_layout_collapses_to_one_column():
    css = STYLESHEET.read_text(encoding="utf-8")

    assert "@media (max-width: 860px)" in css
    assert "grid-template-columns: minmax(0, 1fr)" in css


def test_focus_is_always_visible():
    css = STYLESHEET.read_text(encoding="utf-8")

    assert ":focus-visible" in css
    assert "outline: 2px solid" in css
    assert "outline: none" not in css


def test_motion_is_reduced_when_the_viewer_asks():
    css = STYLESHEET.read_text(encoding="utf-8")

    assert "@media (prefers-reduced-motion: reduce)" in css


# ---------------------------------------------------------------------------
# Accessibility of the rendered page
# ---------------------------------------------------------------------------
def test_every_control_has_a_label_tied_to_it(client):
    """
    A placeholder is not a label. Each input and select must be named by a
    <label for> pointing at its id.
    """
    text = client.get("/").text

    labelled = set(re.findall(r'<label[^>]*\bfor="([^"]+)"', text))
    controls = set(re.findall(r'<(?:input|select)[^>]*\bid="([^"]+)"', text))
    assert controls
    assert controls - labelled == set()


def test_no_control_relies_on_a_placeholder_for_its_name(client):
    text = client.get("/").text

    assert "placeholder=" not in text


def test_the_page_declares_a_language_and_a_viewport(client):
    text = client.get("/").text

    assert '<html lang="en">' in text
    assert 'name="viewport"' in text


def test_the_proxy_pill_and_banner_are_in_the_header_region(client):
    text = client.get("/").text

    assert '<span class="pill">Proxy data</span>' in text
    assert 'class="proxy-banner"' in text
    assert text.index('class="pill"') < text.index("site-main")


def test_decision_buttons_are_grouped_and_named(client):
    text = client.get("/").text

    assert 'role="group"' in text
    assert 'aria-label="Respond to the suggested price"' in text


def test_the_preset_buttons_announce_themselves():
    """
    Pressing Load example moves 25 values. Without a live region a screen
    reader is told nothing. Read from the template, because the form only
    renders when a model is loaded.
    """
    text = (TEMPLATES_DIR / "dashboard.html").read_text(encoding="utf-8")

    assert 'id="form-status"' in text
    assert 'aria-live="polite"' in text
    assert "data-announce" in text
