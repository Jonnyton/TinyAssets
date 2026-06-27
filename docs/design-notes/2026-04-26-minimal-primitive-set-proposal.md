---
title: Minimal primitive-set proposal — what's the fewest tools that let users build everything imaginable
date: 2026-04-26
author: navigator
status: active
companion:
  - project_minimal_primitives_principle (foundational scoping rule)
  - project_user_capability_axis (browser-only / local-app × Claude / OpenAI / OSS-clients)
  - project_community_build_over_platform_build
  - project_user_builds_we_enable
  - docs/audits/2026-04-26-user-capability-axis-implications.md (tactical sibling sweep)
  - docs/design-notes/2026-04-18-full-platform-architecture.md
load-bearing-question: What is the fewest set of MCP-tool primitives that lets a user — on each capability tier × each chat client — build everything they can imagine on top of? Where does the current 7-tool surface match that ideal, and where does it carry redundancy or gaps?
audience: lead, host (final scope decision)
---

# Minimal primitive-set proposal

## §0 — Pre-flight: scope of "primitive" + treatment of MCP roadmap

**Scope:** This note treats the **MCP tool surface** as "primitive" — the verbs the chatbot reaches for to build user outcomes. Engine-level primitives (typed reducers, checkpointing, evaluator hooks) are NOT in scope here; they're the substrate. Tool surface = the contract with the user.

**Roadmap posture:** roadmap-aware. The 2026 MCP roadmap (per `blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/`) signals that **Streamable HTTP transport scaling + enterprise readiness** are the Q1 2026 priorities, with the next spec release ~June 2026. **Sampling, elicitation, and prompts** are server-side primitives that exist in spec but are not yet exposed by Claude.ai web custom connectors (per `support.claude.com/en/articles/11175166`: Claude.ai web supports **only tool calls** as of 2026; resources/prompts/sampling/elicitation are not exposed). ChatGPT custom connectors via Developer Mode have a similar floor for individual users (per OpenAI Help Center). This is a real constraint, not a hypothetical.

This note treats the constraint as foundational for §2 (browser-only primitives must work via tool calls only) but assumes §3 (local-app + future) gets a richer surface as elicitation/sampling/resources land.

---

## §1 — Frame: the question being answered

Two principles in tension shape every primitive decision:

1. **Minimal-primitives** (`project_minimal_primitives_principle`): "What is the fewest number of tools that lets the user do everything they can imagine?" Tool count is a SHRINKING budget toward irreducible building blocks. Composability > convenience.

2. **Capability-axis** (`project_user_capability_axis`): each user is a *(capability tier × chat-client)* pair. Browser-only Claude.ai-web user gets the same primitives as local-app Claude Code user — capability tier just changes which leverage paths are available, not which primitives exist. Provider parity is hard.

**Putting them together:** the irreducible primitive set must work — same shape, same composition story — for the lowest-capability user (phone-browser-only on whatever provider). Anything that requires local file system / local execution / local daemon hosting earns "local-app-only" tagging and demands a tier-portable substitute. Provider-specific behaviors are anti-patterns.

**The user-goal frame.** Derived from chat-trace evidence + persona memories (Maya/Priya/Devin/Mark/Ilse). Real user outcomes break down into 7 verbs the chatbot must always be able to express:

| User-goal verb | What the user wants | Persona evidence |
|---|---|---|
| **DESIGN** | Build a workflow that doesn't exist yet | Mark: bug-to-patch-packet branch. Maya: invoice extraction pipeline. |
| **DISCOVER** | Find work or knowledge that already exists | Priya: "find my prior MaxEnt sweep." Mark: "what's the canonical investigation branch?" Devin: "what nodes does the catalog have?" |
| **RUN** | Execute a workflow against my inputs and produce real outputs | Maya: process this month's invoices. Priya: run the BIOCLIM+RF sweep. Devin: draft this scene. |
| **OBSERVE** | See what's happening / what happened | Priya: "how's the sweep going?" Mark: "what did the bug-investigation say?" Devin: "show me the activity log." |
| **EXTEND** | Take prior work and continue / iterate / adapt | Priya: "add BIOCLIM to my prior MaxEnt sweep." Devin: "redraft scene 7 with the editorial notes." |
| **DELIVER** | Get the actual deliverable out — file, URL, document, message to the right place | Maya: Sage-importable CSV in her hand. Priya: methods paragraph + repro script for the paper. |
| **COLLABORATE** | Share, fork, attribute, build on someone else's work | Mark: file a bug + receive a patch packet. Ilse: fork a branch design + PR back. Priya: tell a colleague how to reuse her pipeline. |

These 7 verbs are the load-bearing test. **A primitive earns its keep if it serves one or more verbs irreducibly.** A tool that doesn't show up under any verb fails the test. A verb with no primitive coverage is a gap. Multiple primitives serving the same verb = consolidation candidate.

---

## §2 — Browser-only tier irreducible primitive set

**Constraint:** browser-only users have NO local file system, NO local code execution, NO daemon hosting, NO ability to receive a callback, NO ability for the platform to run something while they're not in the chat. The platform mediates everything cloud-side.

**Per Claude.ai web's current MCP surface:** TOOLS ONLY. No resources, no prompts, no sampling, no elicitation. (Source: Anthropic Help Center 2026.) ChatGPT custom-connector individual users similarly read/fetch-only. So every primitive must compile to a TOOL CALL that takes a JSON payload and returns a JSON response. That is the primitive ceiling for ~95% of users.

### §2.1 — The proposed irreducible 5

**Five primitives, no more, no less:**

| # | Primitive | Verb coverage | Composition examples | Why irreducible |
|---|---|---|---|---|
| **1** | **`workspace`** | DISCOVER + DESIGN-bootstrap | "what universes exist + their shape" / "create a new universe" / "inspect this one" | The user has to know where they are before any other verb makes sense. Can't be composed from anything smaller. |
| **2** | **`workflow`** | DESIGN + EXTEND | "build / patch / fork / version a branch (workflow definition)" / "register a custom node" / "wire dispatch / edges / state schema" | The act of declaring a workflow is irreducible — there's no smaller verb that lets you go from intent to executable graph. EXTEND ("continue from prior run") is one verb away from DESIGN; same primitive. |
| **3** | **`run`** | RUN + OBSERVE + DELIVER | "submit a request" / "claim status of run X" / "stream events" / "fetch outputs" / "subscribe to completion" | The act of dispatching work + getting events back is the whole point of the platform. Sub-verbs (submit, observe, fetch) are the SAME primitive in 3 modes; one tool with `action=submit/observe/fetch`. |
| **4** | **`evaluate`** | EVALUATE (subset of RUN, but elevated) | "score against rubric" / "claim a gate" / "diff two runs" | EVALUATE is a load-bearing PLATFORM-SCALE verb (parallel evaluators, evaluator-driven loops, gate claiming). It earns its own primitive because it's how the platform CLAIMS A SCALABILITY ADVANTAGE BROWSER-ONLY USERS CAN'T DO ALONE. |
| **5** | **`commons`** | COLLABORATE + DISCOVER (cross-user) | "find shared workflows" / "fork from someone else" / "publish my work" / "attribute" / "file a bug or feature" / "wiki-write" | The cross-user surface — the Wikipedia-scale convergent commons. Without this primitive, the platform is single-user. With it, every user composes on someone else's foundation. |

**That's it. Five.** Every user-goal verb composes from these 5.

### §2.2 — How the 7 verbs compose into the 5 primitives

| User verb | Composition |
|---|---|
| **DESIGN** | `workspace` (find or create universe) → `workflow` (build a branch) → optionally `commons` (fork or look up similar work first) |
| **DISCOVER** | `workspace` (orient) → `commons` (search public work) → `workflow` (read existing branch defs) |
| **RUN** | `run` (submit + observe + fetch) — one primitive, three actions. State-of-progress is part of the same primitive. |
| **OBSERVE** | `run` (action=status, action=events, action=fetch) |
| **EXTEND** | `run` (find prior run) → `workflow` (create variant or fork-from with prior state) → `run` (submit again) |
| **DELIVER** | `run` (fetch outputs) — output payload includes file URLs, formatted artifacts, downloadable content. `commons` for sharing. |
| **COLLABORATE** | `commons` for everything cross-user — fork, attribute, comment, file-bug, wiki-edit. |

### §2.3 — What this kills + what survives

**Kills (current surface elements that DON'T survive the 5-primitive test):**

- **`get_status`** — collapses into `workspace` (universe inspect already returns daemon state, queue counts, etc.) OR into `run` (per-run status). Two primitives doing the same job; consolidate.
- **`gates`** — collapses into `evaluate` (gates ARE evaluator claims; same primitive, different action verb).
- **`branch_design_guide`** — this is a PROMPT, not a tool. Per MCP spec, prompts are user-controlled templates exposed in chat-client UI, not chatbot-callable verbs. Should migrate to MCP `prompts` capability when Claude.ai web supports it. Until then, in-prompt content for `workflow`'s description is the right home, NOT a separate top-level tool.

**Survives + simplifies:**

- **`universe` → `workspace`** (renamed for user-vocabulary alignment per `feedback_user_vocabulary_discipline`)
- **`extensions` → `workflow`** (same — user term over engine term)
- **`goals` → folds into `commons`** (goals ARE shared design intents — convergent commons surface) OR keeps a `commons.action=goal_pool` action
- **`wiki` → folds into `commons`** (wiki IS the shared knowledge layer; cross-user is its essence)

**Net surface count: 5 primitives** (vs 7 today) **with denser action menus inside each.**

### §2.4 — What browser-only CAN'T do — and the platform compensates

Per `project_user_capability_axis` Imperative #2, browser-only users get cloud-mediated leverage. The 5 primitives MUST compose these compensations:

1. **Daemon hosting:** browser user can't run a daemon → `run` primitive has `claim_via=paid|free-queue|self-host` actions. Browser users default to paid-or-queue; the daemon runs cloud-side.
2. **File output:** browser user can't write to local file system → `run` outputs include shareable URLs (wiki page, signed S3, github gist). User clicks → downloads in their browser.
3. **Long-running work:** browser session ends but the run shouldn't → `run` returns immediately with a run_id; user comes back next session, calls `run` again to fetch results. State is universe-scoped so it survives.
4. **Parallelism:** browser user can't run 100 evaluators in parallel → `evaluate` primitive is the platform's batch-evaluator surface; user submits one rubric, platform runs N evaluations cloud-side, returns ranked results.
5. **Notifications:** browser user can't get a webhook → `commons` includes `subscribe_run` (or the equivalent in `run`) that posts results to a wiki page or sends a chat message via the chatbot's own platform notifications when supported.

**The browser-only primitive set is COMPLETE for everything-imaginable.** The compensations are inside the 5 primitives, not new primitives.

---

## §3 — Local-app tier additional primitives

When the user has computer-use access (Claude Code, ChatGPT desktop, OSS-app like Cline that drives the local computer), the primitive set expands minimally — most leverage comes from the chat-client doing things WITHOUT going through MCP tools.

### §3.1 — What changes when computer-use is available

The local-app user's chat-client can:
- Read/write the local file system directly (no MCP roundtrip)
- Spawn local processes (run `python -m tinyassets`, run a daemon, run tests)
- Edit code in an IDE (Cursor, VS Code)
- Show file diffs / preview rich artifacts inline

This means many "compensations" the platform builds for browser-only become redundant for local-app — the chat-client does it natively. The platform's primitive set DOESN'T need to grow much. The user's CHAT-CLIENT grows the surface.

### §3.2 — What additional primitives the platform exposes (3 add-ons)

| # | Primitive | Verb coverage | What it adds |
|---|---|---|---|
| **6** | **`host`** | (new: HOSTING) | Tray-installed daemon: register capabilities, set visibility (self/network/paid), claim incoming requests. Local-app users become PROVIDERS in the paid market. Browser users have no analog. |
| **7** | **`upload`** | DESIGN + DELIVER | Push local files into the platform: canon docs, workflow definitions, datasets. Browser user fakes this via `commons.wiki-write` for text or paste-into-chat for small data. Local-app skips the chat round-trip. |
| **8** | **`develop`** | DESIGN + COLLABORATE (OSS subset) | Local clone-and-edit-and-PR for OSS-tier users (Ilse). Doesn't go through MCP at all — this is a github-native primitive. Listed for completeness. |

Note: #8 isn't really an MCP-tool primitive — it's a workflow that uses git + GitHub directly. Listed because per `project_user_tiers` it IS a load-bearing verb for OSS contributors. Doesn't bloat the MCP surface.

**Net local-app primitive count: 5 + 2 = 7** (or 5 + 3 if you count `develop`-as-workflow). Still tiny vs current 7-tool MCP surface, but the 7th tool is genuinely tier-restricted (`host`).

### §3.3 — When MCP roadmap features ship (sampling / elicitation / resources)

These are roadmap-aware additions, not current-spec primitives. When Claude.ai web + ChatGPT web ship them:

- **MCP `resources`**: read-only browseable artifacts. Could simplify `commons.search` (the user's chat-client BROWSES wiki pages directly, no separate tool call). Doesn't add a primitive; reduces chatter on the existing 5.
- **MCP `sampling`**: server-initiated LLM calls. Lets the platform run evaluators / prompt-template completions without going through the user's chat-client → cheaper + asynchronous. Doesn't add a user-facing primitive; makes `evaluate` more powerful internally.
- **MCP `elicitation`**: server-initiated user prompts mid-tool-call. Lets the platform say "I need confirmation on this destructive action" or "which of these 3 vendor matches is correct?" mid-run. Doesn't add a primitive; makes `run` and `evaluate` interactive.
- **MCP `prompts`**: user-controlled chat-template surface. Lets platform ship "Workflow design wizard" / "Bug investigation flow" as starting templates the user picks from a menu. **This is the right home for `branch_design_guide`** (which is currently a tool but should be a prompt).

**Conclusion:** when the spec features land, the 5-primitive set DOESN'T need to grow. Existing primitives become richer. `branch_design_guide` migrates from tool → prompt.

---

## §4 — Overlap set + collapse trajectory

**The overlap set:** the 5 browser-only primitives (`workspace`, `workflow`, `run`, `evaluate`, `commons`) are also the canonical primitives for local-app users. Local-app users get 2-3 ADDITIONAL primitives (`host`, `upload`, optionally `develop`). The 5 are TIER-PORTABLE.

**Collapse trajectory** (per `project_user_capability_axis` Imperative #4):

As Claude.ai web gains computer-use + local-file capabilities (Anthropic + OpenAI roadmap signals 2026 → 2027), the gap between browser-only and local-app collapses. The primitives don't change — what changes is **which tier requires platform compensation vs which tier gets it natively from the chat-client.**

The `host` primitive becomes the only structurally-tier-restricted one — running a daemon requires a real local computer, not just file system access. (Browser users with persistent tab-pinned connection to a cloud daemon could simulate hosting, but that's a different shape.)

**Provider portability:** the 5 + 2 primitives are CONTRACTS, not implementations. Claude.ai, ChatGPT, Cline, OpenWebUI all implement MCP tools per spec — same JSON shape works on all of them. Per F33 of the capability-axis sweep, current tool descriptions are already client-portable (zero hardcoded "Claude.ai" / "ChatGPT" in canonical tinyassets/api/* tool descriptions). The proposed 5-primitive consolidation MAINTAINS this portability.

**Phone-browser-only canonical persona:** per F26 of the sweep, the lowest-capability target is "phone-browser-only-OR-ChatGPT user." All 5 primitives MUST work on phone-Claude.ai AND phone-ChatGPT. The 5-primitive consolidation reduces tool-list cognitive load on small screens (5 < 7) — net win for phone users.

---

## §5 — Comparison vs current platform surface

### §5.1 — Current 7-tool surface (per `tinyassets/universe_server.py`)

| Current tool | LOC dispatched (approx.) | Action verbs | Survives? | Notes |
|---|---|---|---|---|
| `universe` | 27 _action_* handlers | inspect, list, create, submit_request, queue_list, queue_cancel, daemon_overview, set_tier_config, subscribe_goal, unsubscribe_goal, list_subscriptions, post_to_goal_pool, submit_node_bid, give_direction, query_world, read_premise, set_premise, add_canon, add_canon_from_path, list_canon, read_canon, control_daemon, get_activity, read_output, ... | **Mostly survives** as `workspace`. ~12 actions stay; ~10 fold into other primitives (queue/dispatch/subs into `run`; goal_pool into `commons`; daemon control into `host`). |
| `extensions` | many `_ext_branch_*` handlers | build_branch, patch_branch, list_branches, describe_branch, register_node, list_nodes, ... | **Survives** as `workflow`. |
| `goals` | dispatch to `_action_*` in market.py | propose, get, search, bind, set_canonical, my_recent (retired 2026-05-01; compose from run/goal lookups) | **Folds into `commons`** as `commons.goals.*`. The convergent-commons surface for shared workflow intent. |
| `gates` | dispatch in market.py | claim, list, ... | **Folds into `evaluate`** as `evaluate.gate.*`. Gates ARE evaluator claims. |
| `wiki` | wiki.py | search, read, write, list, file_bug, ... | **Folds into `commons`** as `commons.wiki.*`. Wiki IS the cross-user knowledge layer. |
| `get_status` | dispatch in status.py | (returns daemon + universe + queue state) | **Folds into `workspace`** (universe inspect returns same data) OR into `run` (per-run status). Currently a third surface for the same data; consolidate. |
| `branch_design_guide` | static prompt | (returns a long markdown guide) | **MIGRATES** to MCP `prompts` capability when Claude.ai web supports it. Until then, fold its content into `workflow.tool description` so the chatbot reads it once at session-start. NOT a tool. |

### §5.2 — What the proposed 5-primitive surface looks like

```
workspace ─── inspect, list, create, set_tier_config, control_daemon (T2),
              read_premise, set_premise (universe-scoped settings)
              + folds: get_status

workflow  ─── build, patch, fork, version,
              register_node, list_nodes, describe_node,
              list_branches, describe_branch
              (+ branch_design_guide migrates to prompt)

run       ─── submit, status, events, fetch_outputs,
              cancel, list, resume_from (accepted as run_branch param),
              query_world (read run state),
              + folds: queue/dispatch/subscriptions
              + recency composes from run list/query + goal lookup

evaluate  ─── score, gate.claim, gate.list,
              run_diff, judge_*,
              + folds: gates

commons   ─── wiki.read, wiki.write, wiki.search, wiki.list,
              wiki.file_bug, wiki.cosign,
              goals.propose, goals.search, goals.bind, goals.set_canonical,
              goals.subscribe, goals.post_to_pool,
              attribution.read, attribution.contribute,
              + folds: wiki + goals
```

**Plus 2 local-app-only:** `host`, `upload`.

### §5.3 — Net consolidation

- **Tool count: 7 → 5** (browser tier) + 2 (local-app additions). Net = 5 base + 2 tier-restricted add-ons.
- **Action count: similar** (~80 actions today across 7 tools → ~80 actions across 5 primitives, slightly denser per primitive).
- **`branch_design_guide` retires from tool surface** → migrates to MCP prompts when supported, lives in `workflow` description until then.
- **`get_status` retires** → folded into `workspace.inspect` + `run.status`.
- **`gates` retires** → folded into `evaluate.gate.*`.

**User-cognitive load:** 5 verbs vs 7 verbs is a measurable reduction. More importantly, the 5 verbs MAP DIRECTLY to user-goal verbs (workspace=DISCOVER, workflow=DESIGN, run=RUN/OBSERVE/DELIVER, evaluate=EVALUATE, commons=COLLABORATE). The current 7 mix domain language (extensions, goals) with implementation language (get_status, gates) — confusing.

---

## §6 — Research evidence

### §6.1 — MCP spec roadmap (2026)

Per `blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/`:
- **Top priorities for 2026:** Streamable HTTP transport scaling (stateful sessions, horizontal scaling), enterprise readiness (audit, SSO, gateway, config portability).
- **Next spec release:** ~June 2026. SEPs (Spec Enhancement Proposals) finalizing in Q1.
- **Server-side primitives:** prompts, resources, tools (current). Client-side: roots, sampling, elicitation.
- **Sampling** (servers request LLM completions during execution) and **elicitation** (servers request user input mid-call) are spec'd but not yet exposed by Claude.ai web custom connectors.

Implication: the 5-primitive proposal is robust to roadmap. New MCP capabilities make existing primitives RICHER, not new primitives needed.

### §6.2 — Claude.ai + ChatGPT custom-connector capability bounds

Per `support.claude.com/en/articles/11175166`:
- Claude.ai web custom connectors: **TOOL CALLS ONLY** as of 2026. Resources, prompts, sampling, elicitation NOT exposed.
- Plus + Pro individual users: read/fetch only on custom MCP connectors. Business/Enterprise/Edu: full write.

Per OpenAI Help Center 2026:
- ChatGPT custom MCP via Developer Mode: similar individual-user floor (read/fetch only). Business/Enterprise: full write + apps.
- Confirmation modal before write actions (consistent with BUG-034 pattern).

Implication: the BROWSER-only primitive design must compile to TOOL CALLS, period. Anything assuming richer MCP surface is local-app or enterprise-tier.

### §6.3 — Competitor primitive sets

**Zapier** (per `n8n.io/vs/zapier/`, `datacamp.com/blog/n8n-vs-zapier`):
- Primitive: **trigger → action**. ~7000 integration "apps" each exposing many actions. No state, no branching as first-class. Zaps are linear.
- User-cognitive surface: massive (7000 apps), each with N actions. Workflow design = pick app → pick action → wire fields.
- **Lesson:** Zapier's surface is HUGE because each integration is its own primitive. Workflow's path is the opposite — fewer primitives, each does one thing across all integrations.

**n8n** (per `hatchworks.com/blog/ai-agents/n8n-vs-zapier/`):
- Primitives: **node** (function), **edge** (data flow), **state** (workflow context), **branching/loops**, **error handling**, **sub-workflows**.
- ~6 conceptual primitives + integration nodes. Closer to "build everything from few primitives."
- **Lesson:** n8n proves a LangGraph-shape (node + edge + state) is a tractable user-facing primitive set. Workflow's `workflow` primitive aligns directly.

**Replit Agent** (per `langchain.com/breakoutagents/replit`):
- "Tools calling agents and agents calling tools — fully composable architecture."
- Multi-agent: tools registered dynamically; agents with assigned roles; manager + editor agents.
- **Lesson:** dynamic tool registration is irreducible — Workflow's `workflow.register_node` does this.

**Cursor / Devin / Claude Code** (per `productwithshambhavi.substack.com/p/ai-agent-products-dissected-cursor`):
- Local-app agents with file system + terminal + test-runner ownership.
- Don't expose primitives via MCP; ARE the chat-client.
- **Lesson:** local-app users don't need many platform primitives; the chat-client provides most. Workflow's local-app primitive count (`host`, `upload`) is intentionally small for this reason.

### §6.4 — User composition patterns from chat-traces + persona memories

From `output/user_sim_session.md`, persona memories, and audit chat traces:

**Maya Okafor (T1, Claude.ai phone):**
- Composition: extract → consolidate-by-vendor → transform-to-CSV → file-output. 4 verbs.
- Maps to: `workflow.build` (define extraction graph) + `run.submit` + `run.fetch_outputs` (CSV). 3 primitive calls.

**Priya Ramaswamy (T1, Claude.ai laptop):**
- Composition: discover-prior-sweep → extend-with-new-algos → run → evaluate (sensitivity sweep) → render methods-paragraph + repro-script.
- Maps to: `commons.search` → `workflow.fork` → `run.submit` → `evaluate.score` → `run.fetch_outputs` (artifact). 5 primitive calls.

**Mark (T2, ChatGPT connector):**
- Composition: file-bug → run-canonical-investigation → receive-patch-packet → review.
- Maps to: `commons.wiki.file_bug` → (auto-triggered) `run.submit` → `run.fetch_outputs`. 2 primitive calls (file_bug auto-triggers run).

**Devin (T2, daemon host):**
- Composition: register-as-host → claim-paid-request → run → settle.
- Maps to: `host.register` → (queue) → `run.submit` (host-side claim) → settlement (in `host` primitive).

**Ilse (T3, OSS contributor):**
- Composition: clone repo → read code → write PR.
- Maps to: `develop` (out-of-MCP, github-native).

**All 5 personas' goals compose from the proposed 5 + 2 primitives.** No persona's flow requires a primitive that isn't proposed. Conversely, no proposed primitive lacks a persona that uses it.

### §6.5 — Real "extension is fragile" signal from Priya

From persona memory `priya_ramaswamy/sessions.md` line 177:
> "Extension-as-first-class-primitive. Workflow should have a notion of 'continue the prior sweep' that's distinct from 'scaffold a new pipeline.' ... Priya's ask in T+0:00 ('can we extend') is a natural-language signal — chatbot should recognize extension semantics and route through a different scaffold path."

This was the concrete user-evidence for an explicit continuation path. Superseded 2026-05-01: do not add standalone `continue_branch`; accepted target is optional `resume_from=<run_id>` on existing `run_branch` after #18. The primitive lesson still stands: serve the intent on the run surface, not as a new top-level tool.

Per `feedback_irreducibility_test_before_spec`, the question was: "can chatbot compose continuation from existing primitives in <5 steps?" The accepted answer is narrower now: chatbot can compose recency from existing reads, while continuation gets one `run_branch` parameter because the source-run carryover contract is error-prone enough to deserve a stable affordance.

---

## §7 — Decision asks for the lead → host

### §7.1 — Strategic direction

1. **Approve the 5-primitive consolidation** as the target end-state? (vs current 7-tool surface.) The consolidation is conceptual; implementation lands per arc.
2. **Approve the 7 user-goal verbs** (DESIGN, DISCOVER, RUN, OBSERVE, EXTEND, DELIVER, COLLABORATE) as the load-bearing test the primitive set must serve? Future primitive proposals get scored against this list.
3. **Approve the local-app additions** (`host`, `upload`)? `host` is genuinely tier-restricted; `upload` is a workflow over the chat-client's file-system access.
4. **Migrate `branch_design_guide` from tool to MCP prompt** when Claude.ai web supports prompts? Until then, fold content into `workflow` tool description. Per the proposal, this is one of two retirements.
5. **Retire `get_status` and `gates`** as separate top-level tools? Fold into `workspace`/`run` and `evaluate` respectively.

### §7.2 — Sequencing + execution

6. **When does this consolidation execute?** Recommend SCHEDULE as Phase 7 of the rename arc (after Arc B/C/Phase 6 + A.1 unpack), or as a separate "primitive-set arc." Multi-week structural work — rename `extensions` → `workflow` (API + tool surface + tests), rename `universe` → `workspace` (same), fold `goals` + `wiki` into `commons`, rename `get_status` → universe-inspect-add-fields, etc.
7. **Pre-arc validation:** before the consolidation starts, RUN ON A FORK or use a feature flag — the migration touches every chatbot's working pattern. The persona-replay test scaffold (`docs/audits/...persona-replay`) exists; use it to validate every persona's flow still works after consolidation.

### §7.3 — Naming

8. **Tool name choices:** `workspace` vs keep `universe`? `workflow` vs keep `extensions`? `commons` vs `share` vs other? Recommend the proposed names — they map to user vocabulary (per `feedback_user_vocabulary_discipline`) over engine vocabulary.
9. **`evaluate` vs `judge`** — the existing engine vocabulary uses `EvaluatorKind` and `judgment` interchangeably. Pick one for the user-facing primitive.

### §7.4 — Roadmap-aware vs conservative

10. **Plan for MCP roadmap features** (sampling/elicitation/resources)? Recommend YES — design the primitives so they ABSORB richer MCP capabilities without renaming or restructuring. The 5 primitives proposed already do this (e.g., when elicitation lands, `run` mid-call clarifying questions become a richer mode of `run.submit`, not a new tool).

---

## §8 — Validation: walking each persona through the proposed 5

Per `feedback_irreducibility_test_before_spec`, the test is: "can a competent chatbot reliably compose this from existing primitives in <5 reasoning steps?" Run that test against each persona for their canonical flow:

### §8.1 — Maya Okafor (T1, Claude.ai phone, payables automation)

> "I uploaded 30 invoice PDFs. Make me a Sage CSV."

Proposed primitive flow:
1. `workspace.inspect` → orient (1 step)
2. `commons.search(intent='invoice extraction to CSV')` → check if existing workflow exists (1 step)
3. If no match: `workflow.build` with extraction + transform nodes (1-2 steps)
4. `run.submit(branch_id, inputs=invoice_paths)` (1 step)
5. `run.fetch_outputs(run_id)` → CSV download URL (1 step)

**Total: 4-5 steps. PASS.**

### §8.2 — Priya Ramaswamy (T1, Claude.ai laptop, sensitivity sweep)

> "Extend my prior MaxEnt sweep with BIOCLIM + RF on the same 14 species."

Proposed primitive flow:
1. `commons.search` → find prior sweep (1 step)
2. `workflow.fork(prior_branch_id, add_nodes=[bioclim, rf])` (1 step)
3. `run.submit(forked_branch_id, inputs=species_set)` (1 step)
4. `evaluate.score(rubric=publication-grade)` (1 step)
5. `run.fetch_outputs(run_id)` → methods paragraph + repro script (1 step)

**Total: 5 steps. PASS at the boundary.** Note: `run.continue from_run_id=X` action would compress this to 3 steps (collapses 1+2 into one action). Worth shipping as a `run` action verb per §6.5.

### §8.3 — Mark (T2, ChatGPT connector, bug-to-patch)

> "File a bug: BUG-034 says extensions actions return 'No approval received'."

Proposed primitive flow:
1. `commons.wiki.file_bug(title, body)` → auto-triggers run of canonical bug-investigation branch (1 step)
2. `run.fetch_outputs(run_id)` later → patch packet attached as bug-page comment (1 step)

**Total: 2 steps. PASS.**

### §8.4 — Devin (T2, daemon host, paid market)

> "Register as host for fantasy-author scene-drafting; accept paid bids."

Proposed primitive flow:
1. `host.register(capabilities=[fantasy_author.scene_draft], visibility=paid)` (1 step)
2. (queue auto-claims highest-value-vs-effort request)
3. `run.submit` (host-side claim auto-routes) (0 steps from user; daemon handles)
4. `host.settle(run_id)` for ledger credit (1 step)

**Total: 2 user-facing steps. PASS.** `host` is genuinely tier-restricted but minimal.

### §8.5 — Ilse (T3, OSS contributor, fork-and-PR)

> "I want to add a `continue_branch` action to the run primitive as a PR."

Historical wording note: the current target is `run_branch resume_from=<run_id>`, not a standalone `continue_branch` action.

Proposed primitive flow:
1. `develop.clone` (out of MCP — github clone) (1 step)
2. (local edits in IDE)
3. `develop.pr` (out of MCP — github PR) (1 step)

**Total: 2 user-facing steps + local work. PASS.** `develop` isn't really an MCP primitive; it's a github workflow.

### §8.6 — Result

All 5 personas' canonical flows compose in **≤ 5 chatbot reasoning steps using the proposed 5 + 2 primitives.** The 5-primitive surface is sufficient to cover everything-imaginable that the personas' goals expand to.

Where the proposal needs refinement: Priya's flow is at the 5-step boundary; that's the strongest argument for `run.continue from_run_id=X` as an action verb. Same primitive, named intent.

---

## §9 — Net recommendation

**APPROVE the 5-primitive consolidation as the strategic target.** Schedule execution as a Phase 7 arc post Arc B/C/Phase 6 + A.1 unpack. Use the persona-replay test scaffold for validation.

The proposal is research-backed (MCP spec + competitor analysis + user composition patterns), tests cleanly against the personas' canonical flows, and aligns with both `project_minimal_primitives_principle` and `project_user_capability_axis`. It REDUCES the surface (7 → 5) while preserving every user verb. It maps to user-vocabulary over engine-vocabulary. It's roadmap-robust — MCP capability additions enrich the 5 without growing them.

Pre-execution, host weighs in on §7's 10 decision asks. Once approved, the consolidation arc gets a separate exec-plan with phasing + risk + sequencing, similar to A.1's unpack arc design note.

---

## §10 — Cross-references

- `project_minimal_primitives_principle` — foundational scoping rule
- `project_user_capability_axis` — capability tier × provider × OSS-client
- `project_community_build_over_platform_build` — feature-build heuristic
- `project_chatbot_assumes_workflow_ux` — chatbot-UX rules that constrain primitive shapes
- `project_user_builds_we_enable` — users compose; platform exposes substrate
- `feedback_irreducibility_test_before_spec` — test applied per primitive
- `feedback_user_vocabulary_discipline` — user-vocabulary > engine-vocabulary
- `docs/audits/2026-04-26-user-capability-axis-implications.md` — tactical sibling sweep (this proposal is the strategic answer to it)
- `docs/design-notes/2026-04-18-full-platform-architecture.md` §2.4 — install-friction tier matrix
- `docs/design-notes/2026-04-26-fantasy-daemon-unpack-arc.md` — A.1 arc that precedes this in sequencing
- Persona memories: `maya_okafor/`, `priya_ramaswamy/`, `mark/`, `devin_asante/`, `ilse_marchetti/`
- `tests/test_vocabulary_hygiene.py` — chatbot-vocabulary regression contract (the consolidation must pass this test)

### Web research citations

- [The 2026 MCP Roadmap | Model Context Protocol Blog](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/) — Q1 2026 priorities, June 2026 spec release, sampling/elicitation status
- [Get started with custom connectors using remote MCP | Claude Help Center](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp) — Claude.ai web custom MCP connector capabilities + tool-only constraint
- [Beyond Tool Calling: Understanding MCP's Three Core Interaction Types | Upsun Docs](https://devcenter.upsun.com/posts/mcp-interaction-types-article/) — primitives breakdown: tools / resources / prompts
- [Developer mode, and MCP apps in ChatGPT [beta] | OpenAI Help Center](https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta) — ChatGPT custom-connector individual-user floor
- [n8n vs Zapier: The Definitive 2026 Automation Face-Off | hatchworks.com](https://hatchworks.com/blog/ai-agents/n8n-vs-zapier/) — competitor primitive comparison
- [Replit Agent Case Study: AI Agent Architecture & Build | langchain.com](https://www.langchain.com/breakoutagents/replit) — composable architecture
- [AI Agent Products, Dissected: Cursor and Replit | productwithshambhavi.substack.com](https://productwithshambhavi.substack.com/p/ai-agent-products-dissected-cursor) — local-app agent primitives
- [LangGraph StateGraph reference | reference.langchain.com](https://reference.langchain.com/python/langgraph/graphs) — substrate primitives that Workflow builds atop
