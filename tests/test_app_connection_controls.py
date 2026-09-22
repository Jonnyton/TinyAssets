"""Execute shipped connection UI with synthetic transport; not live acceptance.

The controller under test is the REAL source sliced out of the shipped
``app.html`` — only the transport, the DOM and the account/home globals are
synthetic. Disconnect confirms in the page now: the first click reveals what
would happen, and only a second, separate click writes anything.
"""

import json
import re
import shutil
import subprocess

from tinyassets.onboarding import render_app_html

_SLICE_START = "    // ---- your universe's connections ----"
_SLICE_END = "    function leaveAccount()"

# A synthetic DOM that records what the controller did to it: attributes (the
# accessibility contract), focus moves (which control Enter would hit), hidden
# state, and removal. Nothing here interprets HTML — only what the code sets.
HARNESS = r"""
const elements=new Map(),requests=[],focusLog=[],hooks={};
function node(tag){return {tag,children:[],attrs:{},textContent:'',id:'',className:'',type:'',
 disabled:false,hidden:false,
 replaceChildren(){this.children=[];},append(...nodes){this.children.push(...nodes);},
 setAttribute(k,v){this.attrs[k]=String(v);},
 getAttribute(k){return Object.prototype.hasOwnProperty.call(this.attrs,k)?this.attrs[k]:null;},
 addEventListener(event,handler){this[event]=handler;},
 focus(){focusLog.push(this.id||this.textContent||this.tag);},
 remove(){this.removed=true;}};}
const $=id=>{if(!elements.has(id)){const e=node(id);e.id=id;elements.set(id,e);}
 return elements.get(id);};
const document={createElement:node};
// The durable account/home pair the page learns from the verified /mcp/app/me,
// and the access token, which rotates on an unchanged sign-in.
let queueOwner='acct-owner',queueScope='u-owner',accessToken='tok-1';
const token=()=>accessToken,authHeaders=()=>accessToken?{Authorization:'Bearer '+accessToken}:{};
let engineConnected=true,HostedModelConnect={setup:'connected',paint(){}};
let failPost=false,postRefuses=false,meOk=true,getRefuses=false;
let connections=[{connection_id:'c1',destination:'my-service',incarnation:'first-incarnation'}];
const fire=name=>{if(hooks[name])hooks[name]();};
const fetch=async(url,options={})=>{
 const method=options.method||'GET';
 const kind=method==='POST'?'post':(url.endsWith('/me')?'me':'get');
 requests.push({url,method,kind,body:options.body&&JSON.parse(options.body),
   auth:(options.headers||{}).Authorization||null});
 fire(kind);                        // something changes while the call is in flight
 if(kind==='post'&&failPost)throw new Error('network result ambiguous');
 if(kind==='post')return {ok:!postRefuses,json:async()=>{fire('postJson');
   return postRefuses?{error:'refused'}:{status:'removed'};}};
 if(kind==='me')return {ok:meOk,json:async()=>{fire('meJson');
   return {engine_connected:false,setup:'disconnected'};}};
 return {ok:!getRefuses,json:async()=>{fire('getJson');
   return getRefuses?{error:'unavailable'}:{universe_id:'u-owner',connections};}};
};
__SOURCE__
const rowAt=i=>$('connection-list').children[i];
const row=()=>rowAt(0),reveal=i=>rowAt(i||0).children[1],panel=i=>rowAt(i||0).children[2];
const approve=i=>panel(i).children[1],cancel=i=>panel(i).children[2];
const describe=n=>({removed:!!n.removed,text:n.children[0].textContent,
 revealExpanded:n.children[1].getAttribute('aria-expanded'),
 revealControls:n.children[1].getAttribute('aria-controls'),
 revealDisabled:n.children[1].disabled,revealTag:n.children[1].tag,
 revealType:n.children[1].type,revealText:n.children[1].textContent,
 panelId:n.children[2].id,panelHidden:n.children[2].hidden,panelAttrs:n.children[2].attrs,
 explainId:n.children[2].children[0].id,explain:n.children[2].children[0].textContent,
 buttons:n.children[2].children.slice(1).map(b=>({tag:b.tag,type:b.type,
   text:b.textContent,disabled:b.disabled}))});
(async()=>{
 __STEPS__
 console.log(JSON.stringify({requests,status:$('connection-status').textContent,
   rows:$('connection-list').children.map(describe),focusLog,owner:queueOwner,
   engineConnected,setup:HostedModelConnect.setup,busy:connectionsBusy,
   refreshDisabled:$('btn-refresh-connections').disabled}));
})().catch(e=>{console.error(e);process.exitCode=1;});
"""


def controller_source():
    html, _ = render_app_html()
    return html[html.index(_SLICE_START) : html.index(_SLICE_END)]


def run(steps):
    program = HARNESS.replace("__SOURCE__", controller_source()).replace("__STEPS__", steps)
    result = subprocess.run(
        [shutil.which("node"), "-e", program],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def posts(result):
    return [r for r in result["requests"] if r["method"] == "POST"]


REVEAL = "await loadConnections(); reveal().click();"
CONFIRM = REVEAL + " await approve().click();"


# ---- step one: revealing is read-only -------------------------------------


def test_revealing_the_confirmation_writes_nothing_and_says_what_it_would_do():
    result = run(REVEAL)
    assert posts(result) == []
    assert [r["method"] for r in result["requests"]] == ["GET"]
    row = result["rows"][0]
    assert row["panelHidden"] is False and row["revealExpanded"] == "true"
    explain = row["explain"]
    # The words being authorised, kept from the dialog this replaced.
    assert "my-service" in explain
    assert "saved key" in explain and "model access" in explain
    assert "history and your designs stay" in explain
    assert "provider account itself is not changed or deleted" in explain
    assert "already sent may still finish" in explain
    assert "Nothing has been sent" in result["status"]


def test_cancel_is_read_only():
    result = run(REVEAL + " cancel().click();")
    assert all(r["method"] == "GET" for r in result["requests"])
    row = result["rows"][0]
    assert row["panelHidden"] is True and row["revealExpanded"] == "false"
    assert row["removed"] is False
    assert "still connected" in result["status"]
    # Focus goes back to the control that opened it, not nowhere.
    assert result["focusLog"][-1] == "Disconnect"


def test_confirmation_is_keyboard_reachable_and_is_not_the_default_action():
    result = run(REVEAL)
    row = result["rows"][0]
    # Focus lands on the explanation group, so Enter authorises nothing; the
    # destructive control is the next thing Tab reaches.
    assert result["focusLog"] == [row["panelId"]]
    assert row["panelAttrs"]["tabindex"] == "-1"
    assert row["panelAttrs"]["role"] == "group"
    assert "my-service" in row["panelAttrs"]["aria-label"]
    assert row["panelAttrs"]["aria-describedby"] == row["explainId"]
    assert row["revealControls"] == row["panelId"]
    assert [(b["tag"], b["type"], b["text"]) for b in row["buttons"]] == [
        ("button", "button", "Confirm disconnect"),
        ("button", "button", "Cancel"),
    ]


def _calls(name, source):
    """A call to `name`, ignoring full-line comments — prose is not a call."""
    code = "\n".join(line for line in source.splitlines() if not line.strip().startswith("//"))
    return re.search(r"(?<![\w.$])" + name + r"\s*\(", code)


def test_connection_ui_raises_no_native_dialog():
    # The detector fires on the shape this replaced, so a pass means absence.
    assert _calls("confirm", 'if(!confirm("Disconnect x?"))return;')
    source = controller_source()
    for name in ("confirm", "alert", "prompt"):
        assert not _calls(name, source), name
    assert "Confirm disconnect" in source  # the in-page control is still there


def test_only_one_confirmation_is_open_at_a_time():
    result = run(
        "connections=[{connection_id:'c1',destination:'my-service',incarnation:'i1'},"
        "{connection_id:'c2',destination:'other-service',incarnation:'i2'}];"
        "await loadConnections(); reveal(0).click(); reveal(1).click();"
    )
    assert posts(result) == []
    assert result["rows"][0]["panelHidden"] is True
    assert result["rows"][1]["panelHidden"] is False


# ---- step two: exactly one write, for exactly what was shown --------------


def test_disconnect_uses_observed_connection_and_shows_unpowered_reconnect():
    result = run(CONFIRM)
    assert result["requests"][1]["body"] == {
        "universe_id": "u-owner",
        "destination": "my-service",
        "incarnation": "first-incarnation",
    }
    assert len(posts(result)) == 1
    assert result["engineConnected"] is False and result["setup"] == "disconnected"
    assert "provider account is unchanged" in result["status"]
    assert result["rows"][0]["removed"] is True


def test_double_confirm_click_sends_one_write():
    result = run(
        REVEAL + " const btn=approve(); const a=btn.click(), b=btn.click(); await a; await b;"
    )
    assert len(posts(result)) == 1
    assert result["busy"] is False


def test_uncertain_disconnect_does_not_replay_or_claim_success():
    result = run("failPost=true; " + CONFIRM)
    assert len(posts(result)) == 1
    assert "not confirmed" in result["status"]
    assert "Refresh connections" in result["status"]
    assert not result["rows"][0]["removed"]
    assert result["rows"][0]["panelHidden"] is True
    assert result["engineConnected"] is True


def test_refused_disconnect_is_not_reported_as_success():
    result = run("postRefuses=true; " + CONFIRM)
    assert len(posts(result)) == 1
    assert "not confirmed" in result["status"]
    assert not result["rows"][0]["removed"]
    assert result["engineConnected"] is True


def test_a_confirmed_disconnect_is_not_unsaid_by_a_failed_state_read():
    result = run("meOk=false; " + CONFIRM)
    assert len(posts(result)) == 1
    assert result["rows"][0]["removed"] is True
    assert "Disconnected from TinyAssets" in result["status"]
    assert "refresh this page" in result["status"]
    assert "not confirmed" not in result["status"]


def test_a_reloaded_list_disarms_an_open_confirmation():
    result = run(REVEAL + " const stale=approve(); await loadConnections(); await stale.click();")
    assert posts(result) == []
    assert "refreshed while the confirmation was open" in result["status"]
    assert "Nothing was sent" in result["status"]


# ---- the fence: account, home, sign-in --------------------------------------


def test_old_owner_response_is_not_rendered_after_account_change():
    result = run("hooks.getJson=()=>{queueOwner='another-account';}; await loadConnections();")
    assert result["rows"] == []
    assert "Checking your connections" in result["status"]


def test_account_change_before_confirming_sends_nothing():
    result = run(REVEAL + " queueOwner='another-account'; await approve().click();")
    assert posts(result) == []
    assert "Nothing was sent" in result["status"]


def test_home_change_before_confirming_sends_nothing():
    result = run(REVEAL + " queueScope='u-other-home'; await approve().click();")
    assert posts(result) == []
    assert "Nothing was sent" in result["status"]


def test_account_change_during_the_write_repaints_nothing():
    result = run("hooks.postJson=()=>{queueOwner='another-account';}; " + CONFIRM)
    assert len(posts(result)) == 1
    assert [r["kind"] for r in result["requests"]] == ["get", "post"]  # no /me for the newcomer
    assert not result["rows"][0]["removed"]
    assert result["engineConnected"] is True and result["setup"] == "connected"
    assert "Disconnecting" in result["status"]
    assert result["busy"] is False  # the lock is released, not wedged shut


def test_sign_out_during_the_write_repaints_nothing():
    result = run("hooks.postJson=()=>{accessToken=null;}; " + CONFIRM)
    assert len(posts(result)) == 1
    assert not result["rows"][0]["removed"]
    assert result["engineConnected"] is True and result["setup"] == "connected"


def test_ordinary_token_rotation_neither_blocks_nor_reauthorises():
    result = run("hooks.postJson=()=>{accessToken='tok-2';}; " + CONFIRM)
    assert len(posts(result)) == 1
    assert result["rows"][0]["removed"] is True
    assert result["engineConnected"] is False and result["setup"] == "disconnected"
    assert result["owner"] == "acct-owner"
    # The write carried the token that was current when it was sent.
    assert posts(result)[0]["auth"] == "Bearer tok-1"


def test_rotation_between_reveal_and_confirm_still_disconnects():
    result = run(REVEAL + " accessToken='tok-2'; await approve().click();")
    assert len(posts(result)) == 1
    assert posts(result)[0]["auth"] == "Bearer tok-2"
    assert result["rows"][0]["removed"] is True


def test_a_failed_load_reports_it_and_leaves_the_list_usable():
    result = run("getRefuses=true; await loadConnections();")
    assert result["rows"] == []
    assert "Could not load your connections" in result["status"]
    assert result["busy"] is False and result["refreshDisabled"] is False
