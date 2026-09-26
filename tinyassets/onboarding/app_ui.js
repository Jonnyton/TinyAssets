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

    LIBRARY_LIMIT:4,MAX_NAME:120,MAX_MESSAGE:8192,MAX_READ_TURNS:50,

    ID_RE:/^[a-z0-9][a-z0-9-]{0,63}$/,

    FIELDS:["kind","markup","name","script","style","ui_id","version"],



    epoch:0,home:"",principal:"",enabled:false,busy:false,

    library:[],selection:null,active:null,frame:null,listener:null,

    ready:false,sending:false,pending:0,



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

      const size=JSON.stringify(component).length;

      if(size>this.MAX_BUNDLE_BYTES)

        return this.unsupported("this UI is "+size+" characters; the limit is "+this.MAX_BUNDLE_BYTES);

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

      this.library=[]; this.selection=null; this.busy=false;

      $("btn-ui-switch").hidden=true;

      this.status(""); this.paint();

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

        this.library=[]; this.selection=null;

        this.status("Installed UIs unreadable: "+library.reason+". Default chat is in use."); this.paint(); return;

      }

      this.library=library.entries;

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

      // only this window. Nothing sensitive is ever posted: the bundle's own

      // source, and results the bundle itself asked for as the viewer.

      if(frame) frame.postMessage(payload,"*");

    },

    refuse(id,error){ this.post({ta_ui:this.PROTOCOL,type:"result",id,ok:false,error:String(error)}); },

    async serve(id,action,params){

      const method=Object.prototype.hasOwnProperty.call(this.ACTIONS,action)?this.ACTIONS[action]:null;

      if(!method){ this.refuse(id,"action not available: "+action); return; }

      if(this.pending>=8){ this.refuse(id,"too many requests in flight"); return; }

      const epoch=this.epoch,home=this.home,args=(params&&typeof params==="object"&&!Array.isArray(params))?params:{};

      this.pending++;

      try{

        const result=await this[method](args);

        if(!this.fence(epoch,home)||!this.frame) return;

        this.post({ta_ui:this.PROTOCOL,type:"result",id,ok:true,result});

      }catch(err){

        if(!this.fence(epoch,home)||!this.frame) return;

        if(err&&err.authRequired){ this.refuse(id,"your session ended"); sessionExpired(); return; }

        this.refuse(id,(err&&err.message)||"unavailable");

      }finally{ this.pending--; }

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

    async readConversation(args){

      const limit=Number.isInteger(args.limit)&&args.limit>0?Math.min(args.limit,this.MAX_READ_TURNS):this.MAX_READ_TURNS;

      const doc=await MCP.getConversation();

      if(!doc||doc.error) throw new Error("your conversation is unavailable");

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

    async remember(selection,saved,unsaved){

      const definitionId=AppLayout.installation&&AppLayout.installation.definition_id;

      if(!definitionId){ this.selection=selection; this.status(unsaved+"; no app-experience installation exists to save it in."); this.paint(); return; }

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

      const definitionId=AppLayout.installation&&AppLayout.installation.definition_id;

      if(!definitionId){ this.status("Install an app experience first (App design), then install a UI into it."); this.paint(); return this.unsupported("no installation"); }

      const next=this.library.filter(b=>b.ui_id!==parsed.bundle.ui_id).concat([parsed.bundle]);

      if(next.length>this.LIBRARY_LIMIT){

        this.status("You already have "+this.LIBRARY_LIMIT+" UIs installed. Remove one first.");

        this.paint(); return this.unsupported("library full");

      }

      const outcome=await AppLayout.writeConfiguration({definitionId,noun:"UI install",

        mutate:config=>{config.ui_library=JSON.parse(JSON.stringify(next));}});

      if(!outcome.ok){ this.status("The UI was not installed ("+(outcome.reason||"unavailable")+")."); this.paint(); return outcome; }

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

