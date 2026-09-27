  // ---- Portable app layout: trusted first-party consumer --------------------
  // Reads ONE declarative `tinyassets.app-layout.v1` component from a public
  // agent definition and MOVES the app's existing nodes into that order. A
  // design can name only four trusted surfaces and one density; it can carry
  // no HTML, CSS, script, URL, identity, resource id or action name, and any
  // extra field makes the whole component unsupported. Unsupported means the
  // default arrangement stays and the reason is shown; nothing is guessed.
  //
  // Reads never write. A write happens only on an explicit Apply or Publish
  // click, is never replayed after an uncertain result, and is confirmed by a
  // read-back before anything is reported saved. Every async result is fenced
  // on the controller epoch and the home captured when the request went out.
  // The installation is a dedicated non-serving AgentBinding
  // (configuration.role === "app_experience"); the serving binding is never
  // read for layout and never written by this controller.
  const AppLayout={
    KIND:"tinyassets.app-layout.v1",VERSION:1,ROLE:"app_experience",
    TAG:"tinyassets-app-layout-v1",LIST_LIMIT:100,
    SURFACES:["conversation","requests","models","status"],
    DENSITIES:["comfortable","compact"],
    NODES:{conversation:["thread","attachments","composer"],requests:["request-rail"],
           models:["model-bar"],status:["status-line"]},
    LABELS:{conversation:"Conversation (thread, attachments, composer)",requests:"Requests rail",
            models:"Model bar",status:"Conversation status"},
    epoch:0,home:"",principal:"",loaded:false,enabled:false,busy:false,uncertain:false,
    mode:"default",source:null,arrangement:null,
    installation:null,candidates:[],saturated:false,
    results:[],inspected:null,draft:null,previousTurn:null,
    anchors:new Map(),hiddenIds:[],root:null,

    // ---- component reader (pure; no DOM, no network) ----
    unsupported(reason){ return {ok:false,reason}; },
    parseComponent(component){
      if(!component||typeof component!=="object"||Array.isArray(component))
        return this.unsupported("layout component is not an object");
      const allowed=["density","kind","surfaces","version"];
      const keys=Object.keys(component).sort();
      const extra=keys.filter(k=>!allowed.includes(k));
      if(extra.length) return this.unsupported("layout component carries fields this app does not render: "+extra.join(", "));
      if(keys.length!==allowed.length) return this.unsupported("layout component is missing "+allowed.filter(k=>!keys.includes(k)).join(", "));
      if(component.kind!==this.KIND) return this.unsupported("not a "+this.KIND+" component");
      if(component.version!==this.VERSION) return this.unsupported("layout version "+String(component.version)+" is not supported; this app renders version 1");
      if(!Array.isArray(component.surfaces)||!component.surfaces.length) return this.unsupported("surfaces must be a non-empty list");
      const seen=new Set();
      for(const s of component.surfaces){
        if(typeof s!=="string"||!this.SURFACES.includes(s)) return this.unsupported("unknown surface "+JSON.stringify(s));
        if(seen.has(s)) return this.unsupported("surface "+s+" is listed twice");
        seen.add(s);
      }
      if(!this.DENSITIES.includes(component.density)) return this.unsupported("unknown density "+JSON.stringify(component.density));
      return {ok:true,layout:{surfaces:[...component.surfaces],density:component.density}};
    },
    readDefinition(agent){
      if(!agent||typeof agent!=="object"||!agent.components||typeof agent.components!=="object"||Array.isArray(agent.components))
        return this.unsupported("definition has no components");
      const layoutKeys=[],others=[];
      for(const [key,component] of Object.entries(agent.components)){
        if(component&&typeof component==="object"&&component.kind===this.KIND) layoutKeys.push(key);
        else others.push(key+" ("+String(component&&component.kind)+")");
      }
      if(layoutKeys.length!==1) return this.unsupported(layoutKeys.length
        ? "definition has "+layoutKeys.length+" layout components; this app renders exactly one"
        : "definition has no "+this.KIND+" component");
      const parsed=this.parseComponent(agent.components[layoutKeys[0]]);
      if(!parsed.ok) return parsed;
      return {ok:true,key:layoutKeys[0],layout:parsed.layout,others};
    },

    // ---- DOM: move trusted nodes, never build from imported data ----
    arrange(layout,source,mode){
      this.restore();
      const body=$("thread").parentNode, host=body.parentNode;
      const root=document.createElement("div");
      root.id="layout-root"; root.className="layout-root layout-root--"+layout.density;
      host.insertBefore(root,body);
      for(const name of layout.surfaces){
        const slot=document.createElement("section");
        slot.className="layout-slot layout-slot--"+name; slot.setAttribute("data-surface",name);
        for(const id of this.NODES[name]){
          const node=$(id), anchor=document.createComment("ta-layout-anchor "+id);
          node.parentNode.insertBefore(anchor,node); slot.appendChild(node); this.anchors.set(id,anchor);
        }
        root.appendChild(slot);
      }
      for(const name of this.SURFACES){
        if(layout.surfaces.includes(name)) continue;
        for(const id of this.NODES[name]){ $(id).classList.add("layout-omitted"); this.hiddenIds.push(id); }
      }
      $("view-chat").classList.add("layout-active","layout-density--"+layout.density);
      this.root=root; this.mode=mode; this.source=source;
      this.arrangement={surfaces:[...layout.surfaces],density:layout.density};
      this.paintHeader();
    },
    restore(){
      for(const [id,anchor] of this.anchors){
        const node=$(id);
        if(anchor.parentNode){ anchor.parentNode.insertBefore(node,anchor); anchor.parentNode.removeChild(anchor); }
      }
      this.anchors=new Map();
      for(const id of this.hiddenIds) $(id).classList.remove("layout-omitted");
      this.hiddenIds=[];
      if(this.root&&this.root.parentNode) this.root.parentNode.removeChild(this.root);
      this.root=null;
      $("view-chat").classList.remove("layout-active");
      for(const d of this.DENSITIES) $("view-chat").classList.remove("layout-density--"+d);
      this.mode="default"; this.source=null; this.arrangement=null;
      this.paintHeader();
    },
    restoreDefault(){
      this.restore();
      this.status(this.installation
        ? "Default arrangement restored for this visit. Your installation is kept and applies again next sign-in."
        : "Default arrangement restored.");
      this.paint();
    },

    // ---- lifecycle and fencing ----
    fence(epoch,home){ return this.enabled&&epoch===this.epoch&&home===this.home; },
    reset(){
      this.epoch++; this.restore();
      this.enabled=false; this.home=""; this.principal=""; this.loaded=false; this.busy=false; this.uncertain=false;
      this.installation=null; this.candidates=[]; this.saturated=false;
      this.results=[]; this.inspected=null; this.draft=null; this.previousTurn=null;
      $("btn-layouts").hidden=true;
      if($("layout-dialog").open) $("layout-dialog").close();
      this.status(""); this.paint();
    },
    enable(home,principal){
      if(this.enabled&&this.home===home&&this.principal===principal) return;
      this.reset();
      const id=String(home||"").trim();
      if(!id||!principal){ this.status("Layouts require a verified home and signed-in identity."); return; }
      this.epoch++; this.home=id; this.principal=principal; this.enabled=true;
      $("btn-layouts").hidden=false;
      this.loadInstallation();
    },
    homeChanged(home){
      const id=String(home||"").trim();
      if(!this.enabled||!id||id===this.home) return;
      this.reset();
      this.status("Your home universe changed; layouts were reloaded for the current home.");
    },

    // ---- reads (idempotent, never create anything) ----
    eligible(b){
      return !!(b&&b.created_by===this.principal&&b.universe_id===this.home&&
        b.status==="configured"&&b.agent_binding_id&&b.agent_definition_id&&
        Number.isInteger(b.revision)&&b.configuration&&
        b.configuration.role===this.ROLE&&
        !Object.prototype.hasOwnProperty.call(b.configuration,"provider_ref"));
    },
    async currentBindings(){
      const epoch=this.epoch,home=this.home,principal=this.principal;
      const me=await fetchMe();
      if(!this.fence(epoch,home)) throw new Error("Session changed");
      if(!me||me.principal_id!==principal||me.universe_id!==home||me.setup!=="connected"){
        this.reset(); throw new Error("Signed-in identity or home changed; sign in again.");
      }
      const doc=await MCP.callTool("read_graph",{target:"agent_bindings",graph_id:this.home,limit:this.LIST_LIMIT},{idempotent:true});
      if(!this.fence(epoch,home)) throw new Error("Session changed");
      if(!doc||doc.error||!Array.isArray(doc.bindings)) throw new Error("Installed layouts unavailable");
      this.saturated=doc.bindings.length>=this.LIST_LIMIT;
      this.candidates=doc.bindings.filter(b=>this.eligible(b));
      this.loaded=true;
      if(this.saturated||this.candidates.length>1) throw new Error("Installation list is incomplete or ambiguous. Apply is disabled.");
      return this.candidates;
    },
    async getDefinition(id){
      const doc=await MCP.callTool("read_graph",{target:"agent",agent_definition_id:id},{idempotent:true});
      if(!doc||doc.error||!doc.agent||doc.agent.agent_definition_id!==id) throw new Error("Definition unavailable or mismatched");
      return doc.agent;
    },
    async loadInstallation(){
      if(!this.enabled) return;
      const epoch=this.epoch,home=this.home;
      this.loaded=false;
      this.busy=true; this.status("Checking your installed layout…"); this.paint();
      try{
        const mine=await this.currentBindings();
        if(!this.fence(epoch,home)) return;
        this.uncertain=false; this.installation=null;
        if(mine.length===0){ this.restore(); this.status("No layout installed. The default arrangement is in use."); return; }
        if(mine.length>1){ this.restore(); this.status(mine.length+" layout installations exist in this universe. None was applied automatically; choose one in Layouts."); return; }
        await this.consume(mine[0],epoch,home);
      }catch(err){
        if(!this.fence(epoch,home)) return;
        if(err&&err.authRequired){ sessionExpired(); return; }
        this.restore();
        this.status("Could not read your installed layout ("+(err&&err.message||"unknown error")+"). The default arrangement is in use.");
      }finally{ if(this.fence(epoch,home)){ this.busy=false; this.paint(); } }
    },
    async consume(binding,epoch,home){
      if(!this.eligible(binding)||!this.fence(epoch,home)) throw new Error("Installation ownership or role is not valid");
      this.installation={binding_id:String(binding.agent_binding_id),revision:binding.revision,
        definition_id:String(binding.agent_definition_id),created_by:String(binding.created_by||""),
        configuration:JSON.parse(JSON.stringify(binding.configuration))};
      const agent=await this.getDefinition(binding.agent_definition_id);
      if(!this.fence(epoch,home)) return;
      const read=this.readDefinition(agent);
      if(!read.ok){ this.restore(); this.status("Installed layout unsupported: "+read.reason+". The default arrangement is in use."); return; }
      this.arrange(read.layout,{definition_id:String(agent.agent_definition_id),name:String(agent.name||"unnamed")},"applied");
      this.status("Layout applied: "+String(agent.name||"unnamed")+(read.others.length?". Other components in this design are preserved but not rendered by this app: "+read.others.join(", "):""));
    },
    async select(bindingId){
      if(!this.enabled||this.busy||this.saturated||this.candidates.length!==1) return;
      const binding=this.candidates.find(b=>String(b.agent_binding_id)===String(bindingId));
      if(!binding){ this.status("That installation is no longer listed. Refresh."); return; }
      const epoch=this.epoch,home=this.home;
      this.busy=true; this.paint();
      try{ await this.consume(binding,epoch,home); }
      catch(err){ if(!this.fence(epoch,home)) return; if(err&&err.authRequired){ sessionExpired(); return; } this.status("Could not load that installation ("+(err&&err.message||"unknown error")+")."); }
      finally{ if(this.fence(epoch,home)){ this.busy=false; this.paint(); } }
    },
    async search(){
      if(!this.enabled) return;
      const epoch=this.epoch,home=this.home,query=String($("layout-search").value||"").trim();
      this.status("Searching public layouts…");
      try{
        const doc=await MCP.callTool("read_graph",{target:"agents",query,limit:30},{idempotent:true});
        if(!this.fence(epoch,home)) return;
        if(!doc||doc.error||!Array.isArray(doc.agents)) throw new Error(doc&&doc.error?String(doc.error):"public layouts unavailable");
        this.results=doc.agents;
        this.status(doc.agents.length?doc.agents.length+" public design(s) found. Inspect one to preview it.":"No public layouts match.");
      }catch(err){
        if(!this.fence(epoch,home)) return;
        if(err&&err.authRequired){ sessionExpired(); return; }
        this.results=[]; this.status("Search failed ("+(err&&err.message||"unknown error")+").");
      }
      this.paint();
    },
    async inspect(definitionId){
      if(!this.enabled) return;
      const epoch=this.epoch,home=this.home;
      this.status("Reading design…");
      try{
        const agent=await this.getDefinition(definitionId);
        if(!this.fence(epoch,home)) return;
        const read=this.readDefinition(agent);
        this.inspected={agent,read};
        this.draft=read.ok?this.draftFrom(read.layout):this.draftFrom({surfaces:[...this.SURFACES],density:"comfortable"});
        this.status(read.ok?"Design read. Preview changes nothing saved; Apply installs its layout. Conversation behavior requires its separate selection.":"Layout unavailable: "+read.reason+". Conversation components are shown separately below.");
      }catch(err){
        if(!this.fence(epoch,home)) return;
        if(err&&err.authRequired){ sessionExpired(); return; }
        this.status("Could not read that design ("+(err&&err.message||"unknown error")+").");
      }
      this.paint();
    },

    // Consumer recovery is in the trusted dialog, outside the movable layout.
    // These writes change selection DATA only; ordinary server admission still
    // checks executable provenance, closure, model access and every effect.
    turnComponent(c){
      const fields=["kind","version","branch_version_id","content_hash","input_map","reply_key"].sort();
      const ident=v=>typeof v==="string"&&v.length>0&&v.length<=200&&v.trim()===v&&!/[\x00-\x1f\x7f]/.test(v);
      if(!c||typeof c!=="object"||Array.isArray(c)||JSON.stringify(Object.keys(c).sort())!==JSON.stringify(fields)||
         c.kind!=="tinyassets.turn-graph.v1"||c.version!==1||!ident(c.branch_version_id)||
         !/^[a-f0-9]{64}$/.test(c.content_hash)||!ident(c.reply_key))return this.unsupported("Unsupported conversation adapter or source pin");
      const m=c.input_map;
      if(!m||typeof m!=="object"||Array.isArray(m)||!Object.hasOwn(m,"message")||
         Object.keys(m).some(k=>!["message","history"].includes(k))||
         Object.values(m).some(v=>!ident(v))||new Set(Object.values(m)).size!==Object.values(m).length)
        return this.unsupported("Unsupported conversation input mapping");
      return {ok:true};
    },
    async selectTurn(key){
      const a=this.inspected&&this.inspected.agent,c=a&&a.components&&a.components[key];
      if(!a||!this.turnComponent(c).ok||!/^[a-f0-9]{64}$/.test(a.content_fingerprint))return;
      await this.saveTurn(a.agent_definition_id,{version:1,state:"active",component_key:key,
        definition_fingerprint:a.content_fingerprint});
    },
    async disableTurn(){
      if(this.installation)await this.saveTurn(this.installation.definition_id,{version:1,state:"disabled"});
    },
    async rollbackTurn(){
      const previous=this.previousTurn;
      if(previous)await this.saveTurn(previous.definition_id,previous.selection);
    },
    async saveTurn(definitionId,selection){
      if(!this.enabled||this.busy||this.uncertain||!this.loaded||this.saturated||this.candidates.length>1)return;
      const epoch=this.epoch,home=this.home,observed=this.installation;
      this.busy=true;this.paint();
      try{
        const rows=await this.currentBindings();
        if(!this.fence(epoch,home))return;
        const b=rows[0];
        if((!observed&&b)||(observed&&(!b||b.agent_binding_id!==observed.binding_id||b.revision!==observed.revision)))
          throw Error("Installation changed; refresh before selecting again");
        if(b&&(!this.eligible(b)||b.updated_by!==this.principal))throw Error("Installation is not owner-controlled");
        if(selection.state==="active"){
          const agent=await this.getDefinition(definitionId);
          if(!this.fence(epoch,home))return;
          if(agent.content_fingerprint!==selection.definition_fingerprint||
             !this.turnComponent(agent.components&&agent.components[selection.component_key]).ok)
            throw Error("Selected definition is no longer compatible");
        }
        const config=b?JSON.parse(JSON.stringify(b.configuration)):{schema_version:1,name:"App experience",role:this.ROLE};
        const previous=b?{definition_id:b.agent_definition_id,
          selection:JSON.parse(JSON.stringify(config.turn_consumer||{version:1,state:"disabled"}))}:null;
        config.turn_consumer=JSON.parse(JSON.stringify(selection));
        const result=await MCP.callTool("write_graph",{target:"agent_binding",operation:b?"update":"bind",
          graph_id:home,agent_definition_id:definitionId,...(b?{agent_binding_id:b.agent_binding_id,expected_revision:b.revision}:{}),
          payload_json:JSON.stringify(config)});
        if(!this.fence(epoch,home))return;
        const written=result&&result.binding;
        if(!result||result.error||result.status!=="configured"||!written||!this.eligible(written)||
           written.updated_by!==this.principal||written.agent_definition_id!==definitionId||
           (b&&written.agent_binding_id!==b.agent_binding_id))throw Error("Selection save was not confirmed");
        const doc=await MCP.callTool("read_graph",{target:"agent_binding",graph_id:home,
          agent_binding_id:written.agent_binding_id},{idempotent:true});
        if(!this.fence(epoch,home))return;
        const check=doc&&doc.binding;
        if(!this.eligible(check)||check.updated_by!==this.principal||check.agent_binding_id!==written.agent_binding_id||
           check.agent_definition_id!==definitionId||check.revision!==written.revision||
           JSON.stringify(check.configuration)!==JSON.stringify(config))throw Error("Selection read-back did not match");
        this.previousTurn=previous;
        this.installation={binding_id:check.agent_binding_id,revision:check.revision,
          definition_id:check.agent_definition_id,configuration:JSON.parse(JSON.stringify(check.configuration))};
        this.candidates=[check];
        this.status(selection.state==="disabled"?"Default conversation restored for future messages. Existing work is not cancelled or replayed.":
          "Conversation design selected for future messages. Execution checks still apply. Your model choice and private data are unchanged.");
      }catch(err){
        if(!this.fence(epoch,home))return;
        if(err&&err.authRequired){sessionExpired();return;}
        this.uncertain=true;
        this.status((err&&err.message||"Selection unavailable")+". Nothing was retried. Refresh the installation before another change.");
      }finally{if(this.fence(epoch,home)){this.busy=false;this.paint();}}
    },

    // ---- editor draft (order + inclusion + density) ----
    draftFrom(layout){
      const order=[...layout.surfaces,...this.SURFACES.filter(s=>!layout.surfaces.includes(s))];
      const included={}; for(const s of this.SURFACES) included[s]=layout.surfaces.includes(s);
      return {order,included,density:layout.density};
    },
    draftLayout(){
      if(!this.draft) return this.unsupported("Inspect a design or start from the default first.");
      const surfaces=this.draft.order.filter(s=>this.draft.included[s]);
      if(!surfaces.length) return this.unsupported("Select at least one surface.");
      return {ok:true,layout:{surfaces,density:this.draft.density}};
    },
    startFromDefault(){
      this.inspected=null;
      this.draft=this.draftFrom({surfaces:[...this.SURFACES],density:"comfortable"});
      this.status("Editing a new design from the default arrangement. Publish it to make it applicable."); this.paint();
    },
    toggle(name){ if(this.draft&&name in this.draft.included){ this.draft.included[name]=!this.draft.included[name]; this.paint(); } },
    move(name,delta){
      if(!this.draft) return;
      const i=this.draft.order.indexOf(name), j=i+delta;
      if(i<0||j<0||j>=this.draft.order.length) return;
      const order=this.draft.order; [order[i],order[j]]=[order[j],order[i]]; this.paint();
    },
    setDensity(value){ if(this.draft&&this.DENSITIES.includes(value)){ this.draft.density=value; this.paint(); } },
    preview(){
      if(!this.enabled) return;
      const layout=this.draftLayout();
      if(!layout.ok){ this.status(layout.reason); this.paint(); return; }
      const name=this.inspected?String(this.inspected.agent.name||"unnamed"):"unpublished draft";
      this.arrange(layout.layout,{definition_id:this.inspected?String(this.inspected.agent.agent_definition_id):"",name},"preview");
      this.status("Previewing "+name+". Nothing is saved; Restore default returns the usual arrangement.");
      this.paint();
    },
    draftMatchesInspected(){
      const layout=this.draftLayout();
      return !!(layout.ok&&this.inspected&&this.inspected.read.ok&&
        JSON.stringify(layout.layout)===JSON.stringify(this.inspected.read.layout));
    },

    // ---- writes: explicit, CAS, read back, never replayed ----
    async apply(){
      if(!this.enabled||this.busy) return;
      if(!this.loaded||this.saturated||this.candidates.length>1){ this.status("Refresh a complete, unambiguous installation list before applying."); return; }
      if(!this.inspected||!this.inspected.read.ok){ this.status("Inspect a supported public design before applying."); this.paint(); return; }
      if(this.uncertain){ this.status("The last save was not confirmed. Refresh your installed layout before applying again."); this.paint(); return; }
      if(!this.draftMatchesInspected()){ this.status("Your arrangement differs from the public design. Publish it first, then apply the published design."); this.paint(); return; }
      const epoch=this.epoch,home=this.home,agent=this.inspected.agent,defId=String(agent.agent_definition_id);
      const observed=this.installation?{id:this.installation.binding_id,revision:this.installation.revision}:null;
      this.busy=true; this.status("Saving your layout installation…"); this.paint();
      try{
        const rows=await this.currentBindings();
        if(!this.fence(epoch,home)) return;
        const existing=rows[0];
        if((!observed&&existing)||(observed&&(!existing||existing.agent_binding_id!==observed.id||existing.revision!==observed.revision))){
          this.uncertain=true; this.status("Your installation changed elsewhere. Refresh before applying; the current layout is kept."); return;
        }
        this.installation=existing?{binding_id:existing.agent_binding_id,revision:existing.revision,configuration:JSON.parse(JSON.stringify(existing.configuration))}:null;
        const result=this.installation
          ? await MCP.callTool("write_graph",{target:"agent_binding",operation:"update",graph_id:home,
              agent_binding_id:this.installation.binding_id,agent_definition_id:defId,
              expected_revision:this.installation.revision,payload_json:JSON.stringify(this.installation.configuration)})
          : await MCP.callTool("write_graph",{target:"agent_binding",operation:"bind",graph_id:home,
              agent_definition_id:defId,payload_json:JSON.stringify({schema_version:1,name:"App layout",role:this.ROLE})});
        if(!this.fence(epoch,home)) return;
        if(!result||result.error||result.status!=="configured"||!result.binding){
          const code=result&&result.error?String(result.error):"unexpected reply";
          this.uncertain=true;
          this.status(code==="agent_conflict"
            ?"Your installation changed elsewhere. The current layout is kept; refresh before trying again."
            :"Could not save the layout ("+code+(result&&result.detail?": "+String(result.detail):"")+"). Your current layout is unchanged; refresh before trying again.");
          return;
        }
        const written=result.binding;
        if(!this.eligible(written)||written.agent_definition_id!==defId||
          (this.installation&&written.agent_binding_id!==this.installation.binding_id)) throw new Error("Save returned a mismatched installation");
        const check=await MCP.callTool("read_graph",{target:"agent_binding",graph_id:home,agent_binding_id:written.agent_binding_id},{idempotent:true});
        if(!this.fence(epoch,home)) return;
        const b=check&&check.binding;
        if(!this.eligible(b)||b.agent_binding_id!==written.agent_binding_id||String(b.agent_definition_id)!==defId||b.revision!==written.revision){
          this.uncertain=true;
          this.status("The save could not be confirmed by read-back. Refresh your installed layout before applying again.");
          return;
        }
        await this.consume(b,epoch,home);
        if(!this.fence(epoch,home)) return;
        this.status("Saved and applied: "+String(agent.name||"unnamed")+".");
      }catch(err){
        if(!this.fence(epoch,home)) return;
        if(err&&err.authRequired){ sessionExpired(); return; }
        this.uncertain=true;
        this.status("The save may or may not have happened ("+(err&&err.message||"unknown error")+"). It was not retried; refresh your installed layout before applying again.");
      }finally{ if(this.fence(epoch,home)){ this.busy=false; this.paint(); } }
    },
    publishPayload(name,description){
      const layout=this.draftLayout();
      if(!layout.ok) return layout;
      if(!name) return this.unsupported("Give the published design a name.");
      const src=this.inspected&&this.inspected.read.ok?this.inspected:null;
      const component={kind:this.KIND,version:this.VERSION,surfaces:layout.layout.surfaces,density:layout.layout.density};
      const tags=[this.TAG];
      let components,lineage=null;
      if(src){
        if(!src.agent.portable_definition) return this.unsupported("This design has no portable source envelope; refresh before remixing.");
        components=JSON.parse(JSON.stringify(src.agent.portable_definition.components)); components[src.read.key]=component;
        lineage={};
        for(const key of Object.keys(components))
          lineage[key]=[{definition_id:String(src.agent.agent_definition_id),component_key:key,credit_share:1}];
        for(const t of (src.agent.tags||[])) if(typeof t==="string"&&!tags.includes(t)) tags.push(t);
      }else components={layout:component};
      const payload=src?JSON.parse(JSON.stringify(src.agent.portable_definition||{})):{schema_version:1};
      delete payload.content_fingerprint;
      Object.assign(payload,{name,description,tags,components});
      if(lineage) payload.lineage=lineage;
      return {ok:true,payload,remix:!!src};
    },
    async publish(){
      if(!this.enabled||this.busy) return;
      const built=this.publishPayload(String($("layout-publish-name").value||"").trim(),String($("layout-publish-description").value||""));
      if(!built.ok){ this.status(built.reason); this.paint(); return; }
      const epoch=this.epoch,home=this.home;
      this.busy=true; this.status("Publishing design metadata publicly…"); this.paint();
      try{
        const result=await MCP.callTool("write_graph",{target:"agent",operation:built.remix?"remix":"publish",payload_json:JSON.stringify(built.payload)});
        if(!this.fence(epoch,home)) return;
        if(!result||result.error||result.status!=="published"||!result.agent){
          this.status("Publish failed ("+(result&&result.error?String(result.error):"unexpected reply")+(result&&result.detail?": "+String(result.detail):"")+"). Nothing was published."); return;
        }
        const agent=await this.getDefinition(result.agent.agent_definition_id);
        if(!this.fence(epoch,home)) return;
        this.inspected={agent,read:this.readDefinition(agent)};
        this.results=[agent,...this.results.filter(a=>a&&a.agent_definition_id!==agent.agent_definition_id)];
        this.status("Published "+String(agent.name||"unnamed")+" publicly. Apply it to use it here.");
      }catch(err){
        if(!this.fence(epoch,home)) return;
        if(err&&err.authRequired){ sessionExpired(); return; }
        this.status("Publish may or may not have happened ("+(err&&err.message||"unknown error")+"). It was not retried; search to see whether it exists.");
      }finally{ if(this.fence(epoch,home)){ this.busy=false; this.paint(); } }
    },

    // ---- fixed dialog rendering: textContent only, never markup ----
    status(text){ $("layout-status").textContent=text||""; },
    paintHeader(){
      const restore=$("btn-layout-restore"), label=$("layout-mode");
      restore.hidden=this.mode==="default";
      label.hidden=this.mode==="default";
      label.textContent=this.mode==="default"?"":
        (this.mode==="preview"?"Previewing layout (not saved): ":"Layout: ")+(this.source&&this.source.name||"unnamed");
    },
    button(text,onClick,disabled){
      const b=document.createElement("button"); b.type="button"; b.className="btn btn--link";
      b.textContent=text; b.disabled=!!disabled; b.addEventListener("click",onClick); return b;
    },
    line(parent,text,cls){ const p=document.createElement("p"); if(cls) p.className=cls; p.textContent=text; parent.appendChild(p); return p; },
    paint(){
      const results=$("layout-results"); results.replaceChildren();
      for(const agent of this.results){
        if(!agent||typeof agent!=="object") continue;
        const row=document.createElement("li");
        row.appendChild(this.button(String(agent.name||"unnamed")+" — by "+String(agent.author_id||"unknown"),()=>this.inspect(String(agent.agent_definition_id)),this.busy));
        results.appendChild(row);
      }
      const cands=$("layout-candidates"); cands.replaceChildren();
      if(this.saturated) this.line(cands,"The binding list may be incomplete (100 rows). Installations below are only those listed.","muted");
      for(const b of this.candidates){
        const row=document.createElement("li");
        const current=this.installation&&this.installation.binding_id===String(b.agent_binding_id);
        row.appendChild(this.button((current?"Current: ":"Use installation ")+String(b.agent_binding_id)+" (created by "+String(b.created_by||"unknown")+", revision "+String(b.revision)+")",()=>this.select(String(b.agent_binding_id)),this.busy||current));
        cands.appendChild(row);
      }
      const panel=$("layout-inspect"); panel.replaceChildren();
      if(this.inspected){
        const a=this.inspected.agent, r=this.inspected.read;
        this.line(panel,String(a.name||"unnamed")+" · "+String(a.agent_definition_id),"layout-inspect-title");
        this.line(panel,"By "+String(a.author_id||"unknown")+(Array.isArray(a.tags)&&a.tags.length?" · tags: "+a.tags.map(String).join(", "):""),"muted");
        if(a.description) this.line(panel,String(a.description));
        this.line(panel,r.ok?"Layout: "+r.layout.surfaces.join(" → ")+" · "+r.layout.density+(r.others.length?" · preserved, not rendered: "+r.others.join(", "):"")
                            :"Unsupported: "+r.reason,r.ok?"":"layout-unsupported");
      }else this.line(panel,"No design inspected. Search public designs or start from the default.","muted");
      const turnPanel=$("consumer-controls");turnPanel.replaceChildren();
      const selected=this.installation&&this.installation.configuration.turn_consumer;
      this.line(turnPanel,selected&&selected.state==="active"
        ?"Conversation design: "+this.installation.definition_id+" / "+String(selected.component_key)+" (revision "+this.installation.revision+")"
        :selected&&selected.state!=="disabled"?"Conversation selection is incompatible. Restore default or inspect and select a supported design.":"Conversation design: default");
      this.line(turnPanel,"Your chosen model and existing access still govern every call. Selection changes future messages, not work already started.","muted");
      turnPanel.appendChild(this.button("Restore default conversation",()=>this.disableTurn(),this.busy||this.uncertain||!selected||selected.state==="disabled"));
      if(this.previousTurn)turnPanel.appendChild(this.button("Restore previous conversation selection",()=>this.rollbackTurn(),this.busy||this.uncertain));
      if(this.inspected){
        for(const [key,c] of Object.entries(this.inspected.agent.components||{})){
          if(!c||c.kind!=="tinyassets.turn-graph.v1")continue;
          const compatible=this.turnComponent(c);
          this.line(turnPanel,key+": "+(compatible.ok?"Uses workflow version "+c.branch_version_id+". Receives your message"+(c.input_map.history?" and recent conversation history":"")+". Source, model and effect access are checked when used. Foreign workflows require your own explicit remix first.":compatible.reason));
          turnPanel.appendChild(this.button("Use "+key+" for conversations",()=>this.selectTurn(key),this.busy||this.uncertain||!compatible.ok||!this.loaded||this.saturated||this.candidates.length>1));
        }
      }
      const editor=$("layout-editor"); editor.replaceChildren();
      if(this.draft){
        this.draft.order.forEach((name,i)=>{
          const row=document.createElement("li");
          const box=document.createElement("input"); box.type="checkbox"; box.checked=!!this.draft.included[name];
          box.setAttribute("aria-label","Include "+this.LABELS[name]); box.addEventListener("change",()=>this.toggle(name));
          row.appendChild(box);
          const label=document.createElement("span"); label.textContent=" "+this.LABELS[name]+" "; row.appendChild(label);
          row.appendChild(this.button("Up",()=>this.move(name,-1),i===0));
          row.appendChild(this.button("Down",()=>this.move(name,1),i===this.draft.order.length-1));
          editor.appendChild(row);
        });
        $("layout-density").value=this.draft.density;
      }
      $("layout-density").disabled=!this.draft;
      $("btn-layout-preview").disabled=this.busy||!this.draft;
      $("btn-layout-apply").disabled=this.busy||this.uncertain||!this.loaded||this.saturated||this.candidates.length>1||!this.draftMatchesInspected();
      $("btn-layout-publish").disabled=this.busy||!this.draft;
      $("btn-layout-refresh").disabled=this.busy;
      $("btn-layout-search").disabled=this.busy;
    },
    open(){
      if(!this.enabled) return;
      if(!this.draft) this.draft=this.draftFrom(this.arrangement||{surfaces:[...this.SURFACES],density:"comfortable"});
      this.paint();
      const dialog=$("layout-dialog");
      if(!dialog.open) dialog.showModal();
    },
    init(){
      $("btn-layouts").addEventListener("click",()=>this.open());
      $("btn-layout-restore").addEventListener("click",()=>this.restoreDefault());
      $("btn-layout-search").addEventListener("click",()=>this.search());
      $("layout-search").addEventListener("keydown",e=>{ if(e.key==="Enter"){ e.preventDefault(); this.search(); } });
      $("btn-layout-default").addEventListener("click",()=>this.startFromDefault());
      $("layout-density").addEventListener("change",e=>this.setDensity(e.target.value));
      $("btn-layout-preview").addEventListener("click",()=>this.preview());
      $("btn-layout-apply").addEventListener("click",()=>this.apply());
      $("btn-layout-publish").addEventListener("click",()=>this.publish());
      $("btn-layout-refresh").addEventListener("click",()=>this.loadInstallation());
      $("btn-layout-close").addEventListener("click",()=>$("layout-dialog").close());
      this.paintHeader();
    }
  };
