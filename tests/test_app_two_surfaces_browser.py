"""The chat cloud in a real Chromium: drag, resize, shrink, restore, stay on screen.

The real app page (``render_app_html``, with its own CSP) is served locally,
signed-in state is entered the way the page itself does it (``showView``), and
every gesture is a real mouse or keyboard input.
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tinyassets.onboarding import render_app_html
from tinyassets.onboarding.ui_frame import BOOTSTRAP_HTML, FRAME_HEADERS

# Run, with a skip counted as a failure, by .github/workflows/real-browser-proof.yml.
pytestmark = pytest.mark.real_browser


@pytest.fixture
def app_url():
    html, csp = render_app_html()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if self.path.split("?")[0] == "/app/ui-frame":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                for name, value in FRAME_HEADERS.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(BOOTSTRAP_HTML.encode("utf-8"))
                return
            if self.path.split("?")[0] != "/app":
                self.send_response(404)
                self.end_headers()
                return
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", csp)
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.send_response(404)
            self.end_headers()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/app"
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            chromium = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - no browser binary on this host
            pytest.skip(f"Chromium is not available here: {exc.__class__.__name__}")
        try:
            yield chromium
        finally:
            chromium.close()


def _enter_chat(page, url, *, layout=False):
    page.goto(url)
    # Let the page finish its own boot first: with no session it lands on the
    # sign-in view, and a boot that finished later would hide the chat again.
    page.wait_for_selector("#view-signin", state="visible")
    page.wait_for_load_state("networkidle")
    page.evaluate("""(layout) => {
        setQueueOwner('owner-1');
        if (layout) document.getElementById('view-chat').classList.add('ui-custom-active');
        showView('chat'); refreshChatCloud();
    }""", layout)
    page.wait_for_function("cloudState !== null")


def _box(page, selector):
    return page.locator(selector).bounding_box()


def _drag(page, selector, dx, dy, *, at=(0.5, 0.5)):
    box = _box(page, selector)
    x, y = box["x"] + box["width"] * at[0], box["y"] + box["height"] * at[1]
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y + dy, steps=10)
    page.mouse.up()



def test_blank_command_center(app_url, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    _enter_chat(page, app_url)
    assert page.locator("#cc-blank").is_visible()
    assert _box(page, "#cc-blank") == _box(page, "#chat-stage")
    page.mouse.click(5, 5)
    assert page.evaluate("document.activeElement.id") == "cc-blank"
    page.click("#btn-cloud-shrink")
    page.click("#btn-cc-build")
    assert page.input_value("#composer-input") == "Build me a command center for "
    assert page.evaluate("document.activeElement.id") == "composer-input"
    assert page.locator("#composer-input").evaluate("e=>e.selectionStart") == 30
    page.close()


def test_play_never_needs_a_second_click(app_url, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    _enter_chat(page, app_url)
    page.evaluate("""() => AppUI.mount({ui_id:'play', name:'Play',
      markup:'<div id="hero"></div>',
      style:'#hero{position:absolute;left:0;top:100px;width:20px;height:20px;background:red}',
      script:`document.addEventListener('keydown',e=>{
        if(e.key==='ArrowRight'){
          const h=document.getElementById('hero');
          h.style.left=(parseInt(h.style.left||'0')+10)+'px';
          h.dataset.trusted=String(e.isTrusted);
        }
      });`})""")
    hero = page.frame_locator("#ui-frame").locator("#hero")
    hero.wait_for()
    position = 0

    def walk(*, native=True):
        nonlocal position
        page.keyboard.press("ArrowRight")
        position += 10
        from playwright.sync_api import expect
        expect(hero).to_have_css("left", f"{position}px")
        # Native walks prove the focus handoff itself.
        if native:
            expect(hero).to_have_attribute("data-trusted", "true")

    walk()
    assert page.locator("#cc-blank").is_hidden()
    page.click("#chat-cloud-bubble")
    assert _box(page, "#chat-cloud")["width"] <= 440
    # Put the cloud centrally so all four stage edges and corners are exposed.
    _drag(page, "#chat-cloud-resize", -100, -156)
    _drag(page, "#chat-cloud-bar", -400, -80, at=(0.8, 0.5))
    stage = _box(page, "#chat-stage")
    w, h = stage["width"], stage["height"]
    for x, y in [(2, 2), (w-2, 2), (2, h-2), (w-2, h-2),
                 (w/2, 2), (w/2, h-2), (2, h/2), (w-2, h/2)]:
        page.mouse.click(x, y)
        walk()
    page.click("#chat-cloud-title")
    walk()
    cloud = _box(page, "#chat-cloud")
    for x, y in [(cloud["x"], cloud["y"]+100),
                 (cloud["x"]+cloud["width"]-1, cloud["y"]+100),
                 (cloud["x"]+100, cloud["y"]),
                 (cloud["x"]+100, cloud["y"]+cloud["height"]-1)]:
        page.mouse.click(x, y)
        assert page.evaluate("document.activeElement.id") == "ui-frame"
        walk(native=True)
    page.click("#chat-cloud-resize")
    walk()
    _drag(page, "#chat-cloud-resize", 20, 20)
    walk()
    for close in ("toggle", "escape", "outside"):
        page.click("#btn-cloud-menu")
        assert page.locator("#cloud-menu").is_visible()
        if close == "toggle":
            page.click("#btn-cloud-menu")
        elif close == "escape":
            page.keyboard.press("Escape")
        else:
            page.mouse.click(2, 2)
        page.locator("#cloud-menu").wait_for(state="hidden")
        walk()
    page.fill("#composer-input", "hello")
    page.keyboard.press("Enter")
    walk()
    page.locator("#btn-stop").wait_for(state="hidden")
    page.focus("#composer-input")
    page.keyboard.press("Escape")
    walk()
    page.click("#btn-cloud-shrink")
    walk()
    page.focus("#chat-cloud-bubble")
    page.keyboard.press("Escape")
    walk()
    page.click("#chat-cloud-bubble")
    page.mouse.click(2, 2)
    walk()
    for dialog in ("model-dialog", "ui-dialog"):
        page.evaluate("id=>document.getElementById(id).showModal()", dialog)
        assert page.evaluate(
            "id=>document.getElementById(id).contains(document.activeElement)", dialog)
        page.keyboard.press("Escape")
        page.wait_for_function("""() => !document.querySelector('dialog[open]') &&
            document.activeElement.id === 'ui-frame'""")
        walk()
    page.fill("#composer-input", "draft survives ready")
    page.focus("#composer-input")
    assert page.evaluate("document.activeElement.id") == "composer-input"
    page.evaluate("AppUI.ready=false; AppUI.deliver()")
    assert page.evaluate("document.activeElement.id") == "composer-input"
    assert page.input_value("#composer-input") == "draft survives ready"
    hero.wait_for()
    page.evaluate("AppUI.mount(AppUI.active)")
    hero.wait_for()
    position = 0
    assert page.evaluate("document.activeElement.id") == "composer-input"
    assert page.input_value("#composer-input") == "draft survives ready"
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    assert page.evaluate("document.activeElement.id") == "composer-input"
    page.focus("#btn-cloud-menu")
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    walk()
    page.evaluate("document.getElementById('view-chat').style.paddingTop='24px'")
    page.focus("#composer-input")
    page.mouse.click(5, 5)
    walk()
    # Explicitly exercise the fallback independently of the native-focus play.
    page.evaluate("""() => { const stage=document.getElementById('chat-stage');
      stage.setAttribute('tabindex','-1'); stage.focus(); }""")
    page.keyboard.press("ArrowRight")
    from playwright.sync_api import expect
    expect(hero).to_have_css("left", f"{position+10}px")
    expect(hero).to_have_attribute("data-trusted", "false")
    position += 10
    for control in ("btn-attach", "btn-models"):
        page.focus("#" + control)
        page.keyboard.press("ArrowRight")
        position += 10
        expect(hero).to_have_css("left", f"{position}px")
    page.evaluate("AppUI.unmount()")
    assert page.locator("#cc-blank").is_visible()
    assert page.evaluate("document.activeElement.id") == "cc-blank"
    page.close()
