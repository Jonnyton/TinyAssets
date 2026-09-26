"""The working indicator is the UNIVERSE's state, and a queued line is ordered last.

Live, 2026-09-26. The founder clicked Accept on a rail card while an earlier turn
was still running. The turn journal shows turn ``d1a01eec`` running 20:18:23Z to
about 20:22Z. Two things were wrong on screen for those four minutes:

1. No working indicator at all in the founder's view, so it read as if nothing
   had happened. The indicator was a fact about the PAGE -- ``sendTurn`` set a
   0.78rem grey line under the composer and its ``finally`` cleared it, and
   nothing else ever set it. A turn started by answering a request, by a queued
   line, from another window or device, or one still running across a reload
   showed nothing.
2. The queued "Approved: ..." bubble was appended at click time, so the earlier
   turn's reply -- composed BEFORE that click arrived -- landed underneath it.
   The thread read as though the agent had ignored the approval.

Everything here EXECUTES the page's own ``appendMessage``, ``sendTurn``,
``queueTurn``, ``flushSendQueue``, ``pollStatus``, ``loadHistory``,
``readServerTurn`` and ``renderWorking`` under node. The DOM shim is a real tree
(``parentNode``, ``insertBefore``, a ``remove`` that detaches) because thread
ORDER is the thing under test: a shim whose appendChild is the only insertion
would pass whatever the page did.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

from tests.test_onboarding_app import _js_function
from tinyassets import onboarding

_NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    _NODE is None, reason="node is required to execute the page's own source")

# Declarations the extracted functions close over. Optional ones are matched
# with `re.search` and skipped when absent, so a tree without the fix is RED on
# an assertion rather than on a missing declaration.
_DECLS = (
    r"const INFLIGHT_KEY=[^\n]*;", r"let turnStartedAt=[^\n]*;", r"let activeTurn=[^\n]*;",
    r"let liveInflight=[^\n]*;",
    r"let historyLoaded = [^\n]*;", r"let inflightRestored = [^\n]*;",
    r"const sendQueue=[^\n]*;", r"let sendQueueHeld=[^\n]*;", r"const SEND_QUEUE_MAX=[^\n]*;",
    r"const QUEUE_KEY=[^\n]*;", r"let queueRestored=[^\n]*;", r"const QUEUE_MAX_AGE_MS=[^\n]*;",
    r"let queueScope=[^\n]*;", r"let queueOwner=[^\n]*;", r"let queuePersisted=[^\n]*;",
    r"let retainedItems=[^\n]*;", r"let modelChoiceForNextTurn=[^\n]*;",
    r"const renderedConsumerTurns=[^\n]*;", r"const renderedConsumerFounders=[^\n]*;",
    r"let Uploads=[^\n]*;", r"let uploadsRestored=[^\n]*;",
    # `hasMessages` shares its declaration line with the two timer handles, which
    # the shim owns (it records timers instead of arming them), so it is declared
    # there rather than lifted from the page.
    # Introduced by the fix.
    r"const TURN_WORKING_STATES=[^\n]*;", r"let serverTurn=[^\n]*;",
    r"const STATUS_IDLE_MS=[^\n]*;", r"let statusBeatMs=[^\n]*;",
)
_FUNCS = (
    "formatMessageTimestamp", "appendMessage", "setStatusLine",
    "turnInputMethod", "rememberInflight", "forgetInflight", "readInflight", "renderConverse",
    "sameInflight", "forgetInflightIf",
    "copyModelChoice", "captureTurnOptions", "sendConversationRequest",
    "executionLabel", "answerExecutionDetail", "servedFailureError", "appendFailureNotice",
    "offerResend", "noteHeldQueue", "offerSavedConversationCheck",
    "sendTurn", "loadHistory", "restoreInflight", "pollStatus",
    "messageBody", "expansionHandle", "offerFullMessage", "loadFullMessage",
    "setQueueScope", "setQueueOwner", "ownsSavedRow",
    "flushSendQueue", "queueTurn", "saveQueue", "readSavedQueue", "stillSaved",
    "forgetSavedItem", "savedItem", "sameSavedLine", "restoreQueue", "claimedElsewhere",
    "offerSavedLine", "clearComposerState", "clearThread",
)
# The fix's own functions. Optional for the same reason the declarations are: a
# tree without them must fail on what the screen shows, not on an extraction.
_NEW_FUNCS = ("isQueuedBubble", "firstQueuedBubble", "markQueued", "unmarkQueued",
              "readServerTurn", "serverTurnLive", "workingSince", "workingElapsed",
              "renderWorking", "pulseHeartbeat")

# A real tree. `insertBefore` and a detaching `remove` are the point: thread
# order is what the ordering half of this bug is about.
_SHIM = r"""
const store={};
const localStorage={ getItem:k=>(k in store?store[k]:null),
  setItem:(k,v)=>{store[k]=String(v);}, removeItem:k=>{delete store[k];} };
class El{
  constructor(tag){
    this.tagName=String(tag).toUpperCase(); this.children=[]; this.parentNode=null;
    this.className=""; this.textContent=""; this.value=""; this.style={};
    this.hidden=false; this.disabled=false; this.listeners={};
    this.scrollTop=0; this.scrollHeight=0;
  }
  appendChild(c){ this.detach(c); this.children.push(c); c.parentNode=this; return c; }
  insertBefore(c,ref){
    this.detach(c);
    const at=this.children.indexOf(ref);
    if(at<0) throw new Error("insertBefore reference is not a child");
    this.children.splice(at,0,c); c.parentNode=this; return c;
  }
  detach(c){ if(c&&c.parentNode){ c.parentNode.children=c.parentNode.children.filter(n=>n!==c);
    c.parentNode=null; } }
  remove(){ this.removed=true; if(this.parentNode) this.parentNode.detach(this); }
  setAttribute(){} addEventListener(n,f){ this.listeners[n]=f; }
  click(){ return (this.listeners.click||(()=>{}))(); }
}
const document={ createElement:t=>new El(t),
  createTextNode:t=>{ const e=new El("#text"); e.textContent=t; return e; },
  activeElement:null };
const els={};
for(const id of ["thread","thread-empty","status-line","composer-input","btn-send",
                 "working-banner","working-text","working-note","dot","universe-name"])
  els[id]=new El("div");
els["working-banner"].hidden=true;            // as shipped in the markup
const $=id=>els[id];

// A clock the scenario can move, so "this page has not refreshed the row in
// three working-rate polls" is testable without sleeping through it.
const REAL_NOW=Date.now.bind(Date);
let clockSkew=0;
Date.now=()=>REAL_NOW()+clockSkew;

const Voice={isActive:()=>false,conversationSettled:()=>{},turnStarted:()=>{},stop:()=>{}};
const ModelPicker={observe(){},reset(){},snapshot:null};
function autoGrow(el){ if(el&&el.style) el.style.height="auto"; }
function sessionExpired(){ events.push("session-expired"); }
function enterSignedOut(){ events.push("signed-out"); }
function showConnect(){ events.push("connect"); }
function openConnectRequest(){ events.push("connect-request"); }
async function healServing(){}
function restoreUploadRecords(){}
function clearAccountScopedState(){}
const events=[];
const token=()=>"t";
const SCENARIO=__SCENARIO__;

// Timers: recorded, never armed. An armed interval would keep node alive and
// the scenario's own assertions are what advance time here.
const timers={set:[],cleared:[]};
let timerSeq=0;
function setInterval(fn,ms){ timers.set.push(ms); return ++timerSeq; }
function clearInterval(h){ timers.cleared.push(h); }
// The heartbeat is running, as it is on a live page.
let hasMessages=false, statusTimer=7, workingTimer=null;

// Pre-fix stand-ins, so a tree WITHOUT the fix fails on what the screen shows
// rather than on a ReferenceError. The page's own definitions are appended after
// this shim and a later function declaration is the one that runs, so on a tree
// WITH the fix none of these is ever called.
function readServerTurn(){}
function serverTurnLive(){ return false; }
function renderWorking(){}
function pulseHeartbeat(){}
function markQueued(el){ return el; }
function unmarkQueued(){}
function firstQueuedBubble(){ return null; }

const converseCalls=[], statusPolls=[];
const gates=[];
const MCP={ _loginEpoch:0, invalidateSession(){},
  converse:async(m,inputMethod,modelChoice,consumerRequest)=>{
    converseCalls.push(m);
    return await new Promise((resolve,reject)=>gates.push({resolve,reject,m}));
  },
  callTool:async()=>({}),
  async getStatus(){
    statusPolls.push(1);
    if(SCENARIO.statusError){ const e=new Error("status down"); e.transport=true; throw e; }
    const s={active_host:"h",universe_id:SCENARIO.universe||"u-1",universe_name:"Home"};
    if(Object.prototype.hasOwnProperty.call(SCENARIO,"activeTurn"))
      s.active_turn=SCENARIO.activeTurn;
    return s;
  },
  async getConversation(){
    const r={universe_id:SCENARIO.universe||"u-1",
             recent_conversation:{turns:SCENARIO.history||[]}};
    if(Object.prototype.hasOwnProperty.call(SCENARIO,"historyActiveTurn"))
      r.active_turn=SCENARIO.historyActiveTurn;
    return r;
  },
};
const settle=()=>new Promise(r=>setTimeout(r,20));
function bubbles(){
  // Thread order, top to bottom, with what each bubble says about itself.
  return els.thread.children.map(n=>({
    cls:String(n.className||""),
    queued:String(n.className||"").split(" ").indexOf("msg--queued")>=0,
    text:(n.children.filter(c=>c.className==="msg-body").map(c=>c.textContent)[0])||"",
    note:(n.children.filter(c=>c.className==="msg-queued-note")
          .map(c=>c.textContent).join("")),
  }));
}
function banner(){
  return {hidden:els["working-banner"].hidden,
          text:els["working-text"].textContent,
          note:els["working-note"].textContent};
}
"""

_TAIL = "\n})().catch(e=>{ console.error(e&&e.stack||e); process.exit(1); });"


def _program(html: str, scenario: dict, body: str) -> str:
    decls = [found.group(0) for found in
             (re.search(pat, html) for pat in _DECLS) if found]
    funcs = [_js_function(html, name) for name in _FUNCS]
    for name in _NEW_FUNCS:
        if re.search(r"function\s+" + name + r"\s*\(", html):
            funcs.append(_js_function(html, name))
    return (_SHIM.replace("__SCENARIO__", json.dumps(scenario)) +
            "\n".join(decls) + "\n" + "\n".join(funcs) + "\n(async()=>{\n" + body + _TAIL)


def _run(tmp_path, html: str, scenario: dict, body: str) -> dict:
    script = tmp_path / "working_indicator_case.js"
    script.write_text(_program(html, scenario, body), encoding="utf-8")
    proc = subprocess.run([_NODE, str(script)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60, env=dict(os.environ))
    assert proc.returncode == 0, f"working-indicator harness crashed:\n{proc.stderr}"
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def html() -> str:
    page, _csp = onboarding.render_app_html()
    return page


# ---------------------------------------------------------------------------
# The indicator reflects the SERVER's turn state, whatever started the turn.
# ---------------------------------------------------------------------------

_SERVER_TURN = r"""
setQueueOwner("p-1");
const before=banner();
await pollStatus();
const after=banner();
// `typeof` so a tree without the fix reports a null beat and fails on the
// assertion, instead of crashing on an undeclared identifier.
console.log(JSON.stringify({before, after,
  beat:(typeof statusBeatMs==="undefined"?null:statusBeatMs),
  armed:timers.set, polls:statusPolls.length}));
"""


def test_a_turn_this_page_never_sent_still_shows_the_indicator(tmp_path, html):
    """The founder's own case: this tab sent nothing, the universe is working."""
    out = _run(tmp_path, html, {
        "activeTurn": {"turn_id": "d1a01eec", "state": "inference_started",
                       "started_at": "2026-09-26T20:18:23.000000Z",
                       "age_s": 214.0, "stale": False},
    }, _SERVER_TURN)
    assert out["before"]["hidden"] is True, "the indicator must start out of the way"
    assert out["after"]["hidden"] is False, (
        "a turn the server reports running showed nothing, which is the bug: the "
        "founder's view was blank for four minutes")
    assert "thinking" in out["after"]["text"]
    # How long, and that it did not come from this tab, are both said.
    assert "for 3m 34s" == out["after"]["note"].split(" · ")[0]
    assert "another window" in out["after"]["note"]
    # ...and the page asks again sooner than the 30s host beat, so the indicator
    # clears promptly for a tab that cannot see the turn end locally.
    assert out["beat"] == 10000 and 10000 in out["armed"]


def test_an_idle_server_and_a_stale_row_are_both_left_unpainted(tmp_path, html):
    """Idle is idle; a row older than the served cap is a killed process's leftover."""
    idle = _run(tmp_path, html, {"activeTurn": None}, _SERVER_TURN)
    assert idle["after"]["hidden"] is True and idle["beat"] == 30000
    # Same state, same shape -- only `stale` differs, so a pass here cannot come
    # from the state list or from the row being ignored wholesale.
    stale = _run(tmp_path, html, {
        "activeTurn": {"turn_id": "t-old", "state": "inference_started",
                       "age_s": 90000.0, "stale": True}}, _SERVER_TURN)
    assert stale["after"]["hidden"] is True, (
        "a stale journal row was painted as live work; that is a tab thinking forever")
    fresh = _run(tmp_path, html, {
        "activeTurn": {"turn_id": "t-new", "state": "inference_started",
                       "age_s": 90000.0, "stale": False}}, _SERVER_TURN)
    assert fresh["after"]["hidden"] is False, (
        "only `stale` separates these two scenarios, so this one must still paint")


def test_a_held_or_unreadable_row_is_not_activity(tmp_path, html):
    """A stopped, finished or unreadable turn is not work in progress."""
    for row in ({"turn_id": "t", "state": "held_refusal", "age_s": 3.0, "stale": False},
                {"state": "unreadable", "reason": "DatabaseError"},
                {"turn_id": "t", "state": "completed", "age_s": 1.0, "stale": False}):
        out = _run(tmp_path, html, {"activeTurn": row}, _SERVER_TURN)
        assert out["after"]["hidden"] is True, f"{row['state']} was painted as working"
    # The positive control for the same loop: only `state` differs, so a page
    # that simply cannot paint at all does not pass this test by default.
    live = _run(tmp_path, html, {
        "activeTurn": {"turn_id": "t", "state": "tools_pending",
                       "age_s": 3.0, "stale": False}}, _SERVER_TURN)
    assert live["after"]["hidden"] is False, (
        "a turn waiting on its own tool calls is the universe working")


_RELOAD = r"""
setQueueOwner("p-1");
await loadHistory();
console.log(JSON.stringify({banner:banner(), bubbles:bubbles()}));
"""


def test_a_reload_mid_turn_shows_the_indicator_history_cannot(tmp_path, html):
    """The exchange is stored on completion, so history alone shows nothing."""
    out = _run(tmp_path, html, {
        "history": [{"speaker": "founder", "text": "start the run", "ts": 1000},
                    {"speaker": "universe", "text": "started", "ts": 1001}],
        "historyActiveTurn": {"turn_id": "d1a01eec", "state": "tools_pending",
                              "age_s": 61.0, "stale": False},
    }, _RELOAD)
    assert [b["text"] for b in out["bubbles"]] == ["start the run", "started"]
    assert out["banner"]["hidden"] is False, (
        "a reload during a live turn left the page looking idle")
    assert "for 1m 1s" in out["banner"]["note"]


_STALLED_POLL = r"""
setQueueOwner("p-1");
await pollStatus();                       // the row is observed here
const observed=banner();
SCENARIO.statusError=true;
await pollStatus();                       // ...and the connection drops
const afterFailure=banner();
clockSkew=31000;                          // three working-rate polls later
renderWorking();
const abandoned=banner();
console.log(JSON.stringify({observed, afterFailure, abandoned}));
"""


def test_a_failed_poll_neither_clears_nor_outlives_the_claim(tmp_path, html):
    """A failed poll is not evidence the turn ended -- and not licence to claim it forever."""
    out = _run(tmp_path, html, {
        "activeTurn": {"turn_id": "t-1", "state": "native_started",
                       "age_s": 20.0, "stale": False}}, _STALLED_POLL)
    assert out["observed"]["hidden"] is False
    assert out["afterFailure"]["hidden"] is False, (
        "one failed status poll erased an indicator for a turn that is still running")
    assert out["abandoned"]["hidden"] is True, (
        "a row this page can no longer refresh must stop being claimed, or a dead "
        "connection leaves the tab thinking forever")


_LOCAL_ONLY = r"""
setQueueOwner("p-1");
const turn=sendTurn("what is the status of the run?");
await settle();
const during=banner();
gates[0].resolve({reply:"Running."});
await turn; await settle();
const after=banner();
console.log(JSON.stringify({during, after, served:!!SCENARIO.activeTurn}));
"""


def test_this_pages_own_turn_paints_without_waiting_for_a_poll(tmp_path, html):
    """No `active_turn` in the payload at all: an older daemon, or simply no poll yet."""
    out = _run(tmp_path, html, {}, _LOCAL_ONLY)
    assert out["during"]["hidden"] is False, "the page's own live turn must show at once"
    assert out["after"]["hidden"] is True, "the indicator outlived the turn it was for"


_ACCOUNT_BOUNDARY = r"""
setQueueOwner("p-1");
await pollStatus();
const signedIn=banner();
clearComposerState();
const signedOut=banner();
console.log(JSON.stringify({signedIn, signedOut}));
"""


def test_the_previous_accounts_turn_is_not_reported_to_the_next(tmp_path, html):
    out = _run(tmp_path, html, {
        "activeTurn": {"turn_id": "t-1", "state": "inference_started",
                       "age_s": 10.0, "stale": False}}, _ACCOUNT_BOUNDARY)
    assert out["signedIn"]["hidden"] is False
    assert out["signedOut"]["hidden"] is True, (
        "the indicator is screen state: it belongs to the account that is on screen")


# ---------------------------------------------------------------------------
# A queued answer is ordered where the agent will actually read it.
# ---------------------------------------------------------------------------

_QUEUED_ORDER = r"""
setQueueOwner("p-1");
const first=sendTurn("summarise the run so far");
await settle();
// The founder clicks Accept on a rail card while that turn is still running.
// answerRail relays the click through the SAME send path as any message.
sendTurn('Approved: "grant read access to the notes wiki"', undefined,
  {relay:true, keepComposer:true, inputMethod:"app_action"});
const whileQueued=bubbles();
const queuedBanner=banner();
// ...and only now does the earlier turn's reply come back.
gates[0].resolve({reply:"Here is the summary of the run so far."});
await first; await settle();
const afterReply=bubbles();
gates[1].resolve({reply:"Access granted; starting."});
await settle();
console.log(JSON.stringify({whileQueued, queuedBanner, afterReply, final:bubbles(),
  sent:converseCalls}));
"""


def test_a_queued_answer_renders_after_the_reply_it_waited_behind(tmp_path, html):
    out = _run(tmp_path, html, {}, _QUEUED_ORDER)
    # While it waits: the founder's line is on screen (from their side it is
    # sent) and marked as not yet seen.
    assert [b["text"] for b in out["whileQueued"]] == [
        "summarise the run so far",
        'Approved: "grant read access to the notes wiki"']
    queued = out["whileQueued"][1]
    assert queued["queued"] is True and "Queued" in queued["note"], (
        "a line the universe has not seen yet must not read as delivered")
    assert out["whileQueued"][0]["queued"] is False
    assert out["queuedBanner"]["hidden"] is False

    # THE BUG: the reply was composed before the click arrived, so it belongs
    # ABOVE the queued line. It used to be appended below it, which read as the
    # agent ignoring the approval.
    order = [b["text"] for b in out["afterReply"]]
    assert order == [
        "summarise the run so far",
        "Here is the summary of the run so far.",
        'Approved: "grant read access to the notes wiki"'], (
        "the queued answer must sit BELOW the reply that was written before it")
    # Its turn has started, so the queued mark comes off where the bubble sits.
    started = out["afterReply"][2]
    assert started["queued"] is False and started["note"] == "", (
        "a line whose turn has started is no longer queued")
    assert out["final"][-1]["text"] == "Access granted; starting."
    assert out["sent"] == ["summarise the run so far",
                           'Approved: "grant read access to the notes wiki"'], (
        "the two turns must still go out in order, one at a time")


_TWO_QUEUED = r"""
setQueueOwner("p-1");
const first=sendTurn("kick off the run");
await settle();
sendTurn("first answer", undefined, {relay:true, keepComposer:true});
sendTurn("second answer", undefined, {relay:true, keepComposer:true});
const queued=bubbles();
gates[0].resolve({reply:"kicked off"});
await first; await settle();
console.log(JSON.stringify({queued, afterReply:bubbles()}));
"""


def test_two_queued_lines_keep_their_own_order_under_the_reply(tmp_path, html):
    out = _run(tmp_path, html, {}, _TWO_QUEUED)
    assert [b["text"] for b in out["queued"]] == [
        "kick off the run", "first answer", "second answer"]
    assert [b["queued"] for b in out["queued"]] == [False, True, True]
    assert [b["text"] for b in out["afterReply"]] == [
        "kick off the run", "kicked off", "first answer", "second answer"], (
        "the reply goes above BOTH waiting lines, and they keep the order they "
        "will be read in")
