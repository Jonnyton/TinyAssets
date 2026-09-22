"""The app's own JavaScript, recovering a message the status peek bounded.

Runs the REAL `loadHistory`, `appendMessage`, `offerFullMessage` and
`loadFullMessage` out of app.html in Node against a deterministic transport --
including the real `appendMessage`, so the control is appended to the same
bubble structure a browser builds (`meta` + `.msg-body`), not to a stand-in
whose shape the test itself chose.
"""

import json
import os
import re
import shutil
import subprocess

import pytest

from tests.test_onboarding_app import _js_function
from tinyassets import onboarding

CAP = 4000

_SHIM = r"""
class El{
  constructor(tag){
    this.tagName=tag.toUpperCase(); this.children=[]; this.className="";
    this.textContent=""; this.style={}; this.disabled=false;
    this.listeners={}; this.scrollTop=0; this.scrollHeight=0; this.title="";
  }
  appendChild(c){ this.children.push(c); c.parent=this; return c; }
  remove(){ this.removed=true; if(this.parent)
    this.parent.children=this.parent.children.filter(c=>c!==this); }
  addEventListener(n,f){ this.listeners[n]=f; }
  click(){ return (this.listeners.click||(()=>{}))(); }
}
const document={ createElement:t=>new El(t), createTextNode:t=>{
  const e=new El("#text"); e.textContent=t; return e; }, activeElement:null };
const els={ "thread":new El("div"), "thread-empty":new El("div"),
            "status-line":new El("div"), "composer-input":new El("textarea") };
const $=id=>els[id];
let hasMessages=false;
const SCENARIO=__SCENARIO__;
const chunkCalls=[];
let queueScope=null, queueOwner="";
function setQueueScope(v){ queueScope=v||null; }
function setQueueOwner(v){ queueOwner=v||""; }
const renderedConsumerTurns=new Set(), renderedConsumerFounders=new Set();
const token=()=>"t";
function enterSignedOut(){}
function restoreInflight(){}
function answerExecutionDetail(row){
  if(!row||!row.execution) return null;
  const tag=new El("span"); tag.className="msg-execution";
  tag.textContent="via "+(row.execution.model_id||"model");
  return tag;
}
function appendFailureNotice(text){ const e=new El("div"); e.className="msg msg--platform";
  e.textContent=text; els.thread.appendChild(e); }
const MCP={ _loginEpoch:1,
  getConversation: async()=>({universe_id:SCENARIO.universe||"u-1",
    recent_conversation:{turns:SCENARIO.history||[]}}),
  readConversationChunk: async(id,offset,scope)=>{
    chunkCalls.push({id,offset,scope});
    if(SCENARIO.switchAccountAfterCall===chunkCalls.length){
      // A sign-out / account switch lands WHILE this chunk is in flight.
      MCP._loginEpoch=MCP._loginEpoch+1;
    }
    const replies=SCENARIO.chunks||[];
    const reply=replies[Math.min(chunkCalls.length-1, replies.length-1)];
    if(reply&&reply.throw){ const e=new Error(reply.throw); throw e; }
    return reply||{};
  },
};
__APP_FUNCTIONS__
(async()=>{
  const out={};
  setQueueOwner(SCENARIO.principal||"p-1");
  await loadHistory();
  const bubbles=els.thread.children;
  const describe=n=>({
    cls:n.className,
    body:(n.children.find(c=>c.className==="msg-body")||{}).textContent,
    notes:n.children.filter(c=>c.className==="msg-note").map(c=>c.textContent),
    buttons:n.children.filter(c=>c.tagName==="BUTTON").map(b=>b.textContent),
    meta:(n.children.find(c=>c.className==="msg-meta")||{textContent:""}).textContent,
    extras:n.children.filter(c=>c.className==="msg-execution").map(c=>c.textContent),
  });
  out.before=bubbles.map(describe);
  if(SCENARIO.switchBeforeClick) MCP._loginEpoch++;
  if(SCENARIO.click!==false){
    const target=bubbles[SCENARIO.clickIndex===undefined?bubbles.length-1:SCENARIO.clickIndex];
    const btn=target&&target.children.find(c=>c.tagName==="BUTTON");
    out.clicked=!!btn;
    if(btn){ btn.click(); await new Promise(r=>setTimeout(r,SCENARIO.settle||40)); }
  }
  out.after=bubbles.map(describe);
  out.chunkCalls=chunkCalls;
  out.epoch=MCP._loginEpoch;
  console.log(JSON.stringify(out));
})().catch(e=>{ console.error(e&&e.stack||e); process.exit(1); });
"""


def _run(tmp_path, scenario: dict) -> dict:
    node = shutil.which("node")
    if not node:  # pragma: no cover - environment dependent
        if os.environ.get("TINYASSETS_SKIP_JS_PROBE_TESTS"):
            pytest.skip("node absent; skip explicitly requested via env")
        pytest.fail("node executable not found - the expansion control is JavaScript; "
                    "install Node or set TINYASSETS_SKIP_JS_PROBE_TESTS=1")
    html, _csp = onboarding.render_app_html()
    decls = "\n".join(
        re.search(pat, html).group(0)
        for pat in (r"let historyLoaded = [^\n]*;",)
    )
    funcs = "\n".join(_js_function(html, f) for f in (
        "formatMessageTimestamp", "appendMessage",
        "messageBody", "expansionHandle", "offerFullMessage", "loadFullMessage",
        "loadHistory",
    ))
    program = (_SHIM.replace("__SCENARIO__", json.dumps(scenario))
                    .replace("__APP_FUNCTIONS__", decls + "\n" + funcs))
    script = tmp_path / "expansion_case.js"
    script.write_text(program, encoding="utf-8")
    proc = subprocess.run([node, str(script)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60)
    assert proc.returncode == 0, f"expansion harness crashed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def _long(unit="diagnosis 🦊 α\r\n", repeat=700):
    return unit * repeat


def _turn(text, *, speaker="universe", ident="12", ts=1_700_000_000.0, **extra):
    """One turn exactly as get_status's peek now emits it."""
    return {
        "speaker": speaker,
        "text": text[:CAP],
        "truncated": len(text) > CAP,
        "total_chars": len(text),
        "id": ident,
        "ts": ts,
        **extra,
    }


def _chunks(full, size):
    """What the server returns for each successive read of ``full``."""
    out, offset = [], 0
    points = list(full)
    while offset < len(points):
        part = "".join(points[offset:offset + size])
        nxt = offset + len(part)
        out.append({"available": True, "chunk": part, "offset": offset,
                    "offset_unit": "unicode_code_points", "total_chars": len(points),
                    "next_offset": nxt if nxt < len(points) else None})
        offset = nxt
    return out


def test_a_bounded_turn_offers_its_rest_and_paints_it_verbatim(tmp_path):
    full = _long()
    out = _run(tmp_path, {
        "history": [_turn("hello", speaker="founder", ident="11", ts=1.0,
                          truncated=False, total_chars=5),
                    _turn(full, ts=2.0, execution={"model_id": "sonnet"})],
        "chunks": _chunks(full, 997),
    })
    preview = out["before"][-1]
    assert preview["body"] == full[:CAP]
    assert preview["buttons"] == ["Show full message (" + f"{len(full):,}" + " characters)"]
    assert out["before"][0]["buttons"] == []          # a short turn offers nothing

    painted = out["after"][-1]
    assert painted["body"] == full                     # verbatim, astral intact
    assert painted["buttons"] == [] and painted["notes"] == []
    assert painted["meta"] == preview["meta"]          # original bubble metadata kept
    assert painted["extras"] == ["via sonnet"]         # provider label untouched
    assert [c["id"] for c in out["chunkCalls"]] == ["12"] * len(out["chunkCalls"])
    offsets = [c["offset"] for c in out["chunkCalls"]]
    assert offsets == sorted(set(offsets)) and offsets[0] == 0


def test_the_founder_s_own_long_message_gets_the_same_neutral_control(tmp_path):
    full = "I asked 🤔 " * 900
    out = _run(tmp_path, {
        "history": [_turn(full, speaker="founder", ident="7")],
        "chunks": _chunks(full, 4096),
    })
    assert out["before"][0]["cls"] == "msg msg--founder"
    assert out["before"][0]["buttons"][0].startswith("Show full message (")
    assert out["after"][0]["body"] == full


def test_a_chunk_landing_after_an_account_switch_paints_nothing(tmp_path):
    full = _long()
    out = _run(tmp_path, {
        "history": [_turn(full)],
        "chunks": _chunks(full, 997),
        "switchAccountAfterCall": 1,          # the login changes mid-load
        "settle": 60,
    })
    assert out["epoch"] == 2
    assert out["after"][0]["body"] == full[:CAP]      # the preview, unchanged
    assert out["after"][0]["notes"] == []             # and no disclosure, no notice
    assert len(out["chunkCalls"]) == 1                # the load stopped at the switch


def test_a_failed_expansion_keeps_the_preview_and_re_arms(tmp_path):
    full = _long()
    out = _run(tmp_path, {
        "history": [_turn(full)],
        "chunks": [{"throw": "offline"}],
    })
    bubble = out["after"][0]
    assert bubble["body"] == full[:CAP]
    assert bubble["notes"] == [" Couldn’t load the rest of this message."]
    assert bubble["buttons"][0].startswith("Show full message (")   # retry is one click


def test_a_refused_read_never_paints_a_partial_answer(tmp_path):
    full = _long()
    out = _run(tmp_path, {
        "history": [_turn(full)],
        "chunks": [{"error": "conversation_message_not_found", "chunk": "wrong"}],
    })
    assert out["after"][0]["body"] == full[:CAP]
    assert out["after"][0]["notes"] == [" Couldn’t load the rest of this message."]


@pytest.mark.parametrize("bad_next", [0, "8", 1.5, -1, True])
def test_a_non_advancing_continuation_is_refused_not_looped(tmp_path, bad_next):
    full = _long()
    out = _run(tmp_path, {
        "history": [_turn(full)],
        "chunks": [{"available": True, "chunk": full[:997], "offset": 0,
                    "total_chars": len(full), "next_offset": bad_next}],
    })
    assert len(out["chunkCalls"]) == 1                      # refused on the spot
    assert out["after"][0]["body"] == full[:CAP]            # preview preserved
    assert out["after"][0]["notes"] == [" Couldn’t load the rest of this message."]


def test_a_turn_without_a_stable_id_says_so_instead_of_inventing_one(tmp_path):
    full = _long()
    turn = _turn(full)
    turn.pop("id")                                           # a legacy row, no key
    out = _run(tmp_path, {"history": [turn], "chunks": _chunks(full, 997), "click": False})
    bubble = out["before"][0]
    assert bubble["buttons"] == []
    assert "cannot be expanded here" in bubble["notes"][0]
    assert out["chunkCalls"] == []                           # nothing fabricated


def test_an_untruncated_turn_is_drawn_exactly_as_before(tmp_path):
    out = _run(tmp_path, {
        "history": [{"speaker": "universe", "text": "short answer", "truncated": False,
                     "total_chars": 12, "id": "3", "ts": 5.0}],
        "click": False,
    })
    assert out["before"][0]["body"] == "short answer"
    assert out["before"][0]["buttons"] == [] and out["before"][0]["notes"] == []


def test_stale_expansion_control_makes_no_request(tmp_path):
    full = _long()
    out = _run(tmp_path, {"history": [_turn(full)], "chunks": _chunks(full, 997),
                          "switchBeforeClick": True})
    assert out["chunkCalls"] == []
    assert out["after"][0]["body"] == full[:CAP]


def test_each_chunk_is_bound_to_the_rendered_home(tmp_path):
    full = _long()
    out = _run(tmp_path, {"history": [_turn(full)], "universe": "u-owned",
                          "chunks": _chunks(full, 997)})
    assert out["chunkCalls"] and all(c.get("scope") == "u-owned" for c in out["chunkCalls"])


def test_real_continuation_has_no_arbitrary_page_limit(tmp_path):
    full = "🦊 abcdefghi" * 530
    out = _run(tmp_path, {"history": [_turn(full)], "chunks": _chunks(full, 10)})
    assert len(out["chunkCalls"]) > 512
    assert out["after"][0]["body"] == full


def test_missing_terminal_marker_does_not_claim_a_complete_message(tmp_path):
    full = _long()
    part = _chunks(full, 997)[0]
    part.pop("next_offset")
    out = _run(tmp_path, {"history": [_turn(full)], "chunks": [part]})
    assert out["after"][0]["body"] == full[:CAP]
    assert out["after"][0]["notes"]
