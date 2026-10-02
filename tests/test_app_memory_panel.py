"""Exercise the Account memory panel's own JavaScript under Node."""
import json
import shutil
import subprocess

import pytest

from tests.test_onboarding_app import _js_function
from tinyassets import onboarding

_NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(_NODE is None, reason="node is required")


def test_memory_panel_load_edit_delete_undo_and_conflict(tmp_path):
    page, _ = onboarding.render_app_html()
    assert "What your agent remembers" in page
    assert "loadMemory();" in _js_function(page, "showAccount")
    funcs = "\n".join(_js_function(page, name) for name in (
        "memoryRequest", "renderMemory", "loadMemory", "saveMemory"))
    script = tmp_path / "memory.js"
    script.write_text(r'''
const elements={}, calls=[];
function element(){return {children:[],value:"",disabled:false,
  set textContent(v){this.text=v;this.children=[];},get textContent(){return this.text||"";},
  appendChild(e){this.children.push(e);},setAttribute(){},
  addEventListener(event,fn){this[event]=fn;}};}
function $(id){return elements[id]||(elements[id]=element());}
const document={createElement:element};
function authHeaders(){return {Authorization:"Bearer owner"};}
let conflict=false;
async function fetch(path,init){
  calls.push({path,...init});
  return {ok:!conflict,status:conflict?409:200,json:async()=>conflict
    ?{detail:"MEMORY.md: conflict"}
    :{items:[{id:"m_abcd",text:"<script>plain text</script>"}],
      history:[{id:7,path:"MEMORY.md",prior_state:"present"}]}};
}
''' + funcs + r'''
(async()=>{
  await loadMemory();
  let row=$("memory-list").children[0];
  const original=row.children[0].value;
  row.children[0].value="Changed";
  await row.children[1].click();
  await $("memory-list").children[0].children[2].click();
  await $("btn-memory-undo").onclick();
  conflict=true;
  await saveMemory({undo:7});
  console.log(JSON.stringify({original,calls,status:$("memory-status").textContent}));
})();
''', encoding="utf-8")
    proc = subprocess.run([_NODE, str(script)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["original"] == "<script>plain text</script>"
    assert result["status"] == "MEMORY.md: conflict"
    calls = result["calls"]
    assert all(c["path"] == "/app/memory" and c["credentials"] == "same-origin" for c in calls)
    assert calls[0]["method"] == "GET"
    assert [json.loads(c["body"]) for c in calls[1:]] == [
        {"id": "m_abcd", "text": "Changed"}, {"delete": "m_abcd"}, {"undo": 7}, {"undo": 7}]
