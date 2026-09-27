  // ---- Custom universe UI: isolated renderer + closed bridge ----------------
  // A universe can hold executable UI bundles (`tinyassets.app-ui.v1`) its own
  // agent writes, and this renders them. A bundle is somebody's arbitrary code —
  // usually somebody the viewer has never met, because bundles are shared by
  // publish/remix — so nothing here sanitizes it. It runs in the sandboxed,
  // opaque-origin document `/mcp/app/ui-frame` serves (see ui_frame.py for the
  // policy), which owns no storage, no cookies and no network of its own.
  //
  // Everything the bundle can do is in ACTIONS below and nowhere else. Each
  // handler builds its own tool arguments and pins the universe to the VIEWING
  // user's current home, so a bundle cannot name a universe: cross-user reach is
  // not refused by a check, it is unrepresentable. Replies are assembled from
  // picked fields, never spread from a server payload, so a field added upstream
  // later cannot ride out to untrusted code.
  //
  // Storage is the existing private `app_experience` AgentBinding — the bundles
  // in `ui_library` and the choice in `ui_selection`, written through
  // AppLayout.writeConfiguration so the layout editor and this share ONE
  // revision-guarded write path rather than two that drift.
  const AppUI={
    KIND:"tinyassets.app-ui.v1",VERSION:1,PROTOCOL:1,
    SHELL_KIND:"tinyassets.app-experience-shell.v1",
    FRAME_SRC:"/mcp/app/ui-frame",
    // No `allow-same-origin`: that single word is the whole isolation boundary.
    // With it the frame would share this page's origin and could read
    // `sessionStorage` (the access token), `localStorage` and the parent DOM.
    // The frame's own response header sandboxes it too, so this is the second of
    // two independent locks, not the only one.
    SANDBOX:"allow-scripts",
    // Bounds chosen so a FULL library still fits the binding's canonical-JSON cap
    // (MAX_AGENT_JSON_BYTES in tinyassets/custom_agents.py). A test derives that
    // relation from the Python constant rather than restating the number here.
    MAX_MARKUP:32768,MAX_STYLE:16384,MAX_SCRIPT:32768,MAX_BUNDLE_BYTES:49152,
    // Sizes are UTF-8 BYTES, because that is what the server caps. Counting
    // UTF-16 units let three separately-accepted CJK bundles blow the binding cap
    // at write time (Codex, 2026-09-26), which surfaces as an unexplained
    // "uncertain" shared editor rather than a refusal the user can act on.
    // MAX_CONFIG_BYTES must equal MAX_AGENT_JSON_BYTES; a test asserts that.
    MAX_CONFIG_BYTES:262144,
    LIBRARY_LIMIT:4,MAX_NAME:120,MAX_MESSAGE:8192,MAX_READ_TURNS:50,
    ID_RE:/^[a-z0-9][a-z0-9-]{0,63}$/,
    FIELDS:["kind","markup","name","script","style","ui_id","version"],

    epoch:0,home:"",principal:"",enabled:false,busy:false,
    library:[],unreadable:"",selection:null,active:null,frame:null,listener:null,
    // Bumped on every mount AND unmount. A request captures it, so a reply owed
    // to the bundle that was on screen a moment ago cannot settle a promise in
    // the one that replaced it -- both bootstraps number requests from r1, so the
    // ids collide by construction (Codex, 2026-09-26).
    frameGen:0,ready:false,sending:false,pending:0,

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
    // The library is a LIST, not an object: `_check_binding_content_fields`
    // rejects reserved key names like `messages`, and a list has no user-chosen
    // keys to collide with one.
    readLibrary(configuration){
      const raw=configuration&&configuration.ui_library;
      if(raw===undefined||raw===null) return {ok:true,entries:[]};
      if(!Array.isArray(raw)) return this.unsupported("ui_library is not a list");
      if(raw.length>this.LIBRARY_LIMIT)
        return this.unsupported("ui_library holds "+raw.length+" UIs; this app reads at most "+this.LIBRARY_LIMIT);
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
      // No read of its own: AppLayout owns the binding read, and reading the
      // same rows concurrently would have two controllers racing on one
      // `candidates`/`loaded`/`saturated` state. It hands the result to `adopt`.
      //
      // A read already settled for this home (AppLayout stayed enabled while this
      // controller was reset) would otherwise never be handed over at all.
      if(AppLayout.enabled&&AppLayout.loaded&&AppLayout.home===this.home) this.adopt(AppLayout.installation);
    },
    // Called by AppLayout once its binding read has settled. The configuration
    // handed over is the one AppLayout already verified as the viewer's own,
    // owner-controlled, non-serving app-experience installation.
    adopt(installation){
      if(!this.enabled) return;
      const configuration=installation&&installation.configuration||null;
      const library=this.readLibrary(configuration),selection=this.readSelection(configuration);
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
    // Refresh re-runs the ONE read, which calls `adopt` again when it settles.
    load(){ if(this.enabled) AppLayout.loadInstallation(); },

    // ---- rendering: the bundle never enters this document ------------------
    mount(entry){
      this.unmount();
      const host=$("ui-frame-host"),frame=document.createElement("iframe");
      frame.id="ui-frame"; frame.className="ui-frame"; frame.title=entry.name;
      frame.setAttribute("sandbox",this.SANDBOX);
      frame.setAttribute("referrerpolicy","no-referrer");
      frame.setAttribute("src",this.FRAME_SRC);
      this.frame=frame; this.active=entry; this.ready=false;
      this.frameGen++; this.pending=0; this.sending=false;
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
      this.frame=null; this.active=null; this.ready=false; this.sending=false; this.pending=0;
      this.frameGen++;
      this.paintHeader();
    },

    // ---- the bridge: one frame, one allowlist, one universe ----------------
    // A frozen map. An action absent from it does not exist — the refusal names
    // what was asked and nothing is guessed from a near-match.
    ACTIONS:Object.freeze({
      whoami:"whoami",list_agents:"listAgents",
      send_message:"sendMessage",read_conversation:"readConversation"}),
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
      const doc=await MCP.callTool("read_graph",
        {target:"agent_bindings",graph_id:this.home,limit:AppLayout.LIST_LIMIT},{idempotent:true});
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
      const doc=await MCP.callTool("get_status",
        {universe_id:this.home,include_conversation:true},{idempotent:true});
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
    // Create this account's own private app experience: no published definition,
    // owner-only, and idempotent on the server, so a double click or a retry after
    // an unconfirmed reply returns the same place rather than minting a second one
    // or overwriting what the first one stored.
    async bootstrap(){
      const outcome=await AppLayout.writeConfiguration({definitionId:"",noun:"App experience",
        mutate:()=>{}});
      if(!outcome.ok){
        this.status("Could not set up your app experience ("+
          (outcome.error&&outcome.error.message||outcome.reason||"unavailable")+"). Nothing was changed.");
        this.paint();
      }
      return outcome;
    },
    async remember(selection,saved,unsaved){
      if(!AppLayout.installation){
        // Remembering a choice is not worth creating storage the person did not
        // ask for; the switch still applied for this visit.
        this.selection=selection; this.status(unsaved+"; no app experience exists yet to save it in."); this.paint(); return;
      }
      const definitionId=(AppLayout.installation&&AppLayout.installation.definition_id)||"";
      const outcome=await AppLayout.writeConfiguration({definitionId,noun:"UI choice",
        mutate:config=>{config.ui_selection=JSON.parse(JSON.stringify(selection));}});
      if(!outcome.ok){
        this.status(unsaved+" — the choice was not saved ("+(outcome.reason||"unavailable")+").");
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
      // A fresh account has no app experience yet. Create its private one first
      // rather than telling the person asking for a UI to go and adopt somebody
      // else's published layout: nothing is published by this, and the binding it
      // makes has no definition behind it (see custom_agents.create_binding).
      if(!AppLayout.installation){
        const ready=await this.bootstrap();
        if(!ready.ok) return ready;
      }
      // Whatever design this experience has adopted, if any. "" is normal.
      const definitionId=(AppLayout.installation&&AppLayout.installation.definition_id)||"";
      // Refuse rather than overwrite what could not be read. An install used to
      // rebuild `ui_library` from this controller's cache, and `adopt` empties that
      // cache when ANY stored entry is unsupported -- so installing next to a
      // future-version bundle silently deleted it, and CAS could not notice
      // because the revision was current (Codex, 2026-09-26).
      if(this.unreadable){
        this.status("Your installed UIs cannot be read ("+this.unreadable+"), so installing would overwrite them. Nothing was changed.");
        this.paint(); return this.unsupported("library unreadable");
      }
      // Refuse an over-cap install BEFORE the write, against the configuration
      // last observed. Reaching the same limit inside the guarded mutation works
      // but marks the shared editor uncertain -- correct for a race, wrong for a
      // size this app could see coming.
      const observedConfig=AppLayout.installation&&AppLayout.installation.configuration;
      if(observedConfig){
        const candidate=JSON.parse(JSON.stringify(observedConfig));
        candidate.ui_library=this.library.filter(b=>b.ui_id!==parsed.bundle.ui_id).concat([parsed.bundle]);
        const size=this.bytes(JSON.stringify(candidate));
        if(size>this.MAX_CONFIG_BYTES){
          this.status("This UI would take your app experience to "+size+" bytes, over the "+
            this.MAX_CONFIG_BYTES+"-byte limit. Nothing was changed.");
          this.paint(); return this.unsupported("configuration full");
        }
      }
      let next=null;
      const outcome=await AppLayout.writeConfiguration({definitionId,noun:"UI install",
        // Built from the configuration the write actually observed, not from the
        // cache -- so a library that changed since the last read is re-checked
        // inside the guarded window instead of being replaced by a stale view.
        mutate:config=>{
          const observed=this.readLibrary(config);
          if(!observed.ok) throw Error("Your installed UIs cannot be read ("+observed.reason+"); nothing was overwritten");
          next=observed.entries.filter(b=>b.ui_id!==parsed.bundle.ui_id).concat([parsed.bundle]);
          if(next.length>this.LIBRARY_LIMIT)
            throw Error("You already have "+this.LIBRARY_LIMIT+" UIs installed; remove one first");
          const candidate=JSON.parse(JSON.stringify(config));
          candidate.ui_library=JSON.parse(JSON.stringify(next));
          const size=this.bytes(JSON.stringify(candidate));
          if(size>this.MAX_CONFIG_BYTES)
            throw Error("This UI would take your app experience to "+size+
              " bytes, over the "+this.MAX_CONFIG_BYTES+"-byte limit; nothing was changed");
          config.ui_library=candidate.ui_library;
        }});
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
        AppLayout.line(list,"No custom UI installed. Your universe can write one into this app experience.","muted");
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
