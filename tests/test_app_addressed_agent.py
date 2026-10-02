"""The app's chat talks to one of the owner's agents at a time (harness §4.18).

Runs the page's OWN source under node (the working-indicator harness), plus
the addressed-agent functions: switching shows that agent's thread, and every
send, steer, read and in-flight record names it. A switch waits for the turn,
and a thread read that lands after a switch paints nothing.
"""
# ruff: noqa: E501 -- embedded JavaScript scenarios

from __future__ import annotations

import json
import os
import re
import subprocess

import pytest

from tests.test_app_working_indicator import _DECLS, _FUNCS, _NEW_FUNCS, _NODE, _SHIM, _TAIL
from tests.test_onboarding_app import _js_function
from tinyassets import onboarding

pytestmark = pytest.mark.skipif(
    _NODE is None, reason="node is required to execute the page's own source")

_AGENT_FUNCS = ("addressedAgentId", "resetAddressedAgent", "addressAgent",
                "paintAddressedAgent", "openAddressedChat")


def _method(html: str, head: str, name: str) -> str:
    """An object-literal method (``head`` is its exact first line) as a function."""
    start = html.index(head)
    return _js_function("function " + html[start:], name)


_BODY = r"""
const realGetConversation=__GET_CONVERSATION__;
const realConverse=__CONVERSE__;
setQueueOwner("p-1"); setQueueScope("u-1");
globalThis.authHeaders=()=>({});
// The server: one thread per agent, and every read it was asked for.
const threads={main:[{speaker:"founder",text:"main hello",ts:1},{speaker:"universe",text:"main reply",ts:2}],
               w1:[{speaker:"founder",text:"weaver hello",ts:3},{speaker:"universe",text:"weaver reply",ts:4}]};
const reads=[], held={};
const door={status:async(args)=>{
  reads.push(args);
  const agent=args.conversation_agent||"main";
  if(SCENARIO.holdRead===agent) await new Promise(r=>{held[agent]=r;});
  return {universe_id:"u-1",recent_conversation:{turns:threads[agent]}};
}};
Owner.getConversation=(before)=>realGetConversation.call(door,before);
// The connector: what each converse carried, built by the page's own converse.
const wire=[];
const fakeMcp={callTool:async(name,args)=>{ wire.push(args); return {reply:"ok from "+(args.agent_id||"main")}; }};
MCP.converse=(...a)=>realConverse.apply(fakeMcp,a);
const texts=()=>els.thread.children.map(n=>(n.children.filter(c=>c.className==="msg-body")
  .map(c=>c.textContent)[0])||n.textContent||"").filter(Boolean);

await addressAgent({agent_id:"w1",name:"Evidence Weaver"});
await settle();
const afterSwitch=texts();
await sendTurn("critique my methods");
await settle();
const inflightAgent=(()=>{ rememberInflight("x","x",1,"typed",null); return readInflight().agent; })();
forgetInflight();

// A switch while a turn is running is refused; nothing changes.
let gateResolve;
MCP.converse=(...a)=>{ wire.push({gated:true,agent:a[4]}); return new Promise(r=>{gateResolve=r;}); };
const running=sendTurn("long job");
await settle();
let refused="";
try{ await addressAgent({agent_id:"main",name:"Your agent"}); }catch(e){ refused=e.message; }
const stillW1=addressedAgentId();
gateResolve({reply:"done"}); await running; await settle();

// A read for the agent you just left paints nothing on the new one's thread.
SCENARIO.holdRead="main";
const leaving=addressAgent({agent_id:"main",name:"Your agent"});
await settle();
SCENARIO.holdRead="";
await addressAgent({agent_id:"w1",name:"Evidence Weaver"});
await settle();
held.main(); await leaving.catch(()=>{}); await settle();
const afterStale=texts();

console.log(JSON.stringify({afterSwitch, reads, wire, inflightAgent, refused, stillW1,
  afterStale, agent:addressedAgentId()}));
"""


def _program(html: str, scenario: dict, body: str) -> str:
    decls = [found.group(0) for found in
             (re.search(pat, html) for pat in _DECLS) if found]
    decls.append(re.search(r"let addressedAgent=[^\n]*;", html).group(0))
    funcs = [_js_function(html, name) for name in (*_FUNCS, *_AGENT_FUNCS)]
    for name in _NEW_FUNCS:
        if re.search(r"function\s+" + name + r"\s*\(", html):
            funcs.append(_js_function(html, name))
    body = (body
            .replace("__GET_CONVERSATION__",
                     _method(html, "getConversation(before){", "getConversation"))
            .replace("__CONVERSE__", _method(
                html, "converse(message,inputMethod=", "converse")))
    return (_SHIM.replace("__SCENARIO__", json.dumps(scenario)) +
            "\n".join(decls) + "\n" + "\n".join(funcs) + "\n(async()=>{\n" + body + _TAIL)


def _run(tmp_path, scenario: dict, body: str) -> dict:
    page, _csp = onboarding.render_app_html()
    script = tmp_path / "addressed_agent_case.js"
    script.write_text(_program(page, scenario, body), encoding="utf-8")
    proc = subprocess.run([_NODE, str(script)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60, env=dict(os.environ))
    assert proc.returncode == 0, f"addressed-agent harness crashed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_switching_shows_that_agents_thread_and_every_turn_names_it(tmp_path):
    out = _run(tmp_path, {}, _BODY)
    assert out["afterSwitch"] == ["weaver hello", "weaver reply"]
    assert out["reads"][0] == {"include_conversation": True, "conversation_agent": "w1"}
    first = out["wire"][0]
    assert first["message"] == "critique my methods" and first["agent_id"] == "w1"
    assert out["inflightAgent"] == "w1"


def test_a_switch_waits_for_the_running_turn(tmp_path):
    out = _run(tmp_path, {}, _BODY)
    assert "finish or stop the current message first" in out["refused"]
    assert out["stillW1"] == "w1"
    assert {"gated": True, "agent": "w1"} in out["wire"]


def test_a_read_for_the_agent_you_left_paints_nothing(tmp_path):
    out = _run(tmp_path, {}, _BODY)
    assert out["agent"] == "w1"
    assert "main hello" not in out["afterStale"]
    assert out["afterStale"][:2] == ["weaver hello", "weaver reply"]


def test_main_sends_no_agent_id_and_reads_the_main_thread(tmp_path):
    body = r"""
const realGetConversation=__GET_CONVERSATION__;
const realConverse=__CONVERSE__;
setQueueOwner("p-1"); setQueueScope("u-1");
const reads=[], wire=[];
Owner.getConversation=(before)=>realGetConversation.call({status:async a=>{ reads.push(a);
  return {universe_id:"u-1",recent_conversation:{turns:[]}}; }},before);
MCP.converse=(...a)=>realConverse.apply({callTool:async(n,args)=>{ wire.push(args); return {reply:"r"}; }},a);
await loadHistory(); await sendTurn("hello"); await settle();
console.log(JSON.stringify({reads, wire}));
"""
    out = _run(tmp_path, {}, body)
    assert out["reads"] == [{"include_conversation": True}]
    assert "agent_id" not in out["wire"][0]


def test_a_steer_names_the_agent_the_line_was_typed_to(tmp_path):
    body = r"""
setQueueOwner("p-1"); setQueueScope("u-1");
globalThis.authHeaders=()=>({});
const steerPosts=[];
globalThis.fetch=(url,init)=>{ steerPosts.push(JSON.parse(init.body));
  return Promise.resolve({ok:true,status:200,json:async()=>({steered:true,steer_id:7})}); };
await addressAgent({agent_id:"w1",name:"Evidence Weaver"});
const first=sendTurn("start the long job");
await settle();
sendTurn("also check the methods");
await settle(); await settle();
gates[gates.length-1].resolve({reply:"Done.",steering:{delivered:[7],undelivered:[]}});
await first; await settle();
console.log(JSON.stringify({steerPosts}));
"""
    out = _run(tmp_path, {}, body)
    assert out["steerPosts"] == [
        {"universe_id": "u-1", "text": "also check the methods", "agent_id": "w1"}]
