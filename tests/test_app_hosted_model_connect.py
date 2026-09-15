"""Execute the shipped browser controller; synthetic DOM/transport, not live proof."""

import json
import shutil
import subprocess

import pytest

from tests.test_onboarding_app import _js_function
from tinyassets.onboarding import render_app_html


def run_browser(steps):
    html, _ = render_app_html()
    controller = html[html.index("  const HostedModelConnect={"):
                      html.index("  // End hosted model connection controller.")]
    program = r"""
const elements=new Map(),storage=new Map(),requests=[],navigations=[],answers=[];
const $=id=>{if(!elements.has(id)) elements.set(id,{textContent:'',hidden:false,
 disabled:false,focus(){},addEventListener(){}});return elements.get(id);};
const sessionStorage={getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),
 removeItem:k=>storage.delete(k)};
let NATIVE=false,me={setup:'empty'},auth='owner-token';
let exchangeResult=null,answerResult={status:'answered'};
let signedInNow=false,workosCalls=0,chatCount=0,refreshes=0;
const window={location:{pathname:'/mcp/app',search:'',assign:url=>navigations.push(url)}};
const history={replaceState:(a,b,url)=>{window.location.pathname=url;window.location.search='';}};
const token=()=>auth,ensureFreshToken=async()=>{},authHeaders=()=>({Authorization:auth});
const randToken=()=> 'v'.repeat(43),challengeFor=async()=> 'c'.repeat(43);
const fetch=async(url,options)=>{
 requests.push({url,options,body:JSON.parse(options.body)});
 let result=url.endsWith('/begin') ? {flow:'f'.repeat(43),
  authorize_url:'https://provider.example/auth',expires_in:600} : exchangeResult;
 return {ok:!!result&&!result.error,json:async()=>result||{error:'incomplete'}};
};
const fetchMe=async()=>me,ModelPicker={reset(){}},Voice={refreshCapability(){}};
let engineConnected=null;
const showConnect=()=>HostedModelConnect.paint(),showView=v=>{if(v==='chat')chatCount++;};
const startHeartbeat=()=>{},warmSession=()=>{},loadPlan=()=>{},loadHistory=()=>{};
const wire=()=>{},wireNativeReturn=()=>{},loadOpenAIPending=()=>{},startSessionKeepAlive=()=>{};
const completeSignInIfCallback=async()=>{workosCalls++;return signedInNow;};
const refreshAccessToken=async()=>{refreshes++;};
const enterSignedOut=()=>{HostedModelConnect.reset();};
const MCP={answerRequest:async p=>{answers.push(p);return answerResult;}};
__SOURCE__
(async()=>{
 __STEPS__
 console.log(JSON.stringify({requests,navigations,answers,workosCalls,chatCount,refreshes,
   path:window.location.pathname,search:window.location.search,stored:[...storage.values()],
   setup:HostedModelConnect.setup,request:HostedModelConnect.request,busy:HostedModelConnect.busy,
   status:$('hosted-model-status').textContent,connectStatus:$('connect-status').textContent,
   confirmationHidden:$('hosted-model-confirmation').hidden,callback:globalThis.callback}));
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    source = controller + _js_function(html, "enterSignedIn") + _js_function(html, "boot")
    node = shutil.which("node")
    assert node, "Node is required to execute browser tests"
    result = subprocess.run([node, "-e", program.replace("__SOURCE__", source)
                             .replace("__STEPS__", steps)],
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def saved_callback(query="?code=synthetic-code"):
    return """
sessionStorage.setItem(HostedModelConnect.storageKey,JSON.stringify({flow:'f'.repeat(43),
 verifier:'v'.repeat(43),preset:HostedModelConnect.preset,expires:Date.now()+60000}));
window.location.pathname='/mcp/app/model-callback/'+'f'.repeat(43);
window.location.search=__QUERY__;
""".replace("__QUERY__", json.dumps(query))


def confirmation():
    return """
exchangeResult={status:'confirmation_required',request_id:'request-a',request:{
 request_id:'request-a',title:'Power free models',body:'Free only',
 action:{type:'bind_model_access'}}};
"""


def test_explicit_signin_empty_starts_same_tab_once_not_on_refresh():
    result = run_browser("signedInNow=true;await boot();signedInNow=false;await boot();")
    assert len(result["navigations"]) == 1
    assert len(result["requests"]) == 1
    assert result["requests"][0]["body"] == {
        "preset_id": "openrouter_user_models_v1", "code_challenge": "c" * 43}
    assert json.loads(result["stored"][0])["verifier"] == "v" * 43
    assert not result["answers"]


@pytest.mark.parametrize("state", ["recovery", "connected", "unavailable", None])
def test_nonempty_or_unavailable_cannot_auto_start_even_if_legacy_boolean_disagrees(state):
    result = run_browser("signedInNow=true;me={setup:" + json.dumps(state)
                         + ",engine_connected:false};await boot();")
    assert not result["requests"]
    assert result["chatCount"] == (1 if state == "connected" else 0)


def test_native_does_not_start_web_callback_flow():
    assert not run_browser("NATIVE=true;signedInNow=true;await boot();")["requests"]


def test_hosted_return_is_stripped_before_workos_and_requires_explicit_model_approval():
    result = run_browser(saved_callback() + confirmation() + "await boot();")
    assert result["workosCalls"] == 0
    assert result["path"] == "/mcp/app" and not result["search"]
    assert not result["stored"]
    assert not result["answers"] and not result["navigations"]
    assert len(result["requests"]) == 1
    assert result["requests"][0]["url"].endswith("/exchange")
    assert result["requests"][0]["options"]["referrerPolicy"] == "no-referrer"
    assert result["request"]["request_id"] == "request-a"
    assert result["confirmationHidden"] is False


@pytest.mark.parametrize("query", ["?error=access_denied", "", "?code=one&code=two"])
def test_cancelled_or_invalid_return_never_exchanges_or_restarts(query):
    result = run_browser(saved_callback(query) + "await boot();await boot();")
    assert not result["requests"] and not result["navigations"]
    assert not result["stored"]
    assert "cancelled or expired" in result["status"]


def test_foreign_or_expired_browser_flow_cannot_redeem():
    for mutation in ["saved.flow='x'.repeat(43);", "saved.expires=1;"]:
        result = run_browser(saved_callback() + """
let saved=JSON.parse(sessionStorage.getItem(HostedModelConnect.storageKey));
""" + mutation + """
sessionStorage.setItem(HostedModelConnect.storageKey,JSON.stringify(saved));await boot();
""")
        assert not result["requests"]


def test_uncertain_exchange_is_not_retried_and_exposes_explicit_resume():
    result = run_browser(saved_callback() + "await boot();await boot();")
    assert len(result["requests"]) == 1
    assert "key may already exist" in result["status"]
    assert not result["stored"] and not result["navigations"]


def test_resume_fetches_pending_request_without_any_authorization_or_approval():
    result = run_browser(confirmation() + "me={setup:'recovery'};await boot();"
                         "await HostedModelConnect.complete();")
    assert len(result["requests"]) == 1
    assert result["requests"][0]["url"].endswith("/resume")
    assert not result["answers"] and not result["navigations"]


@pytest.mark.parametrize("accepted", [True, False])
def test_only_owner_click_submits_existing_request_and_rereads_serving(accepted):
    result = run_browser(saved_callback() + confirmation() + "await boot();"
                         + ("me={setup:'connected'};" if accepted else "me={setup:'recovery'};")
                         + f"await HostedModelConnect.answer({str(accepted).lower()});")
    expected = {"request_id": "request-a", **({"values": {}} if accepted
                                             else {"decision": "declined"})}
    assert result["answers"] == [expected]
    assert result["request"] is None
    assert result["chatCount"] == (1 if accepted else 0)


def test_failed_approval_preserves_actionable_request_not_false_success():
    result = run_browser(saved_callback() + confirmation() + """
await boot();answerResult={error:'authority_unavailable',request_pending:true};
await HostedModelConnect.answer(true);
""")
    assert result["request"]["request_id"] == "request-a"
    assert "request remains open" in result["status"]
    assert result["chatCount"] == 0 and result["busy"] is False
