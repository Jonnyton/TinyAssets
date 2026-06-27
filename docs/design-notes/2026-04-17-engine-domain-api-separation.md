---
status: active
status_detail: Principle landed in PLAN.md; A.1 fantasy_daemon unpack arc multi-week pending (per docs/design-notes/2026-04-26-fantasy-daemon-unpack-arc.md)
---

# Engine/Domain API Separation — ROI-First Proposal

**Date:** 2026-04-17
**Author:** navigator
**Status:** Proposal — awaits lead + host approval before exec plan.
**Relates to:** STATUS.md #11, PLAN.md §"Engine And Domains", PLAN.md §"API And MCP Interface".

---

## 1. TL;DR

The task as originally framed ("split engine routes from domain routes in `fantasy_author/api.py`") is worth roughly half what it sounds like. Two interfaces, two answers.

- **REST (`fantasy_author/api.py`, ~51 routes):** do **not** extract engine routes into `tinyassets/api/core.py`. The exec-plan cost is high and the ROI is low — REST is a dashboard / webhook adapter, not the primary interface. Instead, finish the shim: explicit re-exports, `__all__`, drop the wildcard, resolve the 7 cluster-2b failures. **~1 dev-day.**
- **MCP (`tinyassets/universe_server.py`, 5 coarse-grained tools, ~25 actions on `universe`):** **yes** extract. This is where engine/domain discipline earns its keep — multi-domain futures (fantasy / science / archaeology / corporate per memory-scope 2026-04-15) need a clean shared tool surface with domain-specific tools bolted on via `FastMCP.mount()`. **~3–5 dev-days, landed in 2 phases.**

The ROI gap is large enough that treating them as one task is the wrong frame. This note proposes scoping #11 as two separable exec plans and recommends dropping the REST one.

---

## 2. Why REST is not worth splitting right now

### 2.1 The shim is the symptom, not the disease

`tinyassets/api/__init__.py` is a 93-line bridge that does `from fantasy_author.api import *` plus three explicit private imports (`_extract_username`, `_load_provider_keys`, `_slugify`) for tests. `create_app(registry)` currently returns `fantasy_author.api.app` unchanged. This is the wildcard shim noted in PLAN.md as Phase 5.2 scaffolding.

The 7 test failures in cluster 2b trace to the wildcard not re-exporting what tests need. The fix does not require route-moving — it requires finishing the explicit re-export pass.

### 2.2 REST is not the primary interface

Per navigator project memory (`project_mcp_primary_interface`) and PLAN.md §"API And MCP Interface": MCP is the live public interface. REST powers:

1. The desktop dashboard (one caller).
2. Webhook integrations (external, low-volume).
3. Occasional tooling and tests.

An engine/domain split on REST imposes migration cost on callers (dashboard + webhooks + tests) for a surface whose growth trajectory is flat or declining.

### 2.3 The route inventory already proves the point

Of 51 routes in `fantasy_author/api.py`, roughly 45 are engine-generic (universe CRUD, notes, canon ingestion, daemon control, paid-market primitives, ledger, webhooks) and 6 are fantasy-specific (`/overview`, `/facts`, `/characters`, `/promises`, `/output`, `/output/{path}`). That's the shape of a module that was always supposed to be engine-owned but got built in the domain package because fantasy was the only domain. Renaming the file to `tinyassets/api/core.py` and having `fantasy_author` register 6 routes would be architecturally correct — but the callers don't care where the 45 routes live, and the dashboard already hardcodes paths.

### 2.4 What to do instead — the REST "cleanup" track

Minimal work to resolve the stated problem (7 test failures + design clarity):

1. Drop the wildcard. Enumerate every public name `tests/` imports from `workflow.api` and explicitly re-export.
2. Add `__all__` to both `tinyassets/api/__init__.py` and `fantasy_author/api.py`.
3. Resolve cluster-2b test failures by fixing re-exports, not by moving code.
4. Update PLAN.md §"API And MCP Interface" to note that REST engine/domain split is deferred until REST grows a second domain's worth of routes.

Effort: ~1 dev-day. Changes confined to `tinyassets/api/__init__.py` and a test sweep.

**Future trigger to revisit:** second non-fantasy domain that needs REST routes. Until then the split is architectural purism, not user-facing ROI.

---

## 3. Why MCP split is worth doing — the real #11

### 3.1 MCP is the primary surface, and it has real multi-domain pressure

`tinyassets/universe_server.py` is 9784 lines. It exposes 5 coarse-grained `@mcp.tool` entry points: `universe`, `extensions`, `goals`, `gates`, `wiki`. Each dispatches internally to `_action_*` handlers (the `universe` tool alone has 25 action branches).

This is the surface users reach through Claude Desktop + the tinyassets-universe-server plugin. Per `project_memory_scope_mental_model`, the platform is moving toward multi-domain (fantasy / science / archaeology / corporate) with scope isolation per universe. Each domain eventually needs its own *domain-specific* actions without polluting the shared tool surface.

### 3.2 Fantasy-specific leakage is real but bounded

Searching the 9784-line file for fantasy vocabulary (`fantasy|fiction|scene|chapter|book|novel|author|story|character|plot|premise|canon`) finds 29 case-insensitive matches. Most are in docstrings and instruction text, not dispatch logic. But **two dispatch cases are structurally domain-leaky:**

- **`universe` action `query_world`:** `query_type ∈ {facts, characters, promises, timeline}`. These are narrative-KG concepts. A scientific-research domain doesn't have "promises"; a recipe-tracker doesn't have "characters". The action shape forces fantasy semantics into the engine-generic tool.
- **`universe` action `read_premise` / `set_premise` / `add_canon` / `list_canon` / `read_canon`:** "premise" and "canon" are *soft-generic* (any domain has a starting intent and reference material) but their current implementations assume PROGRAM.md + `canon/` directory layout from fantasy.

The other 20 actions on `universe` are genuinely engine-generic (`list`, `inspect`, `read_output`, `get_activity`, `get_ledger`, `control_daemon`, `create_universe`, `switch_universe`, `queue_*`, `subscribe_goal`, paid-market ops, etc.).

### 3.3 Engine and domains need separate MCP servers, composed

FastMCP 2.0+ supports `mcp.mount(child_server)` for server composition — the primary MCP plugin pattern in 2025 ([FastMCP advanced patterns](https://deepwiki.com/jlowin/fastmcp/13-advanced-patterns-and-best-practices), [multi-domain local-server architecture](https://medium.com/@sbayer2/discover-the-elegant-architectural-pattern-that-emerges-from-fastmcp-2-0s-b6e7538ca239)). Mounted servers keep their own tool registries; the parent aggregates and namespaces them.

The target shape:

```
workflow.universe_server:mcp           # engine, 5 tools:
    universe                           #   engine-only actions (20 of 25)
    extensions
    goals
    gates
    wiki

fantasy_author.mcp:mcp                 # domain, 1 tool (mounted):
    fantasy                            #   query_world, premise ops, canon ops
```

Or alternatively, keep a single `universe` tool and have domains contribute actions via a registry — but `mcp.mount()` is the idiomatic FastMCP pattern and gives domains their own namespace without lowering the tool count through the 10-tool discoverability ceiling we already respect.

Either way, the dispatch map in `universe()` stops having hardcoded branches for `query_world | read_premise | set_premise | add_canon`. Those move to the domain's mounted server or to a domain-dispatcher action.

### 3.4 What gets extracted to engine-side

In the target architecture `tinyassets/universe_server.py` keeps:

- Tool `universe` — 20 engine-generic actions.
- Tool `extensions` — branch/graph authoring (engine).
- Tool `goals` — community goals (engine — confirmed generic per scoping pass).
- Tool `gates` — outcome gates (engine).
- Tool `wiki` — knowledge base (engine — no fantasy vocabulary in action set).

What moves to `fantasy_author/mcp.py` (or `domains/fantasy_author/mcp.py` after rename):

- Tool `fantasy` (or `fantasy_story` to be explicit) with actions: `query_world`, `read_premise`, `set_premise`, `add_canon`, `list_canon`, `read_canon`, `add_canon_from_path`. Plus the 6 REST-only fantasy routes if we want REST/MCP parity.

The engine stays at 5 tools; the domain contributes 1 mounted tool. If a second domain is added later (science papers, recipes), it contributes its own mounted tool (`science`, `recipes`). The user's "allow list" grows by one tool per domain, not per action.

### 3.5 Domain discovery and registration

`tinyassets/registry.py` already has a minimal `DomainRegistry.register(domain)` lookup. `tinyassets/domain_registry.py` is a different thing (engine-side opaque node callable store for the graph compiler — poorly named; worth renaming to `opaque_node_registry.py` but out of scope here).

What's missing: a `Domain.mcp_tools() -> FastMCP | None` protocol method. Domains that return a FastMCP instance get mounted at startup by the universe-server entry point. Domains that return `None` are REST-only or compute-only.

Proposal:

```python
# tinyassets/protocols.py — Domain Protocol extension
class Domain(Protocol):
    config: dict
    def mcp_tools(self) -> FastMCP | None: ...
    def api_routes(self) -> APIRouter | None: ...  # parallel for future REST
```

`fantasy_author/__init__.py` registers its FastMCP instance. `universe_server.main()` iterates registered domains, calls `mcp.mount()` for each.

---

## 4. Coordination with adjacent work

### 4.1 Author→Daemon rename (task #3) sequences first

Lead has confirmed. `fantasy_author/` → `fantasy_daemon/` is mechanical; running it after the MCP split would churn imports twice. The rename exec plan (`docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md`) lands Phase 0 (compat flag) and Phases 1+ (module moves) before #11 begins.

### 4.2 Memory-scope Stage 2b / 2c dependency

Minor. `tinyassets/author_server.py` (REST-side Stage 2b touchpoint) and `universe_server.py` share no module globals with `fantasy_author/api.py` beyond what's already declared. MCP split touches `universe_server.py` directly, which memory-scope 2b does not. Clean.

### 4.3 Dual-NodeScope dedup (`node_scope.py` tuple vs `scoping.py` list)

Independent. Post-2c work, navigator-tracked separately in `project_node_scope_dedup_post_2c`.

### 4.4 `add_canon_from_path` sensitivity metadata (STATUS.md concern)

Resolves naturally if `add_canon_from_path` moves to the mounted `fantasy` tool — the MCP "exclude from always-allow" question becomes a per-domain-tool concern rather than a per-action concern. Research still needed on whether MCP tool annotations support per-tool sensitivity tags; to be investigated separately.

---

## 5. Proposed exec plan shape (MCP split only)

Not a full exec plan — a sketch for the host/lead to approve before the navigator (or dev) writes the real one under `docs/exec-plans/active/`.

**Phase M0 — Protocol + scaffolding (0.5 dev-day)**
- Add `Domain.mcp_tools()` to `tinyassets/protocols.py`.
- Stub `fantasy_author/mcp.py` with empty `FastMCP("fantasy")`.
- `universe_server.main()` mounts registered domain MCPs. No behavior change.

**Phase M1 — Move 7 fantasy actions (1.5 dev-days)**
- Move `query_world`, `read_premise`, `set_premise`, `add_canon`, `add_canon_from_path`, `list_canon`, `read_canon` action handlers from `universe_server.py` to `fantasy_author/mcp.py` as a `fantasy` tool with an action dispatch of its own.
- Remove these action keys from `universe()` dispatch map.
- Update MCP client-facing documentation.
- Update activity/ledger wrapping so domain-mounted actions still get logged (shared helper, engine-owned).
- Full test sweep; update any test that called these as `universe` actions.

**Phase M2 — Prove multi-domain by adding a stub second domain (1 dev-day, optional validation)**
- Add `domains/hello_domain/` with one trivial action (e.g. `hello.echo`).
- Register via `DomainRegistry`; confirm it mounts, appears in MCP tool list, does not collide with `fantasy`.
- Delete after validation OR keep as an integration test fixture.

**Phase M3 — Close the loop (0.5 dev-day)**
- Update PLAN.md §"Engine And Domains" with the mount-based pattern.
- Update PLAN.md §"API And MCP Interface" noting the REST/MCP asymmetry decision.
- Navigator memory updated.

**Total: 3–4 dev-days, 3 landings.**

---

## 6. What navigator wants from lead / host

1. **Confirm the split framing.** REST cleanup = ~1 dev-day, do it now. MCP split = 3–4 dev-days, sequence after rename. Are both authorized?
2. **Confirm mount vs dispatcher-registry.** `mcp.mount()` is the FastMCP-native path and gives each domain its own tool namespace. Alternative is keeping a single `universe` tool with a dispatcher that consults the `DomainRegistry`. Mount is cleaner and closer to 2025 FastMCP idiom. Navigator recommends mount; flag if you disagree.
3. **Confirm action-naming.** When `query_world` moves to the `fantasy` tool, does it keep the name or become something more narrative-explicit like `query_story_world` / `narrative_query`? User-facing tool name matters for discoverability. Navigator's lean: keep `query_world` inside the `fantasy` tool — the tool name already namespaces it.
4. **Phase M2 go/no-go.** Adding a throwaway `hello_domain` for validation is the cheapest way to prove the engine is actually domain-agnostic. Cost is one dev-day. Worth it, or premature?

---

## 7. Open questions / research gaps

- **Webhook parity:** some webhook actions hit fantasy-specific endpoints. If MCP split moves fantasy actions to a domain tool but REST keeps them at the engine layer, the two surfaces diverge. Accept the asymmetry, or split both? Navigator lean: accept — REST is deprecating, MCP is primary.
- **Tool annotation migration:** `ToolAnnotations(readOnlyHint=…)` currently set at the `universe` level. Moving actions to a separate tool means re-declaring annotations. Low-effort but audit needed.
- **Fantasy REST routes (6):** if they stay in `fantasy_author/api.py` while the other 45 engine routes stay in the same file, the file never gets cleanly split. Acceptable as long as the wildcard shim is closed. Revisit only when a second domain needs REST.

---

## 8. References

- Codebase: `tinyassets/universe_server.py:1060-1217` (universe tool dispatch), `tinyassets/api/__init__.py` (shim), `tinyassets/registry.py` (minimal DomainRegistry), `fantasy_author/api.py` (current 51-route surface), `tinyassets/mcp_server.py` (separate small single-universe file-interface MCP, not the same thing as universe_server).
- Prior notes: `docs/design-notes/2026-04-15-memory-scope-tiered.md` (multi-domain scope), `docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md` (sequencing dependency).
- External: [FastMCP advanced patterns — mount()](https://deepwiki.com/jlowin/fastmcp/13-advanced-patterns-and-best-practices), [multi-domain local server architecture with FastMCP 2.0](https://medium.com/@sbayer2/discover-the-elegant-architectural-pattern-that-emerges-from-fastmcp-2-0s-b6e7538ca239), [Ragie — context-aware tool design](https://www.ragie.ai/blog/making-mcp-tool-use-feel-natural-with-context-aware-tools).
