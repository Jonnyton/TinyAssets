"""The blank bundle offers packages; only the owner's existing ask can install."""
# ruff: noqa: F811 -- imported pytest fixtures are injected as test parameters

import json
import re
import sqlite3
from pathlib import Path

import pytest

from tests.test_command_center_packages import (  # noqa: F401
    BOB,
    BOB_UNIVERSE,
    OWNER,
    UNIVERSE,
    _answer,
    _as,
    _ask,
    _bob_files,
    _bobs_branches,
    _pin_data_dir,
    _publish_action,
    cloud_runtime,
    home,
)
from tinyassets.api.graph_reads import read_graph
from tinyassets.api.pending_requests import list_requests, try_package
from tinyassets.command_center_picker import BUILD_PROMPT, PLATFORM_DEFAULT_UI, working_packages

pytestmark = pytest.mark.usefixtures("cloud_runtime")


def _publish(name="First"):
    action = {**_publish_action(), "name": name}
    ask = _ask(OWNER, UNIVERSE, action)
    assert "request_id" in ask, ask
    done = _answer(OWNER, UNIVERSE, ask["request_id"])
    assert done.get("published"), done
    return done["agent_definition_id"]


def _read(actor=BOB, uid=BOB_UNIVERSE, door=read_graph):
    with _as(actor):
        return json.loads(door(target="command_center_packages", graph_id=uid))


def test_both_doors_offer_two_latest_packages(home):
    from tinyassets.universe_server import read_graph as model_read

    first = _publish()
    assert _read()["can_try"] is False
    second = _publish("Second")
    for door in (read_graph, model_read):
        result = _read(door=door)
        assert {p["agent_definition_id"] for p in result["packages"]} == {first, second}
        assert result["can_try"] is True
        assert result["build_prompt"] == BUILD_PROMPT
    # A newer publication of a name replaces its older version, not another card.
    newer = _publish()
    result = _read()
    assert {p["agent_definition_id"] for p in result["packages"]} == {newer, second}
    assert result["packages"][0]["agent_definition_id"] == newer


@pytest.mark.parametrize("broken", ["blob", "private", "missing"])
def test_unhealthy_packages_are_not_offered(home, broken, caplog):
    from tinyassets.command_center_packages import _blob_path
    from tinyassets.custom_agents import get_definition

    definition = get_definition(home, _publish())
    if broken == "blob":
        _blob_path(home, definition["components"]["package"]["blob_sha256"]).unlink()
    else:
        version = next(c["published_version_id"] for c in definition["components"].values()
                       if c["kind"] == "tinyassets.branch-ref.v1")
        from tinyassets.branch_versions import _connect

        with _connect(home) as conn:
            if broken == "private":
                conn.execute("UPDATE branch_versions SET public = 0 WHERE branch_version_id = ?",
                             (version,))
            else:
                conn.execute("DELETE FROM branch_versions WHERE branch_version_id = ?", (version,))
    assert _read()["packages"] == []
    assert "Skipping unhealthy" in caplog.text


def test_read_requires_the_named_centers_owner(home):
    from tinyassets.api.http_connection import _NOT_FOUND
    from tinyassets.universe_server import read_graph as model_read

    for door in (read_graph, model_read):
        assert _read(actor=OWNER, door=door) == _NOT_FOUND
        assert _read(uid="missing", door=door) == _NOT_FOUND


def test_default_is_a_valid_bundle_and_is_not_in_storage(home):
    from tinyassets.custom_agents import _check_app_ui_fields, get_app_ui

    with _as(BOB):
        doc = json.loads(read_graph(target="app_ui", graph_id=BOB_UNIVERSE))
        index = json.loads(read_graph(target="app_ui", graph_id=BOB_UNIVERSE, query="index"))
    bundle = doc["app_ui"]["platform_default"]
    assert bundle == PLATFORM_DEFAULT_UI
    assert bundle["ui_id"] == "platform:blank"
    _check_app_ui_fields({"ui_library": [bundle]})
    stored = get_app_ui(home, owner_user_id=BOB, universe_id=BOB_UNIVERSE)
    assert stored["ui_library"] == [] and stored["revision"] == 0
    assert "platform_default" not in stored
    assert "platform_default" not in index["app_ui"]


def test_try_only_asks_until_the_owner_confirms(home):
    from tinyassets.universe_server import write_graph

    definition_id = _publish()
    before = _bob_files(home)
    assert not _bobs_branches(home)
    with _as(BOB):
        ask = json.loads(write_graph(target="connection", operation="try_package",
                                    graph_id=BOB_UNIVERSE, payload_json=json.dumps(
                                        {"agent_definition_id": definition_id})))
        requests = list_requests(universe_id=BOB_UNIVERSE)["pending"]
    assert set(ask) == {"request_id", "title"}
    pending = next(r for r in requests if r["request_id"] == ask["request_id"])
    assert pending["action"]["type"] == "install"
    assert not _bobs_branches(home) and _bob_files(home) == before
    done = _answer(BOB, BOB_UNIVERSE, ask["request_id"])
    assert done.get("installed"), done
    assert _bobs_branches(home) and _bob_files(home) != before


def test_try_refuses_unknown_package_and_other_owners_center(home):
    from tinyassets.api.http_connection import _NOT_FOUND

    definition_id = _publish()
    with _as(BOB):
        assert "error" in try_package(universe_id=BOB_UNIVERSE,
                                      payload={"agent_definition_id": "not-working"})
        assert try_package(universe_id=UNIVERSE,
                           payload={"agent_definition_id": definition_id}) == _NOT_FOUND


def test_list_failure_warns_and_returns_no_offers(monkeypatch, caplog):
    def fail(**kwargs):
        raise sqlite3.OperationalError("unavailable")

    monkeypatch.setattr("tinyassets.api.package_requests.list_packages", fail)
    assert working_packages() == []
    assert "Could not list" in caplog.text


def test_static_bridge_contract():
    source = Path("tinyassets/onboarding/app_ui.js").read_text(encoding="utf-8")
    actions = source.split("ACTIONS:Object.freeze({", 1)[1].split("})", 1)[0]
    for action in ("packages.list_tryable", "packages.try", "chat.prefill"):
        assert f'"{action}":' in actions
    values = re.findall(r':"([^"]+)"', actions)
    assert not any(word in value.lower() for value in values
                   for word in ("answer", "approve", "withdraw"))
    prefill = source.split("prefillChat(args){", 1)[1].split("\n    },", 1)[0]
    assert "chatCloudPrefill" in prefill and "document." not in prefill
    assert "MAX_MESSAGE" in prefill and "mountDefault(){" in source
    bundle = json.dumps(PLATFORM_DEFAULT_UI)
    for text in ("Build one with your agent", "Try one", "No thanks"):
        assert text in bundle
    assert "Not now" not in bundle


def test_executed_bridge_scopes_asks_and_only_prefills(tmp_path):
    from tests.test_custom_ui_bridge import _run

    checks = r'''
(async()=>{
const u=AppUI;
u.enabled=true;u.home=HOME;u.principal=PRINCIPAL;
u.platformDefault=DEFAULT_BUNDLE;u.mountDefault();
assert(u.parseBundle(DEFAULT_BUNDLE).ok);
assert.equal(u.active.ui_id,'platform:blank');
assert.equal(u.frame.attrs.sandbox,u.SANDBOX);
assert.equal(u.library.length,0);
u.deliver();assert.deepEqual(u.frame.contentWindow.posts[0].bundle,
 {markup:DEFAULT_BUNDLE.markup,style:DEFAULT_BUNDLE.style,script:DEFAULT_BUNDLE.script});
assert.throws(()=>u.prefillChat({text:'build'}),/chat is not available/);
let text='';global.chatCloudPrefill=t=>{text=t;};
u.prefillChat({text:'build'});assert.equal(text,'build');assert.equal(sends.length,0);
assert.throws(()=>u.prefillChat({text:'x'.repeat(u.MAX_MESSAGE+1)}),/too long/);
let release;
MCP.callTool=async(tool,args)=>{
 assert.equal(tool,'write_graph');assert.equal(args.target,'connection');
 assert.equal(args.operation,'try_package');assert.equal(args.graph_id,HOME);
 assert.deepEqual(JSON.parse(args.payload_json),{agent_definition_id:'d1'});
 await new Promise(r=>release=r);return {request_id:'r1',title:'Install',secret:'hidden'};
};
const ask=u.tryPackage({agent_definition_id:'d1',graph_id:'other',operation:'answer_request'});
await assert.rejects(u.tryPackage({agent_definition_id:'d1'}),/already in flight/);
release();assert.deepEqual(await ask,{request_id:'r1'});
Owner.read=async args=>{
 assert.deepEqual(args,{target:'command_center_packages',graph_id:HOME});
 return {packages:[{agent_definition_id:'d1',name:'One',description:'',author_id:'Alice',
 version:1,size:'1 KB',file_count:1,needs:{model:'',connections:[],secret:'hidden'},
 secret:'hidden'}],build_prompt:'build',can_try:false,secret:'hidden'};
};
const list=await u.listTryablePackages();assert.equal(list.can_try,false);
assert(!JSON.stringify(list).includes('secret'));
Owner.read=async()=>({packages:[],build_prompt:'build',can_try:true});
await assert.rejects(u.listTryablePackages(),/unavailable/);
console.log('picker bridge passed');
})().catch(e=>{console.error(e);process.exit(1);});
'''
    out = _run(tmp_path, "picker.js", checks,
               extra="const DEFAULT_BUNDLE=" + json.dumps(PLATFORM_DEFAULT_UI) + ";\n")
    assert "picker bridge passed" in out
# -- lead decision: installing and composing are the PLATFORM's, not a UI's ----


def test_only_the_platform_bundle_may_install_or_prefill(tmp_path):
    """``packages.try`` and ``chat.prefill`` are refused to a third-party UI.

    They are the app's own offer to the owner: one installs software as them,
    the other composes a message as them. A UI someone else wrote must not be
    able to reach either, and the check is on the bundle MOUNTED NOW -- a
    bundle cannot name itself ``platform:blank`` to acquire them, because
    ID_RE forbids the colon everywhere except the row the server sends.
    ``packages.list_tryable`` stays open: it only reads what is published.
    """
    from tests.test_custom_ui_bridge import _run

    checks = r"""
(async()=>{
const u=AppUI;
u.enabled=true;u.home=HOME;u.principal=PRINCIPAL;
let prefilled=0;global.chatCloudPrefill=()=>{prefilled++;};
let installs=0;
MCP.callTool=async()=>{installs++;return {request_id:'r1'};};
Owner.read=async()=>({packages:[],build_prompt:'build',can_try:false});

const ask=async(action,params)=>{
 const win=u.frame.contentWindow,before=win.posts.length;
 u.receive({source:win,data:{ta_ui:1,type:'call',id:'q'+before,action,params:params||{}}});
 for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));
 assert(win.posts.length>before,'the bridge always answers '+action);
 return win.posts[win.posts.length-1];
};

// A UI the owner installed. It may read the offers and nothing more.
u.mount({kind:u.KIND,version:1,ui_id:'third-party',name:'Theirs',
 markup:'<p>x</p>',style:'',script:''});
assert.equal(u.isPlatformDefault(),false);
const listed=await ask('packages.list_tryable',{});
assert.equal(listed.ok,true,'reading the offers stays open to any UI');
for(const action of ['packages.try','chat.prefill']){
 const answer=await ask(action,{agent_definition_id:'d1',text:'build'});
 assert.equal(answer.ok,false,action+' must be refused to a third-party UI');
 assert.match(answer.error,/action not available/);
}
assert.equal(installs,0,'nothing was installed');
assert.equal(prefilled,0,'nothing was composed');

// Naming itself the platform's does not make it so: parseBundle refuses the
// colon, so such a bundle can never become `active` through install.
assert.equal(u.parseBundle({kind:u.KIND,version:1,ui_id:'platform:blank',
 name:'Impostor',markup:'',style:'',script:''}).ok,true,
 'the server-sent row parses');
u.mount({kind:u.KIND,version:1,ui_id:'platform:blank',name:'Impostor',
 markup:'',style:'',script:''});
assert.equal(u.isPlatformDefault(),false,
 'only mountDefault grants the platform identity, not the id alone');
const stolen=await ask('chat.prefill',{text:'build'});
assert.equal(stolen.ok,false);
assert.equal(prefilled,0);

// The platform's own blank command center may ask.
u.platformDefault=DEFAULT_BUNDLE;u.mountDefault();
assert.equal(u.isPlatformDefault(),true);
const allowed=await ask('chat.prefill',{text:'build'});
assert.equal(allowed.ok,true);
assert.equal(prefilled,1);
const install=await ask('packages.try',{agent_definition_id:'d1'});
assert.equal(install.ok,true);
assert.equal(installs,1);

// ...and loses it the moment another bundle takes the screen.
u.mount({kind:u.KIND,version:1,ui_id:'third-party',name:'Theirs',
 markup:'<p>x</p>',style:'',script:''});
assert.equal(u.isPlatformDefault(),false);
const after=await ask('packages.try',{agent_definition_id:'d1'});
assert.equal(after.ok,false);
assert.equal(installs,1);
console.log('picker authority passed');
})().catch(e=>{console.error(e);process.exit(1);});
"""
    out = _run(tmp_path, "picker_authority.js", checks,
               extra="const DEFAULT_BUNDLE=" + json.dumps(PLATFORM_DEFAULT_UI) + ";\n")
    assert "picker authority passed" in out


def test_the_allowlist_names_exactly_the_platform_only_actions():
    """The gate's list is pinned: adding a platform action to ACTIONS without
    adding it here would hand it to every UI."""
    source = Path("tinyassets/onboarding/app_ui.js").read_text(encoding="utf-8")
    block = source.split("PLATFORM_ONLY:[", 1)[1].split("]", 1)[0]
    assert sorted(re.findall(r'"([^"]+)"', block)) == ["chat.prefill", "packages.try"]
    assert 'PLATFORM_UI_ID:"platform:blank"' in source
    # Enforced in serve(), the one place every call passes through.
    served = source.split("async serve(id,action,params){", 1)[1].split("\n    },", 1)[0]
    assert "this.PLATFORM_ONLY.indexOf(action)>=0 && !this.isPlatformDefault()" in served
