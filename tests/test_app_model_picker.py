"""Execute the actual picker with synthetic DOM/transport; not live UI proof."""

import json
import shutil
import subprocess

import pytest

from tests.test_onboarding_app import _js_function
from tinyassets.onboarding import render_app_html


def ref(name):
    return {"provider_ref": "owned:future-source", "model_id": name}


def catalogue():
    return {
        "version": 1,
        "kind": "advisory_model_options",
        "universe_id": "home-a",
        "choice_authority": "accepted_manifest",
        "binding_state": "serving",
        "preferences": {"generation": 2, "policy": None},
        "sources": [],
        "source_failures": [],
        "unavailable": [],
        "order": [ref("first"), ref("second")],
        "options": [
            {
                "reference": ref(name),
                "in_candidate_catalog": True,
                "freshness": "fresh",
                "reasons": [],
            }
            for name in ("first", "second", "third")
        ],
    }


def run_picker(tmp_path, steps, doc=None, response=None):
    html, _ = render_app_html()
    picker = html[html.index("  const ModelPicker={") : html.index("  function captureTurnOptions")]
    program = r"""
const elements=new Map();
class Element {
  constructor(){this.children=[];this.textContent="";this.value="";this.disabled=false;this.events={};this.open=false;}
  replaceChildren(){this.children=[];}
  appendChild(child){this.children.push(child);return child;}
  setAttribute(key,value){this[key]=value;}
  addEventListener(key,fn){this.events[key]=fn;}
  focus(){focused=this;}
  showModal(){this.open=true;}
  close(){this.open=false;if(this.events.close)this.events.close();}
}
let focused=null;
const $=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const document={createElement:()=>new Element()};
let modelChoiceForNextTurn=null,requests=[],expired=false,refreshed=0,connects=0;
let confirmed=true,confirmations=[],writes=[];
const confirm=text=>{confirmations.push(text);return confirmed;};
const setTimeout=fn=>{globalThis.expire=fn;return 1;},clearTimeout=()=>{};
const ensureFreshToken=async()=>{refreshed++;},authHeaders=()=>({Authorization:"test fixture"});
const sessionExpired=()=>{expired=true;ModelPicker.reset();};
const showConnect=()=>{connects++;};
let doc=__DOC__,response=__RESPONSE__;
const MCP={getModelOptions:async()=>JSON.parse(JSON.stringify(doc))};
MCP.callTool=async(name,args)=>{
 writes.push({name,args});
 if(name==="read_graph")
  return {binding:{agent_binding_id:"binding-a",revision:3,status:"configured"}};
 return args.operation==="bind_serving_provider"
  ?{status:"ready",agent_binding:{agent_binding_id:"binding-a",revision:3}}
  :{status:"serving",agent_binding:{agent_binding_id:"binding-a",revision:4}};
};
let fetch=async(url,options)=>{
 requests.push({url,method:options.method,body:JSON.parse(options.body)});
 return {ok:!response.error,status:response.error?409:200,json:async()=>response};
};
__FUNCTIONS__
(async()=>{
 ModelPicker.init();await ModelPicker.open();
 __STEPS__
 const ids=["btn-models","model-next","model-status","model-actual","model-primary",
   "btn-model-use","btn-model-save","model-fallbacks","model-inventory","model-saved"];
 const ui=Object.fromEntries(ids.map(id=>[id,{text:$(id).textContent,disabled:$(id).disabled,
   children:$(id).children.map(c=>({text:c.textContent,value:c.value,disabled:c.disabled}))}]));
 console.log(JSON.stringify({choice:modelChoiceForNextTurn,draft:ModelPicker.draft,
   snapshot:ModelPicker.snapshot,stale:ModelPicker.stale,busy:ModelPicker.busy,requests,
   expired,refreshed,connects,writes,confirmations,recovery:ModelPicker.recovery,dialogOpen:$("model-dialog").open,
   focusReturned:focused===$("btn-models"),ui}));
})().catch(err=>{console.error(err);process.exitCode=1;});
"""
    response = response or {
        "universe_id": "home-a",
        "generation": 3,
        "policy": {"version": 1, "mode": "automatic", "saved_default": None, "fallbacks": []},
        "updated_at": "2026-09-10T19:30:00Z",
    }
    program = (
        program.replace("__DOC__", json.dumps(catalogue() if doc is None else doc))
        .replace("__RESPONSE__", json.dumps(response))
        .replace("__FUNCTIONS__", _js_function(html, "copyModelChoice") + picker)
        .replace("__STEPS__", steps)
    )
    script = tmp_path / "picker.js"
    script.write_text(program, encoding="utf-8")
    node = shutil.which("node")
    assert node, "Node is required to execute the app picker"
    result = subprocess.run(
        [node, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=20
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def choose(name):
    return "ModelPicker.select(ModelPicker.key(" + json.dumps(ref(name)) + "));"


def add(name):
    return "ModelPicker.addFallback(ModelPicker.key(" + json.dumps(ref(name)) + "));"


def test_selection_order_is_copied_and_actual_receipt_is_separate(tmp_path):
    result = run_picker(
        tmp_path,
        choose("first")
        + add("second")
        + add("third")
        + """
      ModelPicker.move(1,-1);ModelPicker.use();
      ModelPicker.draft.saved_default.model_id="changed after use";
      ModelPicker.observe("Answered by another source · reported model");
    """,
    )
    assert result["choice"]["saved_default"] == ref("first")
    assert result["choice"]["fallbacks"] == [ref("third"), ref("second")]
    assert "reported model" in result["ui"]["btn-models"]["text"]
    assert "first" in result["ui"]["model-next"]["text"]
    assert result["snapshot"]["preferences"]["policy"] is None
    assert result["requests"] == []


def test_configured_source_claims_are_visible_without_disabling_permitted_choice(tmp_path):
    doc = catalogue()
    doc["options"][0]["availability_basis"] = "owner_configured_contract"
    result = run_picker(tmp_path, choose("first") + "ModelPicker.use();", doc)
    assert result["choice"]["saved_default"] == ref("first")
    text = result["ui"]["model-inventory"]["children"][0]["text"]
    assert "availability, privacy and charges" in text and "not independently verified" in text
    other = result["ui"]["model-inventory"]["children"][1]["text"]
    assert "not independently verified" not in other


def test_remove_last_fallback_preserves_explicit_empty_list(tmp_path):
    result = run_picker(
        tmp_path, choose("first") + add("second") + "ModelPicker.move(0,0);ModelPicker.use();"
    )
    assert result["choice"]["fallbacks"] == []
    assert result["choice"]["mode"] == "explicit"


def test_duplicates_primary_and_repeated_fallback_are_not_added(tmp_path):
    result = run_picker(tmp_path, choose("first") + add("first") + add("second") + add("second"))
    assert result["draft"]["fallbacks"] == [ref("second")]


def test_automatic_replaces_whole_current_order_and_saved_default_clears_override(tmp_path):
    result = run_picker(
        tmp_path,
        choose("first")
        + add("second")
        + """
      ModelPicker.use();ModelPicker.select("");ModelPicker.use();
    """,
    )
    assert result["choice"] == {
        "version": 1,
        "mode": "automatic",
        "saved_default": None,
        "fallbacks": [],
    }
    result = run_picker(tmp_path, choose("first") + "ModelPicker.use();ModelPicker.useSaved();")
    assert result["choice"] is None


@pytest.mark.parametrize(
    "failure", ["source_not_accepted", "outside_accepted_model_scope", "cost_exceeds_cap"]
)
def test_unavailable_model_visible_but_cannot_be_selected_or_authorize_cost(tmp_path, failure):
    doc = catalogue()
    doc["options"][0]["reasons"] = [{"reason": failure}]
    doc["options"][0]["in_candidate_catalog"] = False
    result = run_picker(tmp_path, choose("first"), doc)
    assert result["draft"]["mode"] == "automatic"
    assert result["ui"]["model-primary"]["children"][1]["disabled"]
    assert failure.replace("_", " ") in result["ui"]["model-inventory"]["children"][0]["text"]
    assert result["requests"] == []


def test_complete_catalogue_and_opaque_labels_are_preserved(tmp_path):
    doc = catalogue()
    doc["options"] *= 24
    doc["options"][0] = {**doc["options"][0], "reference": ref('<img onerror="bad"> / モデル')}
    result = run_picker(tmp_path, "", doc)
    assert len(result["ui"]["model-primary"]["children"]) == 73
    assert '<img onerror="bad">' in result["ui"]["model-primary"]["children"][1]["text"]


@pytest.mark.parametrize("state", ["legacy_single_provider", "none"])
def test_unpowered_or_legacy_can_save_auto_but_cannot_invent_override_authority(tmp_path, state):
    doc = catalogue()
    doc["choice_authority"] = state
    result = run_picker(tmp_path, "ModelPicker.use();", doc)
    assert result["choice"] is None
    assert result["ui"]["btn-model-use"]["disabled"]
    assert not result["ui"]["btn-model-save"]["disabled"]


def test_save_exact_home_and_generation_never_grants_or_silently_switches(tmp_path):
    result = run_picker(tmp_path, choose("first") + "await ModelPicker.save();")
    assert result["requests"] == [
        {
            "url": "/mcp/app/models/preferences?universe_id=home-a",
            "method": "POST",
            "body": {
                "expected_generation": 2,
                "policy": {
                    "version": 1,
                    "mode": "explicit",
                    "saved_default": ref("first"),
                    "fallbacks": [],
                },
            },
        }
    ]
    assert result["choice"] is None
    assert result["snapshot"]["preferences"]["generation"] == 3
    assert result["stale"] and not result["busy"]


@pytest.mark.parametrize("error", ["model_preferences_conflict", "model_preference_home_changed"])
def test_save_refusal_is_not_retried_and_settings_are_not_claimed_saved(tmp_path, error):
    result = run_picker(
        tmp_path, "await ModelPicker.save();await ModelPicker.save();", response={"error": error}
    )
    assert len(result["requests"]) == 1
    assert result["snapshot"]["preferences"]["generation"] == 2
    assert result["stale"]
    assert "saved." not in result["ui"]["model-status"]["text"]


def test_ambiguous_save_requires_read_not_automatic_replay(tmp_path):
    result = run_picker(
        tmp_path,
        """
      fetch=async()=>{requests.push({});throw new Error("network");};
      await ModelPicker.save();await ModelPicker.save();
    """,
    )
    assert len(result["requests"]) == 1
    assert "Could not confirm" in result["ui"]["model-status"]["text"]


def test_refresh_failure_retains_labelled_stale_rows_and_blocks_changes(tmp_path):
    result = run_picker(
        tmp_path,
        choose("first")
        + """
      MCP.getModelOptions=async()=>{throw new Error("offline");};
      await ModelPicker.refresh();ModelPicker.use();await ModelPicker.save();
    """,
    )
    assert result["choice"] is None and result["requests"] == []
    assert "stale" in result["ui"]["model-inventory"]["children"][0]["text"]
    assert result["ui"]["btn-model-use"]["disabled"]


def test_expiry_disables_apply_without_altering_captured_choice(tmp_path):
    result = run_picker(
        tmp_path, choose("first") + "ModelPicker.use();expire();ModelPicker.select('');"
    )
    assert result["choice"]["saved_default"] == ref("first")
    assert result["stale"] and result["ui"]["btn-model-save"]["disabled"]


def test_late_refresh_after_signout_cannot_repopulate_dialog(tmp_path):
    result = run_picker(
        tmp_path,
        """
      let finish;MCP.getModelOptions=()=>new Promise(resolve=>{finish=resolve;});
      const pending=ModelPicker.refresh();ModelPicker.reset();finish(doc);await pending;
    """,
    )
    assert result["snapshot"] is None and result["choice"] is None
    assert not result["dialogOpen"] and not result["busy"]


def test_refresh_home_change_clears_old_current_choice(tmp_path):
    result = run_picker(
        tmp_path,
        choose("first") + "ModelPicker.use();doc.universe_id='home-b';await ModelPicker.refresh();",
    )
    assert result["choice"] is None
    assert result["snapshot"]["universe_id"] == "home-b"


def test_native_dialog_close_returns_focus_and_connection_is_real_action(tmp_path):
    result = run_picker(
        tmp_path, '$("btn-model-close").events.click();$("btn-model-connect").events.click();'
    )
    assert result["focusReturned"] and not result["dialogOpen"] and result["connects"] == 1
    html, _ = render_app_html()
    assert '<dialog id="model-dialog"' in html
    assert 'aria-controls="model-dialog"' in html


def test_delayed_save_json_cannot_touch_another_login_snapshot(tmp_path):
    result = run_picker(
        tmp_path,
        """
      let finish;
      fetch=async()=>({ok:true,status:200,json:()=>new Promise(resolve=>{finish=resolve;})});
      const pending=ModelPicker.save();
      while(!finish) await Promise.resolve();
      ModelPicker.reset();doc.universe_id="home-b";await ModelPicker.refresh();
      finish(response);await pending;
    """,
    )
    assert result["snapshot"]["universe_id"] == "home-b"
    assert result["snapshot"]["preferences"]["generation"] == 2
    assert not result["stale"] and not result["busy"]


def test_failed_first_read_does_not_invent_saved_automatic_default(tmp_path):
    result = run_picker(tmp_path, "", doc={"error": "model_options_unavailable"})
    assert result["snapshot"] is None
    assert result["ui"]["model-saved"]["text"] == "Saved default: Not loaded"
    assert result["ui"]["btn-model-save"]["disabled"]


def test_successful_read_without_saved_policy_truthfully_shows_automatic(tmp_path):
    result = run_picker(tmp_path, "")
    assert result["snapshot"]["preferences"]["policy"] is None
    assert result["ui"]["model-saved"]["text"] == "Saved default: Automatic"


def access_catalogue(*, legacy=False, native=False):
    doc = catalogue()
    doc["binding"] = {"id": "binding-a", "revision": 2}
    doc["accepted_model_access"] = {}
    source = {
        "provider_ref": ref("first")["provider_ref"],
        "bind_key": "server-key",
        "access_method": "subscription_cli" if native else "api_key_http",
        "accepted": False,
    }
    doc["sources"] = [source]
    doc["legacy_source"] = {**source, "model_id": "" if native else "old-fixed"} if legacy else None
    if legacy:
        doc["choice_authority"] = "legacy_single_provider"
    for row in doc["options"]:
        row["reasons"] = [{"reason": "source_not_accepted"}]
        row["in_candidate_catalog"] = False
    if native:
        doc["options"] = [doc["options"][0]]
        doc["options"][0]["reference"]["model_id"] = ""
    return doc


def test_access_cancel_has_no_write_or_preference_change(tmp_path):
    result = run_picker(
        tmp_path,
        "confirmed=false;await ModelPicker.allowAccess(doc.sources[0]);",
        access_catalogue(),
    )
    assert result["writes"] == [] and result["requests"] == [] and result["choice"] is None
    assert "3 compatible" in result["confirmations"][0]


@pytest.mark.parametrize("native", [False, True])
def test_confirmed_access_uses_server_discriminator_and_returned_revision(tmp_path, native):
    result = run_picker(
        tmp_path,
        "await ModelPicker.allowAccess(doc.sources[0]);",
        access_catalogue(legacy=True, native=native),
    )
    bind, enable = result["writes"]
    args = bind["args"]
    assert args["target"] == "agent_binding" and args["graph_id"] == "home-a"
    assert args["expected_revision"] == 2 and args["agent_binding_id"] == "binding-a"
    assert json.loads(args["payload_json"]) == {
        "provider": "server-key",
        "model_access": {
            "server-key": {
                "model_scope": "explicit" if native else "discovered",
                "model_ids": [""] if native else [],
                "cost_caps": None,
            }
        },
    }
    assert enable["args"]["operation"] == "set_serving"
    assert enable["args"]["expected_revision"] == 3
    assert json.loads(enable["args"]["payload_json"]) == {"enabled": True}
    assert result["requests"] == [] and result["choice"] is None


def test_expansion_preserves_existing_spending_and_all_other_members(tmp_path):
    doc = access_catalogue()
    old = {
        "server-key": {
            "model_scope": "explicit",
            "model_ids": ["old"],
            "cost_caps": {"input_million_tokens_usd": 1250000},
        },
        "another-key": {"model_scope": "explicit", "model_ids": ["keep"], "cost_caps": None},
    }
    doc["accepted_model_access"] = old
    result = run_picker(tmp_path, "await ModelPicker.allowAccess(doc.sources[0]);", doc)
    changed = json.loads(result["writes"][0]["args"]["payload_json"])["model_access"]
    assert changed["another-key"] == old["another-key"]
    assert changed["server-key"]["cost_caps"] == old["server-key"]["cost_caps"]
    assert changed["server-key"]["model_scope"] == "discovered"


@pytest.mark.parametrize(
    "reason", ["cost_exceeds_cap", "source_revoked", "engine_tools_unavailable"]
)
def test_zero_eligible_models_cannot_begin_access_conversion(tmp_path, reason):
    doc = access_catalogue(legacy=True)
    for row in doc["options"]:
        row["reasons"].append({"reason": reason})
    result = run_picker(tmp_path, "await ModelPicker.allowAccess(doc.sources[0]);", doc)
    assert result["writes"] == [] and result["confirmations"] == []


def test_legacy_conversion_cannot_silently_replace_another_source(tmp_path):
    doc = access_catalogue(legacy=True)
    doc["legacy_source"]["provider_ref"] = "a-different-current-source"
    result = run_picker(tmp_path, "await ModelPicker.allowAccess(doc.sources[0]);", doc)
    assert result["writes"] == []


def test_ambiguous_binding_is_not_retried_or_followed_by_enable(tmp_path):
    result = run_picker(
        tmp_path,
        """
      MCP.callTool=async(name,args)=>{writes.push({name,args});throw new Error("network");};
      await ModelPicker.allowAccess(doc.sources[0]);await ModelPicker.allowAccess(doc.sources[0]);
    """,
        access_catalogue(legacy=True),
    )
    assert len(result["writes"]) == 1 and result["stale"]
    assert result["recovery"] is None


def test_failed_reconnect_has_explicit_fenced_legacy_restore(tmp_path):
    result = run_picker(
        tmp_path,
        """
      const original=MCP.callTool;
      MCP.callTool=async(name,args)=>{
        if(args.operation==="set_serving"&&writes.length===1){
          writes.push({name,args});return {error:"held"};
        }
        return original(name,args);
      };
      await ModelPicker.allowAccess(doc.sources[0]);
      if(!ModelPicker.recovery) throw new Error("missing recovery");
      await ModelPicker.restoreAccess();
    """,
        access_catalogue(legacy=True),
    )
    assert len(result["confirmations"]) == 2
    assert [w["args"].get("operation", "read") for w in result["writes"]] == [
        "bind_serving_provider",
        "set_serving",
        "read",
        "bind_serving_provider",
        "set_serving",
    ]
    restore = result["writes"][3]["args"]
    assert restore["expected_revision"] == 3
    assert json.loads(restore["payload_json"]) == {"provider": "server-key"}
    assert result["recovery"] is None and result["choice"] is None


def test_signout_after_bind_prevents_followup_enable(tmp_path):
    result = run_picker(
        tmp_path,
        """
      const original=MCP.callTool;
      MCP.callTool=async(name,args)=>{
        const result=await original(name,args);ModelPicker.reset();return result;
      };
      await ModelPicker.allowAccess(doc.sources[0]);
    """,
        access_catalogue(legacy=True),
    )
    assert len(result["writes"]) == 1 and result["snapshot"] is None


@pytest.mark.parametrize("changed", ["home", "revision", "serving"])
def test_restore_does_not_overwrite_changed_or_working_state(tmp_path, changed):
    mutation = {
        "home": 'doc.universe_id="new-home";',
        "revision": 'MCP.callTool=async()=>({binding:{revision:99,status:"configured"}});',
        "serving": 'MCP.callTool=async()=>({binding:{revision:3,status:"serving"}});',
    }[changed]
    result = run_picker(tmp_path, """
      const original=MCP.callTool;
      MCP.callTool=async(name,args)=>{
        if(args.operation==="set_serving") {writes.push({name,args});return {error:"held"};}
        return original(name,args);
      };
      await ModelPicker.allowAccess(doc.sources[0]);
    """ + mutation + "await ModelPicker.restoreAccess();", access_catalogue(legacy=True))
    assert len(result["writes"]) == 2
    assert "no restore was attempted" in result["ui"]["model-status"]["text"]
