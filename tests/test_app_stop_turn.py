"""The app's Stop: interrupt the running turn, then send everything queued as ONE turn.

Founder, 2026-09-30: "it should work just like it works in claude code where i
can press escape to interrupt and send all pending messages".

Executes the page's own ``sendTurn``, ``queueTurn``, ``flushSendQueue``,
``interruptTurn`` and the batch helpers under node, in the same DOM shim as
``tests/test_app_working_indicator.py``: the order and number of ``converse``
calls the page makes is the thing under test.
"""
from __future__ import annotations

import pytest

from tests.test_app_working_indicator import _NODE, _run, html  # noqa: F401
from tests.test_onboarding_app import _js_function

pytestmark = pytest.mark.skipif(
    _NODE is None, reason="node is required to execute the page's own source")

_STOP = r"""
setQueueOwner("p-1"); setQueueScope("u-1");
const posts=[];
globalThis.authHeaders=()=>({});
globalThis.refreshAccessToken=async()=>false;
globalThis.fetch=async(url,init)=>{
  posts.push({url, body:JSON.parse(init.body)});
  return {ok:true,status:200,json:async()=>({interrupted:1,universe_id:"u-1"})};
};
const first=sendTurn("start the long job");
await settle();
sendTurn("one"); sendTurn("two"); sendTurn("three");
const queued=bubbles().filter(b=>b.queued).length;
if(SCENARIO.stop) await interruptTurn();
const stoppingLine=indicator().line;
gates[0].resolve(SCENARIO.stop
  ? {error:"Interrupted — you stopped this turn.", interrupted:true,
     turn_failure:{version:1,kind:"turn_failed",code:"interrupted",effects:"none"},
     failure_notice:"Interrupted — you stopped this turn.", history_saved:true}
  : {reply:"Done with the long job."});
await first; await settle();
console.log(JSON.stringify({posts, queued, stoppingLine, sent:converseCalls,
  stillQueued:bubbles().filter(b=>b.queued).length, texts:bubbles().map(b=>b.text)}));
"""


def _run_stop(tmp_path, page, scenario):
    import tests.test_app_working_indicator as harness

    original = harness._program

    def with_interrupt(html_, scenario_, body):
        program = original(html_, scenario_, body)
        head, sep, tail = program.partition("\n(async()=>{\n")
        return head + "\n" + _js_function(html_, "interruptTurn") + sep + tail

    harness._program = with_interrupt
    try:
        return _run(tmp_path, page, scenario, _STOP)
    finally:
        harness._program = original


def test_stop_sends_every_queued_line_as_one_turn_in_order(tmp_path, html):  # noqa: F811
    out = _run_stop(tmp_path, html, {"stop": True})
    assert out["queued"] == 3
    assert out["posts"] == [{"url": "/app/turn/interrupt", "body": {"universe_id": "u-1"}}]
    assert "then sending the 3 waiting messages together" in out["stoppingLine"]
    # Exactly two turns: the interrupted one, then ONE carrying all three lines.
    assert out["sent"] == ["start the long job", "one\n\ntwo\n\nthree"], out["sent"]
    assert out["stillQueued"] == 0, "a line still claims to be waiting"
    assert any(text.startswith("Interrupted") for text in out["texts"])


def test_without_a_stop_the_queue_still_goes_one_line_at_a_time(tmp_path, html):  # noqa: F811
    """The positive control: batching is what the stop does, not a new default."""
    out = _run_stop(tmp_path, html, {"stop": False})
    assert out["posts"] == []
    assert out["sent"] == ["start the long job", "one"], out["sent"]


def test_stop_is_wired_to_the_button_and_to_escape(html):  # noqa: F811
    assert 'id="btn-stop"' in html
    assert '$("btn-stop").addEventListener("click",()=>interruptTurn());' in html
    assert 'if(e.key!=="Escape"||e.defaultPrevented||e.isComposing) return;' in html
    # The phone layout gives Stop the send button's cell, so it is always a
    # visible tap target there too.
    assert ".composer .btn--stop{grid-column:4;grid-row:2}" in html


_LATE_STOP = r"""
setQueueOwner("p-1"); setQueueScope("u-1");
const posts=[];
globalThis.authHeaders=()=>({});
globalThis.refreshAccessToken=async()=>false;
globalThis.fetch=(url,init)=>new Promise(resolve=>posts.push({resolve}));
const a=sendTurn("A");
await settle();
sendTurn("B"); sendTurn("C");
const stopA=interruptTurn();               // A's Stop request is still on the wire...
await settle();
gates[0].resolve({error:"Interrupted — you stopped this turn.", interrupted:true,
  turn_failure:{version:1,kind:"turn_failed",code:"interrupted",effects:"none"},
  failure_notice:"Interrupted — you stopped this turn.", history_saved:true});
await a; await settle();
const whilePending=converseCalls.slice();  // ...so nothing queued may start yet.
posts[0].resolve({ok:false,status:500,json:async()=>({})});   // late failure for A
await stopA; await settle();
const afterLate=converseCalls.slice(), lateLine=indicator().line;
sendTurn("D"); sendTurn("E");
const stopB=interruptTurn();
await settle();
posts[1].resolve({ok:true,status:200,json:async()=>({interrupted:1,universe_id:"u-1"})});
await stopB; await settle();
gates[1].resolve({reply:"B and C answered."});
await settle(); await settle();
console.log(JSON.stringify({whilePending, afterLate, lateLine, sent:converseCalls}));
"""


def test_a_late_stop_answer_never_leaks_into_the_next_turn(tmp_path, html):  # noqa: F811
    """astra round 1: A's late Stop response erased B's batching state."""
    import tests.test_app_working_indicator as harness

    original = harness._program

    def with_interrupt(html_, scenario_, body):
        program = original(html_, scenario_, body)
        head, sep, tail = program.partition("\n(async()=>{\n")
        return head + "\n" + _js_function(html_, "interruptTurn") + sep + tail

    harness._program = with_interrupt
    try:
        out = _run(tmp_path, html, {}, _LATE_STOP)
    finally:
        harness._program = original
    assert out["whilePending"] == ["A"], (
        "the queue went out while A's Stop request was still on the wire")
    assert out["afterLate"] == ["A", "B\n\nC"]
    # A's answer arrived after A ended: it describes nothing on screen now.
    # (Transient here -- B's send repaints the line; the account case below is
    # where an unfenced answer would stay on screen.)
    assert "Could not stop" not in out["lateLine"], out["lateLine"]
    assert out["sent"] == ["A", "B\n\nC", "D\n\nE"], out["sent"]


_STOP_ACROSS_ACCOUNTS = r"""
setQueueOwner("p-1"); setQueueScope("u-1");
const posts=[];
globalThis.authHeaders=()=>({});
globalThis.refreshAccessToken=async()=>false;
globalThis.fetch=(url,init)=>new Promise(resolve=>posts.push({resolve}));
const a=sendTurn("A private line");
await settle();
sendTurn("B"); sendTurn("C");
const stopA=interruptTurn();
await settle();
// The account changes while that Stop request is still on the wire.
MCP._loginEpoch++; clearComposerState(); setQueueOwner("p-2");
posts[0].resolve({ok:false,status:500,json:async()=>({})});
await stopA; await settle();
const line=indicator().line;
console.log(JSON.stringify({line,
  flags:{interruptRequested, flushAfterInterrupt}}));
"""


def test_a_stop_answer_for_another_account_is_never_painted(tmp_path, html):  # noqa: F811
    import tests.test_app_working_indicator as harness

    original = harness._program

    def with_interrupt(html_, scenario_, body):
        program = original(html_, scenario_, body)
        head, sep, tail = program.partition("\n(async()=>{\n")
        return head + "\n" + _js_function(html_, "interruptTurn") + sep + tail

    harness._program = with_interrupt
    try:
        out = _run(tmp_path, html, {}, _STOP_ACROSS_ACCOUNTS)
    finally:
        harness._program = original
    assert "Could not stop" not in out["line"], (
        "the previous account's Stop answer was painted on the next account's screen")
    assert out["flags"] == {"interruptRequested": False, "flushAfterInterrupt": False}
