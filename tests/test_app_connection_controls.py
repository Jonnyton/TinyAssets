"""Execute shipped connection UI with synthetic transport; not live acceptance."""

import json
import shutil
import subprocess

from tinyassets.onboarding import render_app_html


def run(steps):
    html, _ = render_app_html()
    source = html[
        html.index("    let connectionsBusy=false;") : html.index("    function leaveAccount()")
    ]
    program = r"""
const elements=new Map(),requests=[];
function node(tag){return {tag,children:[],textContent:'',disabled:false,
 replaceChildren(){this.children=[];},append(...nodes){this.children.push(...nodes);},
 addEventListener(event,handler){this[event]=handler;},remove(){this.removed=true;}};}
const $=id=>{if(!elements.has(id))elements.set(id,node(id));return elements.get(id);};
const document={createElement:node};let identity='owner',confirmResult=true;
const token=()=>identity,authHeaders=()=>({Authorization:identity}),confirm=()=>confirmResult;
let engineConnected=true,HostedModelConnect={setup:'connected',paint(){}};
let failPost=false,changeIdentity=false;
const fetch=async(url,options={})=>{
 requests.push({url,method:options.method||'GET',body:options.body&&JSON.parse(options.body)});
 if(options.method==='POST'&&failPost)throw new Error('network result ambiguous');
 if(url.endsWith('/me'))return {
   ok:true,json:async()=>({engine_connected:false,setup:'disconnected'})};
 return {ok:true,json:async()=>{
   if(changeIdentity)identity='another-owner';
   return options.method==='POST'?{status:'removed'}:{universe_id:'u-owner',connections:[
     {connection_id:'c1',destination:'my-service',incarnation:'first-incarnation'}]};
 }};
};
__SOURCE__
(async()=>{
 __STEPS__
 console.log(JSON.stringify({requests,status:$('connection-status').textContent,
   rows:$('connection-list').children.map(n=>({removed:!!n.removed,text:n.children[0].textContent})),
   engineConnected,setup:HostedModelConnect.setup,busy:connectionsBusy}));
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    result = subprocess.run(
        [
            shutil.which("node"),
            "-e",
            program.replace("__SOURCE__", source).replace("__STEPS__", steps),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_disconnect_uses_observed_connection_and_shows_unpowered_reconnect():
    result = run(
        "await loadConnections(); await $('connection-list').children[0].children[1].click();"
    )
    assert result["requests"][1]["body"] == {
        "universe_id": "u-owner",
        "destination": "my-service",
        "incarnation": "first-incarnation",
    }
    assert result["engineConnected"] is False and result["setup"] == "disconnected"
    assert "provider account is unchanged" in result["status"]


def test_uncertain_disconnect_does_not_replay_or_claim_success():
    result = run(
        "await loadConnections(); failPost=true; "
        "await $('connection-list').children[0].children[1].click();"
    )
    assert len([r for r in result["requests"] if r["method"] == "POST"]) == 1
    assert "not confirmed" in result["status"]
    assert not result["rows"][0]["removed"]


def test_cancel_is_read_only():
    result = run(
        "await loadConnections(); confirmResult=false; "
        "await $('connection-list').children[0].children[1].click();"
    )
    assert all(r["method"] == "GET" for r in result["requests"])


def test_old_owner_response_is_not_rendered_after_account_change():
    result = run("changeIdentity=true; await loadConnections();")
    assert result["rows"] == []
