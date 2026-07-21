"""Task #35 part B — inline permission-card dismiss.

Tests ``_dismiss_inline_permission_card`` gating + click behavior.
The detector runs ``page.evaluate`` on live Playwright state; we
fake the page with a tiny stub so the gate logic and notepad-log
wiring are unit-testable without a browser.

The Python-side stub can only pin payload handling — it never runs the
JS. The bottom half of this file therefore executes the *real*
``_INLINE_ALWAYS_ALLOW_PROBE`` source in Node against a minimal DOM
shim, which is the only way to assert what the probe actually clicks.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def chat_module(tmp_path, monkeypatch):
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    monkeypatch.syspath_prepend(str(scripts_dir))
    sys.modules.pop("claude_chat", None)
    module = importlib.import_module("claude_chat")
    module.NOTEPAD = tmp_path / "user_sim_session.md"
    return module


class _FakePage:
    """Minimal page stub — ``evaluate`` returns a scripted payload."""

    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    def evaluate(self, _script):
        self.calls += 1
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _notepad_text(module) -> str:
    path = Path(module.NOTEPAD)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def test_inline_dismiss_click_success_returns_1(chat_module):
    """Detector reports clicked=True → return 1 and log ok."""
    page = _FakePage({
        "found": True, "clicked": True, "label": "Always allow",
    })
    result = chat_module._dismiss_inline_permission_card(page)
    assert result == 1
    body = _notepad_text(chat_module)
    assert "SYSTEM DIALOG _dismiss_inline_permission_card" in body
    assert "auto-dismiss: ok" in body
    assert "Always allow" in body


def test_inline_dismiss_not_found_returns_0_no_log(chat_module):
    """No permission card on page → return 0, nothing logged."""
    page = _FakePage({"found": False, "reason": "no permission card text"})
    result = chat_module._dismiss_inline_permission_card(page)
    assert result == 0
    # Notepad untouched.
    assert _notepad_text(chat_module) == ""


def test_inline_dismiss_detected_but_click_failed_logs_failed(chat_module):
    """Found but click failed → return 0, log 'failed' so host sees it."""
    page = _FakePage({
        "found": True, "clicked": False, "label": "Always allow",
        "error": "node detached",
    })
    result = chat_module._dismiss_inline_permission_card(page)
    assert result == 0
    body = _notepad_text(chat_module)
    assert "auto-dismiss: failed" in body
    assert "Always allow" in body


def test_inline_dismiss_evaluate_raises_returns_0(chat_module):
    """page.evaluate raising is treated as a miss, never propagates."""
    page = _FakePage(RuntimeError("CDP dropped"))
    result = chat_module._dismiss_inline_permission_card(page)
    assert result == 0
    assert _notepad_text(chat_module) == ""


def test_inline_dismiss_empty_payload_returns_0(chat_module):
    """evaluate returning None/empty dict → treated as no-op."""
    page = _FakePage(None)
    assert chat_module._dismiss_inline_permission_card(page) == 0


def test_inline_dismiss_missing_label_falls_back_to_default(chat_module):
    """Missing label still logs a usable line (default 'Always allow')."""
    page = _FakePage({"found": True, "clicked": True})
    result = chat_module._dismiss_inline_permission_card(page)
    assert result == 1
    assert "Always allow" in _notepad_text(chat_module)


def test_inline_dismiss_refusal_is_logged_once(chat_module):
    """A deliberate refusal is visible to the host — but only once, so
    the per-poll cadence can't flood the notepad."""
    page = _FakePage({"found": False, "reason": "not TinyAssets Server card"})
    assert chat_module._dismiss_inline_permission_card(page) == 0
    body = _notepad_text(chat_module)
    assert "auto-dismiss: skipped" in body
    assert "not TinyAssets Server card" in body
    # Second poll with the same reason adds nothing.
    chat_module._dismiss_inline_permission_card(page)
    assert _notepad_text(chat_module).count("not TinyAssets Server card") == 1


def test_inline_dismiss_ordinary_misses_stay_quiet(chat_module):
    """The two every-poll reasons must never reach the notepad."""
    for reason in ("no permission card text", "no visible Always-allow button"):
        page = _FakePage({"found": False, "reason": reason})
        assert chat_module._dismiss_inline_permission_card(page) == 0
    assert _notepad_text(chat_module) == ""


def test_inline_probe_script_gating_strings(chat_module):
    """The JS probe uses the exact gate strings team-lead specified —
    "Claude wants to use" AND a brand match (TinyAssets / TinyAssets Server /
    legacy Universe Server) AND a button whose text starts with "Always
    allow". Pin the contract."""
    probe = chat_module._INLINE_ALWAYS_ALLOW_PROBE
    assert "Claude wants to use" in probe
    # Brand gate covers the new "TinyAssets" connector name AND retains
    # the legacy "Universe Server" name so the probe still works for
    # connectors that haven't been reconnected yet. NOTE: presence of
    # these strings is necessary but nowhere near sufficient — the name
    # is compared EXACTLY, and what the probe actually clicks is pinned
    # by the behavioral tests below.
    assert "TinyAssets" in probe
    assert "Universe Server" in probe
    # Case-insensitive exact-prefix match on Always allow.
    assert "^always allow" in probe.lower()


# ---------------------------------------------------------------------------
# Behavioral probe tests — run the real JS in Node against a DOM shim.
#
# The source-substring test above pins that the gate *strings* exist. It
# cannot tell a card-scoped match from a whole-page match, which is the
# difference between "click our own permission card" and "auto-grant
# Always-allow to whatever connector happens to be on screen". These
# tests execute the shipped probe and assert which button it clicks.
# ---------------------------------------------------------------------------

_DOM_SHIM = r"""
'use strict';
// Minimal DOM good enough for the probe: innerText composed from the
// subtree, parentElement chains, offsetParent visibility, and a
// tag-name-only querySelectorAll. Clicks are recorded, never real.
const CLICKS = [];

class El {
  constructor(spec, parent) {
    this.id = spec.id || null;
    this.tag = (spec.tag || 'div').toLowerCase();
    this.ownText = spec.text || '';
    this.hidden = spec.hidden === true;
    this.parentElement = parent || null;
    this.children = (spec.children || []).map((c) => new El(c, this));
  }
  get innerText() {
    const parts = [];
    if (this.ownText) parts.push(this.ownText);
    for (const child of this.children) {
      const text = child.innerText;
      if (text) parts.push(text);
    }
    return parts.join('\n');
  }
  get offsetParent() {
    // null when this node or any ancestor is hidden (matches the real
    // property closely enough for a visibility gate).
    let node = this;
    while (node) {
      if (node.hidden) return null;
      node = node.parentElement;
    }
    return this.parentElement;
  }
  scrollIntoView() {}
  click() {
    CLICKS.push(this.id || this.ownText);
  }
  walk(out) {
    out.push(this);
    for (const child of this.children) child.walk(out);
    return out;
  }
}

const SCENARIO = __SCENARIO__;
const documentElement = new El(
  {tag: 'html', children: [Object.assign({}, SCENARIO, {tag: 'body'})]},
  null,
);
const document = {
  body: documentElement.children[0],
  documentElement: documentElement,
  querySelectorAll(selector) {
    const tag = String(selector).toLowerCase();
    return documentElement.walk([]).filter((el) => el.tag === tag);
  },
};
"""


def _run_probe(chat_module, tmp_path, scenario):
    """Execute the real probe source against ``scenario`` in Node.

    Returns ``{"result": <probe payload>, "clicks": [<button id>, ...]}``.
    """
    node = shutil.which("node")
    if not node:  # pragma: no cover - environment dependent
        # Fail loudly rather than skip. These are the only tests that
        # assert what the probe actually clicks; a silent skip would let
        # the whole-page-match regression land unnoticed on a runner
        # without node. Explicit opt-out for environments that genuinely
        # cannot install it.
        if os.environ.get("TINYASSETS_SKIP_JS_PROBE_TESTS"):
            pytest.skip("node absent; skip explicitly requested via env")
        pytest.fail(
            "node executable not found — the inline permission-card probe "
            "is JavaScript and its click behavior cannot be verified "
            "without it. Install Node, or set "
            "TINYASSETS_SKIP_JS_PROBE_TESTS=1 to accept the coverage gap."
        )
    program = (
        _DOM_SHIM.replace("__SCENARIO__", json.dumps(scenario))
        + "\nconst RESULT = "
        + chat_module._INLINE_ALWAYS_ALLOW_PROBE
        + "\nconsole.log(JSON.stringify({result: RESULT, clicks: CLICKS}));\n"
    )
    script = tmp_path / "probe_case.js"
    script.write_text(program, encoding="utf-8")
    proc = subprocess.run(
        [node, str(script)], capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"probe harness crashed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def _allow_button(bid="allow-btn", text="Always allow", **extra):
    return dict({"tag": "button", "id": bid, "text": text}, **extra)


def _card(prompt, *, cid="card", button=None):
    """One inline permission card: prompt text + its Always-allow button."""
    return {
        "id": cid,
        "children": [
            {"id": f"{cid}-prompt", "text": prompt},
            button or _allow_button(f"{cid}-allow"),
        ],
    }


def test_probe_clicks_tinyassets_card(chat_module, tmp_path):
    """The happy path still works: our own card gets Always-allow."""
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "children": [_card("Claude wants to use TinyAssets", cid="ta")],
    })
    assert out["result"]["found"] is True
    assert out["result"]["clicked"] is True
    assert out["clicks"] == ["ta-allow"]


def test_probe_clicks_legacy_universe_server_card(chat_module, tmp_path):
    """Legacy-connector fallback, asserted behaviorally rather than by
    grepping the source.

    A Claude.ai custom connector keeps the display name it was installed
    with — this repo's rename to TinyAssets cannot retroactively change
    an already-installed connector's card text. So a host who has not
    reconnected still sees "Universe Server" and must still be matched.
    """
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "children": [_card("Claude wants to use Universe Server", cid="legacy")],
    })
    assert out["result"]["clicked"] is True
    assert out["clicks"] == ["legacy-allow"]


def test_probe_does_not_grant_another_connector_after_our_card(
    chat_module, tmp_path,
):
    """Whole-page matching would auto-grant a THIRD-PARTY connector.

    A resolved TinyAssets permission card stays in the transcript DOM.
    If the brand gate reads the whole page, that stale text vouches for
    a live Google Drive card and the probe clicks *its* Always-allow —
    silently granting the model standing access to the host's Drive.
    """
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "children": [
            {"id": "transcript", "children": [
                _card("Claude wants to use TinyAssets", cid="old-ta",
                      button={"id": "old-ta-resolved", "text": "Allowed"}),
                _card("Claude wants to use Google Drive", cid="gdrive"),
            ]},
        ],
    })
    assert out["clicks"] == [], "probe clicked a third-party connector's card"
    assert out["result"]["found"] is False


def test_probe_ignores_brand_mentioned_in_chat_prose(chat_module, tmp_path):
    """The brand appearing in ordinary conversation must not vouch for
    someone else's permission card."""
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "children": [
            {"id": "msg", "text": "Let's use TinyAssets to plan my novel."},
            _card("Claude wants to use Gmail", cid="gmail"),
        ],
    })
    assert out["clicks"] == []
    assert out["result"]["found"] is False


def test_probe_rejects_card_whose_arguments_mention_us(chat_module, tmp_path):
    """A third-party card that merely *mentions* TinyAssets in its tool
    arguments must not be approved.

    The user-sim talks about TinyAssets constantly, so a Gmail/Drive card
    carrying "TinyAssets" in its displayed arguments is the common case,
    not a contrived one. Found by Codex review, reproduced in headless
    Chromium.
    """
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "children": [{"id": "gmail", "children": [
            {"id": "gmail-prompt", "text": "Claude wants to use Gmail"},
            {"id": "gmail-args", "text": 'search: "TinyAssets invoice"'},
            _allow_button("gmail-allow"),
        ]}],
    })
    assert out["clicks"] == []
    assert out["result"]["found"] is False


def test_probe_rejects_lookalike_connector_name(chat_module, tmp_path):
    """Substring brand matching would approve any connector whose name
    merely contains ours. Match the connector identity exactly."""
    for name in ("EvilTinyAssetsBackup", "TinyAssets Mirror", "Not TinyAssets"):
        out = _run_probe(chat_module, tmp_path, {
            "id": "body",
            "children": [_card(f"Claude wants to use {name}", cid="evil")],
        })
        assert out["clicks"] == [], f"approved lookalike connector {name!r}"
        assert out["result"]["found"] is False


# Non-breaking space, built explicitly: a reformat must never be able to
# silently turn it into an ordinary space and void the cases below.
NBSP = chr(0xA0)


def _real_card(tool, connector, *, cid="card", button=None):
    """The card shape Claude.ai actually renders, per browser capture
    output/claude_chat_failures/20260414T231328_response_timeout.txt:

        Claude wants to use / <tool> / from / <connector> / Always allow

    Each fragment is its own element, so innerText puts them on separate
    lines. The connector name is what authorises the click; the tool
    name is chosen by the connector and must never be read as identity.
    """
    return {"id": cid, "children": [
        {"id": f"{cid}-ask", "text": "Claude wants to use"},
        {"id": f"{cid}-tool", "text": tool},
        {"id": f"{cid}-from", "text": "from"},
        {"id": f"{cid}-conn", "text": connector},
        button or _allow_button(f"{cid}-allow"),
    ]}


@pytest.mark.parametrize("connector", [
    "Universe Server",
    "TinyAssets",
    "TinyAssets Server",
    "  TinyAssets  ",
    f"TinyAssets{NBSP}Server",
])
def test_probe_clicks_real_card_shape(chat_module, tmp_path, connector):
    """The captured card shape must match for every approved connector
    name, including whitespace variants."""
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "children": [_real_card("Universe Operations", connector, cid="ta")],
    })
    assert out["clicks"] == ["ta-allow"], f"missed connector {connector!r}"


def test_probe_connector_lookup_is_card_scoped_not_page_scoped(
    chat_module, tmp_path,
):
    """Claude.ai has rendered both card shapes over time, so a page can
    hold one of each. A resolved TinyAssets card in the "from" shape must
    not supply the connector identity for a live third-party card in the
    older single-line shape — reading the "from" line page-wide instead
    of card-scoped would do exactly that.
    """
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "children": [{"id": "transcript", "children": [
            # Already-resolved TinyAssets card: real shape, no live button.
            _real_card("Universe Operations", "TinyAssets", cid="old",
                       button={"id": "old-resolved", "text": "Allowed"}),
            # Live Google Drive card in the older single-line shape.
            _card("Claude wants to use Google Drive", cid="gdrive"),
        ]}],
    })
    assert out["clicks"] == [], "TinyAssets card vouched for a third party"
    assert out["result"]["found"] is False


def test_probe_inline_fallback_cannot_reach_a_tool_name(chat_module, tmp_path):
    """The no-"from"-line fallback must read only the SAME line as the
    prompt.

    If it reached onto the next line it would capture the tool name in a
    card that never names its connector — so a hostile connector could
    simply publish a tool called "TinyAssets" and approve itself. With no
    connector stated anywhere, the only safe answer is to refuse.
    """
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "children": [{"id": "evil", "children": [
            {"id": "evil-ask", "text": "Claude wants to use"},
            {"id": "evil-tool", "text": "TinyAssets"},  # tool name, not connector
            _allow_button("evil-allow"),
        ]}],
    })
    assert out["clicks"] == [], "a tool named TinyAssets approved itself"
    assert out["result"]["found"] is False


def test_probe_reads_connector_not_tool_name(chat_module, tmp_path):
    """A connector chooses its own TOOL names. A tool called
    "x from TinyAssets" must not vouch for the card — identity is the
    connector after the structural "from" line."""
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "children": [_real_card("x from TinyAssets", "EvilCorp", cid="evil")],
    })
    assert out["clicks"] == []
    assert out["result"]["found"] is False


@pytest.mark.parametrize("connector", [
    "TinyAssets!", "TinyAssets.", "TinyAssets-", "Google Drive", "Gmail",
])
def test_probe_rejects_punctuated_and_third_party_connectors(
    chat_module, tmp_path, connector,
):
    """Punctuation is part of the name, not noise to strip — a connector
    named "TinyAssets!" is not ours."""
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "children": [_real_card("Universe Operations", connector, cid="x")],
    })
    assert out["clicks"] == [], f"approved connector {connector!r}"


def test_probe_requires_always_allow_prefix_not_substring(chat_module, tmp_path):
    """Only a button whose copy *starts* with "Always allow" is a grant.
    A button that merely mentions the phrase is explanatory UI."""
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "children": [{"id": "ta", "children": [
            {"id": "ta-prompt", "text": "Claude wants to use TinyAssets"},
            _allow_button("explainer", text="Learn what Always allow means"),
        ]}],
    })
    assert out["clicks"] == []


def test_probe_clicks_qualified_always_allow_copy(chat_module, tmp_path):
    """Prefix semantics: Claude.ai qualifies the button copy, and those
    are still the grant button."""
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "children": [_card("Claude wants to use TinyAssets", cid="ta",
                           button=_allow_button("qualified-allow",
                                                text="Always allow for this chat"))],
    })
    assert out["clicks"] == ["qualified-allow"]


def test_probe_matches_button_with_nested_markup(chat_module, tmp_path):
    """Claude.ai wraps button copy in spans; innerText composition must
    still see 'Always allow'."""
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "children": [_card("Claude wants to use TinyAssets", cid="ta", button={
            "tag": "button", "id": "nested-allow",
            "children": [{"tag": "span", "text": "Always allow"}],
        })],
    })
    assert out["clicks"] == ["nested-allow"]


def test_probe_fails_closed_on_ambiguous_container(chat_module, tmp_path):
    """When the smallest ancestor holding the prompt spans two cards, the
    brand cannot be attributed to this button — reject, don't guess."""
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "children": [
            {"id": "wrapper", "children": [
                {"id": "p1", "text": "Claude wants to use TinyAssets"},
                {"id": "p2", "text": "Claude wants to use Google Drive"},
                _allow_button("ambiguous-allow"),
            ]},
        ],
    })
    assert out["clicks"] == []
    assert out["result"]["found"] is False


def test_probe_ignores_button_not_inside_a_card(chat_module, tmp_path):
    """A stray Always-allow button whose only prompt ancestor is <body>
    is not a card — fail closed."""
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "text": "Claude wants to use TinyAssets",
        "children": [_allow_button("stray-allow")],
    })
    assert out["clicks"] == []
    assert out["result"]["found"] is False


def test_probe_skips_hidden_button_and_takes_visible_card(
    chat_module, tmp_path,
):
    """Hidden Always-allow buttons are never clicked; a later visible
    TinyAssets card still is."""
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "children": [
            _card("Claude wants to use TinyAssets", cid="hidden",
                  button=_allow_button("hidden-allow", hidden=True)),
            _card("Claude wants to use TinyAssets Server", cid="live"),
        ],
    })
    assert out["clicks"] == ["live-allow"]


def test_probe_no_permission_text_is_a_clean_miss(chat_module, tmp_path):
    """No card anywhere → no click, even with an Always-allow button."""
    out = _run_probe(chat_module, tmp_path, {
        "id": "body",
        "children": [
            {"id": "msg", "text": "TinyAssets is going well."},
            _allow_button("loose-allow"),
        ],
    })
    assert out["clicks"] == []
    assert out["result"]["found"] is False
    assert out["result"]["reason"] == "no permission card text"
