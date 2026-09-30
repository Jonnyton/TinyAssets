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
    RETIRED_OK_STATUSES,
    verify_app_surface,
)

CODE_QUERY = "?code=probe-not-a-real-code&state=probe"
SUBSCRIBED_QUERY = "?subscribed=1"

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
        "GET /app" + CODE_QUERY: _Reply(200, {APP_BUILD_HEADER: "deadbeef"}),
        "GET /app" + SUBSCRIBED_QUERY: _Reply(200, {APP_BUILD_HEADER: "deadbeef"}),
        # Anonymously the retired path gets the connector namespace's 401, the
        # same as any absent /mcp/* path. That is the real production shape.
        f"GET {RETIRED_APP_PATH}": _Reply(401, {"WWW-Authenticate": "Bearer"}),
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


@pytest.mark.parametrize("query", [CODE_QUERY, SUBSCRIBED_QUERY])
def test_a_query_bearing_app_url_that_404s_is_caught(query):
    """The review finding: an EXACT `tinyassets.io/app` Cloudflare route matches
    only the bare path, because a route is matched against the whole URL
    including the query. Sign-in and billing both return with a query."""
    script = _healthy()
    script["GET /app" + query] = _Reply(404, {}, b"")
    failures, _ = _run(script)
    assert any("tinyassets.io/app*" in f for f in failures)


@pytest.mark.parametrize("query", [CODE_QUERY, SUBSCRIBED_QUERY])
def test_a_query_bearing_200_from_the_wrong_origin_is_caught(query):
    """The probe's own earlier hole: the query check asserted status only, so a
    website 200 satisfied the very check that exists to catch a website 200."""
    script = _healthy()
    script["GET /app" + query] = _Reply(200, {"Content-Type": "text/html"}, b"<h1>site</h1>")
    failures, _ = _run(script)
    assert any("the website origin answered the callback URL" in f for f in failures)


def test_the_retired_path_still_serving_is_a_failure():
    script = _healthy()
    script[f"GET {RETIRED_APP_PATH}"] = _Reply(200, {APP_BUILD_HEADER: "x"})
    failures, _ = _run(script)
    assert any("still serves the app" in f for f in failures)


def test_a_retired_path_carrying_the_build_header_is_a_failure():
    """Even on a refusal status: the header means the app is mounted there."""
    script = _healthy()
    script[f"GET {RETIRED_APP_PATH}"] = _Reply(404, {APP_BUILD_HEADER: "x"}, b"")
    failures, _ = _run(script)
    assert any("still being served from the retired path" in f for f in failures)


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_a_redirect_from_the_retired_path_is_a_failure(status):
    """Founder directive: no back-compat. A redirect is back-compat."""
    script = _healthy()
    script[f"GET {RETIRED_APP_PATH}"] = _Reply(status, {"Location": "/app"}, b"")
    failures, _ = _run(script)
    assert any("back-compat" in f for f in failures)


@pytest.mark.parametrize("status", [500, 502, 503])
def test_a_sick_origin_on_the_retired_path_is_not_retirement(status):
    """The probe's other earlier hole: it accepted any non-200, non-3xx, so a
    503 outage read as a successful retirement."""
    script = _healthy()
    script[f"GET {RETIRED_APP_PATH}"] = _Reply(status, {}, b"")
    failures, _ = _run(script)
    assert any("the origin is sick, not retired" in f for f in failures)


def test_the_accepted_retirement_statuses_are_exactly_the_refusals():
    """401 is the real production shape — `/mcp/app` is inside the connector
    namespace, which challenges everything under it, so anonymously it answers
    exactly what `/mcp/anything` answers. 404 is what a bearer would see.
    Carving the retired path out to force a 404 would be a special case FOR the
    retired path, i.e. the back-compat this move removes."""
    assert RETIRED_OK_STATUSES == frozenset({401, 404})
    for status in sorted(RETIRED_OK_STATUSES):
        script = _healthy()
        script[f"GET {RETIRED_APP_PATH}"] = _Reply(status, {}, b"")
        failures, _ = _run(script)
        assert failures == [], (status, failures)


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
