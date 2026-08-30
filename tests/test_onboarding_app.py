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


def test_request_tab_text_colour_is_one_named_variable():
    """The universe's first end-to-end change is a colour edit on the request
    rail. Routing that text through a single named variable makes the patch one
    line with a tiny blast radius, and makes "did it land?" answerable by eye."""
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()
    assert "--request-text:" in html
    assert "color:var(--request-text)" in html


def test_the_request_colour_lives_in_a_file_an_agent_can_reproduce():
    """Codex, 2026-08-27: the GitHub Contents API replaces a WHOLE file and has
    no patch parameter, and app.html is ~98KB — no prompt reproduces that
    byte-for-byte. So the founder's "change the colour and ship it live" goal was
    unreachable through the substrate the agent actually has. The colour moved to
    a few-line file, which is reachable."""
    import json
    from pathlib import Path

    from tinyassets import onboarding
    from tinyassets.onboarding import render_app_html, request_theme

    theme_path = Path(onboarding.__file__).with_name("request_theme.json")
    assert theme_path.is_file()
    assert theme_path.stat().st_size < 1000, "the point is that it is small"
    assert json.loads(theme_path.read_text("utf-8"))["request_text"].startswith("#")

    html, _csp = render_app_html()
    assert "__TA_REQUEST_TEXT__" not in html, "the placeholder must be substituted"
    assert f"--request-text:{request_theme()['request_text']}" in html


def test_a_bad_theme_value_never_reaches_the_page(tmp_path, monkeypatch):
    """The file is editable by an agent through a pull request, so it is input,
    not trusted CSS. A non-colour value falls back rather than being injected."""
    from tinyassets import onboarding

    bad = tmp_path / "request_theme.json"
    bad.write_text('{"request_text": "red; } body{display:none} :root{"}', "utf-8")
    monkeypatch.setattr(
        onboarding.Path, "__truediv__", onboarding.Path.__truediv__, raising=False
    )
    monkeypatch.setattr(
        onboarding, "_DEFAULT_REQUEST_TEXT", "#eef0ff", raising=False
    )
    # Point the reader at the hostile file.
    real_with_name = onboarding.Path.with_name

    def _fake_with_name(self, name):
        return bad if name == "request_theme.json" else real_with_name(self, name)

    monkeypatch.setattr(onboarding.Path, "with_name", _fake_with_name, raising=False)
    assert onboarding.request_theme()["request_text"] == "#eef0ff"

def test_the_app_restores_the_conversation_on_load():
    """Founder, 2026-08-28: "the webapp seems to clear the conversation if you
    refresh". It was worse than that — the app rendered ONLY what the current
    page instance had appended, so EVERY refresh emptied the thread, finished
    reply or not. The conversation was intact server-side the whole time; the
    app simply never asked for it, including after its own automatic reload on a
    new build."""
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()
    assert "include_conversation:true" in html
    assert "function loadHistory()" in html
    assert "loadHistory();" in html
    # Oldest-first render by each turn's OWN ts, never by assuming the peek's
    # order: `load_recent_readonly` returns oldest-first (it reverses its DESC
    # page), and a blind reverse drew the thread upside down after every reload
    # ("the conversation is reset to the past" — founder, 2026-08-29).
    assert "turns.slice().sort((a,b)=>a.ts-b.ts)" in html
    assert "turns.slice().reverse()" not in html
    # It must never block the chat on a history failure.
    assert "history is a convenience; never block the chat on it" in html

def _js_function(html: str, name: str) -> str:
    """Source of ``function NAME(`` / ``async function NAME(`` from the app's
    script, by brace matching that skips strings and comments."""
    import re

    m = re.search(r"(?:async\s+)?function\s+" + re.escape(name) + r"\s*\(", html)
    assert m, f"app.html has no function {name}"
    i = html.index("{", m.end())
    depth, j, n = 0, i, len(html)
    while j < n:
        c = html[j]
        if c in "\"'`":
            j += 1
            while j < n and html[j] != c:
                if html[j] == "\\":
                    j += 1
                j += 1
        elif html.startswith("//", j):
            j = html.index("\n", j)
        elif html.startswith("/*", j):
            j = html.index("*/", j) + 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return html[m.start(): j + 1]
        j += 1
    raise AssertionError(f"unbalanced braces in {name}")
    # No regex-literal or nested-template lexing (Codex round 2, P2): the
    # functions extracted today contain neither, and a mis-cut span is a
    # syntax error that crashes the node harness - loud, never a silent pass.


# The real send/resend/build-check code, run in Node against a DOM shim. A
# string assertion could not tell "the in-flight record is kept" from "kept,
# then forgotten one line later" (Codex round 1, P2: that mutation passed the
# old test); this drives the functions and reads the state they leave behind.
_APP_SHIM = r"""
const store={};
const localStorage={
  getItem:k=>(k in store?store[k]:null),
  setItem:(k,v)=>{store[k]=String(v);},
  removeItem:k=>{delete store[k];},
};
class El{
  constructor(tag){
    this.tagName=tag.toUpperCase(); this.children=[]; this.className="";
    this.textContent=""; this.value=""; this.style={}; this.disabled=false;
    this.listeners={}; this.scrollTop=0; this.scrollHeight=0;
  }
  appendChild(c){ this.children.push(c); return c; }
  remove(){ this.removed=true; }
  addEventListener(n,f){ this.listeners[n]=f; }
  click(){ (this.listeners.click||(()=>{}))(); }
}
const document={
  createElement:t=>new El(t),
  createTextNode:t=>{const e=new El("#text"); e.textContent=t; return e;},
  activeElement:null,
};
const els={
  "composer-input":new El("textarea"), "btn-send":new El("button"),
  "thread":new El("div"), "status-line":new El("div"),
};
const $=id=>els[id];
const messages=[];
function appendMessage(role,text,extra){ messages.push({role,text}); }
function setStatusLine(t){ els["status-line"].textContent=t||""; }
function sessionExpired(){ messages.push({role:"session-expired"}); }
function showConnect(){ messages.push({role:"connect"}); }
const SCENARIO=__SCENARIO__;
const converseCalls=[];
const MCP={ converse: async m => {
  converseCalls.push(m);
  if(SCENARIO.transportError){ const e=new Error("offline"); e.transport=true; throw e; }
  const payloads=SCENARIO.payloads||[SCENARIO.payload];
  return payloads[Math.min(converseCalls.length-1, payloads.length-1)];
}};
const CFG={build: SCENARIO.build||"b1"};
const token=()=>"t";
MCP.getConversation=async()=>{
  if(SCENARIO.historyError) throw new Error("peek failed");
  return {recent_conversation:{turns: SCENARIO.history||[]}};
};
const answered=[];
MCP.answerRequest=async(payload)=>{
  answered.push(payload); return SCENARIO.answerReply||{receipt:"Sent."};
};
let refreshed=0; async function refreshRail(){ refreshed++; }
function enterSignedOut(){ messages.push({role:"signed-out"}); }
let reloaded=false; const location={reload:()=>{ reloaded=true; }};
let fetched=0;
async function fetch(){ fetched++; return {headers:{get:()=>SCENARIO.liveBuild||null}}; }
__APP_FUNCTIONS__
(async()=>{
  const out={};
  if(SCENARIO.kind==="send"){
    await sendTurn(SCENARIO.message);
    if(SCENARIO.clickResend){
      const btn=els.thread.children.flatMap(n=>n.children).find(c=>c.tagName==="BUTTON");
      btn.click();                                   // the listener fires sendTurn (async)
      await new Promise(r=>setTimeout(r, 20));
    }
    out.converseCalls=converseCalls;
    out.notesRemoved=els.thread.children.filter(n=>n.removed).length;
    out.inflight=JSON.parse(localStorage.getItem(INFLIGHT_KEY)||"null");
    out.messages=messages;
    out.notes=els.thread.children.map(n=>({cls:n.className,
      text:n.textContent+n.children.map(c=>c.textContent).join(""),
      buttons:n.children.filter(c=>c.tagName==="BUTTON").map(b=>b.textContent)}));
    out.sendDisabled=els["btn-send"].disabled;
    out.status=els["status-line"].textContent;
  }else if(SCENARIO.kind==="rail"){
    const req=SCENARIO.request;
    els["fb_"+req.request_id]=new El("input");
    els["fb_"+req.request_id].value=SCENARIO.feedback||"";
    els["mute_"+req.request_id]=new El("input"); els["mute_"+req.request_id].checked=false;
    if(SCENARIO.turnInFlight){ els["btn-send"].disabled=true; turnStartedAt=Date.now(); }
    const note=new El("div"); const buttons=[new El("button"), new El("button")];
    await answerRail(req, !!SCENARIO.dismiss, note, buttons);
    await new Promise(r=>setTimeout(r, 20));           // the relayed sendTurn is not awaited
    out.answered=answered; out.refreshed=refreshed; out.note=note.textContent;
    out.converseCalls=converseCalls; out.messages=messages;
    out.buttonsEnabled=buttons.every(b=>!b.disabled);
  }else if(SCENARIO.kind==="restore"){
    localStorage.setItem(INFLIGHT_KEY, JSON.stringify({
      message:SCENARIO.pending, display:SCENARIO.pending,
      ts: Date.now()-(SCENARIO.pendingAgeS||0)*1000}));
    await loadHistory();
    await loadHistory();                                 // a second pass must not double-restore
    out.inflight=JSON.parse(localStorage.getItem(INFLIGHT_KEY)||"null");
    out.messages=messages;
    out.notes=els.thread.children.map(n=>({cls:n.className, text:n.textContent,
      buttons:n.children.filter(c=>c.tagName==="BUTTON").map(b=>b.textContent)}));
  }else{
    const min=60*1000;
    if(SCENARIO.pendingAgeMin!=null){
      localStorage.setItem(INFLIGHT_KEY, JSON.stringify(
        {message:"m", display:"m", ts: Date.now()-SCENARIO.pendingAgeMin*min}));
    }
    if(SCENARIO.inflightAgeMin!=null){
      els["btn-send"].disabled=true; turnStartedAt=Date.now()-SCENARIO.inflightAgeMin*min;
    }
    await checkForNewBuild();
    out.reloaded=reloaded; out.fetched=fetched;
  }
  console.log(JSON.stringify(out));
})().catch(e=>{ console.error(e&&e.stack||e); process.exit(1); });
"""


def _run_app(tmp_path, scenario: dict) -> dict:
    import json
    import os
    import re
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:  # pragma: no cover - environment dependent
        if os.environ.get("TINYASSETS_SKIP_JS_PROBE_TESTS"):
            pytest.skip("node absent; skip explicitly requested via env")
        pytest.fail("node executable not found - the app's send/resend behaviour is "
                    "JavaScript; install Node or set TINYASSETS_SKIP_JS_PROBE_TESTS=1")
    html, _csp = onboarding.render_app_html()
    decls = "\n".join(
        re.search(pat, html).group(0)
        for pat in (r"const INFLIGHT_KEY=[^\n]*;", r"let turnStartedAt=[^\n]*;",
                    r"let historyLoaded = [^\n]*;", r"let inflightRestored = [^\n]*;",
                    r"let railOpen = [^\n]*;")
    )
    funcs = "\n".join(_js_function(html, f) for f in (
        "rememberInflight", "forgetInflight", "readInflight", "renderConverse",
        "offerResend", "sendTurn", "checkForNewBuild", "loadHistory", "restoreInflight",
        "answerLine", "answerRail",
    ))
    program = (_APP_SHIM
               .replace("__SCENARIO__", json.dumps(scenario))
               .replace("__APP_FUNCTIONS__", decls + "\n" + funcs))
    script = tmp_path / "app_case.js"
    script.write_text(program, encoding="utf-8")
    proc = subprocess.run([node, str(script)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60)
    assert proc.returncode == 0, f"app harness crashed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_a_served_error_keeps_the_message_resendable_with_the_servers_sentence(tmp_path):
    """The universe never answered, so the message stays the user's: the
    in-flight record survives, the note is the server's own sentence, and
    "Send it again" is one click away. (2026-08-29: the app drew the error as
    a finished turn, forgot the message, and a reload wiped both.)"""
    sentence = "Your universe went quiet mid-turn, so the turn was ended."
    out = _run_app(tmp_path, {"kind": "send", "message": "hi",
                              "payload": {"error": sentence}})
    assert out["inflight"] and out["inflight"]["message"] == "hi"
    assert [m["role"] for m in out["messages"]] == ["founder"]      # no fake reply
    notes = [n for n in out["notes"] if "msg--system" in n["cls"]]
    assert len(notes) == 1 and notes[0]["text"].startswith(sentence)
    assert notes[0]["buttons"] == ["Send it again"]
    assert out["sendDisabled"] is False and out["status"] == ""


def test_send_it_again_resends_the_same_message_once_without_a_second_bubble(tmp_path):
    """Codex round 2 (P2): the button was rendered but never pressed. Press it:
    the SAME text goes to the universe again, the founder bubble is not drawn
    twice (`echoed`), the note is gone, and a delivered reply then clears the
    in-flight record."""
    out = _run_app(tmp_path, {
        "kind": "send", "message": "hi", "clickResend": True,
        "payloads": [{"error": "Your universe went quiet mid-turn."}, {"reply": "hello"}],
    })
    assert out["converseCalls"] == ["hi", "hi"]
    assert [m["role"] for m in out["messages"]] == ["founder", "universe"]
    assert out["notesRemoved"] == 1
    assert out["inflight"] is None
    assert out["sendDisabled"] is False


def test_a_delivered_reply_forgets_the_in_flight_record(tmp_path):
    out = _run_app(tmp_path, {"kind": "send", "message": "hi",
                              "payload": {"reply": "hello"}})
    assert out["inflight"] is None
    assert [m["role"] for m in out["messages"]] == ["founder", "universe"]
    assert out["sendDisabled"] is False


def test_a_transport_failure_still_offers_the_resend(tmp_path):
    out = _run_app(tmp_path, {"kind": "send", "message": "hi", "transportError": True})
    assert out["inflight"]["message"] == "hi"
    assert any("didn’t get through" in n["text"] for n in out["notes"])


def _turn(speaker, text, age_s):
    """A history turn as the peek sends it: epoch SECONDS, oldest first."""
    import time

    return {"speaker": speaker, "text": text, "ts": time.time() - age_s, "truncated": False}


def test_a_held_message_is_restored_on_an_empty_thread(tmp_path):
    """Codex round 3 (P1): `loadHistory` returned before `restoreInflight` when
    history was empty, so the FIRST message a user ever sent, if it failed,
    vanished on reload."""
    out = _run_app(tmp_path, {"kind": "restore", "pending": "hello there", "history": []})
    assert out["inflight"]["message"] == "hello there"
    assert [m["role"] for m in out["messages"]] == ["founder"]          # once, not twice
    notes = [n for n in out["notes"] if "msg--system" in n["cls"]]
    assert len(notes) == 1 and "never confirmed" in notes[0]["text"]
    assert notes[0]["buttons"] == ["Send it again"]


def test_a_held_message_is_restored_when_the_peek_fails(tmp_path):
    out = _run_app(tmp_path, {"kind": "restore", "pending": "hello", "historyError": True})
    assert out["inflight"]["message"] == "hello"
    assert [m["role"] for m in out["messages"]] == ["founder"]


def test_an_older_identical_prompt_does_not_count_as_delivery(tmp_path):
    """Codex round 3 (P1): "continue" sent ten minutes ago and answered must
    not make a NEW failed "continue" look delivered."""
    out = _run_app(tmp_path, {
        "kind": "restore", "pending": "continue", "pendingAgeS": 30,
        "history": [_turn("founder", "continue", 600), _turn("universe", "ok", 600)],
    })
    assert out["inflight"]["message"] == "continue"
    assert [m["role"] for m in out["messages"]] == ["you", "universe", "founder"]


def test_a_message_delivered_while_away_is_not_restored(tmp_path):
    """The newest founder turn IS the held message and is stamped after the
    send: the reply landed, the local copy is stale and is dropped."""
    out = _run_app(tmp_path, {
        "kind": "restore", "pending": "continue", "pendingAgeS": 120,
        "history": [_turn("founder", "continue", 60), _turn("universe", "done", 60)],
    })
    assert out["inflight"] is None
    assert [m["role"] for m in out["messages"]] == ["you", "universe"]


@pytest.mark.parametrize("scenario, reloads", [
    ({}, True),                                   # nothing in flight: update
    ({"liveBuild": "b1"}, False),                 # same build: nothing to do
    ({"inflightAgeMin": 1}, False),               # a turn being served: hold
    ({"inflightAgeMin": 70}, False),              # a raised per-universe cap: still hold
    ({"inflightAgeMin": 200}, True),              # past any cap: a dead fetch; reload
    ({"pendingAgeMin": 5}, False),                # a failed message waiting: hold
    ({"pendingAgeMin": 25}, True),                # abandoned: update
])
def test_the_build_check_holds_for_a_live_turn_but_never_forever(tmp_path, scenario, reloads):
    """Codex round 1 (P1): a never-settling send used to hold updates for good."""
    case = {"kind": "build", "liveBuild": "b2", **scenario}
    out = _run_app(tmp_path, case)
    assert out["reloaded"] is reloads, case


def test_an_unconfirmed_message_survives_a_reload_and_says_so():
    """Founder, 2026-08-28: "you still need to fix it all, webapp is a promary
    surface". Restoring recorded history was not enough — a turn is recorded only
    when the exchange COMPLETES, so a reload mid-reply had nothing to restore and
    the message vanished.

    It is kept locally now, and shown with its REAL state: a 503 during a deploy
    ate one of these while the bubble sat there looking delivered, so an
    unconfirmed message must not be drawn as a normal sent one."""
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()
    assert "ta_inflight_turn" in html
    assert "rememberInflight(message, display)" in html
    # Cleared on success, KEPT on failure — a failed send is still the user's.
    assert "forgetInflight();" in html
    assert "the send failed, so the message is still the" in html
    # Restored only when history does not already contain it.
    assert "function restoreInflight(turns)" in html
    assert "This message was never confirmed" in html
    assert "Send it again" in html


def test_the_connect_nav_button_is_gone_and_the_rail_is_the_way_in():
    """Founder 2026-08-27: "the entire connect/add api connection button at the
    top right of the app is being cut". It was also clipping against Upgrade and
    Sign out at that width. The rail replaces it — including a way to add a key
    proactively, so cutting the button does not remove the ability."""
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()
    assert 'id="btn-connect"' not in html
    assert 'id="btn-rail-add"' in html
    # The rail stays present even with nothing waiting, or that route vanishes.
    assert "rail.hidden = false;" in html


def test_a_sticky_ask_renders_expanded_and_offers_no_dismiss():
    """A universe with no model cannot be asked to accept having no model."""
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()
    assert "req.sticky ?" in html
    assert 'req.action.type === "connect_llm"' in html
    # It hands off to the provider cards that already work, rather than
    # reinventing the OAuth and token flows inside a tab.
    assert "no fields, no feedback, no dismiss" in html



# --- a rail answer is the founder's line (2026-08-30) -----------------------------
#
# Live 2026-08-29: tiny raised an ask, the founder approved it in the rail, and
# tiny sat idle until the founder typed "approved - go ahead" - twice. The click
# is that line; the app now says it in the thread through the normal send path.

_TITLE = "Extend GitHub access so I can repair the README"
_REQ = {"request_id": "req_1", "kind": "API", "title": _TITLE, "fields": []}


def test_an_approval_is_relayed_as_the_founders_line(tmp_path):
    out = _run_app(tmp_path, {"kind": "rail", "request": _REQ, "payload": {"reply": "on it"}})
    assert out["answered"][0]["request_id"] == "req_1" and "dismiss" not in out["answered"][0]
    assert out["converseCalls"] == [f'Approved: "{_TITLE}"']
    assert [m["role"] for m in out["messages"]] == ["founder", "universe"]
    assert out["refreshed"] == 1 and out["note"] == "Sent." and out["buttonsEnabled"]


def test_feedback_rides_along_and_not_now_is_relayed_too(tmp_path):
    out = _run_app(tmp_path, {
        "kind": "rail", "request": _REQ, "dismiss": True,
        "feedback": "ask again after the PR is open", "payload": {"reply": "ok"},
    })
    assert out["answered"][0]["dismiss"] is True
    assert out["answered"][0]["feedback"] == "ask again after the PR is open"
    assert out["converseCalls"] == [f'Not now: "{_TITLE}" \u2014 ask again after the PR is open']


def test_no_relay_over_a_turn_in_flight(tmp_path):
    out = _run_app(tmp_path, {"kind": "rail", "request": _REQ, "turnInFlight": True})
    assert out["answered"] and out["converseCalls"] == []
    assert "will see it when its current turn ends" in out["note"]


def test_a_failed_answer_relays_nothing(tmp_path):
    out = _run_app(tmp_path, {
        "kind": "rail", "request": _REQ, "answerReply": {"error": "not_found"},
    })
    assert out["converseCalls"] == [] and out["refreshed"] == 0
    assert out["note"].startswith("Couldn't do that")
