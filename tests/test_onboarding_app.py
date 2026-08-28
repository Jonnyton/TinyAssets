"""Tests for the daemon-served onboarding app (tinyassets/onboarding).

Unit-level: exercises the dark flag, the route handler, config injection, the
per-request CSP nonce, and secret-safety. Final onboarding acceptance is a real
user against the DEPLOYED cloud daemon (tinyassets.io) — never a local run.
"""

from __future__ import annotations

import asyncio

import pytest

from tinyassets import onboarding


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("TINYASSETS_ONBOARDING_APP", raising=False)
    monkeypatch.delenv("TINYASSETS_ONBOARDING_APP_CLIENT_ID", raising=False)
    yield


def _fake_prm(resource="https://tinyassets.io/mcp",
              issuer="https://inventive-van-62-staging.authkit.app"):
    return {
        "resource": resource,
        "authorization_servers": [issuer] if issuer else [],
        "scopes_supported": ["openid", "profile", "email", "offline_access"],
    }


def _render(monkeypatch, *, enabled=True, client_id="client_ABC", prm=None):
    if enabled:
        monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    if client_id is not None:
        monkeypatch.setenv("TINYASSETS_ONBOARDING_APP_CLIENT_ID", client_id)
    monkeypatch.setattr(
        "tinyassets.auth.wellknown.protected_resource_metadata",
        lambda: prm or _fake_prm(),
    )


# --------------------------------------------------------------------------- #
# dark flag
# --------------------------------------------------------------------------- #


def test_disabled_by_default():
    assert onboarding.onboarding_enabled() is False


@pytest.mark.parametrize("val,expected", [("1", True), ("true", True), ("on", True),
                                          ("0", False), ("", False), ("no", False)])
def test_flag_parsing(monkeypatch, val, expected):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", val)
    assert onboarding.onboarding_enabled() is expected


def test_handler_404_when_flag_off(monkeypatch):
    monkeypatch.setattr(
        "tinyassets.auth.wellknown.protected_resource_metadata", lambda: _fake_prm()
    )
    resp = asyncio.run(onboarding._handle_app(object()))
    assert resp.status_code == 404


def test_handler_200_html_when_enabled(monkeypatch):
    _render(monkeypatch)
    resp = asyncio.run(onboarding._handle_app(object()))
    assert resp.status_code == 200
    assert resp.media_type == "text/html"
    body = resp.body.decode("utf-8")
    assert "window.__TA_ONBOARDING__" in body
    assert "__TA_ONBOARDING_CONFIG__" not in body  # placeholder was substituted
    assert "__TA_NONCE__" not in body


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #


def test_config_configured_when_issuer_and_client_present(monkeypatch):
    _render(monkeypatch)
    cfg = onboarding.app_config()
    assert cfg["configured"] is True
    assert cfg["client_id"] == "client_ABC"
    assert cfg["authorization_endpoint"].endswith("/oauth2/authorize")
    assert cfg["token_endpoint"].endswith("/oauth2/token")
    assert cfg["resource"] == "https://tinyassets.io/mcp"
    assert "offline_access" in cfg["scopes"]


def test_config_not_configured_without_client_id(monkeypatch):
    _render(monkeypatch, client_id=None)
    cfg = onboarding.app_config()
    assert cfg["configured"] is False
    assert cfg["client_id"] == ""


def test_config_not_configured_without_issuer(monkeypatch):
    _render(monkeypatch, prm=_fake_prm(issuer=""))
    cfg = onboarding.app_config()
    assert cfg["configured"] is False
    assert cfg["authorization_endpoint"] == ""


# --------------------------------------------------------------------------- #
# CSP + nonce + injection safety
# --------------------------------------------------------------------------- #


def test_csp_nonce_is_per_request_and_matches_body(monkeypatch):
    _render(monkeypatch)
    html1, csp1 = onboarding.render_app_html()
    html2, csp2 = onboarding.render_app_html()
    assert csp1 != csp2  # fresh nonce each render
    nonce1 = csp1.split("'nonce-")[1].split("'")[0]
    assert f'nonce="{nonce1}"' in html1        # the inline script/style carry it
    assert f"'nonce-{nonce1}'" in csp1
    # CSP locks the network surface down to self + the AuthKit origin.
    assert "connect-src 'self' https://inventive-van-62-staging.authkit.app" in csp1
    assert "default-src 'none'" in csp1
    assert "frame-ancestors 'none'" in csp1


def test_config_injection_escapes_angle_brackets(monkeypatch):
    # A client id containing </script> must not break out of the script context.
    _render(monkeypatch, client_id="</script><script>alert(1)</script>")
    html, _ = onboarding.render_app_html()
    assert "</script><script>alert(1)" not in html
    assert "\\u003c/script>" in html


def test_no_secret_leaks_into_page(monkeypatch):
    monkeypatch.setenv("WORKOS_API_KEY", "sk_secret_should_never_render")
    monkeypatch.setenv("WORKOS_CLIENT_SECRET", "cs_secret_should_never_render")
    _render(monkeypatch)
    html, _ = onboarding.render_app_html()
    assert "sk_secret_should_never_render" not in html
    assert "cs_secret_should_never_render" not in html


def test_response_sets_security_headers(monkeypatch):
    _render(monkeypatch)
    resp = asyncio.run(onboarding._handle_app(object()))
    assert "Content-Security-Policy" in resp.headers
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Cache-Control"] == "no-store"


# --------------------------------------------------------------------------- #
# route
# --------------------------------------------------------------------------- #


def test_route_is_mcp_app_get(monkeypatch):
    routes = onboarding.onboarding_routes()
    by_path = {r.path: r for r in routes}
    # The SPA page (GET) + its same-origin PKCE token-exchange proxy (POST) +
    # the one-tap OpenAI device-auth broker (POST only, identity-gated).
    assert set(by_path) == {
        "/mcp/app", "/mcp/app/token", "/mcp/app/me",
        "/mcp/app/openai/device/start", "/mcp/app/openai/device/poll",
        "/mcp/app/openai/begin", "/mcp/app/openai/exchange", "/mcp/app/trace",
        "/mcp/app/serving/bind",
        "/mcp/app/billing/status", "/mcp/app/billing/checkout",
        "/mcp/app/billing/cancel", "/mcp/app/billing/webhook",
    }
    assert "GET" in by_path["/mcp/app"].methods
    assert "GET" in by_path["/mcp/app/billing/status"].methods
    assert "GET" in by_path["/mcp/app/me"].methods
    for post_only in (
        "/mcp/app/token", "/mcp/app/openai/device/start", "/mcp/app/openai/device/poll",
        "/mcp/app/openai/begin", "/mcp/app/openai/exchange", "/mcp/app/trace",
        "/mcp/app/serving/bind",
        "/mcp/app/billing/checkout", "/mcp/app/billing/cancel",
        "/mcp/app/billing/webhook",
    ):
        assert "POST" in by_path[post_only].methods
        assert "GET" not in by_path[post_only].methods


def test_app_embeds_build_and_serves_matching_header(monkeypatch):
    """Refresh-on-deploy: the page embeds the served build sha in its config and the
    handler sends the same value as X-TinyAssets-Build, so the SPA's HEAD probe can
    detect a newer deploy and reload (the founder saw a pre-deploy form in an app
    that had been open across a deploy)."""
    import asyncio

    from tinyassets import onboarding

    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    monkeypatch.setattr(onboarding, "build_sha", lambda: "deadbeefcafe")
    resp = asyncio.run(onboarding._handle_app(object()))
    assert resp.status_code == 200
    assert resp.headers["X-TinyAssets-Build"] == "deadbeefcafe"
    body = resp.body.decode("utf-8")
    assert '"build": "deadbeefcafe"' in body
    assert "checkForNewBuild" in body



def test_deposit_form_makes_the_x_path_discoverable():
    """Founder 2026-08-25 looking at the live form: "its still very confusing where
    goes what" - the four labelled X fields are hidden behind the auth-type select,
    so a user who does not know X needs OAuth 1.0a never sees them. The form must
    offer to fill it in and must switch itself when an X host is typed."""
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()
    # A one-tap preset that targets the real X posting endpoint.
    assert 'id="preset-x"' in html
    assert '"http-host":"api.x.com"' in html
    assert '"http-path":"/2/tweets"' in html
    assert '"http-auth-scheme":"oauth1a"' in html
    # Typing an X host switches to the four-key form on its own.
    assert 'x\\.com|twitter\\.com' in html or "x\\.com" in html
    assert "switched to the four-key form below" in html
    # The select itself says which one X needs.
    assert 'X/Twitter needs "OAuth 1.0a - 4 keys"' in html
    # The four labelled boxes still exist, one value per box.
    for field in (
        "http-oauth1a-api-key",
        "http-oauth1a-api-secret",
        "http-oauth1a-access-token",
        "http-oauth1a-access-token-secret",
    ):
        assert field in html




def test_deposit_error_surfaces_the_actionable_detail():
    """Founder 2026-08-27: deposited a GitHub API connection repeatedly ("i think i
    deposited it") and it never landed. The form rendered only the bare error code
    -- the founder eventually reported seeing exactly "Couldn't add it:
    endpoint_not_permitted" -- while the server's ``detail`` said which rule fired.
    The detail is the half a user can act on; render it like the Claude path does."""
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()
    assert "+(r.detail||r.error)" in html
    assert '"+r.error;' not in html
    # The Name field states the constraint the server actually enforces.
    assert "no spaces" in html


def test_deposit_path_is_presented_as_required_because_it_is():
    """The field was labelled "optional; default any path". It is neither.

    ``_parse_allowed_endpoints`` refuses an endpoint carrying no ``path_template``,
    and there is no any-path form this deposit can express: every ``{placeholder}``
    needs ``param_patterns`` the form does not collect. So a user who believed the
    label got the ``endpoint_not_permitted`` refusal the founder actually saw."""
    from tinyassets.api.http_connection import _parse_allowed_endpoints
    from tinyassets.onboarding import render_app_html
    from tinyassets.storage.outbound_connections import SsrfValidationError

    # The server half: blank really is refused, so the old label was false.
    with pytest.raises(SsrfValidationError):
        _parse_allowed_endpoints([{"host": "api.github.com", "methods": ["POST"]}])
    _parse_allowed_endpoints(
        [{"host": "api.github.com", "path_template": "/repos/o/r/pulls",
          "methods": ["POST"]}]
    )

    html, _csp = render_app_html()
    assert "optional; default any path" not in html
    assert "required; one exact path starting with /" in html
    # The endpoint always carries the path now, and a blank one is caught in words.
    assert "const endpoint={host,methods,path_template:path};" in html
    assert "not treated as" in html


def test_deposit_host_tolerates_a_pasted_scheme():
    """A pasted "https://api.github.com" is refused by the allow-list ("endpoint
    host is not a permitted hostname"). The form strips the scheme rather than
    round-tripping the user through a refusal for something unambiguous."""
    from tinyassets.api.http_connection import _parse_allowed_endpoints
    from tinyassets.onboarding import render_app_html
    from tinyassets.storage.outbound_connections import SsrfValidationError

    with pytest.raises(SsrfValidationError):
        _parse_allowed_endpoints(
            [{"host": "https://api.github.com", "path_template": "/x",
              "methods": ["POST"]}]
        )

    html, _csp = render_app_html()
    assert r'replace(/^[a-z][a-z0-9+.-]*:\/\//i,"")' in html


def test_paste_box_is_the_primary_deposit_and_manual_fields_survive():
    """Founder 2026-08-27: the form asked for "confusing unneeded things that the
    ai or plateform could figure out". One box replaces five fields; the explicit
    fields stay behind a disclosure so a wrong inference is a correction, not a
    dead end."""
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()
    for element in ("paste-blob", "paste-intent", "btn-paste-connect", "paste-result"):
        assert f'id="{element}"' in html
    # The explicit fields are still reachable, now inside the disclosure.
    assert 'id="http-manual"' in html
    assert "Fill it in myself" in html
    assert 'id="btn-connect-http"' in html
    # No confirmation step: the paste handler deposits straight through.
    assert "MCP.connectHTTP(r.destination,secret,r.allowed_endpoints,r.auth_scheme)" in html
    # ... and states the grant afterwards, as a receipt.
    assert "r.receipt" in html


def test_paste_extraction_sends_shape_never_the_credential():
    """The no-transmission guarantee, asserted on the code the browser runs.

    Only label + public prefix + length may be built into the resolve payload;
    the resolve call must not be handed raw pasted values.
    """
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()
    # A public prefix ends at a delimiter — the rule that keeps entropy local.
    assert "const PREFIX_RE=/^[A-Za-z][A-Za-z0-9_-]{0,10}[-_]/" in html
    assert "shape.push({label,prefix:pm?pm[0]:\"\",length:raw.length})" in html
    # The resolve call carries shape/hints/intent and nothing else.
    assert "resolveConnection(shape,hints,intent)" in html
    assert "payload_json:JSON.stringify({shape,hints,intent})" in html
    # The pasted blob is cleared before any await, like the manual form.
    assert "blobEl.value=\"\";" in html


def test_resolve_operation_is_dispatched_but_adds_no_advertised_handle():
    """Hard Rule 11: the public tool catalog stays pinned at the canonical set."""
    import inspect

    from tinyassets import universe_server as us

    source = inspect.getsource(us)
    assert '"resolve_connection"' in source
    assert "from tinyassets.api.connection_inference import resolve_connection" in source


def test_paste_extraction_closes_the_codex_client_findings():
    """Codex cross-family review 2026-08-27 (REJECT) reproduced three of these
    against the exact browser code; all are asserted on the shipped page."""
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()
    # A webhook URL's secret is its PATH — hints carry the host only.
    assert r'split(/[\/?#]/)[0]' in html
    # A labelled short value ("Username: bob") is real; only unlabelled ones
    # need length, or basic auth can never assemble user:pass.
    assert "if(raw.length < (label?3:8)) return;" in html
    # A Stripe page lists the publishable key first; it must never be chosen
    # while another candidate exists.
    assert "const publishable=(v)=>/^(?:pk|pub)[_-]/i.test(v.value||\"\");" in html
    assert "/secret.{0,3}key/i" in html
    # The intent box is cleared with the paste, so a credential typed into the
    # wrong box does not persist through an inference failure.
    assert 'blobEl.value=""; intentEl.value="";' in html


def test_pending_requests_render_as_a_side_rail_of_tabs():
    """Founder 2026-08-27: *"pending-request should show up as tabs on the ...
    side screen of the app, the hedder notates what it is like api in this case
    you tap/click them to expand and in this case paist in the api right there"*
    — moved to the RIGHT on his follow-up the same evening.
    """
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()
    assert 'id="request-rail"' in html and 'id="rail-items"' in html
    # On the right: the thread comes first in the flex row, and the rail's
    # divider is its left edge.
    assert html.index('id="thread"') < html.index('id="request-rail"')
    assert "border-left:1px solid var(--line)" in html
    # The header IS the agent's chosen kind, not a fixed label.
    assert 'kind.textContent = req.kind;' in html
    # Tap to expand, answer in place.
    assert "railOpen = (railOpen === req.request_id)" in html
    assert "MCP.answerRequest(payload)" in html
    # Fields are whatever the agent composed, including a paste box for a key.
    assert 'field.type === "secret" ? "textarea" : "input"' in html
    # Secrets are cleared from the DOM once submitted.
    assert 'values[f.name] = el.value; el.value = "";' in html


def test_the_rail_offers_feedback_and_dont_ask_again():
    """An approval needs a way to disagree and a way to stop being asked."""
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()
    assert "Don't ask me this again" in html
    assert "payload.dont_ask_again = true" in html
    assert "payload.feedback =" in html
