"""Real connection UI code with deferred transport and deterministic deadlines."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tinyassets import onboarding


def source():
    html = (Path(onboarding.__file__).parent / "app.html").read_text(encoding="utf-8")
    marker = "  // ---- Subscription connection progress ----"
    start = html.find(marker)
    if start < 0:
        start = html.index("  async function connectClaude(){")
    return html[start:html.index("  function wire(){", start)]


HARNESS = r"""
const assert=require('node:assert/strict');
const realTimers=require('node:timers');
const watchdog=realTimers.setTimeout(()=>{
  console.error('connection UI did not settle');process.exit(1);
},3000);
const elements=new Map();
function $(id){
  if(!elements.has(id)) elements.set(id,{value:'',textContent:'',disabled:false,hidden:true});
  return elements.get(id);
}
$('claude-material').value='synthetic-test-token';
const views={connect:{hidden:false}};
let signedOut=0, connected=0, deposits=0, binds=0, clockId=0;
const timers=new Map();
function setTimeout(fn,ms){const id=++clockId;timers.set(id,{fn,ms});return id;}
function clearTimeout(id){timers.delete(id);}
async function tick(){for(let i=0;i<16;i++) await Promise.resolve();}
async function expire(){
  const pending=[...timers.entries()].filter(([id,t])=>t.ms===30000);
  assert.equal(pending.length,1,'one bounded observation deadline');
  for(const [id,t] of pending){timers.delete(id);t.fn();}
  await tick();
}
function deferred(){
  let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});
  return {promise,resolve,reject};
}
const save=deferred(),bind=deferred();
const MCP={connectLLM(service,material){
  deposits++; assert.equal(service,'claude');
  assert.equal($('claude-material').value,'','secret cleared before sending');
  return save.promise;
}};
function authHeaders(){return {};}
function fetch(url,opts){
  binds++;assert.equal(url,'/mcp/app/serving/bind');
  assert.equal(opts.method,'POST');return bind.promise;
}
function onEngineConnected(){connected++;}
function enterSignedOut(){signedOut++;resetClaudeConnection();}
function reply(serving,status=200){return {ok:status===200,status,json:async()=>({serving})};}
function result(){return $('claude-result').textContent;}
__SOURCE__
(async()=>{
  const scenario=__SCENARIO__;
  if(scenario==='empty'){
    $('claude-material').value='';await connectClaude();assert.equal(deposits,0);
    assert.match(result(),/Paste/);return;
  }
  const running=connectClaude();await tick();
  assert.equal(deposits,1);assert.equal($('btn-claude-connect').disabled,true);
  if(scenario==='success') assert.match(result(),/Saving/);
  if(scenario==='duplicate'){
    $('claude-material').value='another-synthetic-token';await connectClaude();
    assert.equal(deposits,1);return;
  }
  if(scenario==='refusal'){
    save.resolve({error:'invalid_auth_material',detail:'Use the final setup token.'});
    await running;assert.equal(binds,0);assert.equal(connected,0);
    assert.match(result(),/Use the final setup token/);
    assert.equal($('btn-claude-connect').disabled,false);return;
  }
  if(scenario==='malformed'){
    save.resolve({});await running;assert.equal(binds,0);
    assert.match(result(),/confirm|unconfirmed/i);return;
  }
  if(scenario==='offline'){
    save.reject(new Error('synthetic-test-token'));await running;
    assert.equal(binds,0);assert.match(result(),/confirm|unconfirmed/i);
    assert.ok(!result().includes('synthetic-test-token'));return;
  }
  if(scenario==='signout'){
    resetClaudeConnection();$('claude-result').textContent='Different session';
    save.resolve({status:'deposited'});await running;
    assert.equal(binds,0);assert.equal(result(),'Different session');return;
  }
  if(scenario==='left_during_save'){
    views.connect.hidden=true;save.resolve({status:'deposited'});await running;
    assert.equal(binds,0);assert.equal(connected,0);
    assert.equal($('btn-claude-connect').textContent,'Enable Claude');return;
  }
  if(scenario==='save_timeout'){
    await expire();await running;
    assert.match(result(),/confirm|unconfirmed/i);assert.equal(binds,0);
    assert.equal($('btn-claude-connect').disabled,true);
    $('claude-material').value='another-synthetic-token';await connectClaude();
    assert.equal(deposits,1);
    save.resolve({status:'deposited'});await tick();
    assert.equal(binds,0,'late deposit cannot automatically bind');
    assert.equal($('btn-claude-connect').textContent,'Enable Claude');
    $('claude-material').value='';
    const finishing=connectClaude();await tick();assert.equal(binds,1);
    bind.resolve(reply({status:'serving'}));await finishing;
    assert.equal(deposits,1);assert.equal(connected,1);return;
  }
  save.resolve({status:'deposited'});await tick();
  assert.equal(binds,1);assert.match(result(),/saved/i);assert.match(result(),/Enabling/);
  if(scenario==='bind_timeout'){
    await expire();await running;assert.match(result(),/saved/i);
    assert.match(result(),/confirm|unconfirmed/i);assert.equal(connected,0);
    bind.resolve(reply({status:'serving'}));await tick();
    assert.equal(connected,0,'late result must not navigate');
    assert.equal(binds,1);assert.match(result(),/enabled|connected|saved/i);return;
  }
  if(scenario==='bind_auth'){
    bind.resolve(reply(null,401));await running;
    assert.equal(signedOut,1);assert.equal(connected,0);return;
  }
  if(scenario==='held'){
    bind.resolve(reply({status:'held',detail:'Needs access approval'}));await running;
    assert.match(result(),/saved/i);assert.match(result(),/Needs access approval/);
    assert.equal(connected,0);
    assert.equal($('btn-claude-connect').textContent,'Enable Claude');return;
  }
  if(scenario==='left_view') views.connect.hidden=true;
  bind.resolve(reply({status:'serving'}));await running;
  assert.equal(connected,scenario==='left_view'?0:1);
  assert.match(result(),/saved model choices are unchanged/);
  assert.equal(timers.size,0);
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>realTimers.clearTimeout(watchdog));
"""


@pytest.mark.parametrize("scenario", [
    "empty", "duplicate", "refusal", "malformed", "offline", "signout",
    "save_timeout", "bind_timeout", "bind_auth", "held", "left_view", "success",
    "left_during_save",
])
def test_connection_stages(tmp_path, scenario):
    node = shutil.which("node")
    assert node, "Node is required to execute the shipped connection UI"
    script = tmp_path / "connection-progress.cjs"
    script.write_text(HARNESS.replace("__SOURCE__", source()).replace(
        "__SCENARIO__", json.dumps(scenario)), encoding="utf-8")
    run = subprocess.run([node, str(script)], capture_output=True, text=True,
                         encoding="utf-8", timeout=15)
    assert run.returncode == 0, run.stdout + run.stderr
