"""Client-side MCP session-recovery invariants in the onboarding app.

The inline browser MCP client (app.html) must survive the ~5-min access-token
refresh — which nulls the session because it was bound to the now-rotated bearer
(refreshAccessToken sets MCP.sessionId=null) — without failing the next turn with
"Invalid request parameters" (live desktop bug 2026-08-22). There is no JS test
harness in this repo, so these are STRUCTURAL tripwires guarding the specific
recovery guards; the behavioral gate is the live rendered-turn check after deploy
(ui-test): a turn must survive a refresh cycle with no reload.
"""

from __future__ import annotations

from pathlib import Path

import tinyassets.onboarding as onboarding

_APP_HTML = Path(onboarding.__file__).parent / "app.html"


def _html() -> str:
    return _APP_HTML.read_text(encoding="utf-8")


def test_proactive_reinit_after_refresh_before_non_handshake_call():
    # After ensureFreshToken() nulls the session, re-establish it before any
    # non-handshake call (the primary fix for the observed bug).
    assert (
        "this.sessionId===null && !isHandshake) await this.ensureInit()" in _html()
    )


def test_session_recovery_is_scoped_to_http_404_not_rpc_errors():
    html = _html()
    # Reactive recovery fires ONLY on HTTP 404 with a live session id (MCP
    # transport's stale-session signal)...
    assert (
        "resp.status===404 && this.sessionId && !_retried && !isHandshake" in html
    )
    # ...and an ordinary JSON-RPC error is thrown, never retried — retrying it
    # would replay state-changing calls and discard a healthy session.
    assert 'if(rpc.error){ const e=new Error(rpc.error.message||"MCP error")' in html


def test_initialize_handshake_is_serialized():
    # Two concurrent post-refresh callers must share ONE initialize, or the
    # second's session orphans the first's.
    html = _html()
    assert "_initing:null" in html
    assert "if(this._initing){ await this._initing; return; }" in html
