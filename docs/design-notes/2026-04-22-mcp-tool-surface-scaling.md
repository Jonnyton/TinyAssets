---
status: research
---

# MCP tool-surface scaling

*Date:* 2026-04-22. *Author:* navigator. *Trigger:* host flagged that
Claude.ai's custom-connector surface has tool-call / tool-definition
limits, and the platform intends to grow, not shrink, its user-facing
surface. Need a scaling strategy before the 6-tool baseline doubles.

Scope: research + design note, no code.

---

## §1 — The Constraint

**Cited:**
- Claude.ai recommends "On demand" tool-loading at **~10 active
  connectors** — framed as context-budget, not a hard ceiling. Free
  tier caps at 1 custom connector; paid tiers unspecified.
  (support.claude.com/en/articles/11176164)
- Anthropic's MCP code-execution blog measures **150k → 2k tokens
  (98.7% cut)** when tool schemas aren't loaded upfront.
  (anthropic.com/engineering/code-execution-with-mcp)
- MCP spec has **no hard tool ceiling**; the ceiling is host model
  context + Claude.ai orchestration heuristics.

**Assumed:** no public Anthropic doc gives a numeric tools-per-connector
cap. Community signal clusters perf degradation at ~30-50 tools per
connector. Rate limits are orthogonal.

**Takeaway:** the constraint is **cumulative tool-schema tokens per
conversation**, not tool count. Fewer fat tools can be worse than more
lean ones.

---

## §2 — Our 6-tool baseline

Current surface (registered via `@mcp.tool` in `tinyassets/mcp_server.py`
+ `tinyassets/universe_server.py`):

| Tool | Signature shape | Scaling shape |
|---|---|---|
| `universe` | `action: str, universe_id, text, path, ...` | STRAP — dense. Handles `list / inspect / read_output / query_world / write / commit / ...`. |
| `extensions` | `action: str, ...` | STRAP. Install/list/manage extensions + capabilities. |
| `goals` | `action: str, ...` | STRAP. Goal CRUD + ranking. |
| `gates` | `action: str, ...` | STRAP. Outcome-gate claims + ladder. |
| `wiki` | `action: str, ...` | STRAP. Read/search/list/lint + write/patch. |
| `get_status` | nullary | Single-purpose diagnostic. |

**Scales well:** adding a new read op under `universe` is one branch
+ one doc line, zero new tool-schema cost. Textbook STRAP —
"96 ops → 10 tools" in the literature.

**Breaks down in three ways:**
1. **Docstring bloat.** `universe` docs ~15 actions with per-action arg
   semantics. Each action linearly inflates schema tokens for *every*
   caller. Only compounding cost in the design.
2. **Dual-semantic params.** `path` means different things per action;
   `universe_id` sometimes required, sometimes ignored. Chatbots
   mis-pick action↔arg pairings.
3. **Action count doesn't multiply across tools.** 6 tools × ~15
   actions ≈ 90 ops, but adding a 7th *category* (say `market`) is a
   whole schema block, not an incremental line.

We're at the six-tool-pattern sweet spot. Growth past here stops being
free.

---

## §3 — Research sweep

Five patterns in order of ecosystem weight:

1. **STRAP / six-tool pattern** (almatuck; mcpbundles). What we do.
   Validated to ~15 tools. ~80% context savings vs one-tool-per-op.
2. **Progressive discovery** (klavis). Categories first, drill in for
   specific schemas. "Scales to any number of tools." Cost: extra hop.
3. **TinyAssets / compound tools** (klavis). One tool per user-goal.
   Complement, not substitute.
4. **Semantic / tool RAG** (apxml; klavis). Query → embedding → tool
   subset. Embedding misses are real.
5. **Code execution with MCP** (Anthropic). Tools as filesystem;
   agent writes code. **98.7% savings** at limit. Sandboxing cost.

**MCP resources + prompts** (spec primitives) are complementary:
read-only info → `resources://` (no tool-schema cost); tools reserved
for side-effects. Claude.ai's "On demand" mode is progressive discovery
at the *connector* layer — doesn't help scale *within* one connector,
which is what we control.

---

## §4 — Candidate architectures

- **A. Single mega-dispatcher.** One `workflow(category, action, args)`
  tool. Min schema cost. Kills per-tool name discoverability; the chatbot
  picks among `universe / goals / wiki / ...` by *name* before action —
  collapsing that axis is a UX regression.
- **B. Tiered routing.** 6 tools → ~4 super-tools (`state`, `design`,
  `run`, `knowledge`). Same docstring bloat at 2× per tool.
- **C. Resources + prompts for read-only.** Move `wiki:read`,
  `wiki:search/list`, `get_status`, `universe:inspect/read_output`,
  `goals:list`, `gates:leaderboard` to `resource://` URIs. Tools keep
  only side-effecting actions. Spec-aligned; Claude caches resource
  listings instead of re-billing tool schemas per turn.
- **D. Progressive discovery inside a super-tool.** `workflow_catalog()`
  → `workflow_action_docs(category)` → `workflow_invoke(category,
  action, args)`. Best asymptotic scaling; 3 hops for cold actions.
- **E. Code execution (Anthropic pattern).** MCP surface as a
  Python module tree the agent imports. 98.7% token savings at the
  limit. Sandboxing + multi-tenant auth scoping + debuggability are
  real costs; Rev-2 destination, not Rev-1.
- **F. Session-aware tool subsets.** Use MCP
  `notifications/tools/list_changed` to hot-swap the tool list per
  user/context. Underexplored; adjacent to Claude.ai's auto/on-demand
  mode but server-driven.

---

## §5 — Recommendation

**Near-term: C + STRAP-docstring diet.** The growth vector hurting us
first is *docstring bloat on `universe` + `wiki`*, not adding a 7th
tool — fix primary cost before restructuring. MCP resources are a
spec-native lever we haven't used; read operations on wiki/status/
inspect are natural resource URIs. Preserves action-invocation UX
the chatbot relies on; user-scoping via URI templates
(`resource://wiki/{user_id}/...`) satisfies multi-tenant-by-design.

**What breaks in existing chatbot flows:**
- `wiki(action="read", ...)` → fetch `resource://wiki/<slug>`.
  Claude.ai handles resource fetch natively; chatbot-side change is
  zero on the read side.
- Prompt language "use the wiki tool to look up X" → "fetch the wiki
  resource." Scope: `control_station` prompt + persona onboarding
  memories. Small, localized.
- Writes (`action="write|patch"`) **stay on the tool**. The split is
  read → resource, write → tool. Side-effect discoverability preserved.

**Medium-term:** Adopt D (progressive discovery) when tool count
crosses ~10 OR summed actions-across-tools crosses ~100 OR Claude.ai
surfaces a "too many connectors" prompt in the wild.

**Long-term:** Keep E on the radar. Revisit when node-execution API is
stable enough to expose as a sandboxed import surface.

---

## §6 — Prototype scope

Smallest viable reshape proving C + parameter-doc discipline:

1. **Pick one tool for the spike — `wiki`.** Highest read-to-write
   ratio. Resource-migration upside is clearest.
2. **Add MCP resources** for `wiki:read`, `wiki:search`, `wiki:list`.
   Tool keeps `write / patch / lint / delete`.
3. **Measure schema-token delta.** Count tokens in registered
   tool-schema JSON before + after. Target: ≥30% reduction on
   `wiki`'s share of the surface.
4. **Run one user-sim mission end-to-end.** Confirm chatbot adapts
   to resource-fetch for reads with zero prompt changes, or
   document what prompt updates are needed.
5. **Tighten `universe` + `goals` docstrings** — strip per-action
   arg redundancy; move long examples to `resources://help/...`.
   This is free and standalone, no protocol changes.

If the spike proves the pattern, the follow-up is mechanical:
migrate `get_status`, `universe:inspect/read_output`,
`goals:list/inspect`, `gates:leaderboard` to resources in one
dev task. Cost estimate: half-day per tool for migration + tests.

**Do not, in the prototype:** restructure tool names, merge tools,
add dispatcher layers, or touch the action-parameter schemas.
Resource migration + docstring diet is the whole spike. Anything
else is premature.

---

## Sources

- [MCP Bundles — The Six-Tool Pattern](https://www.mcpbundles.com/blog/mcp-tool-design-pattern)
- [Alma Tuck — STRAP: 96 tools to 10](https://almatuck.com/articles/reduced-mcp-tools-96-to-10-strap-pattern)
- [Klavis — Less is More: 4 MCP design patterns](https://www.klavis.ai/blog/less-is-more-mcp-design-patterns-for-ai-agents)
- [Anthropic Engineering — Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)
- [apxml — How to scale MCP to 100+ tools](https://apxml.com/posts/scaling-mcp-with-tool-rag)
- [Claude Help Center — Use connectors to extend Claude's capabilities](https://support.claude.com/en/articles/11176164-use-connectors-to-extend-claude-s-capabilities)
