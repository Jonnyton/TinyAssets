"""The app-surface probe must be able to go red for each way the move can fail.

A post-deploy probe that cannot fail is worse than none: it converts an outage
into a green check. So every case here drives the REAL `verify_app_surface`
against a scripted opener and asserts the specific failure text, including the
one that motivated the probe — a `/app` that answers 200 from the *website*
origin rather than the daemon.
"""

from __future__ import annotations

import urllib.error
from email.message import Message

import pytest

from scripts.probe_app_surface import (
    APEX_APP_PREFIXED_ASSET,
    APP_API_PATH,
    APP_BUILD_HEADER,
    RETIRED_APP_PATH,
    verify_app_surface,
)

BASE = "https://tinyassets.io"


def _headers(pairs):
    message = Message()
    for key, value in pairs.items():
        message[key] = value
    return message


class _Reply:
    def __init__(self, status, headers=None, body=b""):
        self.code = status
        self.headers = _headers(headers or {})
        self._body = body

    def read(self):
        return self._body


class _ScriptedOpener:
    """Answers by `METHOD path` key; an unscripted request is a test bug."""

    def __init__(self, script):
        self.script = script
        self.seen = []

    def open(self, request, timeout):  # noqa: ARG002 - probe passes a timeout
        url = request.full_url
        path = url[len(BASE):]
        key = f"{request.method} {path}"
        self.seen.append(key)
        if key not in self.script:
            raise AssertionError(f"probe made an unscripted request: {key}")
        reply = self.script[key]
        if isinstance(reply, Exception):
            raise reply
        if reply.code >= 400:
            raise urllib.error.HTTPError(url, reply.code, "err", reply.headers, None)
        return reply


def _healthy():
    """Every observation as it should look once the move is live."""
    app = _Reply(200, {APP_BUILD_HEADER: "deadbeef"}, b"<title>TinyAssets</title>")
    return {
        "GET /app": app,
        "GET /app?subscribed=1": _Reply(200, {APP_BUILD_HEADER: "deadbeef"}),
        f"GET {RETIRED_APP_PATH}": _Reply(404, {}, b"Not Found"),
        f"GET {APEX_APP_PREFIXED_ASSET}": _Reply(200, {"Content-Type": "image/png"}),
        f"GET {APP_API_PATH}": _Reply(401, {"WWW-Authenticate": "Bearer"}),
    }


def _run(script):
    opener = _ScriptedOpener(script)
    return verify_app_surface(base_url=BASE, deadline_seconds=0, opener=opener), opener


def test_a_correct_surface_is_green():
    failures, opener = _run(_healthy())
    assert failures == []
    # Every check actually issued a request; a silently skipped check would
    # otherwise read as a pass.
    assert set(opener.seen) == set(_healthy())


def test_app_404_names_the_missing_worker_route():
    """The most likely failure: routes not registered, website origin answers."""
    script = _healthy()
    script["GET /app"] = _Reply(404, {}, b"not found")
    failures, _ = _run(script)
    assert any("Cloudflare Worker has no tinyassets.io/app route" in f for f in failures)


def test_a_200_from_the_wrong_origin_is_not_a_pass():
    """This is why the probe checks a header and not just the status.

    A Pages landing page returns 200 for any path under a catch-all, so
    `/app` "working" is indistinguishable from `/app` being the landing page
    unless the daemon's own stamp is required.
    """
    script = _healthy()
    script["GET /app"] = _Reply(200, {"Content-Type": "text/html"}, b"<h1>TinyAssets</h1>")
    failures, _ = _run(script)
    assert any(APP_BUILD_HEADER in f and "other than" in f for f in failures)


def test_a_dropped_query_string_is_caught():
    script = _healthy()
    script["GET /app?subscribed=1"] = _Reply(404, {}, b"")
    failures, _ = _run(script)
    assert any("subscribed=1" in f for f in failures)


def test_the_retired_path_still_serving_is_a_failure():
    script = _healthy()
    script[f"GET {RETIRED_APP_PATH}"] = _Reply(200, {APP_BUILD_HEADER: "x"})
    failures, _ = _run(script)
    assert any("the move is not complete" in f for f in failures)


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_a_redirect_from_the_retired_path_is_a_failure(status):
    """Founder directive: no back-compat. A redirect is back-compat."""
    script = _healthy()
    script[f"GET {RETIRED_APP_PATH}"] = _Reply(status, {"Location": "/app"}, b"")
    failures, _ = _run(script)
    assert any("back-compat" in f for f in failures)


def test_an_apex_asset_swallowed_by_a_wide_route_is_a_failure():
    script = _healthy()
    script[f"GET {APEX_APP_PREFIXED_ASSET}"] = _Reply(404, {}, b"Not Found")
    failures, _ = _run(script)
    assert any("bound too widely" in f for f in failures)


def test_an_apex_asset_served_by_the_daemon_is_a_failure():
    """A 200 is not enough: the daemon could answer 200 for it too."""
    script = _healthy()
    script[f"GET {APEX_APP_PREFIXED_ASSET}"] = _Reply(200, {APP_BUILD_HEADER: "x"})
    failures, _ = _run(script)
    assert any("route is too wide" in f for f in failures)


def test_an_anonymous_app_api_200_is_a_failure():
    """The regression the path move could hide: the bearer challenge used to
    cover these routes only because they sat under /mcp/."""
    script = _healthy()
    script[f"GET {APP_API_PATH}"] = _Reply(200, {APP_BUILD_HEADER: "x"}, b"{}")
    failures, _ = _run(script)
    assert any("expected 401" in f for f in failures)


def test_a_transport_error_is_reported_not_swallowed():
    script = _healthy()
    script["GET /app"] = urllib.error.URLError("connection refused")
    failures, _ = _run(script)
    assert any("transport=" in f for f in failures)


def test_retry_window_is_bounded_and_uses_injected_clock():
    """A probe run right after a Worker deploy must tolerate propagation, but a
    permanently broken surface must still end."""
    script = _healthy()
    script["GET /app"] = _Reply(404, {}, b"")
    clock = {"now": 0.0}
    slept: list[float] = []

    def _sleep(seconds: float) -> None:
        slept.append(seconds)
        clock["now"] += seconds

    failures = verify_app_surface(
        base_url=BASE,
        deadline_seconds=12,
        retry_delay=5,
        opener=_ScriptedOpener(script),
        monotonic=lambda: clock["now"],
        sleep=_sleep,
    )
    assert failures
    assert slept, "a deadline above zero must retry at least once"
    assert sum(slept) <= 12


@pytest.mark.parametrize(("kwargs", "message"), [
    ({"request_timeout": 0}, "request_timeout must be positive"),
    ({"deadline_seconds": -1}, "deadline_seconds must be non-negative"),
])
def test_invalid_bounds_fail_loudly(kwargs, message):
    with pytest.raises(ValueError, match=message):
        verify_app_surface(base_url=BASE, opener=_ScriptedOpener({}), **kwargs)
