  // ---- Custom universe UI: isolated renderer + closed bridge ----------------
  // A universe can hold executable UI bundles (`tinyassets.app-ui.v1`) its own
  // agent writes, and this renders them. A bundle is somebody's arbitrary code —
  // usually somebody the viewer has never met, because bundles are shared by
  // publish/remix — so nothing here sanitizes it. It runs in the sandboxed,
  // opaque-origin document `/app/ui-frame` serves (see ui_frame.py for the
  // policy), which owns no storage, no cookies and no network of its own.
  //
  // Everything the bundle can do is in ACTIONS below and nowhere else. Each
  // handler builds its own tool arguments and pins the universe to the VIEWING
  // user's current home, so a bundle cannot name a universe: cross-user reach is
  // not refused by a check, it is unrepresentable. Replies are assembled from
  // picked fields, never spread from a server payload, so a field added upstream
  // later cannot ride out to untrusted code.
  //
  // Storage is the viewer's own `app_ui` row (read_graph/write_graph
  // target="app_ui"): the bundles in `ui_library` and the choice in
  // `ui_selection`, one row per person and universe, keyed server-side by who is
  // signed in. It is not an agent binding and never appears to a binding reader.
  // Every write is compare-and-set on the row's revision.
  const AppUI={
    KIND:"tinyassets.app-ui.v1",VERSION:1,PROTOCOL:1,
    SHELL_KIND:"tinyassets.app-experience-shell.v1",
    FRAME_SRC:"/app/ui-frame",
    // No `allow-same-origin`: that single word is the whole isolation boundary.
    // With it the frame would share this page's origin and could read
    // `sessionStorage` (the access token), `localStorage` and the parent DOM.
    // The frame's own response header sandboxes it too, so this is the second of
    // two independent locks, not the only one.
    SANDBOX:"allow-scripts",
    // Per-UI bounds only. There is NO bound on the library as a whole -- neither
    // a count of UIs nor a byte total. A 4 MiB library ceiling used to refuse an
    // install once the stored library was full; those bytes are the universe's
    // tier storage now, one of the two limits an account has (founder 2026-09-30).
    // Sizes are UTF-8 BYTES, because that is what the server validates: counting
    // UTF-16 units let multi-byte bundles pass here and fail at write time
    // (Codex, 2026-09-26).
    MAX_MARKUP:32768,MAX_STYLE:16384,MAX_SCRIPT:32768,MAX_BUNDLE_BYTES:49152,
    MAX_NAME:120,MAX_MESSAGE:8192,MAX_READ_TURNS:50,
    MAX_LIST_RUNS:50,MAX_OUTPUT_CHUNK:8192,MAX_ID:200,MAX_PATH:1024,MAX_FILE_CHUNK:65536,
    ID_RE:/^[a-z0-9][a-z0-9-]{0,63}$/,
    FIELDS:["kind","markup","name","script","style","ui_id","version"],

    epoch:0,home:"",principal:"",enabled:false,busy:false,
    library:[],unreadable:"",selection:null,active:null,frame:null,listener:null,
    // The stored row's revision as last read; 0 means no row exists yet.
    revision:0,
    // Bumped on every mount AND unmount. A request captures it, so a reply owed
    // to the bundle that was on screen a moment ago cannot settle a promise in
    // the one that replaced it -- both bootstraps number requests from r1, so the
    // ids collide by construction (Codex, 2026-09-26).
    frameGen:0,ready:false,sending:false,emitting:false,pending:0,

    bytes(value){ return new TextEncoder().encode(String(value)).length; },

    // ---- component reader (pure; no DOM, no network, no sanitizing) ---------
    unsupported(reason){ return {ok:false,reason}; },
    text(value,limit){ return typeof value==="string"&&value.length<=limit; },
    parseBundle(component){
      if(!component||typeof component!=="object"||Array.isArray(component))
        return this.unsupported("UI component is not an object");
      const keys=Object.keys(component).sort();
      const extra=keys.filter(k=>!this.FIELDS.includes(k));
      if(extra.length) return this.unsupported("UI component carries fields this app does not render: "+extra.join(", "));
      if(keys.length!==this.FIELDS.length)
        return this.unsupported("UI component is missing "+this.FIELDS.filter(k=>!keys.includes(k)).join(", "));
      if(component.kind!==this.KIND) return this.unsupported("not a "+this.KIND+" component");
      if(component.version!==this.VERSION)
        return this.unsupported("UI version "+String(component.version)+" is not supported; this app renders version 1");
      if(!this.text(component.ui_id,64)||!this.ID_RE.test(component.ui_id))
        return this.unsupported("ui_id must be lowercase letters, digits or dashes");
      if(!this.text(component.name,this.MAX_NAME)||!component.name.trim())
        return this.unsupported("name must be a non-empty string of at most "+this.MAX_NAME+" characters");
      if(!this.text(component.markup,this.MAX_MARKUP))
        return this.unsupported("markup must be a string of at most "+this.MAX_MARKUP+" characters");
      if(!this.text(component.style,this.MAX_STYLE))
        return this.unsupported("style must be a string of at most "+this.MAX_STYLE+" characters");
      if(!this.text(component.script,this.MAX_SCRIPT))
        return this.unsupported("script must be a string of at most "+this.MAX_SCRIPT+" characters");
      const size=this.bytes(JSON.stringify(component));
      if(size>this.MAX_BUNDLE_BYTES)
        return this.unsupported("this UI is "+size+" bytes; the limit is "+this.MAX_BUNDLE_BYTES);
      return {ok:true,bundle:{kind:this.KIND,version:this.VERSION,ui_id:component.ui_id,
        name:component.name.trim(),markup:component.markup,style:component.style,script:component.script}};
    },
    // The library is a LIST of any length, ordered as stored, with no
    // user-chosen keys; each entry names itself by `ui_id`.
    readLibrary(configuration){
      const raw=configuration&&configuration.ui_library;
      if(raw===undefined||raw===null) return {ok:true,entries:[]};
      if(!Array.isArray(raw)) return this.unsupported("ui_library is not a list");
      const entries=[],seen=new Set();
      for(const component of raw){
        const parsed=this.parseBundle(component);
        if(!parsed.ok) return parsed;
        if(seen.has(parsed.bundle.ui_id)) return this.unsupported("ui_id "+parsed.bundle.ui_id+" is listed twice");
        seen.add(parsed.bundle.ui_id); entries.push(parsed.bundle);
      }
      return {ok:true,entries};
    },
    readSelection(configuration){
      const raw=configuration&&configuration.ui_selection;
      if(raw===undefined||raw===null) return {ok:true,selection:null};
      if(!raw||typeof raw!=="object"||Array.isArray(raw)) return this.unsupported("ui_selection is not an object");
      const keys=Object.keys(raw).sort();
      if(raw.version!==1) return this.unsupported("ui_selection version is not supported");
      if(raw.state==="default"){
        if(JSON.stringify(keys)!==JSON.stringify(["state","version"]))
          return this.unsupported("a default ui_selection carries unexpected fields");
        return {ok:true,selection:{version:1,state:"default"}};
      }
      if(raw.state!=="active") return this.unsupported("unknown ui_selection state");
      if(JSON.stringify(keys)!==JSON.stringify(["state","ui_id","version"]))
        return this.unsupported("an active ui_selection carries unexpected fields");
      if(!this.text(raw.ui_id,64)||!this.ID_RE.test(raw.ui_id)) return this.unsupported("ui_selection names an invalid ui_id");
      return {ok:true,selection:{version:1,state:"active",ui_id:raw.ui_id}};
    },
    // For inspecting a PUBLIC design: exactly one UI component, or nothing.
    readDefinition(agent){
      if(!agent||typeof agent!=="object"||!agent.components||typeof agent.components!=="object"||Array.isArray(agent.components))
        return this.unsupported("definition has no components");
      const keys=[];
      for(const [key,component] of Object.entries(agent.components))
        if(component&&typeof component==="object"&&component.kind===this.KIND) keys.push(key);
      if(keys.length!==1) return this.unsupported(keys.length
        ? "definition has "+keys.length+" UI components; this app renders exactly one"
        : "definition has no "+this.KIND+" component");
      const parsed=this.parseBundle(agent.components[keys[0]]);
      if(!parsed.ok) return parsed;
      return {ok:true,key:keys[0],bundle:parsed.bundle};
    },

    // ---- lifecycle and fencing (same shape as AppLayout) -------------------
    fence(epoch,home){ return this.enabled&&epoch===this.epoch&&home===this.home; },
    reset(){
      this.epoch++; this.unmount();
      this.enabled=false; this.home=""; this.principal="";
      this.library=[]; this.unreadable=""; this.selection=null; this.busy=false;
      this.revision=0;
      $("btn-ui-switch").hidden=true;
      this.status(""); this.paint();
    },
    // The SAME account can move to another home mid-session (the status poll
    // observes it and calls setQueueScope). A bundle mounted for the old home
    // would otherwise keep a live bridge and be served the NEW home's
    // conversation, because `converse`/`get_status` resolve the caller's current
    // home rather than the one the bundle was granted (Codex, 2026-09-26).
    // Sign-out already tore the bridge down; this closes the same-login path.
    homeChanged(home){
      const id=String(home||"").trim();
      if(!this.enabled||!id||id===this.home) return;
      this.reset();
      this.status("Your home universe changed; the custom UI was closed and its access ended.");
    },
    enable(home,principal){
      if(this.enabled&&this.home===home&&this.principal===principal) return;
      this.reset();
      const id=String(home||"").trim();
      if(!id||!principal) return;
      this.epoch++; this.home=id; this.principal=principal; this.enabled=true;
      $("btn-ui-switch").hidden=false;
      this.paint();
      this.load();
    },
    // One read of the viewer's own row. The server keys it by the signed-in
    // caller, so there is nothing here to name and no owner to check.
    async fetchRow(){
      const doc=await Owner.read({target:"app_ui",graph_id:this.home});
      const row=doc&&doc.app_ui;
      if(!row||doc.error||!Number.isInteger(row.revision)||row.revision<0||row.universe_id!==this.home)
        throw Error((doc&&(doc.detail||doc.error))||"unexpected app UI reply");
      return row;
    },
    // Refresh and first load. Fenced like every other request here: a reply for
    // a home this controller has left is dropped.
    async load(){
      if(!this.enabled||this.busy) return;
      const epoch=this.epoch,home=this.home;
      this.busy=true; this.paint();
      try{
        const row=await this.fetchRow();
        if(!this.fence(epoch,home)) return;
        this.adopt(row);
      }catch(err){
        if(!this.fence(epoch,home)) return;
        if(err&&err.authRequired){ sessionExpired(); return; }
        this.status("Could not read your installed UIs ("+(err&&err.message||"unknown error")+"). Default chat is in use.");
      }finally{ if(this.fence(epoch,home)){ this.busy=false; this.paint(); } }
    },
    adopt(row){
      if(!this.enabled) return;
      this.revision=row.revision;
      const library=this.readLibrary(row),selection=this.readSelection(row);
      this.unmount();
      if(!library.ok){
        // An unreadable library is remembered as unreadable, NOT as empty. An
        // empty cache here is what let a later install rewrite `ui_library` from
        // nothing and drop the bundles it could not parse (Codex, 2026-09-26).
        this.library=[]; this.unreadable=library.reason; this.selection=null;
        this.status("Installed UIs unreadable: "+library.reason+". Default chat is in use. Installing would overwrite them, so it is disabled."); this.paint(); return;
      }
      this.library=library.entries; this.unreadable="";
      if(!selection.ok){
        this.selection=null;
        this.status("Saved UI choice unreadable: "+selection.reason+". Default chat is in use."); this.paint(); return;
      }
      this.selection=selection.selection;
      if(this.selection&&this.selection.state==="active"){
        const entry=this.library.find(b=>b.ui_id===this.selection.ui_id);
        if(entry){ this.mount(entry); this.status("Using "+entry.name+"."); }
        else this.status("Your saved UI ("+this.selection.ui_id+") is no longer installed. Default chat is in use.");
      }else this.status(this.library.length?"Default chat is in use.":"");
      this.paint();
    },

    // ---- rendering: the bundle never enters this document ------------------
    mount(entry){
      this.unmount();
      const host=$("ui-frame-host"),frame=document.createElement("iframe");
      frame.id="ui-frame"; frame.className="ui-frame"; frame.title=entry.name;
      frame.setAttribute("sandbox",this.SANDBOX);
      frame.setAttribute("referrerpolicy","no-referrer");
      frame.setAttribute("src",this.FRAME_SRC);
      this.frame=frame; this.active=entry; this.ready=false;
      this.frameGen++; this.pending=0; this.sending=false; this.emitting=false;
      this.listener=event=>this.receive(event);
      window.addEventListener("message",this.listener);
      host.replaceChildren(frame);
      host.hidden=false;
      $("view-chat").classList.add("ui-custom-active");
      this.paintHeader();
    },
    unmount(){
      if(this.listener){ window.removeEventListener("message",this.listener); this.listener=null; }
      const host=$("ui-frame-host");
      host.replaceChildren(); host.hidden=true;
      $("view-chat").classList.remove("ui-custom-active");
      this.frame=null; this.active=null; this.ready=false; this.sending=false; this.emitting=false; this.pending=0;
      this.frameGen++;
      this.paintHeader();
    },

    // ---- the bridge: one frame, one allowlist, one universe ----------------
    // A frozen map. An action absent from it does not exist — the refusal names
    // what was asked and nothing is guessed from a near-match.
    ACTIONS:Object.freeze({
      whoami:"whoami",list_agents:"listAgents",
      send_message:"sendMessage",read_conversation:"readConversation",
      list_automations:"listAutomations",list_runs:"listRuns",
      read_run:"readRun",read_run_output:"readRunOutput",
      list_files:"listFiles",read_file:"readFile",emit:"emit"}),
    receive(event){
      // Only THIS frame's window is heard. Another frame, a popup, or the page
      // itself cannot speak for the bundle, and the check is on the window
      // object rather than on an origin string, which an opaque origin makes "null"
      // for every sandboxed document on the page.
      if(!this.frame||event.source!==this.frame.contentWindow) return;
      const message=event.data;
      if(!message||typeof message!=="object"||message.ta_ui!==this.PROTOCOL) return;
      if(message.type==="ready"){ this.deliver(); return; }
      if(message.type!=="call"||typeof message.id!=="string"||typeof message.action!=="string") return;
      this.serve(message.id,message.action,message.params);
    },
    deliver(){
      if(!this.frame||!this.active||this.ready) return;
      this.ready=true;
      this.post({ta_ui:this.PROTOCOL,type:"bundle",bundle:{
        markup:this.active.markup,style:this.active.style,script:this.active.script}});
    },
    post(payload){
      const frame=this.frame&&this.frame.contentWindow;
      // The frame's origin is opaque, so it cannot be named; "*" still reaches
      // only this window. What crosses is the bundle's own source and results the
      // bundle asked for as the viewer -- which includes this viewer's
      // conversation text, so it IS sensitive; see the residual-risk note in
      // openspec/changes/composable-ui-experiences/design.md.
      if(frame) frame.postMessage(payload,"*");
    },
    refuse(id,error){ this.post({ta_ui:this.PROTOCOL,type:"result",id,ok:false,error:String(error)}); },
    // Re-checks, against the server, that the signed-in identity and home are
    // still the ones this bundle was granted. `converse` and `get_status` resolve
    // the CALLER's current home, so a bundle mounted before a home change would
    // otherwise be served the new home's data.
    async verify(){
      const epoch=this.epoch,home=this.home,principal=this.principal;
      const me=await fetchMe();
      if(!this.fence(epoch,home)) throw new Error("your session changed");
      if(!me||me.principal_id!==principal||me.universe_id!==home||me.setup!=="connected"){
        const err=new Error("your signed-in identity or home changed; this UI's access ended");
        err.revoke=true; throw err;
      }
    },
    async serve(id,action,params){
      // A reply is owed to the frame that ASKED. Without this, bundle A's answer
      // reaches bundle B, and since both bootstraps number requests from r1 it
      // settles B's own r1 promise with A's data (Codex, 2026-09-26).
      const gen=this.frameGen;
      const method=Object.prototype.hasOwnProperty.call(this.ACTIONS,action)?this.ACTIONS[action]:null;
      if(!method){ this.refuse(id,"action not available: "+action); return; }
      if(this.pending>=8){ this.refuse(id,"too many requests in flight"); return; }
      const epoch=this.epoch,home=this.home,args=(params&&typeof params==="object"&&!Array.isArray(params))?params:{};
      this.pending++;
      try{
        await this.verify();
        const result=await this[method](args);
        if(!this.fence(epoch,home)||gen!==this.frameGen||!this.frame) return;
        this.post({ta_ui:this.PROTOCOL,type:"result",id,ok:true,result});
      }catch(err){
        if(err&&err.revoke){ this.refuse(id,err.message); this.reset(); return; }
        if(!this.fence(epoch,home)||gen!==this.frameGen||!this.frame) return;
        if(err&&err.authRequired){ this.refuse(id,"your session ended"); sessionExpired(); return; }
        this.refuse(id,(err&&err.message)||"unavailable");
      }finally{ if(gen===this.frameGen) this.pending--; }
    },
    // The viewer's identity, reduced to what a UI needs to greet them. No
    // principal id, no token, no provider or credential material.
    async whoami(){
      return {protocol:this.PROTOCOL,universe_id:this.home,
        universe_name:String(($("universe-name")&&$("universe-name").textContent)||"").trim()};
    },
    // The viewer's OWN agents. `graph_id` is this.home, never an argument, so a
    // bundle cannot enumerate anybody else's universe.
    async listAgents(){
      // One page, the size AppLayout reads with. A bundle asking "what agents do
      // I have" is a display read: if a viewer keeps more than a page of them it
      // sees the newest page, which is a page size, not a refusal. Nothing here
      // disables a control on the count (that cliff was removed 2026-09-30).
      const doc=await Owner.read(
        {target:"agent_bindings",graph_id:this.home,limit:AppLayout.PAGE});
      if(!doc||doc.error||!Array.isArray(doc.bindings)) throw new Error("your agents are unavailable");
      const selected=AppLayout.installation&&AppLayout.installation.configuration&&
        AppLayout.installation.configuration.turn_consumer;
      const selectedId=selected&&selected.state==="active"?String(AppLayout.installation.binding_id):"";
      const agents=[];
      for(const b of doc.bindings){
        if(!b||typeof b!=="object"||b.universe_id!==this.home) continue;
        // Picked fields only. A configuration is private operational data and
        // never crosses into a bundle, so only its NAME does.
        agents.push({agent_id:String(b.agent_binding_id||""),
          name:String((b.configuration&&b.configuration.name)||"Unnamed agent"),
          selected:String(b.agent_binding_id||"")===selectedId&&selectedId!==""});
      }
      return {agents};
    },
    // Sends through the app's ordinary turn path, so a bundle's message gets the
    // same recovery, queueing and thread record a typed one gets — and appears
    // in the shared conversation rather than a private side channel.
    //
    // `agent` is NOT yet honoured per message: the server admits a turn only for
    // the universe's ONE currently selected conversation
    // (consumer_runtime.reserve_prepared_turn). Naming a different agent is
    // refused by name rather than silently sent to the selected one.
    async sendMessage(args){
      const text=typeof args.text==="string"?args.text.trim():"";
      if(!text) throw new Error("text is required");
      if(text.length>this.MAX_MESSAGE) throw new Error("text exceeds "+this.MAX_MESSAGE+" characters");
      const wanted=typeof args.agent==="string"?args.agent.trim():"";
      if(wanted){
        const agents=await this.listAgents();
        const match=agents.agents.find(a=>a.agent_id===wanted||a.name===wanted);
        if(!match) throw new Error("no agent of yours is named "+wanted);
        if(!match.selected) throw new Error(
          "this universe sends turns to its selected conversation only; select "+match.name+" in App design first");
      }
      if(this.sending) throw new Error("a message from this UI is already in flight");
      this.sending=true;
      try{ await sendTurn(text,text,{inputMethod:"app_action"}); }
      finally{ this.sending=false; }
      return {sent:true};
    },
    // The viewer's own saved conversation, field by field.
    //
    // Pinned to `this.home` and the ANSWER is checked against it. `get_status`
    // with no universe defaults to the caller's ACTIVE universe, so an unpinned
    // read hands a bundle whichever home the account moved to rather than the one
    // it was granted (Codex, 2026-09-26). `verify()` closes the window; this
    // closes the read itself, so neither depends on the other being right.
    async readConversation(args){
      const limit=Number.isInteger(args.limit)&&args.limit>0?Math.min(args.limit,this.MAX_READ_TURNS):this.MAX_READ_TURNS;
      const doc=await Owner.status(
        {universe_id:this.home,include_conversation:true});
      if(!doc||doc.error) throw new Error("your conversation is unavailable");
      if(String(doc.universe_id||"")!==this.home)
        throw new Error("that conversation belongs to another universe; this UI's access ended");
      const conversation=doc.recent_conversation;
      const raw=(conversation&&Array.isArray(conversation.turns))?conversation.turns:[];
      const turns=[];
      for(const turn of raw.slice(-limit)){
        if(!turn||typeof turn.text!=="string") continue;
        turns.push({speaker:String(turn.speaker||"unknown"),text:turn.text,
          at:typeof turn.ts==="number"?turn.ts:null,truncated:!!turn.truncated});
      }
      return {turns};
    },

    // ---- live state: the viewer's own automations and runs, read-only -------
    // What a screen needs to show agents WORKING rather than a picture of them.
    // Same rules as the reads above: `graph_id` is always this.home, the answer
    // is checked against it where it names a universe, and every reply is built
    // from picked fields. Automation `inputs` and a run's `actor` never cross:
    // the first is the owner's private configuration, the second a principal id.
    //
    // The server scopes each of these to the named universe, so a run id from
    // anywhere else reads as not found rather than being returned.
    async listAutomations(){
      const doc=await Owner.read(
        {target:"automations",graph_id:this.home,limit:100});
      if(!doc||doc.error||!Array.isArray(doc.automations)) throw new Error("your automations are unavailable");
      if(String(doc.universe_id||"")!==this.home)
        throw new Error("those automations belong to another universe; this UI's access ended");
      const automations=[];
      for(const a of doc.automations){
        // A retired fleet-era row names no universe and runs nothing: skip it.
        if(!a||typeof a!=="object"||a.universe_id!==this.home) continue;
        const t=(a.trigger&&typeof a.trigger==="object")?a.trigger:{};
        automations.push({automation_id:String(a.automation_id||""),name:String(a.name||""),
          branch_id:String(a.branch_def_id||""),
          trigger:{kind:String(t.kind||""),interval_seconds:Number.isFinite(t.interval_seconds)?t.interval_seconds:null,
            cron:String(t.cron_expr||""),event:String(t.event_type||"")},
          state:String(a.desired_state||""),paused_because:String(a.pause_reason||""),
          last_run_id:String(a.last_run_id||""),last_result:String(a.last_reason||""),
          last_finished_at:a.last_finished_at||null,next_due_at:a.next_due_at||null,
          consecutive_failures:Number.isInteger(a.consecutive_failures)?a.consecutive_failures:0});
      }
      return {automations};
    },
    async listRuns(args){
      const limit=Number.isInteger(args.limit)&&args.limit>0?Math.min(args.limit,this.MAX_LIST_RUNS):this.MAX_LIST_RUNS;
      const call={target:"runs",graph_id:this.home,limit};
      if(typeof args.status==="string"&&args.status.trim()) call.run_status=args.status.trim();
      const doc=await Owner.read(call);
      if(!doc||doc.error||!Array.isArray(doc.runs)) throw new Error("your runs are unavailable");
      const runs=[];
      for(const r of doc.runs){
        if(!r||typeof r!=="object") continue;
        runs.push(this.runSummary(r));
      }
      return {runs};
    },
    runSummary(r){
      return {run_id:String(r.run_id||""),branch_id:String(r.branch_def_id||""),
        name:String(r.run_name||""),status:String(r.status||""),
        started_at:r.started_at||null,finished_at:r.finished_at||null,
        last_node_id:String(r.last_node_id||"")};
    },
    runId(args){
      const id=typeof args.run_id==="string"?args.run_id.trim():"";
      if(!id||id.length>this.MAX_ID) throw new Error("run_id is required");
      return id;
    },
    async readRun(args){
      const id=this.runId(args);
      const doc=await Owner.read(
        {target:"run",graph_id:this.home,run_id:id});
      if(!doc||doc.error||String(doc.run_id||"")!==id) throw new Error("that run is not one of yours");
      const nodes=[];
      for(const n of Array.isArray(doc.node_statuses)?doc.node_statuses:[])
        if(n&&typeof n==="object") nodes.push({node_id:String(n.node_id||""),status:String(n.status||"")});
      const catalog=doc.output_catalog&&Array.isArray(doc.output_catalog.fields)?doc.output_catalog.fields:[];
      return Object.assign(this.runSummary(doc),{error:String(doc.error||""),nodes,
        output_fields:catalog.filter(f=>f&&typeof f.name==="string").map(f=>f.name)});
    },
    // One output field of one of the viewer's runs, in bounded chunks: what an
    // agent node wrote is how a screen shows what that agent said.
    async readRunOutput(args){
      const id=this.runId(args);
      const field=typeof args.field==="string"?args.field:"";
      if(!field||field.length>this.MAX_ID) throw new Error("field is required");
      const offset=Number.isInteger(args.offset)&&args.offset>0?args.offset:0;
      const doc=await Owner.read({target:"run_output",graph_id:this.home,run_id:id,
        field_name:field,output_offset:offset,output_max_chars:this.MAX_OUTPUT_CHUNK});
      if(!doc||doc.error||typeof doc.chunk!=="string") throw new Error("that output is not available");
      return {field:String(doc.field_name||field),encoding:doc.encoding==="json"?"json":"text",
        text:doc.chunk,offset:Number.isInteger(doc.offset)?doc.offset:offset,
        total_chars:Number.isInteger(doc.total_chars)?doc.total_chars:null,
        next_offset:Number.isInteger(doc.next_offset)?doc.next_offset:null};
    },

    // ---- the shared folder and the wake -------------------------------------
    // Agents coordinate through files in the universe folder, so a screen of
    // them reads those files. Owner-only on the server (an admin grant on this
    // home), pinned to this.home here, picked fields back.
    filePath(value,required){
      const path=typeof value==="string"?value.trim():"";
      if(required&&!path) throw new Error("path is required");
      if(path.length>this.MAX_PATH) throw new Error("path is too long");
      return path;
    },
    async listFiles(args){
      const path=this.filePath(args.path,false);
      const doc=await Owner.read(
        {target:"universe_files",graph_id:this.home,query:path});
      if(!doc||doc.error||!Array.isArray(doc.entries)) throw new Error("that folder is not available");
      if(String(doc.universe_id||"")!==this.home)
        throw new Error("that folder belongs to another universe; this UI's access ended");
      const entries=[];
      for(const e of doc.entries){
        if(!e||typeof e.name!=="string") continue;
        const kind=e.kind==="dir"?"dir":"file";
        entries.push(kind==="dir"?{name:e.name,kind}:{name:e.name,kind,
          size_bytes:Number.isInteger(e.size_bytes)?e.size_bytes:null});
      }
      return {path:String(doc.path||""),entries,truncated:!!doc.truncated};
    },
    async readFile(args){
      const path=this.filePath(args.path,true);
      const offset=Number.isInteger(args.offset)&&args.offset>0?args.offset:0;
      const doc=await Owner.read({target:"universe_file",graph_id:this.home,
        query:path,file_offset:offset,file_max_bytes:this.MAX_FILE_CHUNK});
      if(!doc||doc.error) throw new Error("that file is not available");
      if(String(doc.universe_id||"")!==this.home)
        throw new Error("that file belongs to another universe; this UI's access ended");
      const text=doc.encoding==="text"&&typeof doc.text==="string";
      return {path:String(doc.path||path),encoding:text?"text":"base64",
        content:text?doc.text:String(doc.base64||""),size_bytes:Number.isInteger(doc.size_bytes)?doc.size_bytes:null,
        offset:Number.isInteger(doc.offset)?doc.offset:offset,
        next_offset:Number.isInteger(doc.next_offset)?doc.next_offset:null};
    },
    // Wakes the viewer's OWN agent subscribed to `name` (an app_event
    // automation). It cannot run anything by id: what listens to a name is the
    // owner's decision, made when the subscription was created.
    async emit(args){
      const name=typeof args.name==="string"?args.name.trim():"";
      if(!name) throw new Error("name is required");
      const data=args.data===undefined||args.data===null?{}:args.data;
      if(typeof data!=="object"||Array.isArray(data)) throw new Error("data must be an object");
      if(this.emitting) throw new Error("an event from this UI is already in flight");
      this.emitting=true;
      try{
        const doc=await MCP.callTool("run_graph",{operation:"emit_event",graph_id:this.home,
          inputs_json:JSON.stringify({name,data})});
        if(!doc||doc.error) throw new Error((doc&&(doc.detail||doc.error))||"the event was not sent");
        return {emitted:doc.emitted===true,woke:Number.isInteger(doc.woke)?doc.woke:0};
      }finally{ this.emitting=false; }
    },

    // ---- switching: explicit, persisted through ONE write path -------------
    async choose(uiId){
      if(!this.enabled||this.busy) return;
      const entry=this.library.find(b=>b.ui_id===uiId);
      if(!entry){ this.status("That UI is not installed. Refresh."); this.paint(); return; }
      // Apply first so the switch is immediate; persistence is what makes it
      // survive a sign-in, and a failed write says so rather than reverting the
      // view the user just asked for.
      this.mount(entry);
      await this.remember({version:1,state:"active",ui_id:entry.ui_id},
        "Now using "+entry.name+".","Now using "+entry.name+" for this visit only");
    },
    async chooseDefault(){
      if(!this.enabled||this.busy) return;
      this.unmount();
      await this.remember({version:1,state:"default"},
        "Default chat restored.","Default chat restored for this visit only");
    },
    // The ONE write path. Re-reads the row so `mutate` works on what is stored
    // now rather than on this controller's cache, then saves only the fields
    // `mutate` returns, compare-and-set on the revision just read. A save that
    // loses a race is refused by the server and reported; nothing is retried.
    // A fresh account needs no setup step: its first save (revision 0) creates
    // the row, and nothing about it is published.
    async save(noun,mutate){
      if(!this.enabled||this.busy) return {ok:false,reason:"not ready"};
      const epoch=this.epoch,home=this.home;
      this.busy=true; this.paint();
      try{
        const row=await this.fetchRow();
        if(!this.fence(epoch,home)) return {ok:false,reason:"stale"};
        const changes=mutate(JSON.parse(JSON.stringify(row)));
        const result=await MCP.callTool("write_graph",{target:"app_ui",operation:"save",
          graph_id:home,expected_revision:row.revision,payload_json:JSON.stringify(changes)});
        if(!this.fence(epoch,home)) return {ok:false,reason:"stale"};
        const saved=result&&result.app_ui;
        if(!result||result.error||result.status!=="saved"||!saved||saved.universe_id!==home||
           saved.revision!==row.revision+1)
          throw Error((result&&(result.detail||result.error))||noun+" save was not confirmed");
        for(const key of Object.keys(changes))
          if(JSON.stringify(saved[key])!==JSON.stringify(changes[key])) throw Error(noun+" save did not match");
        this.revision=saved.revision;
        return {ok:true,row:saved};
      }catch(err){
        if(!this.fence(epoch,home)) return {ok:false,reason:"stale"};
        if(err&&err.authRequired){ sessionExpired(); return {ok:false,reason:"auth"}; }
        return {ok:false,reason:"failed",error:err};
      }finally{ if(this.fence(epoch,home)){ this.busy=false; this.paint(); } }
    },
    async remember(selection,saved,unsaved){
      const outcome=await this.save("UI choice",()=>({ui_selection:JSON.parse(JSON.stringify(selection))}));
      if(!outcome.ok){
        const why=outcome.error&&outcome.error.message||outcome.reason||"unavailable";
        this.status(unsaved+" — the choice was not saved ("+why+").");
      }else{
        this.selection=selection; this.status(saved);
      }
      this.paint();
    },
    // Install a bundle into the viewer's own library: a remix installs the
    // COMPONENT, so it runs against this viewer's bridge and this viewer's
    // universe. The author's universe is never addressed by an installed copy.
    async install(component){
      if(!this.enabled||this.busy) return {ok:false,reason:"not ready"};
      const parsed=this.parseBundle(component);
      if(!parsed.ok){ this.status("Cannot install: "+parsed.reason); this.paint(); return parsed; }
      // Refuse rather than overwrite what could not be read. An install used to
      // rebuild `ui_library` from this controller's cache, and `adopt` empties that
      // cache when ANY stored entry is unsupported -- so installing next to a
      // future-version bundle silently deleted it, and CAS could not notice
      // because the revision was current (Codex, 2026-09-26).
      if(this.unreadable){
        this.status("Your installed UIs cannot be read ("+this.unreadable+"), so installing would overwrite them. Nothing was changed.");
        this.paint(); return this.unsupported("library unreadable");
      }
      let next=null;
      const outcome=await this.save("UI install",row=>{
        // Built from the row the save actually read, not from the cache -- so a
        // library that changed since the last read is re-checked here instead
        // of being replaced by a stale view.
        const observed=this.readLibrary(row);
        if(!observed.ok) throw Error("Your installed UIs cannot be read ("+observed.reason+"); nothing was overwritten");
        next=observed.entries.filter(b=>b.ui_id!==parsed.bundle.ui_id).concat([parsed.bundle]);
        // No library-wide limit, so no install is ever turned away for the size
        // of what is already there. The bundle itself was validated above, and
        // its bytes are the universe's storage.
        return {ui_library:JSON.parse(JSON.stringify(next))};
      });
      if(!outcome.ok){
        const why=outcome.error&&outcome.error.message||outcome.reason||"unavailable";
        this.status("The UI was not installed ("+why+")."); this.paint(); return outcome;
      }
      this.library=next;
      this.status("Installed "+parsed.bundle.name+". Switch to it whenever you like.");
      this.paint();
      return {ok:true,bundle:parsed.bundle};
    },
    // Sharing is the existing path: a UI component inside a public definition.
    // Publishing is a separate, explicit act — an installed UI stays private.
    publishPayload(bundle,description){
      const parsed=this.parseBundle(bundle);
      if(!parsed.ok) return parsed;
      return {ok:true,payload:{schema_version:1,name:parsed.bundle.name,
        description:String(description||""),tags:[this.KIND],
        components:{ui:JSON.parse(JSON.stringify(parsed.bundle))}}};
    },

    // ---- fixed chrome: textContent only, never markup ----------------------
    status(text){ const node=$("ui-status"); if(node) node.textContent=text||""; },
    paintHeader(){
      const label=$("ui-mode");
      if(!label) return;
      label.hidden=!this.active;
      label.textContent=this.active?"UI: "+this.active.name:"";
    },
    paint(){
      this.paintHeader();
      const list=$("ui-list");
      if(!list) return;
      list.replaceChildren();
      const row=document.createElement("li");
      row.appendChild(AppLayout.button("Default chat",()=>this.chooseDefault(),this.busy||!this.active));
      list.appendChild(row);
      for(const bundle of this.library){
        const item=document.createElement("li"),current=!!(this.active&&this.active.ui_id===bundle.ui_id);
        item.appendChild(AppLayout.button((current?"Using: ":"Use ")+bundle.name,
          ()=>this.choose(bundle.ui_id),this.busy||current));
        list.appendChild(item);
      }
      if(!this.library.length)
        AppLayout.line(list,"No custom UI installed. Ask your universe to build one.","muted");
      $("btn-ui-refresh").disabled=this.busy;
    },
    open(){
      if(!this.enabled) return;
      this.paint();
      const dialog=$("ui-dialog");
      if(!dialog.open) dialog.showModal();
    },
    init(){
      $("btn-ui-switch").addEventListener("click",()=>this.open());
      $("btn-ui-refresh").addEventListener("click",()=>this.load());
      $("btn-ui-close").addEventListener("click",()=>$("ui-dialog").close());
      this.paintHeader();
    }
  };
