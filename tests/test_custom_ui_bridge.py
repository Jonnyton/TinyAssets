"""Execute the shipped custom-UI controller and bridge, not a reimplementation.

The bundle side is untrusted by construction, so the interesting assertions are
what the bridge *sends* and *returns* when a hostile bundle asks for more than it
has: the recorded tool arguments, the refusal text, and the fields that reach the
frame. Asserting only that "nothing happened" would pass against a bridge that
silently did the wrong thing.

Both real controllers run together, so the private-configuration write is the
actual revision-guarded path rather than a stand-in for it.
"""
# ruff: noqa: E501 -- embedded JavaScript fixture mirrors controller expressions
import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS = r'''
const assert=require('node:assert/strict');
const registry={};
class FrameWindow{ constructor(){ this.posts=[]; } postMessage(data){ this.posts.push(data); } }
class Element {
 constructor(id='',tag=''){this.id=id;this.tag=tag;this.children=[];this.parentNode=null;this.value='';
  this.open=false;this.hidden=false;this.textContent='';this.disabled=false;this.attrs={};
  this.classes=new Set();
  this.classList={add:c=>this.classes.add(c),remove:c=>this.classes.delete(c),contains:c=>this.classes.has(c)};
  if(tag==='iframe')this.contentWindow=new FrameWindow();
  if(id)registry[id]=this;}
 appendChild(n){if(n.parentNode)n.parentNode.removeChild(n);this.children.push(n);n.parentNode=this;return n;}
 insertBefore(n,ref){if(n.parentNode)n.parentNode.removeChild(n);const i=this.children.indexOf(ref);assert(i>=0);this.children.splice(i,0,n);n.parentNode=this;}
 removeChild(n){const i=this.children.indexOf(n);assert(i>=0);this.children.splice(i,1);n.parentNode=null;}
 replaceChildren(...nodes){for(const n of [...this.children])this.removeChild(n);for(const n of nodes)this.appendChild(n);}
 setAttribute(name,value){this.attrs[name]=String(value);} addEventListener(){}
 close(){this.open=false;} showModal(){this.open=true;}
}
const $=id=>registry[id]||(registry[id]=new Element(id));
const document={createElement:tag=>new Element('',tag),createComment:()=>new Element()};
const host=$('view-chat'),body=new Element();host.appendChild(body);
for(const id of ['thread','request-rail'])body.appendChild($(id));
for(const id of ['attachments','model-bar','composer','status-line'])host.appendChild($(id));
$('universe-name').textContent='Alice universe';

// --- the window the bridge listens on ---------------------------------------
let listeners=[];
const window={addEventListener:(name,fn)=>{if(name==='message')listeners.push(fn);},
 removeEventListener:(name,fn)=>{if(name==='message')listeners=listeners.filter(f=>f!==fn);}};
const emit=event=>{for(const fn of [...listeners])fn(event);};

// --- server double: one binding row with a real revision --------------------
const HOME='u-alice',PRINCIPAL='alice';
let me={principal_id:PRINCIPAL,universe_id:HOME,setup:'connected'};
let binding=null, definitions={}, calls=[], sends=[], conversation=[];
let otherConversation=[{speaker:'universe',text:'BOBS PRIVATE TURN',ts:1,truncated:false}];
let statusUniverseOverride='';
const fetchMe=async()=>me;
const sessionExpired=()=>{throw Error('expired');};
const sendTurn=async(message,display,opts)=>{sends.push({message,display,opts});};
const MCP={
 async callTool(tool,args){
  calls.push({tool,args:JSON.parse(JSON.stringify(args||{}))});
  if(tool==='read_graph'&&args.target==='agent_bindings')return {bindings:binding?[binding]:[]};
  if(tool==='read_graph'&&args.target==='agent_binding')return {binding};
  if(tool==='read_graph'&&args.target==='agent')return {agent:definitions[args.agent_definition_id]||{agent_definition_id:args.agent_definition_id,components:{}}};
  if(tool==='get_status'){
   const scope=statusUniverseOverride||args.universe_id||me.universe_id;
   return {universe_id:scope,
     recent_conversation:{turns:scope===HOME?conversation:otherConversation}};
  }
  if(tool==='write_graph'&&args.target==='agent_binding'){
   const config=JSON.parse(args.payload_json);
   if(args.operation==='update'){
    assert.equal(args.agent_binding_id,binding.agent_binding_id);
    assert.equal(args.expected_revision,binding.revision);
    binding={...binding,configuration:config,revision:binding.revision+1,
      agent_definition_id:args.agent_definition_id,updated_by:PRINCIPAL};
   }else{
    binding={agent_binding_id:'b1',universe_id:args.graph_id,agent_definition_id:args.agent_definition_id,
      configuration:config,revision:1,status:'configured',created_by:PRINCIPAL,updated_by:PRINCIPAL};
   }
   return {status:'configured',binding};
  }
  return {};
 },
 getStatus(){return this.callTool('get_status',{},{idempotent:true});},
 getConversation(){return this.callTool('get_status',{include_conversation:true},{idempotent:true});},
};
const bundleOf=over=>Object.assign({kind:'tinyassets.app-ui.v1',version:1,ui_id:'office',
 name:'Office building',markup:'<div id="lobby">Lobby</div>',style:'#lobby{color:red}',
 script:'tinyassets.whoami()'},over||{});
const installed=(library,selection)=>({agent_binding_id:'b1',universe_id:HOME,agent_definition_id:'d1',
 status:'configured',revision:1,created_by:PRINCIPAL,updated_by:PRINCIPAL,
 configuration:Object.assign({schema_version:1,name:'App experience',role:'app_experience',private:{keep:1}},
  library?{ui_library:library}:{},selection?{ui_selection:selection}:{})});
'''

CHECKS = r'''
(async()=>{
const u=AppUI;

// ---- the reader refuses anything it cannot render, by reason ---------------
assert(u.parseBundle(bundleOf()).ok);
for(const [over,needle] of [
 [{extra:'x'},/does not render: extra/],
 [{kind:'other'},/not a tinyassets\.app-ui\.v1/],
 [{version:2},/version 2 is not supported/],
 [{ui_id:'Office'},/ui_id must be lowercase/],
 [{ui_id:''},/ui_id must be lowercase/],
 [{name:'  '},/name must be a non-empty string/],
 [{markup:{}},/markup must be a string/],
 [{script:null},/script must be a string/],
 [{markup:'x'.repeat(u.MAX_MARKUP+1)},/markup must be a string/],
]){ const r=u.parseBundle(bundleOf(over)); assert(!r.ok,JSON.stringify(over)); assert(needle.test(r.reason),r.reason); }
assert(!u.parseBundle({...bundleOf(),ui_id:undefined}).ok);
// A field-legal bundle that still busts the whole-bundle budget.
const fat=bundleOf({markup:'m'.repeat(u.MAX_MARKUP),style:'s'.repeat(u.MAX_STYLE),script:'j'.repeat(u.MAX_SCRIPT)});
assert(!u.parseBundle(fat).ok);

assert.deepEqual(u.readLibrary(null).entries,[]);
assert(!u.readLibrary({ui_library:{}}).ok);
assert(!u.readLibrary({ui_library:[bundleOf(),bundleOf()]}).ok);            // duplicate ui_id
assert(!u.readLibrary({ui_library:Array.from({length:u.LIBRARY_LIMIT+1},(_,i)=>bundleOf({ui_id:'ui-'+i}))}).ok);
assert(!u.readSelection({ui_selection:{version:1,state:'active'}}).ok);      // no ui_id
assert(!u.readSelection({ui_selection:{version:1,state:'active',ui_id:'office',extra:1}}).ok);
assert(!u.readSelection({ui_selection:{version:1,state:'default',ui_id:'office'}}).ok);
assert(!u.readSelection({ui_selection:{version:2,state:'default'}}).ok);
assert.deepEqual(u.readSelection({ui_selection:{version:1,state:'active',ui_id:'office'}}).selection,
 {version:1,state:'active',ui_id:'office'});

// ---- one read serves both controllers, and it applies the saved choice -----
binding=installed([bundleOf()],{version:1,state:'active',ui_id:'office'});
definitions['d1']={agent_definition_id:'d1',content_fingerprint:'f'.repeat(64),components:{}};
AppLayout.enable(HOME,PRINCIPAL); u.enable(HOME,PRINCIPAL);
await new Promise(r=>setImmediate(r)); await new Promise(r=>setImmediate(r));
await new Promise(r=>setImmediate(r)); await new Promise(r=>setImmediate(r));
assert(u.active&&u.active.ui_id==='office','the remembered UI must be applied: '+$('ui-status').textContent);
// AppUI listed no bindings of its own: only AppLayout's read is on the wire.
assert.equal(calls.filter(c=>c.tool==='read_graph'&&c.args.target==='agent_bindings').length,1);

// ---- the frame is created with the isolation the boundary depends on ------
const frame=u.frame;
assert.equal(frame.tag,'iframe');
assert.equal(frame.attrs.sandbox,'allow-scripts');          // no allow-same-origin, ever
assert.equal(frame.attrs.src,'/mcp/app/ui-frame');
assert.equal(frame.attrs.referrerpolicy,'no-referrer');
assert.equal($('ui-frame-host').hidden,false);
assert($('view-chat').classes.has('ui-custom-active'));

// ---- the bundle is handed over only after the frame says ready ------------
const win=frame.contentWindow;
assert.equal(win.posts.length,0,'nothing is posted before the frame reports ready');
emit({source:win,data:{ta_ui:1,type:'ready'}});
assert.equal(win.posts.length,1);
assert.deepEqual(Object.keys(win.posts[0].bundle).sort(),['markup','script','style']);
assert.equal(win.posts[0].bundle.markup,'<div id="lobby">Lobby</div>');
emit({source:win,data:{ta_ui:1,type:'ready'}});
assert.equal(win.posts.length,1,'a replayed ready does not re-deliver the bundle');

// ---- a message from anything but this frame is not heard ------------------
const stranger=new FrameWindow();
emit({source:stranger,data:{ta_ui:1,type:'call',id:'x',action:'whoami',params:{}}});
await new Promise(r=>setImmediate(r));
assert.equal(stranger.posts.length,0);
assert.equal(win.posts.length,1,'a foreign window cannot make this frame receive a result');

const ask=async(action,params)=>{
 const before=win.posts.length;
 emit({source:win,data:{ta_ui:1,type:'call',id:'q'+before,action,params:params||{}}});
 for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));
 assert(win.posts.length>before,'the bridge always answers '+action);
 return win.posts[win.posts.length-1];
};

// ---- an unlisted action does not exist -----------------------------------
for(const action of ['write_graph','connectHTTP','whoami ','WHOAMI','constructor','__proto__','toString']){
 const before=calls.length;
 const reply=await ask(action,{});
 assert.equal(reply.ok,false,action);
 assert(reply.error.includes(action),reply.error);
 assert.equal(calls.length,before,action+' must reach no tool');
}

// ---- the viewer's identity, and nothing else ------------------------------
const who=(await ask('whoami',{universe_id:'u-bob'})).result;
assert.deepEqual(Object.keys(who).sort(),['protocol','universe_id','universe_name']);
assert.equal(who.universe_id,HOME);
assert.equal(who.universe_name,'Alice universe');

// ---- a bundle cannot name a universe: the argument is pinned -------------
calls=[];
const agents=(await ask('list_agents',{graph_id:'u-bob',universe_id:'u-bob',limit:9999})).result;
const listed=calls.filter(c=>c.tool==='read_graph'&&c.args.target==='agent_bindings');
assert.equal(listed.length,1);
assert.equal(listed[0].args.graph_id,HOME,'graph_id came from the viewer, not the bundle');
assert(!('universe_id' in listed[0].args));
assert.deepEqual(Object.keys(agents.agents[0]).sort(),['agent_id','name','selected']);
assert.equal(agents.agents[0].name,'App experience');

// ---- private operational data does not cross into a bundle ---------------
binding={...binding,configuration:{...binding.configuration,provider_secret_note:'never'}};
const again=(await ask('list_agents',{})).result;
assert.equal(JSON.stringify(again).includes('never'),false);

// ---- reading the conversation returns picked fields only -----------------
conversation=[{speaker:'founder',text:'hello',ts:100,truncated:false,
 access_token:'leak',internal:{credential:'leak'}}];
const read=(await ask('read_conversation',{limit:1})).result;
assert.deepEqual(read.turns,[{speaker:'founder',text:'hello',at:100,truncated:false}]);
assert.equal(JSON.stringify(read).includes('leak'),false);

// ---- send goes through the app's own turn path ---------------------------
sends=[];
const blank=await ask('send_message',{text:'   '});
assert.equal(blank.ok,false); assert.equal(sends.length,0);
const long=await ask('send_message',{text:'x'.repeat(u.MAX_MESSAGE+1)});
assert.equal(long.ok,false); assert.equal(sends.length,0);
const sent=await ask('send_message',{text:'open the lobby door'});
assert.equal(sent.ok,true); assert.deepEqual(sent.result,{sent:true});
assert.equal(sends.length,1);
assert.equal(sends[0].message,'open the lobby door');
assert.equal(sends[0].opts.inputMethod,'app_action');

// ---- naming an agent the server will not accept is refused, not redirected
const wrong=await ask('send_message',{text:'hi',agent:'not-an-agent-of-mine'});
assert.equal(wrong.ok,false);
assert(/no agent of yours is named not-an-agent-of-mine/.test(wrong.error),wrong.error);
assert.equal(sends.length,1,'a refused agent must not fall back to the default conversation');
const unselected=await ask('send_message',{text:'hi',agent:'b1'});
assert.equal(unselected.ok,false);
assert(/selected conversation only/.test(unselected.error),unselected.error);
assert.equal(sends.length,1);

// ---- switching persists through the ONE revision-guarded write ----------
const startRevision=binding.revision;
calls=[];
await u.chooseDefault();
assert.equal(u.active,null,'default chat is applied immediately');
assert.equal($('ui-frame-host').hidden,true);
assert(!$('view-chat').classes.has('ui-custom-active'));
const wrote=calls.filter(c=>c.tool==='write_graph');
assert.equal(wrote.length,1);
assert.equal(wrote[0].args.expected_revision,startRevision);
assert.deepEqual(JSON.parse(wrote[0].args.payload_json).ui_selection,{version:1,state:'default'});
assert.deepEqual(JSON.parse(wrote[0].args.payload_json).private,{keep:1},'other private config survives');
assert.deepEqual(JSON.parse(wrote[0].args.payload_json).ui_library,[bundleOf()],'the library survives a selection write');

await u.choose('office');
assert(u.active&&u.active.ui_id==='office');
assert.deepEqual(binding.configuration.ui_selection,{version:1,state:'active',ui_id:'office'});

// ---- a stale observed revision is a conflict, never an overwrite --------
binding={...binding,revision:binding.revision+5};
const before=binding.revision;
AppLayout.uncertain=false;
await u.chooseDefault();
assert.equal(binding.revision,before,'a stale write must not land');
assert(AppLayout.uncertain,'the conflict is reported, not retried');

// ---- a remixed bundle acts as the REMIXER ------------------------------
// Bob authored it; Alice installs the component into her own library. Nothing
// about Bob travels into the calls it can make.
AppLayout.uncertain=false;
const bobs=bundleOf({ui_id:'bob-tower',name:'Bob tower',
 script:'tinyassets.call("list_agents",{graph_id:"u-bob"})'});
binding={...binding,revision:binding.revision};
AppLayout.installation={binding_id:binding.agent_binding_id,revision:binding.revision,
 definition_id:binding.agent_definition_id,configuration:JSON.parse(JSON.stringify(binding.configuration))};
AppLayout.candidates=[binding]; AppLayout.loaded=true; AppLayout.saturated=false;
const outcome=await u.install(bobs);
assert(outcome.ok,JSON.stringify(outcome));
assert.equal(binding.configuration.ui_library.length,2);
await u.choose('bob-tower');
assert(u.active&&u.active.ui_id==='bob-tower');
const bobFrame=u.frame.contentWindow;
emit({source:bobFrame,data:{ta_ui:1,type:'ready'}});
calls=[];
emit({source:bobFrame,data:{ta_ui:1,type:'call',id:'z',action:'list_agents',params:{graph_id:'u-bob'}}});
for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));
const remixCalls=calls.filter(c=>c.tool==='read_graph'&&c.args.target==='agent_bindings');
assert.equal(remixCalls.length,1);
assert.equal(remixCalls[0].args.graph_id,HOME,'a remix reaches the remixer, never the author');
const remixWho=await (async()=>{const before=bobFrame.posts.length;
 emit({source:bobFrame,data:{ta_ui:1,type:'call',id:'w',action:'whoami',params:{}}});
 for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));
 return bobFrame.posts[bobFrame.posts.length-1];})();
assert.equal(remixWho.result.universe_id,HOME);

// ---- sharing produces a public component, and only that ----------------
const published=u.publishPayload(bobs,'A tower');
assert(published.ok);
assert.deepEqual(Object.keys(published.payload.components),['ui']);
assert.equal(published.payload.components.ui.kind,u.KIND);
assert.equal(published.payload.name,'Bob tower');
assert(!u.publishPayload({...bobs,extra:1},'').ok);
// One UI component per definition, so there is never a question which one runs.
assert(!u.readDefinition({components:{a:bobs,b:bundleOf()}}).ok);
assert(!u.readDefinition({components:{}}).ok);
assert.equal(u.readDefinition({components:{only:bobs}}).bundle.ui_id,'bob-tower');

// ---- the read is pinned, and its answer is checked (Codex P1) ---------
// `verify()` sees nothing wrong here: `fetchMe` still reports this home. Only
// the status answer disagrees, which is the window between the two.
const pinnedFrame=u.frame.contentWindow;
calls=[];
const pinnedRead=await (async()=>{const before=pinnedFrame.posts.length;
 emit({source:pinnedFrame,data:{ta_ui:1,type:'call',id:'pin',action:'read_conversation',params:{}}});
 for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));
 return pinnedFrame.posts[pinnedFrame.posts.length-1];})();
const statusCalls=calls.filter(c=>c.tool==='get_status');
assert.equal(statusCalls.length,1);
assert.equal(statusCalls[0].args.universe_id,HOME,'the read names the granted home');
assert.equal(pinnedRead.ok,true);

// Now the server answers about a DIFFERENT universe while fetchMe still says
// this one. The reply must be refused, not rendered.
statusUniverseOverride='u-bob';
const mismatched=await (async()=>{const before=pinnedFrame.posts.length;
 emit({source:pinnedFrame,data:{ta_ui:1,type:'call',id:'mis',action:'read_conversation',params:{}}});
 for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));
 return pinnedFrame.posts[pinnedFrame.posts.length-1];})();
assert.equal(mismatched.ok,false,'an answer about another universe is refused');
assert(/another universe/.test(mismatched.error),mismatched.error);
assert.equal(JSON.stringify(mismatched).includes('BOBS PRIVATE TURN'),false);
statusUniverseOverride='';

// ---- a home change under the same login ends the grant (Codex P1) ------
// The account moves home while a bundle is mounted. `get_status` with no
// universe would hand it the NEW home's conversation.
conversation=[{speaker:'founder',text:'ALICE PRIVATE TURN',ts:2,truncated:false}];
const mountedFrame=u.frame.contentWindow;
me={principal_id:PRINCIPAL,universe_id:'u-bob',setup:'connected'};
const leak=await (async()=>{const before=mountedFrame.posts.length;
 emit({source:mountedFrame,data:{ta_ui:1,type:'call',id:'leak',action:'read_conversation',params:{}}});
 for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));
 return mountedFrame.posts[mountedFrame.posts.length-1];})();
assert.equal(leak.ok,false,'a moved home must not be served to the old bundle');
assert(/identity or home changed/.test(leak.error),leak.error);
assert.equal(JSON.stringify(leak).includes('BOBS PRIVATE TURN'),false);
assert.equal(u.frame,null,'the bridge is revoked, not merely refused once');
assert.equal(u.enabled,false);

// The funnel the app actually calls must revoke too, not just the handler.
me={principal_id:PRINCIPAL,universe_id:HOME,setup:'connected'};
binding=installed([bundleOf()],{version:1,state:'active',ui_id:'office'});
AppLayout.installation={binding_id:'b1',revision:binding.revision,definition_id:'d1',
 configuration:JSON.parse(JSON.stringify(binding.configuration))};
AppLayout.candidates=[binding];AppLayout.loaded=true;AppLayout.saturated=false;
AppLayout.uncertain=false;AppLayout.enabled=true;AppLayout.home=HOME;AppLayout.principal=PRINCIPAL;
u.enabled=true;u.home=HOME;u.principal=PRINCIPAL;u.adopt(AppLayout.installation);
assert(u.active,'the saved UI is mounted again');
u.homeChanged('u-carol');
assert.equal(u.frame,null,'homeChanged tears the frame down');
assert.equal(u.enabled,false);
u.homeChanged('u-carol');   // idempotent on an already-reset controller

// ---- a reply is owed to the frame that asked (Codex P2) ----------------
me={principal_id:PRINCIPAL,universe_id:HOME,setup:'connected'};
binding=installed([bundleOf(),bundleOf({ui_id:'second',name:'Second'})],null);
AppLayout.installation={binding_id:'b1',revision:binding.revision,definition_id:'d1',
 configuration:JSON.parse(JSON.stringify(binding.configuration))};
AppLayout.candidates=[binding];AppLayout.loaded=true;AppLayout.saturated=false;
AppLayout.uncertain=false;AppLayout.enabled=true;AppLayout.home=HOME;AppLayout.principal=PRINCIPAL;
u.enabled=true;u.home=HOME;u.principal=PRINCIPAL;u.adopt(AppLayout.installation);
u.mount(u.library[0]);
const frameA=u.frame.contentWindow;
emit({source:frameA,data:{ta_ui:1,type:'ready'}});
const postsA=frameA.posts.length;
// Ask, then swap the bundle before the answer lands. Both bootstraps number
// their requests from r1, so a misrouted reply would settle B's own promise.
emit({source:frameA,data:{ta_ui:1,type:'call',id:'r1',action:'read_conversation',params:{}}});
u.mount(u.library[1]);
const frameB=u.frame.contentWindow;
for(let i=0;i<10;i++)await new Promise(r=>setImmediate(r));
assert.equal(frameB.posts.filter(m=>m.type==='result'&&m.id==='r1').length,0,
 "bundle A's answer must not reach bundle B");
assert.equal(frameA.posts.length,postsA,'and it is not delivered to a torn-down frame either');
assert.equal(u.pending,0,"a stale completion must not decrement the new frame's counter");

// ---- installing next to an unreadable library refuses (Codex P1) -------
// One stored bundle is a future version this app cannot parse. Installing must
// not rebuild the library from a cache that dropped it.
const future={...bundleOf({ui_id:'from-tomorrow'}),version:2};
binding=installed([bundleOf(),future],null);
AppLayout.installation={binding_id:'b1',revision:binding.revision,definition_id:'d1',
 configuration:JSON.parse(JSON.stringify(binding.configuration))};
AppLayout.candidates=[binding];AppLayout.loaded=true;AppLayout.saturated=false;
AppLayout.uncertain=false;
u.enabled=true;u.home=HOME;u.principal=PRINCIPAL;u.adopt(AppLayout.installation);
assert(u.unreadable,'an unreadable library is remembered as unreadable, not as empty');
assert.deepEqual(u.library,[]);
const storedBefore=JSON.stringify(binding.configuration.ui_library);
calls=[];
const refused=await u.install(bundleOf({ui_id:'newcomer'}));
assert(!refused.ok,'install must refuse rather than overwrite');
assert.equal(calls.filter(c=>c.tool==='write_graph').length,0,'and write nothing');
assert.equal(AppLayout.uncertain,false,
 'refusing up front must not leave the shared editor uncertain; only the write backstop does that');
assert.equal(JSON.stringify(binding.configuration.ui_library),storedBefore,
 'the bundle it could not parse is still stored');

// The guarded mutation is the backstop: even with a clean cache, a library that
// became unreadable since the read is refused inside the write window.
u.unreadable='';u.library=[bundleOf()];
AppLayout.uncertain=false;
const sneaky=await u.install(bundleOf({ui_id:'newcomer'}));
assert(!sneaky.ok,'the mutation re-checks what the write actually observed');
assert.equal(JSON.stringify(binding.configuration.ui_library),storedBefore);

// ---- size is measured in UTF-8 bytes, not UTF-16 units (Codex P2) ------
// Characters that cost three bytes each. A character-counting limit accepts
// this; the server, which caps bytes, would not.
const cjk=bundleOf({ui_id:'cjk',markup:'漢'.repeat(20000)});
assert.equal(cjk.markup.length,20000);
assert(u.bytes(cjk.markup)>3*19000,'the fixture really is multi-byte');
const cjkRead=u.parseBundle(cjk);
assert(!cjkRead.ok,'a bundle over the BYTE limit is refused');
assert(/bytes/.test(cjkRead.reason),cjkRead.reason);
// And the whole configuration is checked before a write, not just one bundle.
binding=installed([],null);
AppLayout.installation={binding_id:'b1',revision:binding.revision,definition_id:'d1',
 configuration:JSON.parse(JSON.stringify(binding.configuration))};
AppLayout.candidates=[binding];AppLayout.loaded=true;AppLayout.uncertain=false;
u.adopt(AppLayout.installation);
const near=u.MAX_MARKUP-1024;   // inside the field bound AND the bundle budget
for(let i=0;i<u.LIBRARY_LIMIT-1;i++){
 AppLayout.uncertain=false;
 const r=await u.install(bundleOf({ui_id:'big-'+i,markup:'x'.repeat(near)}));
 assert(r.ok,'a bundle inside its own budget installs: '+JSON.stringify(r));
}
assert(u.bytes(JSON.stringify(binding.configuration))<u.MAX_CONFIG_BYTES);

// With bulk already in the configuration, one more bundle crosses the cap. The
// refusal must come from this app, before a write, naming the size.
binding=installed([],null);
binding.configuration.private={bulk:'p'.repeat(u.MAX_CONFIG_BYTES-30000)};
AppLayout.installation={binding_id:'b1',revision:binding.revision,definition_id:'d1',
 configuration:JSON.parse(JSON.stringify(binding.configuration))};
AppLayout.candidates=[binding];AppLayout.loaded=true;AppLayout.saturated=false;
AppLayout.uncertain=false;
u.adopt(AppLayout.installation);
const storedBulk=JSON.stringify(binding.configuration);
calls=[];
const tooBig=await u.install(bundleOf({ui_id:'straw',markup:'y'.repeat(u.MAX_MARKUP)}));
assert(!tooBig.ok,'a bundle that would bust the binding cap is refused');
assert.equal(calls.filter(c=>c.tool==='write_graph').length,0,'and nothing is written');
assert.equal(JSON.stringify(binding.configuration),storedBulk);
assert(/over the /.test($('ui-status').textContent),$('ui-status').textContent);
// This size was visible BEFORE the write, so the refusal must not leave the
// shared editor uncertain -- that state is for outcomes nobody can be sure of.
assert.equal(AppLayout.uncertain,false,
 'a size this app could see coming is refused without an uncertain write');

// ---- the in-write cap is the backstop for a RACE (Codex P2) -----------
// The pre-write check reads the configuration last OBSERVED; the stored one can
// have grown since. Make them disagree: observed small, stored already near the
// cap, same revision so CAS is satisfied. The pre-write check passes and the
// guarded mutation must refuse -- and THAT refusal legitimately marks the shared
// editor uncertain, which the pre-write one must not.
binding=installed([],null);
binding.configuration.private={bulk:'q'.repeat(u.MAX_CONFIG_BYTES-30000)};
AppLayout.installation={binding_id:'b1',revision:binding.revision,definition_id:'d1',
 configuration:{schema_version:1,name:'App experience',role:'app_experience'}};  // the small view
AppLayout.candidates=[binding];AppLayout.loaded=true;AppLayout.saturated=false;
AppLayout.uncertain=false;
u.enabled=true;u.home=HOME;u.principal=PRINCIPAL;u.library=[];u.unreadable='';
const storedRace=JSON.stringify(binding.configuration);
calls=[];
const raced=await u.install(bundleOf({ui_id:'raced',markup:'z'.repeat(u.MAX_MARKUP)}));
assert(!raced.ok,'the guarded mutation refuses what the stale view allowed');
assert.equal(JSON.stringify(binding.configuration),storedRace,'and nothing was written');
assert(AppLayout.uncertain,'a refusal inside the write window IS uncertain');
// The reason must survive out to the user, not be flattened to "failed".
assert(/over the /.test($('ui-status').textContent),$('ui-status').textContent);
assert(/bytes/.test($('ui-status').textContent),$('ui-status').textContent);
AppLayout.uncertain=false;

// ---- sign-out tears the bridge down ----------------------------------
u.reset();
assert.equal(u.frame,null);
assert.equal(listeners.length,0,'the message listener is removed with the frame');
assert.equal($('btn-ui-switch').hidden,true);

console.log('custom-ui bridge checks passed');
})().catch(err=>{console.error(err);process.exit(1);});
'''


# The sample the founder named: an office building whose rooms are agents. It
# lives here and only here -- the platform ships no bundle, because a shipped one
# would be a fixed archetype and the point is that a universe writes its own.
#
# Its markup is deliberately the kind a sanitizer would mangle (an inline handler,
# a data URI, an entity, a CDATA-looking string). Nothing sanitizes it, so the
# assertion below is that it arrives at the frame byte for byte.
OFFICE_BUNDLE = r'''
const OFFICE={kind:'tinyassets.app-ui.v1',version:1,ui_id:'office-tower',
 name:'Office tower',
 markup:'<div class="floor" data-room="lobby">'+
  '<img src="data:image/gif;base64,R0lGOD" alt="lobby &amp; desk" onerror="this.hidden=true">'+
  '<button id="room-lobby" onclick="enter(\'lobby\')">Lobby &rarr;</button>'+
  '<pre><![CDATA[ not really cdata ]]></pre></div>',
 style:'.floor{display:grid}.floor[data-room="lobby"]::after{content:"\\2318"}',
 script:"async function enter(room){const who=await tinyassets.whoami();"+
  "const mine=await tinyassets.listAgents();"+
  "const agent=mine.agents.find(a=>a.name.toLowerCase().includes(room));"+
  "await tinyassets.sendMessage('I walked into the '+room,agent&&agent.agent_id);"+
  "document.title=who.universe_name;}"};
'''

SAMPLE_CHECKS = r'''
(async()=>{
const u=AppUI;
// Install it the way a universe's own agent would, then select it.
binding=installed([],null);
definitions['d1']={agent_definition_id:'d1',content_fingerprint:'f'.repeat(64),components:{}};
AppLayout.installation={binding_id:'b1',revision:1,definition_id:'d1',
 configuration:JSON.parse(JSON.stringify(binding.configuration))};
AppLayout.candidates=[binding];AppLayout.loaded=true;AppLayout.saturated=false;
AppLayout.enabled=true;AppLayout.home=HOME;AppLayout.principal=PRINCIPAL;
u.enabled=true;u.home=HOME;u.principal=PRINCIPAL;

const installOutcome=await u.install(OFFICE);
assert(installOutcome.ok,JSON.stringify(installOutcome));
await u.choose('office-tower');
assert(u.active&&u.active.ui_id==='office-tower');

const win=u.frame.contentWindow;
emit({source:win,data:{ta_ui:1,type:'ready'}});
const delivered=win.posts[0].bundle;

// Hard Rule 9: what the user wrote is what runs. A markup sanitizer, an entity
// re-encode, or a CSS rewrite would all show up right here.
assert.strictEqual(delivered.markup,OFFICE.markup);
assert.strictEqual(delivered.style,OFFICE.style);
assert.strictEqual(delivered.script,OFFICE.script);
assert(delivered.markup.includes('onerror='),'an inline handler survives verbatim');
assert(delivered.markup.includes('&amp;'),'entities are not re-encoded');
assert(delivered.markup.includes('<![CDATA['),'nothing is parsed and re-serialised');

// And it survives the round trip through the private configuration it is stored
// in: what the binding holds parses back to the same bundle.
const reread=u.readLibrary(binding.configuration);
assert(reread.ok,reread.reason);
assert.strictEqual(reread.entries[0].script,OFFICE.script);

// Every action its script calls is one the bridge actually has. A sample that
// programmed against an action the allowlist lacks would be a broken example.
for(const action of ['whoami','listAgents','sendMessage'])
 assert(Object.values(u.ACTIONS).includes(action),action+' must exist for the sample to work');

console.log('office sample checks passed');
})().catch(err=>{console.error(err);process.exit(1);});
'''


def _run(tmp_path, name, checks, extra=""):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for actual JavaScript controller")
    layout = Path("tinyassets/onboarding/app_layout.js").read_text(encoding="utf-8")
    controller = Path("tinyassets/onboarding/app_ui.js").read_text(encoding="utf-8")
    script = tmp_path / name
    script.write_text(HARNESS + extra + layout + controller + checks, encoding="utf-8")
    result = subprocess.run(
        [node, str(script)], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_bundle_bridge_is_a_closed_allowlist_acting_as_the_viewer(tmp_path):
    out = _run(tmp_path, "custom_ui_bridge.js", CHECKS)
    assert "custom-ui bridge checks passed" in out


def test_a_real_bundle_reaches_the_frame_exactly_as_its_author_wrote_it(tmp_path):
    out = _run(tmp_path, "custom_ui_sample.js", SAMPLE_CHECKS, extra=OFFICE_BUNDLE)
    assert "office sample checks passed" in out
