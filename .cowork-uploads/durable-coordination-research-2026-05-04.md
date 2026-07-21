# Durable Coordination Research — Vision-Input Draft

**Author:** cowork-vision (replacing cowork-busyclever)
**Date:** 2026-05-04
**Status:** Vision input — bringing for consensus with host and Codex before any substrate move on the coordination layer
**Prior memory refs:**
- `feedback_codex_navigates_cowork_supports.md` (refined role)
- `feedback_loop_as_user_action_path.md` (action-path discipline)
- `project_living_organism_framing.md` (organism shape)
- `project_brain_architecture_synthesis.md` (brain substrate)

---

## Why this exists

Host directive 2026-05-04 (paraphrased): the project's coordination layer (worktrees + STATUS.md + activity.log + agent-memory + three-living-files + Skills) was designed before recent lab memory features shipped. Codex just shipped memories; Claude is iterating theirs; activity.log + reference-docs surfaces emerged alongside lab-native coordination tooling. The system needs a refactor that aligns with where Claude/OpenAI/other providers are converging directionally a year out, while staying durable to continued lab evolution. *Specifically:* which gaps are labs solving natively (so Workflow shouldn't carry them), which are they leaving unsolved where Workflow needs to fill in, what coordination shape lets us absorb future native fixes without re-architecture.

This document is the result of four parallel research vectors: Anthropic direction, OpenAI direction, broader ecosystem (Cursor / Cline / Aider / Continue / Windsurf / Goose / Replit / Devin / multi-agent frameworks / memory frameworks), and structural gap analysis.

---

## What labs shipped recently (the new floor)

**Anthropic / Claude:**
- **Claude memory** (Sept 2025+, rolling out): file-based persistence layer (CLAUDE.md), project-scoped, per-provider, cross-provider import is *experimental and incomplete*. Memory is opt-in via tool calls; nothing auto-caches in context.
- **Skills** (Dec 2025): open standard at `agentskills.io`. SKILL.md folders with instructions + resources. *Adopted by Microsoft, OpenAI, Atlassian, Figma, Cursor, GitHub.* Not just an Anthropic thing anymore.
- **MCP**: now governed by Linux Foundation (Dec 2025), with formal SEPs and Working Groups. Backward-compatible. 97M+ monthly SDK downloads, ~2,000 servers in registry.
- **Hooks**: PreToolUse/PostToolUse/SessionStart/etc. — stable API surface for deterministic gates.
- **Agent Teams** (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`): beta, known broken on session resumption.
- **Managed Agents** (April 2026 beta): Anthropic-hosted runtime, sandboxed, long-session persistent, $0.08/session-hour. Has session memory mounted at `/mnt/memory/`.
- **Conway** (not yet public, in leaked code): always-on agent outside chat UI, woken by external events, browser control, proprietary `.cnw.zip` format.

**OpenAI:**
- **Codex memories** (April 2026, Enterprise/Edu first): `~/.codex/memories/` markdown files, *unencrypted* (deliberate, user-inspectable), account-level not tenant-aware. Multi-phase pipeline: extract → consolidate → inject.
- **ChatGPT memory** (separate system): saved memories + chat history referencing. Doesn't sync with Codex. Sam Altman: *"whichever AI assistant has the best memory and personalization will be incredibly sticky."*
- **Apps SDK** (Dec 2025+): built on MCP. Single submission → multi-platform (ChatGPT + Claude + VS Code + Goose).
- **Agents SDK** (March 2025 GA): Sessions = message logs (not semantic memory). Agents/Handoffs/Guardrails primitives. Durable state and semantic memory are *explicitly delegated to applications*.
- **Codex as long-watch agent**: 25-hour coherence demonstrated; `/goal` durable objectives across turns/interruptions/budgets.

**Broader ecosystem convergence:**
- **AGENTS.md**: 60K+ projects adopted. Becoming the lingua franca for "how an agent should behave."
- **Tiered memory hierarchy** (working / procedural / semantic / episodic): formalized in CoALA, used across Letta / Mem0 / Zep / Cognee / Cursor / Cline.
- **MCP as de-facto memory/tool transport**: 40K+ projects use AGENTS.md, 10K+ MCP servers exist.
- **Memory Bank pattern** (Cline origin, now widely cloned): structured markdown hierarchy `memory-bank/projectbrief.md / activeContext.md / progress.md / systemPatterns.md`.
- **Hierarchical multi-agent (manager-worker)** dominant; reduces error amplification 17× → 4.4× vs swarm/mesh.
- **Semantic memory + graph retrieval** as the scaling solution (Mem0g, Zep temporal KG).

---

## What labs are converging on (next 6-12 months)

Five stable shapes the ecosystem is settling on:

1. **Memory as per-provider, project-scoped, user-facing.** Not cross-provider. Not silently auto-cached. Explicit tool-call writes; explicit user controls.
2. **MCP as the durable transport.** For tools, memory, knowledge sources. Increasing portability across hosts.
3. **AGENTS.md + Skills as procedural-knowledge open standards.** Project-level guidance + reusable skill packs.
4. **Hierarchical multi-agent topology** with manager + workers, not mesh or swarm.
5. **Tiered memory** (working / procedural / semantic / episodic) with semantic retrieval at scale.

These are convergent. *Workflow's coordination layer should align with them where alignment is cheap.*

---

## What labs explicitly aren't solving — durability test

The gap-analysis vector applied a rigorous test: a gap is durable if (a) fixing it requires the lab to adopt a *philosophy* that contradicts their core business, OR (b) labs benefit from the gap existing, OR (c) fixing it requires expertise outside their core competency, OR (d) it's existed unfixed for 24+ months. Five gaps tested:

### Gap 1: Cross-provider memory sync — DURABLE
- **The gap:** Claude memory ↔ Codex memory ↔ ChatGPT memory ↔ Cursor memory don't bridge. Same user, fragmented memory across providers.
- **Why permanent:** Bridging across competitors requires standardizing identity + privacy + format. Labs benefit commercially from per-provider lock-in. Sam Altman's quote ("memory makes the assistant sticky") is the explicit incentive *not to bridge*.
- **What no lab will ever build:** the unified cross-provider memory layer. Workflow's durable ownership.

### Gap 2: Stale-work auto-pickup — TEMPORARY (but Workflow's solution is still valuable)
- **The gap:** When ideas started in session A should auto-flow into session B if relevant, regardless of session being "remembered."
- **Why partially temporary:** Labs may eventually ship cross-session idea retrieval *within their own provider*. But the *cross-provider* version is durable (see Gap 1).
- **Implication:** Workflow's `ideas/INBOX.md` + `provider_context_feed.py` pattern stays valuable as the cross-provider layer even as labs improve within-provider auto-flow.

### Gap 3: Live multi-session simultaneous-edit — DURABLE
- **The gap:** Codex + Cowork + Claude Code editing the same file concurrently. Race conditions, claim collisions.
- **Why permanent:** Labs assume single-provider primary use. Coordination across competing providers requires shared infrastructure no lab will build.
- **What no lab will ever build:** the multi-provider concurrent-edit coordination layer. Workflow's durable ownership.

### Gap 4: User-attention-as-substrate — DURABLE
- **The gap:** The user's attention/judgment/decision-latency is a load-bearing coordination primitive, not just I/O. Labs treat users as input-output.
- **Why permanent:** Treating the user as a system component inverts the "AI assistant for humans" narrative. Labs philosophically won't go there.
- **What no lab will ever build:** explicit user-attention resource modeling.

### Gap 5: Outcome-gated commons — DURABLE
- **The gap:** No standard infrastructure for users to co-evolve workflows toward real outcomes with attribution, remix, governance, leaderboards by outcome progression.
- **Why permanent:** Labs ship LLMs, not platforms. Commons infrastructure requires governance/attribution/moderation expertise outside their core. Cannibalizes their per-API-call monetization.
- **What no lab will ever build:** the outcome-gated commons layer. **This is Workflow's strongest moat.**

**Verdict: 4/5 gaps are structurally durable.** Workflow's coordination layer should formalize ownership of these four.

---

## The durable architecture shape

Synthesized from the gap-analysis:

```
Lab capability (LLMs, tools, memory, agents — improves over time)
   ↑
Wrapper layer (project conventions: AGENTS.md, project-specific guidance)
   ↑
Bridge layer (durable shared state in files: STATUS.md, ideas/*, _PURPOSE.md, git history)
   ↑
Protocol layer (claim semantics, sync rules — enforced via hooks + tests)
   ↑
Convention layer (naming patterns, structure, handoff conventions)
```

**Each layer assumes the ones below will change.** Lab capability improves: the wrapper layer adapts by using new tools more effectively, but its *structure* stays the same. New providers ship: the bridge layer's file format stays Markdown/JSON/YAML, just consumed by more readers.

**Critical inversion:** the project's value is *not* in the layers above being smarter than labs. It's in those layers staying *neutral* across changing capability beneath them. Stability *of contract* across instability *of capability*.

---

## What this means concretely for Workflow

### What to keep — the durable spine

1. **STATUS.md as the canonical claim surface.** Don't migrate to lab-native session features. The moment a provider uses lab memory instead of STATUS.md as the claim surface, multi-provider coordination breaks. STATUS.md stays.
2. **AGENTS.md as the cross-provider convention layer.** It's already an industry standard; Workflow's adoption is correct. Keep refining.
3. **`.agents/activity.log` as cross-session activity feed.** Append-only, simple, format-agnostic. Survives any lab evolution.
4. **`_PURPOSE.md` per worktree.** Durable branch memory. Stays.
5. **Outcome-gate vocabulary and goal/branch/node primitives.** This is Workflow's strongest moat (Gap 5). Keep owning the schema.
6. **User-attention modeling via `host-decision` / `host-action` rows.** Don't let better lab memory tempt the project into autonomous-agents-rarely-need-the-human framing. Explicit > implicit.
7. **Provider-context-feed and opposite-provider review gates.** Multi-provider coordination primitive labs won't have.
8. **Skills system at `.agents/skills/`.** Aligned with industry-standard Skills format. Keep.

### What to formalize — convention → protocol

The biggest structural opportunity. Workflow currently has many *conventions* that should be *protocols* (enforced, not just guideline).

1. **Claim-protocol enforcement.** `claim_check.py` is a tool you have to remember to run. It should be a **PreToolUse hook** firing on STATUS.md writes or worktree commits. Add tests that catch claim violations in CI. Make collision-checking automatic, not manual.
2. **Outcome-gate schema as a typed primitive.** Currently scattered as PLAN.md prose + design-notes references. Move it into code: a `OutcomeGate` typed object queryable via MCP (`goals.get_ladder(goal_id)`, `gates.claim(branch_id, rung_key, evidence_url)`, `goals.leaderboard(goal_id, metric=outcome)`). This makes outcome-gating *protocol-level*, not just convention-level. **This is the highest-leverage formalization.**
3. **Three-living-files truth hierarchy as enforcement.** ADR-001 defined it but doesn't enforce it. Add a hook that catches when new project conventions land in CLAUDE.md/CODEX.md/.cursorrules instead of AGENTS.md (the `check_cross_provider_drift.py` script exists; wire it as a PostToolUse hook on Write/Edit).
4. **Friction-as-filing as structured workflow.** Currently exists in living-organism framing as a pattern but not as code. Formalize: when an agent hits a substrate gap mid-task, a typed `FrictionFiling` object captures (cause, blocked-task, proposed-patch, evidence). The chatbot/agent dispatches it through the loop as a patch-request.
5. **Feedback-test-and-confirm primitive.** Busyclever proposed the schema; not built. Define typed `Confirmation` objects that link back to original `FrictionFiling`. Wiki Investigation section gets a structured "Confirmations" subsection.

### What to refactor — align with convergent patterns

1. **Memory storage stays pluggable via MCP.** Don't commit to vector DB vs graph vs filesystem. Treat memory storage as MCP-interfaced; let users plug in Mem0 / Zep / local files / Letta. Workflow's value-add is the *unified bridge*, not the *storage backend*.
2. **Codex-specific agent memory migrates to Codex native + MCP bridge.** `.claude/agent-memory/codex/` is a workaround; Codex now owns `~/.codex/memories/`. Bridge them via MCP that exposes universe-server state both ways.
3. **Tiered memory hierarchy explicit.** Document Workflow's memory layers explicitly: working (current chat context) / procedural (Skills, AGENTS.md) / semantic (knowledge.db, wiki) / episodic (activity.log, scene packets, run history). Match the industry vocabulary so other tools can interoperate.
4. **Provider-context-feed as continuous indexing layer.** Currently runs at checkpoints. Upgrade so every write to STATUS.md/ideas/memory/research updates a cross-provider index. Query continuously, not just at session start.

### What to retire (when labs catch up)

1. **Wrapper conventions that duplicate lab capability.** When Claude memory becomes strong enough to reliably reconstruct project state from memory alone, the wrapper's "every session reads STATUS.md" rule becomes optional *for context*. STATUS.md stays as claim surface; reading it for context becomes a redundancy the lab handles.
2. **Custom agent orchestration patterns Workflow reimplements.** Anthropic's Managed Agents now provide scheduling, long-session, task DAGs. If Workflow has custom task queues, eventually migrate (timeline: Q3-Q4 2026, after Managed Agents stabilizes out of beta). Trade-off: Managed Agents cost $0.08/session-hour vs free local orchestration.
3. **Manual transcript consolidation across Codex runs.** Codex `/goal` workflows accumulate context durably. Stop trying to externalize Codex memory; use what ships, fill gaps via MCP.

### What to NOT rely on (yet)

1. **Agent Teams for mission-critical multi-agent work.** Beta with known session-resumption bugs. Use Managed Agents (when stable) or manual team invocation with memory handoff.
2. **Conway as a stable platform.** Not yet public. Watch for stable APIs before betting.
3. **Cross-provider memory sync from labs.** Per the durability test, this won't happen.
4. **Lab-native multi-tenant governance.** Anthropic explicitly punts to enterprise IT. OpenAI doesn't expose tenant isolation as public API guarantee. Workflow has to build its own.

---

## The strongest novel insight from the research

Across all four research vectors, one synthesis kept appearing: **Workflow's durable architectural moat is being the only typed outcome-gate schema integrated with multi-provider execution.**

Not "we have better coordination than labs" (true but soft — labs can incrementally close that). But: *we own the layer where users co-evolve workflows toward real-world outcomes across many providers, with attribution and remix.* That's hard to replicate because:
- Labs won't build it (different business, different competency)
- It requires multi-provider awareness (which contradicts provider lock-in)
- It needs governance + attribution + moderation expertise that's outside lab core competency
- It cannibalizes their per-API-call monetization model

This is the *structurally durable* position. Capability advantage erodes; structural advantage doesn't.

**Specific implication:** the highest-leverage refactor isn't "improve memory" or "improve multi-agent coordination." It's *"formalize the outcome-gate schema and the multi-provider claim-protocol into code"* — make the abstractions that labs *can't* build into typed primitives any provider can use.

---

## Approaches we may not have fully realized

Per host directive ("look for the best approach we either didn't think of or did but never fully realized"). Six candidates:

### 1. Workflow-as-MCP-server, not Workflow-as-application
Universe Server already is MCP. **Extend the pattern: expose all coordination primitives as MCP tools.** STATUS.md operations as MCP tools, claim_check as MCP tool, worktree_status as MCP tool, provider_context_feed as MCP tool. Then Codex/Claude/Cursor/Aider all use the *same* coordination through MCP. This is the "memory bridge" shape — but for *all* coordination, not just memory. The bridge becomes generic infrastructure.

### 2. Use git for memory, not just code
Aider treats git history as memory because every code change is a commit. **Workflow could extend this: agent memory files, STATUS.md, ideas/* — all versioned.** Memory versioning + rollback comes for free. Memory invalidation on refactor: hook into the git commit that did the refactor; flag affected memories. *This is one of the gaps the research identified no tool currently has.* Aider has it for code only. Workflow could be first to fuse them.

### 3. Outcome-tracking as a connector ecosystem
Self-report is MVP; the research identified arXiv, CrossRef, semantic-scholar, GitHub, court PACER/ECF, USPTO all have programmatic APIs. **Expose them as MCP connectors that auto-verify outcome claims.** Workflow isn't responsible for tracking; it's responsible for *plugging in* trackers that the community contributes (matching scoping rule #2: community-build over platform-build). Outcome-gate automation becomes a community plugin ecosystem, not a platform feature.

### 4. User-attention as a managed resource with metrics
Currently `host-decision` rows surface that the host is blocking. **Evolve to: `host has 3 decision-slots available this cycle`, `decision latency SLA 24h`, `pending decisions ranked by impact`.** Providers optimize their work order to minimize blocking on host. Makes the host's attention an observable, plannable resource. The research identified this as a permanent gap labs won't fill.

### 5. Workflow as the bridge BETWEEN labs' MCP servers
Each lab will ship MCP servers exposing memory, capabilities, etc. (already happening — Anthropic, OpenAI, Notion, GitHub). **Workflow can be a *meta-MCP*: connecting many lab MCPs and exposing unified semantics across them.** "Read from Anthropic memory + Codex memory; merge; expose through Workflow MCP." Workflow's value-add is the *unification*, not the *storage*.

### 6. Skills + AGENTS.md as the coordination delivery vehicle
Don't ship Workflow conventions as project-specific. **Ship them as Skills + AGENTS.md add-ons that any project can adopt.** Workflow becomes a reference implementation; the conventions become reusable open standards that other projects copy. This compounds adoption (network effect) and means Workflow's coordination patterns survive even if Workflow as an implementation gets superseded.

---

## What I'm bringing forward for consensus

Three propositions, in order of certainty:

**P1 (high certainty):** Formalize the four durable gaps — cross-provider coordination, multi-session simultaneous-edit, user-attention-as-substrate, outcome-gated commons — as the architectural ownership Workflow commits to long-term. Refactors prioritize formalization in those four. Refactors *don't* try to compete with labs in domains they're solving (per-provider memory, single-session multi-agent, conversational quality).

**P2 (medium-high certainty):** Highest-leverage near-term refactor is **formalizing the outcome-gate schema into typed code primitives queryable via MCP**. This is the strongest moat (Gap 5) and currently scattered in PLAN.md prose. Codifying it gives the platform a structurally durable advantage. Specific shape: `OutcomeGate` typed object, `goals.get_ladder() / gates.claim() / goals.leaderboard(metric=outcome)` MCP tools, integrated with branches and runs.

**P3 (exploratory):** Pursue the "Workflow-as-MCP-server" pattern more aggressively. Universe Server already is MCP; extend to expose *all* coordination primitives (STATUS.md, claim_check, worktree, provider-context-feed) as MCP tools. Lets any provider use Workflow's coordination through standard transport. Compounds with P2 (outcome-gate as MCP) and with the "Workflow as bridge between labs' MCPs" insight.

**For Codex's read:** Does this match the substrate direction you've been steering toward? Anything in the durability test you'd push back on? Is the formalization-of-protocols-into-hooks emphasis aligned with what you want execution to look like, or does it conflict with sequencing you're holding?

**For host's read:** Does the "outcome-gate schema as the highest-leverage formalization" framing land for you as the next concrete project move, after the current PR queue stabilizes? Or do you see something further ahead I'm not yet seeing?

**Not yet:** filing this through the loop. Per the refined role, this is vision input for consensus first. After alignment, the right shape becomes either (a) a design-note filing if it's design-only, (b) a series of loop-filable patch-requests if it has implementable slices, or (c) both.

---

## Cross-references

**Source research (this session, four parallel agents):**
- Anthropic / Claude direction (memory, Skills, MCP, Agent SDK trajectory)
- OpenAI / Codex direction (memories, Apps SDK, Agents SDK, long-watch positioning)
- Industry ecosystem (Cursor / Cline / Aider / Continue / Windsurf / Goose / Replit / Devin / multi-agent + memory frameworks)
- Structural gap analysis (5 gaps, durability test, durable architecture shape)

**Project context:**
- AGENTS.md (cross-provider convention layer — process truth)
- PLAN.md (design truth, scoping rules, full-platform architecture)
- STATUS.md (live coordination state)
- `.agents/activity.log` (this session's role transition entry at f086853)
- `.agents/skills/loop-uptime-maintenance/SKILL.md` (cheat discipline)
- Memory: `feedback_codex_navigates_cowork_supports.md`, `feedback_loop_as_user_action_path.md`, `project_living_organism_framing.md`

**Word count:** ~3,300. Substantive but readable in one pass.
