"""The isolation boundary a user-authored UI bundle runs behind.

A bundle is arbitrary code written by somebody the viewer may never have met, so
these assertions are the containment itself, not a nicety. Each one is written
against the property that holds (an opaque origin, no network of its own) rather
than against the exact spelling of a policy string, so a reordered CSP still
passes and a *weakened* one still fails.

What this file cannot prove: that a real browser enforces the policy. That needs
a rendered conversation through the live connector. These are the preconditions.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tinyassets.onboarding import onboarding_routes, render_app_html
from tinyassets.onboarding.ui_frame import BOOTSTRAP_HTML, FRAME_CSP, FRAME_HEADERS

APP_UI = Path("tinyassets/onboarding/app_ui.js").read_text(encoding="utf-8")


def _directives(policy: str) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    for part in policy.split(";"):
        tokens = part.split()
        if tokens:
            parsed[tokens[0]] = tokens[1:]
    return parsed


def test_frame_document_is_an_opaque_origin_with_no_network() -> None:
    frame = _directives(FRAME_CSP)

    # The whole boundary: sandboxed, and NEVER with allow-same-origin. With that
    # grant the frame would share the app's origin and could read the access
    # token out of sessionStorage.
    assert "sandbox" in frame, FRAME_CSP
    assert frame["sandbox"] == ["allow-scripts"], frame["sandbox"]

    # No network of its own, so the only way out is the bridge. An image URL is a
    # GET a bundle could smuggle data through, so remote images are refused too.
    assert frame["connect-src"] == ["'none'"]
    assert frame["form-action"] == ["'none'"]
    assert frame["default-src"] == ["'none'"]
    assert frame["img-src"] == ["data:"]
    assert "'self'" not in frame["img-src"] and "*" not in frame["img-src"]

    # frame-src is absent, so it falls back to default-src 'none': the bundle
    # cannot nest a frame to shop for a weaker context.
    assert "frame-src" not in frame and "child-src" not in frame
    assert frame["frame-ancestors"] == ["'self'"]
    assert frame["base-uri"] == ["'none'"]


def test_frame_response_carries_the_policy_and_no_user_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert FRAME_HEADERS["Content-Security-Policy"] == FRAME_CSP
    assert FRAME_HEADERS["Cache-Control"] == "no-store"
    assert FRAME_HEADERS["X-Content-Type-Options"] == "nosniff"

    # The sandbox rides the RESPONSE, so a direct top-level navigation to this
    # route is sandboxed too -- an iframe attribute alone would not cover that.
    assert "sandbox" in FRAME_HEADERS["Content-Security-Policy"]

    # The document is fixed. No placeholder and nowhere for a bundle to be
    # inlined server-side: the parent posts it in after "ready".
    assert "__TA_" not in BOOTSTRAP_HTML
    assert 'type: "ready"' in BOOTSTRAP_HTML

    # And the served body IS that constant -- nothing per-request is woven in, so
    # there is no request-shaped path for content to reach this origin.
    import asyncio

    from tinyassets.onboarding.ui_frame import handle_ui_frame

    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    served = asyncio.run(handle_ui_frame(object()))
    assert served.body.decode("utf-8") == BOOTSTRAP_HTML


def test_frame_route_is_registered_for_reads_only() -> None:
    frame_routes = [r for r in onboarding_routes() if getattr(r, "path", "") == "/mcp/app/ui-frame"]
    assert len(frame_routes) == 1
    assert set(frame_routes[0].methods) == {"GET", "HEAD"}


def test_app_page_grants_frames_but_keeps_nonce_only_script() -> None:
    _html, policy = render_app_html()
    app = _directives(policy)

    # The one grant a bundle needs, and it reaches only this origin's fixed
    # bootstrap.
    assert app["frame-src"] == ["'self'"]

    # Deliberately unchanged: even a bug that inserted bundle script into this
    # page would not execute it, because nothing carries the per-request nonce.
    assert len(app["script-src"]) == 1
    assert app["script-src"][0].startswith("'nonce-")
    assert "'unsafe-inline'" not in app["script-src"]
    assert "'unsafe-eval'" not in app["script-src"]


def test_bundle_source_never_enters_the_app_document() -> None:
    # The frame is the ONLY renderer. A bundle field assigned to innerHTML,
    # document.write, eval or a Function constructor in the parent would put
    # somebody else's code on the app's own origin.
    for forbidden in ("document.write", "eval(", "new Function", "insertAdjacentHTML"):
        assert forbidden not in APP_UI, forbidden

    # innerHTML does appear -- inside the frame's bootstrap, not here.
    assert "innerHTML" not in APP_UI
    assert "innerHTML" in BOOTSTRAP_HTML

    # The sandbox attribute is the second, independent lock. Assert the property
    # (no same-origin grant), not the literal string.
    sandbox = re.search(r'SANDBOX:"([^"]*)"', APP_UI)
    assert sandbox, "AppUI must declare the sandbox it applies"
    grants = sandbox.group(1).split()
    assert grants == ["allow-scripts"], grants
    assert 'setAttribute("sandbox",this.SANDBOX)' in APP_UI


def test_frame_handler_honours_the_dark_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from tinyassets.onboarding.ui_frame import handle_ui_frame

    monkeypatch.delenv("TINYASSETS_ONBOARDING_APP", raising=False)
    off = asyncio.run(handle_ui_frame(object()))
    assert off.status_code == 404
    assert "Content-Security-Policy" not in off.headers

    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    on = asyncio.run(handle_ui_frame(object()))
    assert on.status_code == 200
    assert on.headers["Content-Security-Policy"] == FRAME_CSP


def test_bundle_bounds_fit_the_real_binding_cap() -> None:
    """The JS bounds are derived from the Python cap, not a coincidence.

    A full library must still fit one canonical-JSON binding configuration. This
    reads the enforcing constant rather than restating its value, so raising
    either side without the other fails here instead of at a user's write.
    """
    from tinyassets.custom_agents import MAX_AGENT_JSON_BYTES

    def constant(name: str) -> int:
        found = re.search(rf"\b{name}:(\d+)", APP_UI)
        assert found, name
        return int(found.group(1))

    per_bundle = constant("MAX_BUNDLE_BYTES")
    library = constant("LIBRARY_LIMIT")

    # Every field bound must be reachable inside one bundle's own budget, or the
    # field bound is decoration.
    assert constant("MAX_MARKUP") <= per_bundle
    assert constant("MAX_STYLE") <= per_bundle
    assert constant("MAX_SCRIPT") <= per_bundle

    # And a full library plus the rest of the configuration must fit the cap the
    # server actually enforces, with room left for layout and turn selection.
    assert per_bundle * library < MAX_AGENT_JSON_BYTES
    assert MAX_AGENT_JSON_BYTES - per_bundle * library >= 32 * 1024
