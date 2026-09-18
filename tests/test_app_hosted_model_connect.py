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
 disabled:false,focus(){this.focused=true;},scrollIntoView(){this.scrolled=true;},
 addEventListener(event,handler){this.listeners=this.listeners||{};this.listeners[event]=handler;}
 });return elements.get(id);};
const sessionStorage={getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),
 removeItem:k=>storage.delete(k)};
let NATIVE=false,me={setup:'empty'},auth='owner-token',viewGeneration=0;
let exchangeResult=null,answerResult={status:'answered'};
let signedInNow=false,workosCalls=0,chatCount=0,refreshes=0;
const window={location:{pathname:'/mcp/app',search:'',assign:url=>navigations.push(url)}};
const history={replaceState:(a,b,url)=>{window.location.pathname=url;window.location.search='';}};
const token=()=>auth,authHeaders=()=>({Authorization:auth});
let ensureFreshToken=async()=>{};
const randToken=()=> 'v'.repeat(43),challengeFor=async()=> 'c'.repeat(43);
let fetch=async(url,options)=>{
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


def test_existing_key_shortcut_focuses_original_box_without_credentials_or_authority():
    result = run_browser(r"""
const assert=require('node:assert/strict');
$('paste-blob').value='synthetic-private-key';
$('paste-intent').value='Keep my existing intent';
$('api-key-connection').hidden=true;$('paste-key-guidance').hidden=true;
HostedModelConnect.wire();
HostedModelConnect.setup='empty';
$('btn-hosted-key').listeners.click();
assert.equal($('api-key-connection').hidden,false);
assert.equal($('paste-key-guidance').hidden,false);
assert.equal($('api-key-connection').scrolled,true);
assert.equal($('paste-blob').focused,true);
assert.equal($('paste-blob').value,'');
assert.equal($('paste-intent').value,'');
assert.equal($('btn-paste-connect').hidden,true);
assert.equal($('btn-hosted-deposit').hidden,false);
// Navigation must not even inspect a credential value.
Object.defineProperty($('paste-blob'),'value',{get(){throw Error('credential read');},set(){}});
$('btn-hosted-key').listeners.click();
""")
    assert result["requests"] == result["navigations"] == result["answers"] == []
    assert result["stored"] == []
    assert result["path"] == "/mcp/app" and result["search"] == ""
    assert "synthetic-private-key" not in json.dumps(result)


def test_signup_handoff_and_key_shortcut_use_one_existing_secure_form():
    from html.parser import HTMLParser

    class IDs(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = []

        def handle_starttag(self, tag, attrs):
            self.ids.extend(value for key, value in attrs if key == "id")

    html, _ = render_app_html()
    parser = IDs()
    parser.feed(html)
    assert len(parser.ids) == len(set(parser.ids))
    assert parser.ids.count("paste-blob") == 1
    assert html.index('id="btn-hosted-key"') < html.index('id="btn-openai-connect"')
    assert "Your workspace is ready" in html and "TinyAssets authorization" in html
    assert "No key needs to be copied or pasted" in html
    assert "Signed up, but landed on your OpenRouter workspace?" in html
    assert "You will return here automatically" not in html
    assert "Saving it does not" in html and "approve model access" in html
    assert 'aria-controls="api-key-connection"' in html
    assert 'aria-describedby="paste-key-guidance"' in html


def test_manual_key_posts_once_after_clearing_then_reuses_pending_approval():
    result = run_browser(confirmation() + r"""
const assert=require('node:assert/strict');
HostedModelConnect.setup='empty';HostedModelConnect.showKeyEntry();
$('paste-blob').value='synthetic-private-key';
const realFetch=fetch;fetch=async(...args)=>{
 assert.equal($('paste-blob').value,'');return realFetch(...args);
};
await HostedModelConnect.depositKey();await HostedModelConnect.depositKey();
assert.equal($('paste-blob').value,'');
assert.equal($('btn-hosted-accept').focused,true);
""")
    assert len(result["requests"]) == 1
    call = result["requests"][0]
    assert call["url"] == "/mcp/app/model-connect/deposit_key"
    assert call["body"] == {"preset_id": "openrouter_user_models_v1",
                            "key": "synthetic-private-key"}
    assert "synthetic-private-key" not in call["url"]
    assert not result["answers"] and not result["navigations"] and not result["stored"]
    assert result["request"]["request_id"] == "request-a"
    assert result["confirmationHidden"] is False


@pytest.mark.parametrize("key", ["", "key with space", "key\n", "é", "x" * 2049])
def test_manual_key_validation_clears_without_request(key):
    result = run_browser("HostedModelConnect.setup='empty';HostedModelConnect.showKeyEntry();"
                         "$('paste-blob').value=" + json.dumps(key) + ";"
                         "await HostedModelConnect.depositKey();"
                         "if($('paste-blob').value!=='')throw Error('not cleared');")
    assert not result["requests"] and not result["stored"]
    assert result["setup"] == "empty"


def test_manual_key_login_change_during_refresh_never_sends_under_new_login():
    result = run_browser(r"""
HostedModelConnect.setup='empty';HostedModelConnect.showKeyEntry();
$('paste-blob').value='synthetic-private-key';
ensureFreshToken=async()=>{HostedModelConnect.reset();auth='new-login';};
await HostedModelConnect.depositKey();
""")
    assert not result["requests"] and not result["answers"] and not result["stored"]
    assert "synthetic-private-key" not in json.dumps(result)


@pytest.mark.parametrize("change", ["HostedModelConnect.reset();", "viewGeneration++;"])
def test_manual_late_response_does_not_render_approval_in_changed_login_or_view(change):
    result = run_browser(confirmation() + r"""
HostedModelConnect.setup='empty';HostedModelConnect.showKeyEntry();
$('paste-blob').value='synthetic-private-key';
const original=fetch;
fetch=async(...args)=>{const result=await original(...args);__CHANGE__return result;};
await HostedModelConnect.depositKey();
""".replace("__CHANGE__", change))
    assert len(result["requests"]) == 1
    assert not result["request"] and not result["answers"] and not result["stored"]


def test_manual_timeout_stays_guarded_and_requires_secret_free_resume():
    result = run_browser(confirmation() + r"""
const assert=require('node:assert/strict');
let expire,settle;
globalThis.setTimeout=callback=>{expire=callback;return 1;};
globalThis.clearTimeout=()=>{};
HostedModelConnect.setup='empty';HostedModelConnect.showKeyEntry();
$('paste-blob').value='synthetic-private-key';
const original=fetch;
fetch=async(...args)=>{
 const response=await original(...args);
 return new Promise(resolve=>{settle=()=>resolve(response);});
};
const pending=HostedModelConnect.depositKey();
await Promise.resolve();await Promise.resolve();await Promise.resolve();
expire();assert.equal(HostedModelConnect.busy,true);
await HostedModelConnect.depositKey();settle();await pending;
assert.equal(HostedModelConnect.request,null);
assert.match($('hosted-model-status').textContent,/Resume saved connection/);
fetch=original;await HostedModelConnect.complete();
""")
    assert len(result["requests"]) == 2
    assert result["requests"][1]["url"].endswith("/resume")
    assert result["requests"][1]["body"] == {"preset_id": "openrouter_user_models_v1"}
    assert not result["answers"] and not result["stored"]


def test_manual_unknown_failure_is_redacted_and_not_replayed():
    result = run_browser(r"""
HostedModelConnect.setup='empty';HostedModelConnect.showKeyEntry();
$('paste-blob').value='synthetic-private-key';
exchangeResult={error:'synthetic-private-key'};
await HostedModelConnect.depositKey();await HostedModelConnect.depositKey();
""")
    assert len(result["requests"]) == 1
    assert "synthetic-private-key" not in result["status"]
    assert not result["answers"] and not result["stored"]


def test_manual_approval_keeps_portable_layout_current_owner_hooks():
    result = run_browser(confirmation() + r"""
const assert=require('node:assert/strict'),layoutCalls=[];
globalThis.AppLayout={init(){layoutCalls.push(['init']);},
 reset(){layoutCalls.push(['reset']);},
 enable(home,principal){layoutCalls.push(['enable',home,principal]);}};
await boot();
assert(layoutCalls.some(call=>call[0]==='init'));
assert(layoutCalls.some(call=>call[0]==='reset'));
HostedModelConnect.showKeyEntry();$('paste-blob').value='synthetic-private-key';
await HostedModelConnect.depositKey();
assert(!layoutCalls.some(call=>call[0]==='enable'));
me={setup:'connected',universe_id:'u-owner',principal_id:'owner'};
await HostedModelConnect.answer(true);
assert.deepEqual(layoutCalls.filter(call=>call[0]==='enable'),[['enable','u-owner','owner']]);
""")
    assert len(result["answers"]) == 1
    assert result["setup"] == "connected"


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


@pytest.mark.parametrize("code,expected", [
    ("no_eligible_free_agent_model", "no eligible free model"),
    ("model_authorization_required", "Choose Continue with OpenRouter"),
    ("model_connection_expired", "Choose Continue with OpenRouter"),
    ("unknown_model_connection", "Choose Continue with OpenRouter"),
    ("model_setup_changed", "existing setup needs review"),
    ("current_home_changed", "existing setup needs review"),
    ("model_confirmation_requires_review", "existing setup needs review"),
    ("model_connection_incomplete", "saved connection is not ready yet"),
    ("raw upstream error must not be shown", "saved connection is not ready yet"),
])
def test_recovery_message_matches_safe_error_without_automatic_retry(code, expected):
    result = run_browser("exchangeResult={error:" + json.dumps(code) + "};await boot();"
                         "await HostedModelConnect.complete();")
    assert expected in result["status"]
    assert len(result["requests"]) == 1
    assert not result["answers"] and not result["navigations"]
    assert result["busy"] is False
    assert "raw upstream error" not in result["status"]


def test_missing_authorization_does_not_offer_disabled_restart_for_existing_setup():
    result = run_browser("me={setup:'recovery'};"
                         "exchangeResult={error:'model_authorization_required'};await boot();"
                         "await HostedModelConnect.complete();")
    assert "Existing setup was preserved" in result["status"]
    assert "Choose Continue with OpenRouter" not in result["status"]
    assert result["setup"] == "recovery"
    assert not result["answers"] and not result["navigations"]


def test_key_management_link_uses_readable_existing_link_style():
    html, _ = render_app_html()
    assert ('class="legal-link" data-external href="https://openrouter.ai/settings/keys"'
            in html)


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
