"""In a real Chromium: a device with no local copy lays the chat cloud out from
the owner's record, and a placement made there is written back.

The shipped page is served with its own CSP; ``/app/ui-prefs`` answers like the
route does (``{"prefs": ...}`` for GET, ``{"saved": true}`` for POST).
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tinyassets.onboarding import render_app_html

# Run, with a skip counted as a failure, by .github/workflows/real-browser-proof.yml.
pytestmark = pytest.mark.real_browser

RECORD = {"v": 1, "mode": "open", "open": {"x": 200, "y": 60, "w": 520, "h": 420},
          "bubble": {"x": 30, "y": 30}}


@pytest.fixture
def server():
    html, csp = render_app_html()
    posts: list[dict] = []
    delay = {"seconds": 0.0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def _send(self, body: bytes, ctype: str, extra=None):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.split("?")[0] == "/app":
                self._send(html.encode("utf-8"), "text/html; charset=utf-8",
                           {"Content-Security-Policy": csp})
            elif self.path.startswith("/app/ui-prefs?") and "viewport=wide" in self.path:
                time.sleep(delay["seconds"])
                self._send(json.dumps({"prefs": {"chat_cloud": RECORD}}).encode(),
                           "application/json")
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == "/app/ui-prefs":
                length = int(self.headers.get("content-length") or 0)
                posts.append(json.loads(self.rfile.read(length)))
                self._send(b'{"saved": true}', "application/json")
            else:
                self.send_response(404)
                self.end_headers()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/app", posts, delay
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture
def page():
    sync_api = pytest.importorskip(
        "playwright.sync_api",
        reason="owner=owner-ui-prefs runs-in=real-browser-proof; Playwright required",
    )
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - no browser binary on this host
            pytest.skip(
                "owner=owner-ui-prefs runs-in=real-browser-proof; "
                f"Chromium is not available here: {exc.__class__.__name__}"
            )
        try:
            yield browser.new_page(viewport={"width": 1280, "height": 800})
        finally:
            browser.close()


def test_a_new_device_takes_the_owners_record_and_writes_back_its_placement(server, page):
    url, posts, _delay = server
    page.goto(url)
    page.wait_for_selector("#view-signin", state="visible")
    page.wait_for_load_state("networkidle")
    page.evaluate("() => { setQueueOwner('owner-1'); showView('chat'); refreshChatCloud(); }")

    page.wait_for_function("cloudState && cloudState.open.x === 200")
    box = page.locator("#chat-cloud").bounding_box()
    stage = page.locator("#chat-stage").bounding_box()
    assert box["x"] - stage["x"] == pytest.approx(200, abs=2)
    assert box["width"] == pytest.approx(520, abs=2)
    cached = "JSON.parse(localStorage.getItem('app.chatCloud.v1:owner-1:main:wide')).open.x"
    assert page.evaluate(cached) == 200

    page.click("#btn-cloud-shrink")
    page.wait_for_function("document.getElementById('chat-cloud-bubble').offsetParent !== null")
    page.wait_for_timeout(300)
    assert posts and posts[-1]["key"] == "chat_cloud" and posts[-1]["value"]["mode"] == "bubble"
    assert posts[-1]["agent"] == "main" and posts[-1]["viewport"] == "wide"


def test_a_record_arriving_mid_drag_does_not_move_the_cloud(server, page):
    url, posts, delay = server
    delay["seconds"] = 1.5
    page.goto(url)
    page.wait_for_selector("#view-signin", state="visible")
    page.evaluate("() => { setQueueOwner('owner-1'); showView('chat'); refreshChatCloud(); }")
    page.wait_for_function("cloudState !== null")
    corner = page.locator("#chat-cloud-resize").bounding_box()

    page.mouse.move(corner["x"] + 9, corner["y"] + 9)
    page.mouse.down()
    page.mouse.move(corner["x"] - 600, corner["y"] - 300, steps=10)
    page.wait_for_timeout(2000)                       # the record lands mid-drag
    page.mouse.up()
    page.wait_for_timeout(300)

    width = page.evaluate("cloudState.open.w")
    assert width != 520                               # not the record's width
    assert posts and posts[-1]["value"]["open"]["w"] == width
