"""Trusted consumer controls execute the shipped controller, not a copy."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_consumer_selection_disable_rollback_and_uncertain_save(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for actual JavaScript controller")
    source = Path("tinyassets/onboarding/app_layout.js").read_text(encoding="utf-8")
    harness = r'''
const assert=require('node:assert/strict');
const elements={}; const $=id=>elements[id]||(elements[id]={textContent:''});
let writes=[], rows=[], failRead=false;
const component={kind:'tinyassets.turn-graph.v1',version:1,branch_version_id:'v',
 content_hash:'a'.repeat(64),input_map:{message:'question'},reply_key:'answer'};
const definition={agent_definition_id:'d',content_fingerprint:'b'.repeat(64),
 components:{turn:component},name:'My selected design'};
const binding={agent_binding_id:'b',agent_definition_id:'d',revision:1,
 created_by:'owner',updated_by:'owner',universe_id:'home',status:'configured',
 configuration:{schema_version:1,name:'Private label',role:'app_experience',private:{keep:1}}};
rows=[binding];
const MCP={callTool:async(tool,args)=>{
 if(tool==='write_graph'){
  writes.push(args); rows=[{...rows[0],revision:rows[0].revision+1,
   agent_definition_id:args.agent_definition_id,configuration:JSON.parse(args.payload_json)}];
  return {status:'configured',binding:rows[0]};
 }
 if(args.target==='agent_binding'){if(failRead)throw Error('lost reply');return {binding:rows[0]};}
 throw Error('unexpected read');
}};
const sessionExpired=()=>{throw Error('expired');};
'''
    checks = r'''
(async()=>{
 const a=AppLayout;
 a.enabled=true;a.home='home';a.principal='owner';a.loaded=true;a.paint=()=>{};
 a.currentBindings=async()=>rows;
 a.getDefinition=async()=>definition;
 a.installation={binding_id:'b',revision:1,definition_id:'d',configuration:binding.configuration};
 a.inspected={agent:definition};
 assert(a.turnComponent(component).ok);
 assert(!a.turnComponent({...component,code:'unsafe'}).ok);
 await a.selectTurn('turn');
 assert.equal(writes.length,1);assert.equal(writes[0].expected_revision,1);
 assert.deepEqual(rows[0].configuration.private,{keep:1});
 assert.equal(rows[0].configuration.turn_consumer.state,'active');
 await a.disableTurn();
 assert.equal(writes.length,2);
 assert.deepEqual(rows[0].configuration.turn_consumer,{version:1,state:'disabled'});
 await a.rollbackTurn();
 assert.equal(writes.length,3);assert.equal(rows[0].configuration.turn_consumer.state,'active');
 assert.deepEqual(rows[0].configuration.private,{keep:1});
 rows[0]={...rows[0],revision:9};await a.disableTurn();
 assert.equal(writes.length,3);assert(a.uncertain);
 a.uncertain=false;a.installation.revision=9;failRead=true;
 await a.disableTurn();assert.equal(writes.length,4);assert(a.uncertain);
 await a.disableTurn();assert.equal(writes.length,4);
 a.uncertain=false;failRead=false;a.installation.revision=rows[0].revision;
 rows[0]={...rows[0],updated_by:'collaborator'};
 await a.disableTurn();assert.equal(writes.length,4);
 console.log('consumer controls passed');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    script = tmp_path / "consumer-controls.cjs"
    script.write_text(harness + source + checks, encoding="utf-8")
    result = subprocess.run([node, str(script)], capture_output=True, text=True,
                            encoding="utf-8", timeout=20, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
