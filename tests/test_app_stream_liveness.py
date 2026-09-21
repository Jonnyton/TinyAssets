"""The response reader must correlate by id and never wait without a bound.

Live, 2026-09-21: the tab that sent a message stayed "thinking" while a fresh
page already showed the same turn had failed. Three facts were confirmed from
the deployed runtime, and all three live in the same place -- the client's
response reader:

1. the original sending tab never stopped waiting;
2. the reader awaited the WHOLE body, so a stream that never closes never ends;
3. the reader took the first ``data:`` frame it found, with no id check, so a
   notification or another call's response could become this turn's answer.

These tests drive the real transport block from ``app.html`` against actual
``Response``/``ReadableStream`` objects in Node -- real chunk boundaries, real
CRLF splits, real multi-byte characters cut in half -- so they assert what the
client does on the wire rather than what its source looks like.

The two bounds here are LIVENESS bounds, never turn-duration caps. A granted
turn runs until it is finished; the server's SSE response pings every ~15s, so
bytes keep arriving throughout a healthy long turn. Silence is the failure.
And a bound that fires is UNCONFIRMED -- never proof the tool did not run --
so nothing it reports is ever auto-replayed.
"""

from __future__ import annotations

import json
import subprocess

from tests.test_onboarding_mcp_session_recovery import _node, _transport_source

_PRELUDE = """
'use strict';
const assert = require('node:assert/strict');
function token(){ return 'test-bearer'; }
async function ensureFreshToken(){ }
async function refreshAccessToken(){ throw new Error('unexpected token refresh'); }
const encoder = new TextEncoder();

// One SSE response whose frames are pushed by the test, byte by byte if it
// wants. `push` writes a chunk, `close` ends the stream. Nothing closes on its
// own: an open connection is the shape under test.
function openSse(state){
  let controller = null;
  const stream = new ReadableStream({
    start(c){ controller = c; },
    cancel(){ state.cancelled = true; },
  });
  state.push = (text) => controller.enqueue(encoder.encode(text));
  state.close = () => { try{ controller.close(); }catch(_e){} };
  return new Response(stream, {headers:{'content-type':'text/event-stream'}});
}
function frame(doc){ return 'data: ' + JSON.stringify(doc) + '\\n\\n'; }
function reply(id, text){
  return {jsonrpc:'2.0', id, result:{structuredContent:{reply:text}}};
}
const tick = (ms) => new Promise(r=>setTimeout(r, ms||5));
__TRANSPORT__
MCP._pause = function(){ return Promise.resolve(); };
MCP.sessionId = 'existing-session';
const OUT = {};
(async () => {
__BODY__
  console.log(JSON.stringify(OUT));
})().catch(e => { console.error((e && e.stack) || e); process.exitCode = 1; });
"""


def _run(tmp_path, body: str, name: str = "stream_case.js") -> dict:
    script = tmp_path / name
    script.write_text(
        _PRELUDE.replace("__TRANSPORT__", _transport_source()).replace("__BODY__", body),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [_node(), str(script)], capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert proc.returncode == 0, f"transport harness failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


# --- correlation --------------------------------------------------------------


def test_only_the_frame_carrying_this_request_id_answers_it(tmp_path):
    """Pings, notifications and another call's response are all skipped."""
    out = _run(tmp_path, """
  const state = {cancelled:false};
  let calls = 0, wanted = null;
  globalThis.fetch = async (_url, init) => {
    calls++; wanted = JSON.parse(init.body).id;
    const resp = openSse(state);
    // Split the SSE prefix, the JSON, and a multi-byte character across chunks,
    // and use CRLF for one frame, so the reader is proven against real cuts.
    setTimeout(()=>{
      state.push(': keep');
      state.push('alive\\r\\n');
      state.push('\\r\\n');
      state.push('data: ' + JSON.stringify(
        {jsonrpc:'2.0', method:'notifications/progress', params:{progress:1}}));
      state.push('\\n\\n');
      state.push(frame(reply(wanted + 7, 'someone else')));
      const mine = frame(reply(wanted, 'caf\\u00e9 \\u2014 done'));
      const bytes = encoder.encode(mine);
      state.push(new TextDecoder().decode(bytes.slice(0, 9), {stream:true}));
      // Hand the remaining raw bytes over so the multi-byte split is genuine.
      state.push('');
      const rest = bytes.slice(9);
      // Re-enqueue raw bytes directly: the decoder in the client must join them.
      state.pushRaw ? state.pushRaw(rest) : state.push(new TextDecoder().decode(rest));
    }, 5);
    return resp;
  };
  const answer = await MCP.converse('report progress');
  OUT.answer = answer;
  OUT.calls = calls;
  OUT.cancelled = state.cancelled;
  OUT.sessionAfter = MCP.sessionId;
""")
    assert out["answer"] == {"reply": "café — done"}
    assert out["calls"] == 1, "a state-changing call was sent more than once"
    assert out["cancelled"] is True, "the stream was not released after the match"


def test_an_rpc_error_for_this_request_is_the_answer_and_keeps_the_session(tmp_path):
    """A JSON-RPC error IS terminal -- and a working session reported it."""
    out = _run(tmp_path, """
  const state = {cancelled:false};
  let calls = 0;
  globalThis.fetch = async (_url, init) => {
    calls++; const id = JSON.parse(init.body).id;
    const resp = openSse(state);
    setTimeout(()=>{
      state.push(': ping\\n\\n');
      state.push(frame({jsonrpc:'2.0', id:id+1,
        error:{code:-32000, message:'somebody else failed'}}));
      state.push(frame({jsonrpc:'2.0', id,
        error:{code:-32602, message:'Invalid params'}}));
    }, 5);
    return resp;
  };
  try{ await MCP.converse('hello'); OUT.threw = false; }
  catch(e){ OUT.threw = true; OUT.message = e.message; OUT.rpc = e.rpc || null;
            OUT.transport = e.transport || null; }
  OUT.calls = calls;
  OUT.sessionAfter = MCP.sessionId;
""")
    assert out["threw"] is True
    assert out["message"] == "Invalid params", "the foreign error was adopted"
    assert out["rpc"]["code"] == -32602
    assert out["transport"] is None, "an application fault is not a transport fault"
    assert out["sessionAfter"] == "existing-session", "a healthy session was churned"
    assert out["calls"] == 1


def test_a_stream_of_only_foreign_frames_is_not_an_answer(tmp_path):
    """EOF with nothing for this id is a cut reply, and is never replayed."""
    out = _run(tmp_path, """
  const state = {cancelled:false};
  let calls = 0;
  globalThis.fetch = async (_url, init) => {
    calls++; const id = JSON.parse(init.body).id;
    const resp = openSse(state);
    setTimeout(()=>{
      state.push(frame(reply(id + 1, 'not yours')));
      state.push(frame({jsonrpc:'2.0', method:'notifications/message', params:{}}));
      state.close();
    }, 5);
    return resp;
  };
  try{ await MCP.converse('hello'); OUT.threw = false; }
  catch(e){ OUT.threw = true; OUT.transport = e.transport; OUT.replayable = e.replayable; }
  OUT.calls = calls;
  OUT.sessionAfter = MCP.sessionId;
""")
    assert out["threw"] is True
    assert out["transport"] == "stream_truncated"
    assert out["replayable"] is False
    assert out["calls"] == 1, "an unconfirmed turn was sent again"
    assert out["sessionAfter"] is None


def test_a_frame_cut_mid_json_is_a_truncated_stream_not_an_answer(tmp_path):
    """A half-arrived terminal frame must not parse into a reply."""
    out = _run(tmp_path, """
  const state = {cancelled:false};
  let calls = 0;
  globalThis.fetch = async (_url, init) => {
    calls++; const id = JSON.parse(init.body).id;
    const resp = openSse(state);
    setTimeout(()=>{
      state.push('data: {"jsonrpc":"2.0","id":' + id + ',"result":{"structuredCon');
      state.close();
    }, 5);
    return resp;
  };
  try{ await MCP.converse('hello'); OUT.threw = false; }
  catch(e){ OUT.threw = true; OUT.transport = e.transport; OUT.replayable = e.replayable;
            OUT.message = e.message; }
  OUT.calls = calls;
""")
    assert out["threw"] is True
    assert out["transport"] == "stream_truncated"
    assert out["replayable"] is False
    assert "no JSON or SSE frame" not in out["message"]
    assert out["calls"] == 1


# --- liveness bounds ----------------------------------------------------------


def test_a_silent_stream_ends_the_wait_without_replaying_the_turn(tmp_path):
    """Headers landed, one ping, then nothing. The tab must not wait forever."""
    out = _run(tmp_path, """
  const state = {cancelled:false};
  let calls = 0;
  globalThis.fetch = async (_url, _init) => {
    calls++;
    const resp = openSse(state);
    setTimeout(()=>{ state.push(': ping\\n\\n'); }, 5);   // and then silence
    return resp;
  };
  MCP.SILENCE_MS = 120;
  const started = Date.now();
  try{ await MCP.converse('a long piece of work'); OUT.threw = false; }
  catch(e){ OUT.threw = true; OUT.transport = e.transport; OUT.replayable = e.replayable;
            OUT.authRequired = !!e.authRequired; }
  OUT.elapsed = Date.now() - started;
  OUT.calls = calls;
  OUT.cancelled = state.cancelled;
  OUT.sessionAfter = MCP.sessionId;
""")
    assert out["threw"] is True, "the client waited on a dead stream forever"
    assert out["transport"] == "stream_silent"
    assert out["replayable"] is False, "a silence bound is not proof the tool never ran"
    assert out["calls"] == 1, "an unconfirmed converse was re-sent"
    assert out["cancelled"] is True, "the dead stream was left open"
    assert out["sessionAfter"] is None, "the untrusted session was kept"


def test_a_response_that_never_arrives_is_bounded_and_not_replayed(tmp_path):
    """fetch never yields headers: the shape with no bound of any kind before."""
    out = _run(tmp_path, """
  let calls = 0, aborted = 0;
  globalThis.fetch = async (_url, init) => {
    calls++;
    return new Promise((_resolve, reject) => {
      if(init && init.signal) init.signal.addEventListener('abort', ()=>{
        aborted++; reject(new Error('aborted')); });
    });
  };
  MCP.HEADERS_MS = 120;
  try{ await MCP.converse('hello'); OUT.threw = false; }
  catch(e){ OUT.threw = true; OUT.transport = e.transport; OUT.replayable = e.replayable; }
  await tick(30);
  OUT.calls = calls;
  OUT.aborted = aborted;
  OUT.sessionAfter = MCP.sessionId;
""")
    assert out["threw"] is True, "the client waited for headers forever"
    assert out["transport"] == "no_response"
    assert out["replayable"] is False
    assert out["calls"] == 1, "an unconfirmed converse was re-sent"
    assert out["aborted"] == 1, "the request was not actually cancelled"
    assert out["sessionAfter"] is None


def test_a_pinging_turn_outlives_the_silence_bound(tmp_path):
    """Liveness, not duration: bytes keep coming, so the turn keeps running."""
    out = _run(tmp_path, """
  const state = {cancelled:false};
  let calls = 0, pings = 0;
  globalThis.fetch = async (_url, init) => {
    calls++; const id = JSON.parse(init.body).id;
    const resp = openSse(state);
    const beat = setInterval(()=>{ pings++; state.push(': ping\\n\\n'); }, 40);
    setTimeout(()=>{ clearInterval(beat); state.push(frame(reply(id, 'finished'))); }, 600);
    return resp;
  };
  MCP.SILENCE_MS = 120;        // five times shorter than the turn itself
  const started = Date.now();
  OUT.answer = await MCP.converse('a turn that takes a while');
  OUT.elapsed = Date.now() - started;
  OUT.pings = pings;
  OUT.calls = calls;
""")
    assert out["answer"] == {"reply": "finished"}
    assert out["elapsed"] >= 500, "the turn did not actually outlast the bound"
    assert out["pings"] >= 5
    assert out["calls"] == 1


# --- one request's failure is not another's -----------------------------------


def test_retiring_a_failed_call_does_not_abort_a_healthy_turn(tmp_path):
    """A status poll dying mid-turn must not cancel the turn's own stream."""
    out = _run(tmp_path, """
  const turnState = {cancelled:false};
  let calls = 0, turnId = null;
  globalThis.fetch = async (_url, init) => {
    calls++;
    const body = JSON.parse(init.body);
    const isTurn = body.params && body.params.name === 'converse';
    if(isTurn){
      turnId = body.id;
      const resp = openSse(turnState);
      const beat = setInterval(()=>turnState.push(': ping\\n\\n'), 20);
      setTimeout(()=>{ clearInterval(beat);
        turnState.push(frame(reply(turnId, 'finished'))); }, 300);
      return resp;
    }
    // The poll's own response: the session is gone. It retires the session and
    // bumps the generation WHILE the turn is still streaming.
    return new Response(JSON.stringify(
      {jsonrpc:'2.0', id:'server-error', error:{code:-32600, message:'Session not found'}}),
      {status:404, headers:{'content-type':'application/json'}});
  };
  MCP.SILENCE_MS = 200;
  const turn = MCP.converse('keep working');
  await tick(40);
  OUT.pollFailed = await MCP.getStatus().then(()=>false, ()=>true);
  OUT.answer = await turn;
  OUT.turnStreamCancelledEarly = false;
  OUT.calls = calls;
""")
    assert out["pollFailed"] is True, "the scripted poll was supposed to fail"
    assert out["answer"] == {"reply": "finished"}, "another call's failure killed the turn"


def test_an_account_change_mid_stream_never_adopts_the_old_result(tmp_path):
    """A result that lands after sign-in changed belongs to nobody on screen."""
    out = _run(tmp_path, """
  const state = {cancelled:false};
  let calls = 0;
  globalThis.fetch = async (_url, init) => {
    calls++; const id = JSON.parse(init.body).id;
    const resp = openSse(state);
    setTimeout(()=>{ state.push(frame(reply(id, 'the previous account reply'))); }, 60);
    return resp;
  };
  MCP.SILENCE_MS = 500;
  const turn = MCP.converse('hello');
  await tick(20);
  MCP.endLogin();                       // the founder signs out / switches account
  try{ OUT.answer = await turn; OUT.threw = false; }
  catch(e){ OUT.threw = true; OUT.transport = e.transport; OUT.replayable = e.replayable; }
  OUT.calls = calls;
  OUT.sessionAfter = MCP.sessionId;
""")
    assert out["threw"] is True, "a previous account's reply was handed back"
    assert out["transport"] == "login_changed"
    assert out["replayable"] is False
    assert out["sessionAfter"] is None
