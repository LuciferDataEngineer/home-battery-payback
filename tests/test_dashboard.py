"""Open the static site and check every tab.

Run with the site already served, or let the test start a local server.
Screenshots land in docs/screenshots when HBP_SCREENSHOTS=1.
"""

from __future__ import annotations

import os
import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SHOTS = ROOT / "docs" / "screenshots"
TABS = ["overview", "where", "payback", "prices", "action"]

pytestmark = pytest.mark.browser


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def site_url():
    port = _free_port()
    handler = partial(SimpleHTTPRequestHandler, directory=str(SITE))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/index.html"
    server.shutdown()


def test_each_tab_renders(site_url):
    playwright = pytest.importorskip("playwright.sync_api")
    errors: list[str] = []
    SHOTS.mkdir(parents=True, exist_ok=True)
    with playwright.sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto(site_url, wait_until="networkidle")
        page.wait_for_selector("#banner")
        assert "South Australia" in page.inner_text("#banner")
        assert page.locator(".kpi").count() >= 4
        for tab in TABS:
            page.click(f'nav button[data-tab="{tab}"]')
            page.wait_for_timeout(250)
            visible = page.locator(f"#page-{tab}")
            assert visible.is_visible()
            canvases = page.locator(f"#page-{tab} canvas")
            for index in range(canvases.count()):
                box = canvases.nth(index).bounding_box()
                assert box and box["width"] > 200, f"{tab} canvas {index} has no width"
            if os.environ.get("HBP_SCREENSHOTS") == "1":
                page.screenshot(path=str(SHOTS / f"{tab}.png"), full_page=True)
        # Filters actually change the payback sentence.
        page.click('nav button[data-tab="payback"]')
        page.click('button[data-scenario="cut"]')
        page.wait_for_timeout(100)
        assert "January 2027" in page.inner_text("#pay-title")
        page.click('button[data-size="20"]')
        assert "20 kWh" in page.inner_text("#pay-kpis")
        # Narrow viewport still shows the banner.
        page.set_viewport_size({"width": 390, "height": 844})
        page.click('nav button[data-tab="overview"]')
        page.wait_for_timeout(200)
        assert page.locator("#banner").is_visible()
        if os.environ.get("HBP_SCREENSHOTS") == "1":
            page.screenshot(path=str(SHOTS / "overview-mobile.png"), full_page=True)
        browser.close()
    assert errors == [], errors
