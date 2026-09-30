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
