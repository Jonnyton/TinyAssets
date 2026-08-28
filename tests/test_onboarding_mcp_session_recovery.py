"""The onboarding app's MCP client must recover from a dead session.

The session id is a server-side handle that dies for ordinary reasons: the
daemon restarts on every deploy, the bearer rotates every ~5 min, an idle
session is evicted, a stream is cut mid-flight. Until 2026-08-28 only ONE of
those (HTTP 404) reset it client-side, so any other failure left the dead handle
in place and every later call reused it -- the page stayed broken until a manual
reload, surfacing the parser internal ``no JSON or SSE frame`` each time.
Founder, 2026-08-28: *"the mcp session going stale and giving the json issue is
a bug to fix"*.

These are BEHAVIOURAL tests, not string tripwires. They extract the real
transport source from ``app.html`` and drive it in Node against a scripted
``fetch``, so they assert what the client actually does -- which requests it
sends, what it retries, and what it leaves behind -- and can genuinely go red.

The second invariant they guard is the one that makes recovery safe: a call is
replayed automatically ONLY when it provably never ran. A session rejection is
pre-dispatch (the transport refused the envelope), so replaying is free. A cut
stream is NOT -- the universe may have taken the turn and be answering it -- so
those surface to the user instead of being silently double-sent.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import tinyassets.onboarding as onboarding

_APP_HTML = Path(onboarding.__file__).parent / "app.html"


def _transport_source() -> str:
    """The real MCP client source, lifted from the page it ships in."""
    html = _APP_HTML.read_text(encoding="utf-8")
    head = "// ---- MCP client"
    tail = "// ---- UI ----"
    assert head in html and tail in html, "MCP client block markers moved"
    return head + html.split(head, 1)[1].split(tail, 1)[0]


_HARNESS = """
'use strict';
// Scripted transport. Each entry is one response, consumed in order; `null`
// means "the connection failed before any response" (offline / dropped).
const PLAN = __PLAN__;
const SENT = [];
let refreshes = 0;

function token(){ return "test-bearer"; }
async function ensureFreshToken(){ }
async function refreshAccessToken(){ refreshes++; MCP.sessionId=null; return true; }

function makeResponse(spec){
  const headers = spec.headers || {};
  return {
    status: spec.status,
    ok: spec.status >= 200 && spec.status < 300,
    headers: {get(name){ return headers[String(name).toLowerCase()] || null; }},
    async text(){
      if(spec.readFails) throw new Error("stream closed");
      return spec.body === undefined ? "" : spec.body;
    },
  };
}

async function fetch(url, init){
  const frame = JSON.parse(init.body);
  SENT.push({
    method: frame.method,
    tool: (frame.params && frame.params.name) || null,
    sessionId: init.headers["mcp-session-id"] || null,
  });
  const spec = PLAN.shift();
  if(spec === undefined) throw new Error("harness ran out of scripted responses");
  if(spec === null) throw new TypeError("Failed to fetch");
  return makeResponse(spec);
}

__TRANSPORT__

// Recovery pauses are real seconds in production; here they only slow the test.
MCP._pause = function(){ return Promise.resolve(); };

(async () => {
  const out = {sent: SENT, refreshes: 0, sessionIdAfter: null};
  try{
    out.result = await (__CALL__);
    out.ok = true;
  }catch(err){
    out.ok = false;
    out.error = {
      message: String(err && err.message),
      transport: (err && err.transport) || null,
      replayable: !!(err && err.replayable),
      authRequired: !!(err && err.authRequired),
    };
  }
  out.refreshes = refreshes;
  out.sessionIdAfter = MCP.sessionId;
  out.unusedResponses = PLAN.length;
  console.log(JSON.stringify(out));
})();
"""


def _node() -> str:
    node = shutil.which("node")
    if not node:  # pragma: no cover - environment dependent
        # Fail loudly rather than skip: these are the only tests that prove the
        # client actually recovers, and the behaviour is JavaScript. A silent
        # skip would let the stale-session regression land unnoticed.
        if os.environ.get("TINYASSETS_SKIP_JS_PROBE_TESTS"):
            pytest.skip("node absent; skip explicitly requested via env")
        pytest.fail(
            "node executable not found -- the MCP session-recovery behaviour is "
            "JavaScript and cannot be verified without it. Install Node, or set "
            "TINYASSETS_SKIP_JS_PROBE_TESTS=1 to accept the coverage gap."
        )
    return node


def _drive(tmp_path, plan, call):
    """Run ``call`` against the real client with ``plan`` as the wire."""
    program = (
        _HARNESS.replace("__PLAN__", json.dumps(plan))
        .replace("__TRANSPORT__", _transport_source())
        .replace("__CALL__", call)
    )
    script = tmp_path / "session_case.js"
    script.write_text(program, encoding="utf-8")
    proc = subprocess.run(
        [_node(), str(script)], capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"harness crashed:\n{proc.stderr}"
    return json.loads(proc.stdout)


# --- wire fixtures -----------------------------------------------------------

_SID = {"mcp-session-id": "sess-1"}
_SID2 = {"mcp-session-id": "sess-2"}


def _ok(payload, headers=None):
    """A successful tools/call, framed the way the server actually frames it."""
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"structuredContent": payload},
        }
    )
    return {"status": 200, "body": "event: message\ndata: " + body + "\n\n",
            "headers": headers or {}}


def _handshake():
    """initialize + notifications/initialized, the pair ensureInit sends."""
    return [
        {"status": 200, "headers": _SID,
         "body": json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}})},
        {"status": 202, "body": "", "headers": _SID},
    ]


def _session_gone():
    """Exactly what the MCP transport sends for an unknown/expired session."""
    return {
        "status": 404,
        "headers": _SID,
        "body": json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "server-error",
                "error": {"code": -32600, "message": "Session not found"},
            }
        ),
    }


# --- the regression the founder reported -------------------------------------


def test_a_dead_session_is_never_carried_forward(tmp_path):
    """The bug: one failure poisoned the page until a manual reload.

    A 5xx used to throw while LEAVING ``sessionId`` set, so every later call
    reused the handle the server had already forgotten and failed identically.
    """
    out = _drive(
        tmp_path,
        _handshake() + [{"status": 500, "body": "upstream boom"}],
        'MCP.converse("hello")',
    )
    assert out["ok"] is False
    assert out["sessionIdAfter"] is None, (
        "a failed call left the dead session id in place -- the next call will "
        "reuse it and fail the same way, which is the reload-to-fix bug"
    )


def test_the_user_never_sees_the_parser_internal(tmp_path):
    """``no JSON or SSE frame`` is a parser detail, not something to show."""
    out = _drive(
        tmp_path,
        # A 200 whose SSE stream was cut after the event line, before its data
        # line -- what a mid-flight disconnect looks like from the client.
        _handshake() + [{"status": 200, "body": "event: message\n"}],
        'MCP.converse("hello")',
    )
    assert out["ok"] is False
    assert "no JSON or SSE frame" not in out["error"]["message"]
    assert out["error"]["transport"] == "stream_truncated"


def test_expired_session_is_recovered_and_the_turn_still_runs(tmp_path):
    """A session rejection is pre-dispatch, so the turn is replayed for real."""
    out = _drive(
        tmp_path,
        _handshake()
        + [_session_gone()]
        + _handshake()          # the client re-initializes...
        + [_ok({"reply": "hi there"}, _SID2)],   # ...then runs the turn
        'MCP.converse("hello")',
    )
    assert out["ok"] is True, out.get("error")
    assert out["result"] == {"reply": "hi there"}
    methods = [s["method"] for s in out["sent"]]
    assert methods.count("initialize") == 2, methods
    assert methods.count("tools/call") == 2, methods
    # The replay must carry the NEW session, never the handle that was rejected.
    calls = [s for s in out["sent"] if s["method"] == "tools/call"]
    assert calls[0]["sessionId"] == "sess-1"
    assert calls[1]["sessionId"] == "sess-1"  # re-issued by the second handshake
    assert out["sessionIdAfter"] == "sess-2"


def test_session_recovery_does_not_loop_forever(tmp_path):
    """Bounded at one attempt: a server stuck on 404 must surface, not spin."""
    out = _drive(
        tmp_path,
        _handshake() + [_session_gone()] + _handshake() + [_session_gone()],
        'MCP.converse("hello")',
    )
    assert out["ok"] is False
    assert [s["method"] for s in out["sent"]].count("tools/call") == 2


# --- the invariant that makes recovery safe ----------------------------------


def test_a_cut_stream_never_silently_resends_a_turn(tmp_path):
    """The universe may already be answering -- replaying would double-send."""
    out = _drive(
        tmp_path,
        _handshake() + [{"status": 200, "body": "event: message\n"}],
        'MCP.converse("hello")',
    )
    assert out["ok"] is False
    sent = [s for s in out["sent"] if s["tool"] == "converse"]
    assert len(sent) == 1, "a state-changing turn was replayed after a cut stream"
    assert out["error"]["replayable"] is False


def test_a_gateway_blip_never_silently_resends_a_turn(tmp_path):
    """A 502 can mean 'never arrived' OR 'died after accepting'. Ask the user."""
    out = _drive(
        tmp_path,
        _handshake() + [{"status": 503, "body": "<html>bad gateway</html>"}],
        'MCP.converse("hello")',
    )
    assert out["ok"] is False
    assert len([s for s in out["sent"] if s["tool"] == "converse"]) == 1
    assert out["error"]["transport"] == "unavailable"
    assert out["sessionIdAfter"] is None


def test_an_idempotent_read_does_retry_a_cut_stream(tmp_path):
    """get_status is safe to run twice, so the user never sees the blip."""
    out = _drive(
        tmp_path,
        _handshake()
        + [{"status": 200, "body": "event: message\n"}]
        + _handshake()
        + [_ok({"active_host": "codex"}, _SID2)],
        "MCP.getStatus()",
    )
    assert out["ok"] is True, out.get("error")
    assert out["result"] == {"active_host": "codex"}


# --- narrower faults must not be mistaken for a dead session -----------------


def test_a_protocol_version_400_is_not_treated_as_a_dead_session(tmp_path):
    """Re-initializing on it would loop; it is a different, fatal fault."""
    out = _drive(
        tmp_path,
        _handshake()
        + [
            {
                "status": 400,
                "body": json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "server-error",
                        "error": {
                            "code": -32600,
                            "message": "Bad Request: Unsupported protocol version: 1",
                        },
                    }
                ),
            }
        ],
        'MCP.converse("hello")',
    )
    assert out["ok"] is False
    assert [s["method"] for s in out["sent"]].count("initialize") == 1
    assert out["error"]["transport"] == "http_error"


def test_a_400_naming_the_session_is_recovered(tmp_path):
    """The transport also rejects a missing/invalid session with 400."""
    out = _drive(
        tmp_path,
        _handshake()
        + [
            {
                "status": 400,
                "body": json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "server-error",
                        "error": {
                            "code": -32600,
                            "message": "Bad Request: Missing session ID",
                        },
                    }
                ),
            }
        ]
        + _handshake()
        + [_ok({"reply": "recovered"}, _SID2)],
        'MCP.converse("hello")',
    )
    assert out["ok"] is True, out.get("error")
    assert out["result"] == {"reply": "recovered"}


def test_an_application_error_leaves_a_healthy_session_alone(tmp_path):
    """A JSON-RPC error is a WORKING session reporting a fault. Don't churn it."""
    out = _drive(
        tmp_path,
        _handshake()
        + [
            {
                "status": 200,
                "headers": _SID,
                "body": "data: "
                + json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "error": {"code": -32602, "message": "Invalid params"},
                    }
                ),
            }
        ],
        'MCP.converse("hello")',
    )
    assert out["ok"] is False
    assert out["error"]["message"] == "Invalid params"
    assert out["sessionIdAfter"] == "sess-1", "a healthy session was discarded"
    assert [s["method"] for s in out["sent"]].count("tools/call") == 1


def test_an_error_response_cannot_re_arm_the_failed_session(tmp_path):
    """Error bodies echo a session header; adopting it re-arms the dead handle."""
    out = _drive(
        tmp_path,
        _handshake() + [{"status": 500, "body": "boom", "headers": _SID2}],
        "MCP.getStatus()",
    )
    assert out["ok"] is False
    assert out["sessionIdAfter"] is None


# --- recovery budgets are per-kind, not one shared flag ----------------------


def test_a_gateway_retry_does_not_spend_the_session_retry(tmp_path):
    """One boolean used to serve both, so the second fault could never recover."""
    out = _drive(
        tmp_path,
        _handshake()
        + [{"status": 502, "body": "<html>gw</html>"}]   # gateway budget
        + _handshake()
        + [_session_gone()]                              # session budget
        + _handshake()
        + [_ok({"active_host": "codex"}, _SID2)],
        "MCP.getStatus()",
    )
    assert out["ok"] is True, out.get("error")
    assert out["result"] == {"active_host": "codex"}


def test_a_dropped_connection_is_reported_as_offline(tmp_path):
    """fetch rejecting must not surface as a raw TypeError."""
    out = _drive(
        tmp_path, _handshake() + [None], 'MCP.converse("hello")',
    )
    assert out["ok"] is False
    assert out["error"]["transport"] == "offline"
    assert "Failed to fetch" not in out["error"]["message"]
    assert out["sessionIdAfter"] is None


# --- the UI must offer the retry, not just report the failure ----------------


def test_a_failed_turn_offers_to_send_again():
    html = _APP_HTML.read_text(encoding="utf-8")
    # The failure path hands back a working button rather than a dead sentence.
    assert "function offerResend(" in html
    assert "Send it again" in html
    # ...and a resend reuses the bubble already on screen instead of drawing the
    # same message twice, which would read as two sends.
    assert "sendTurn(message, display, {echoed:true})" in html
