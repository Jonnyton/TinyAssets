"""Execute the shipped layout controller with a minimal DOM, not a reimplementation."""
# ruff: noqa: E501 -- embedded JavaScript fixture mirrors controller expressions
import shutil
import subprocess
from pathlib import Path

import pytest

from tinyassets.onboarding import render_app_html


def test_controller_owner_fences_remix_and_lossless_dom(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for actual JavaScript controller")
    source = Path("tinyassets/onboarding/app_layout.js").read_text(encoding="utf-8")
    harness = r'''
const assert=require('node:assert/strict');
const registry={};
class Element {
 constructor(id=''){this.id=id;this.children=[];this.parentNode=null;this.value='';this.open=false;
 this.classList={add(){},remove(){}};if(id)registry[id]=this;}
 appendChild(n){if(n.parentNode)n.parentNode.removeChild(n);this.children.push(n);n.parentNode=this;return n;}
 insertBefore(n,ref){if(n.parentNode)n.parentNode.removeChild(n);const i=this.children.indexOf(ref);assert(i>=0);this.children.splice(i,0,n);n.parentNode=this;}
 removeChild(n){const i=this.children.indexOf(n);assert(i>=0);this.children.splice(i,1);n.parentNode=null;}
 replaceChildren(){for(const n of [...this.children])this.removeChild(n);}
 setAttribute(){} addEventListener(){} close(){this.open=false;} showModal(){this.open=true;}
}
const $=id=>registry[id]||(registry[id]=new Element(id));
const document={createElement:()=>new Element(),createComment:()=>new Element()};
const host=$('view-chat'),body=new Element();host.appendChild(body);
for(const id of ['thread','request-rail'])body.appendChild($(id));
for(const id of ['attachments','model-bar','composer','status-line'])host.appendChild($(id));
$('composer-input').value='private unsent draft';$('composer').appendChild($('composer-input'));
const original=[...host.children],bodyOriginal=[...body.children];
let me={principal_id:'alice',universe_id:'u-alice',setup:'connected'},rows=[],calls=[];
const fetchMe=async()=>me,sessionExpired=()=>{throw Error('expired');};
const MCP={callTool:async(tool,args)=>{calls.push({tool,args});return {bindings:rows};}};
'''
    checks = r'''
(async()=>{
const a=AppLayout;a.enabled=true;a.home='u-alice';a.principal='alice';
const binding={agent_binding_id:'b',agent_definition_id:'d',created_by:'alice',universe_id:'u-alice',status:'configured',revision:1,configuration:{schema_version:1,role:'app_experience',custom:{private:'retained'}}};
assert(a.eligible(binding));
for(const delta of [{created_by:'bob'},{universe_id:'u-bob'},{status:'serving'},
 {configuration:{role:'app_experience',provider_ref:'secret'}},{configuration:{role:'other'}}])assert(!a.eligible({...binding,...delta}));
rows=[{...binding,created_by:'bob'}];assert.deepEqual(await a.currentBindings(),[]);
rows=[binding,{...binding,agent_binding_id:'b2'}];await assert.rejects(a.currentBindings(),/ambiguous/);
rows=Array.from({length:100},()=>({...binding,created_by:'bob'}));await assert.rejects(a.currentBindings(),/incomplete/);
a.inspected={read:{ok:true,layout:{surfaces:['models','conversation'],density:'compact'}}};
a.draft=a.draftFrom(a.inspected.read.layout);calls=[];await a.apply();assert.equal(calls.length,0);
const component={kind:a.KIND,version:1,surfaces:['models','conversation'],density:'compact'};
assert(a.parseComponent(component).ok);assert(!a.parseComponent({...component,html:'<script>'}).ok);
assert(!a.parseComponent({...component,surfaces:['models','models']}).ok);
assert(!a.readDefinition({components:{one:component,two:component}}).ok);
const opaque={kind:'future',field:'preserve'};
const agent={agent_definition_id:'d',components:{layout:component,opaque},tags:['original'],portable_definition:{schema_version:1,components:{layout:component,opaque},external_origins:[{keep:'origin'}],native_extra:{keep:true},content_fingerprint:'stale'}};
a.inspected={agent,read:a.readDefinition(agent)};a.draft=a.draftFrom(component);
const payload=a.publishPayload('remix','description').payload;
assert.deepEqual(payload.external_origins,agent.portable_definition.external_origins);
assert.deepEqual(payload.native_extra,{keep:true});assert.deepEqual(payload.components.opaque,opaque);
assert(!('content_fingerprint' in payload));assert(!JSON.stringify(payload).includes('private unsent'));
a.arrange(component,{name:'<img onerror=evil>'},'preview');
assert.equal(a.root.children[0].children[0],$('model-bar'));
assert.equal($('composer-input').value,'private unsent draft');a.restore();
assert.deepEqual(host.children,original);assert.deepEqual(body.children,bodyOriginal);
assert.equal($('composer-input').value,'private unsent draft');
a.enabled=true;a.home='u-alice';a.principal='alice';a.loaded=true;a.saturated=false;a.candidates=[];
rows=[binding];calls=[];
a.installation={binding_id:'b',revision:1,configuration:binding.configuration};
let wrongReadback=true;
MCP.callTool=async(tool,args)=>{
 calls.push({tool,args});
 if(args.target==='agent_bindings')return {bindings:rows};
 if(tool==='write_graph')return {status:'configured',binding:{...binding,revision:2}};
 if(args.target==='agent_binding')return {binding:{...binding,revision:2,created_by:wrongReadback?'bob':'alice'}};
 if(args.target==='agent')return {agent};
 throw Error('unexpected call');
};
rows=[{...binding,revision:2}];await a.apply();assert(a.uncertain);
assert.equal(calls.filter(c=>c.tool==='write_graph').length,0);
assert.equal(a.mode,'default');rows=[binding];a.uncertain=false;calls=[];
await a.apply();assert(a.uncertain);assert.equal(a.mode,'default');
assert.equal(calls.filter(c=>c.tool==='write_graph').length,1);
assert.deepEqual(JSON.parse(calls.find(c=>c.tool==='write_graph').args.payload_json),binding.configuration);
calls=[];await a.apply();assert.equal(calls.length,0);
wrongReadback=false;a.uncertain=false;await a.apply();assert.equal(a.mode,'applied');a.restore();
me={...me,principal_id:'bob'};calls=[];await a.apply();assert.equal(calls.length,0);assert(!a.enabled);
console.log('actual controller checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    script = tmp_path / "layout-controller.cjs"
    script.write_text(harness + source + checks, encoding="utf-8")
    result = subprocess.run([node, str(script)], text=True, encoding="utf-8",
                            capture_output=True, check=False, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_render_includes_controller_under_existing_nonce_and_fixed_recovery():
    html, csp = render_app_html()
    assert "__TA_APP_LAYOUT__" not in html
    assert "const AppLayout=" in html
    assert "AppLayout.enable(me.universe_id,me.principal_id)" in html
    assert 'id="btn-layout-restore"' in html
    assert 'id="model-bar"' in html
    assert "'unsafe-inline'" not in csp
