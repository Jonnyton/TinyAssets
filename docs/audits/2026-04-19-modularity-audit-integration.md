# Modularity Audit Integration

**Date:** 2026-04-19
**Author:** navigator
**Status:** Integration audit. Cross-references Codex's modularity audit against the full-platform rewrite.
**Relates to:**
- `docs/design-notes/2026-04-19-modularity-audit.md` (Codex's findings, 2026-04-19).
- `docs/design-notes/2026-04-18-full-platform-architecture.md` (rewrite design, §26/§27 gateway + §2/§17 schema).
- `docs/specs/2026-04-18-mcp-gateway-skeleton.md` (track C).
- `docs/specs/2026-04-18-daemon-host-tray-changes.md` (track D).
- `docs/specs/2026-04-18-full-platform-schema-sketch.md` (track A).
- `docs/design-notes/2026-04-19-minimum-viable-launch-narrowing.md` (MVP scope).

---

## §1. Key framing

Codex's audit surfaced three real modularity concerns in the **current legacy code** (`tinyassets/universe_server.py`, `tinyassets/discovery.py`, `tinyassets/daemon_server.py`). The rewrite replaces all three with distinct, greenfield artifacts.

**The integration question is: do we fix the legacy code now, or skip the legacy cleanup because the rewrite replaces it?**

Rewrite timeline per `2026-04-19-minimum-viable-launch-narrowing.md`: **~4.5 weeks (upper bound) to MVP**, host choosing between narrowed (~21–24d) or fuller (~27–32d) scope.

Live user traffic today: one host (Jonathan) + user-sim dogfooding via Claude.ai → cloudflared → legacy stack. No public launch load against the legacy mega-surfaces yet. That's the crucial constraint for the defer decision below.

---

## §2. Concern-by-concern cross-reference

### §2.1 `tinyassets/universe_server.py` mega-surface (~8.6k lines, 4 dispatch tables)

**Codex recommendation:** FastMCP `mount()` + capability-surface split (engine universe / extensions-branch / runs / judgments / goals+gates+wiki / domain-mounted fantasy actions).

**Already addressed by the rewrite — YES, fully.** The new MCP gateway in `docs/specs/2026-04-18-mcp-gateway-skeleton.md`:

- §3 specifies a **flat FastMCP mount** with capability-sharded tool registration.
- §3.1 tool table enumerates bounded surfaces: `discover_nodes`, `update_node`, `remix_node`, `converge_nodes`, `submit_request`, `claim_request`, `complete_request`, `add_canon_from_path`, `control_daemon`, plus design-note §23/§27/§28/§29/§30/§31 tools (per drift audit gap #4).
- §3.3 **prompts/\*** surface isolates behavioral directives from tool descriptions — exactly the "shape is architecture" principle Codex's PLAN.md cross-reference named.
- Design §16 formally splits engine (`TinyAssets/` repo) from content (`TinyAssets-catalog/` repo), the equivalent at a higher level of the "engine vs domain" split Codex identified.
- Track N (vibe-coding authoring surface, design §27) introduces `/node_authoring.*` as its own capability surface, not as actions bolted onto a mega-tool.

The legacy `universe` tool with 26-action dispatch + `_BRANCH_ACTIONS` / `_RUN_ACTIONS` / `_JUDGMENT_ACTIONS` dispatch tables is **obsoleted in one piece** by the new gateway, not migrated. Every concern Codex raised is structurally solved by not rebuilding the mega-surface.

**Needs new work?** No. The existing gateway spec #27 + design §26–§31 cover the modularity directive comprehensively. One minor improvement: spec #27 could cite Codex's FastMCP `mount()` research link directly, but that's editorial — it already follows the pattern.

**Legacy cleanup — interim splitting? Decision: NO.** Reasoning:

- Current legacy surface serves one host (Jonathan) + user-sim. No scale pain today.
- Track C rewrite is ~2 dev-days (per §10 table). Interim-splitting the legacy file for durability is similar effort (likely 1.5–2 dev-days for an honest capability split) and **produces code that ships for ~4 weeks then gets deleted.**
- The pure-bytes-thrown-away calculation: interim split = ~2d wasted. Interim not-split = existing state, no worse than today. **Skip legacy cleanup.**
- Task #15 (injection-hallucination text mitigations) does still need to land in the legacy `tinyassets/universe_server.py` because it's the live surface until cutover. That's bug-fix work, not modularity work. Still must happen.

**Exception:** if any unforeseen new feature must land in the legacy surface during the rewrite window (e.g. an urgent security fix), that's the moment to reconsider. Until then, hold.

### §2.2 `tinyassets/discovery.py` — source-tree scan, not a real plugin boundary

**Codex recommendation:** `importlib.metadata.entry_points()` group `workflow.domains`; current filesystem scan as dev-mode fallback only; keep rename-compat aliases out of discovery (they belong in import shims).

**Already addressed by the rewrite?** **Partially — the problem shifts category.** The rewrite's world looks different:

- Design §2 / spec #25: **Postgres is canonical.** Node + branch definitions are rows, not on-disk `domains/<name>/skill.py` files. There's no per-domain source-tree plugin to discover anymore.
- Design §16 + §27 tier-3 contribution model: platform code is MIT in `TinyAssets/` and content is CC0 YAML in `TinyAssets-catalog/`. No `domains/<name>/` directories served as Python packages at runtime.
- The existing `domains/fantasy_daemon/skill.py` + peer `skill.py` pattern is **legacy**. It existed because the legacy daemon ran one domain's graph locally. The rewrite separates content (Postgres) from engine (MIT Python) and makes "domain" a `domain_ids uuid[]` tag on nodes, not a package directory.

**So the Codex recommendation of entry-point discovery for `workflow.domains` is a legacy concern, not a rewrite concern — because the rewrite has no `workflow.domains` plugin contract.**

**Needs new work?** **Yes, small.** Two new things:

1. **Rewrite has no domain-plugin API equivalent documented.** Design note §2.7 introduces "branches as first-class composite workflows" and §27 vibe-coded nodes, but neither names a packaging/distribution mechanism for engine-side plugins (e.g., a third-party shipping a `connector` — §28 — or a `handoff` — §30). Those are the closest-analogs to "domains" in the new world, and they should use entry-points. **Recommended spec addition:** when the Connectors exec spec (task #68) and Handoffs exec spec (task #69) land, they should declare **`workflow.connectors` and `workflow.handoffs` entry-point groups** as the distribution mechanism. Filesystem scan as dev-mode fallback only.
2. **Legacy `tinyassets/discovery.py` stays as-is** until the legacy stack is decommissioned. Current rename-compat injection at `:66` is a live-correctness fix, not a modularity refactor. Don't touch it.

**Legacy cleanup — interim entry-point migration? Decision: NO.** Reasoning:

- Legacy `discovery.py` has one real consumer today (the live legacy daemon). Rewriting discovery to use entry-points requires packaging `domains/fantasy_daemon/` as an installed distribution, a non-trivial packaging change.
- Tier-3 of the rewrite does not consume legacy discovery; design §27 tier-3 contributions go through the new node-authoring flow to Postgres.
- Cost: ~1.5 dev-days entry-point refactor + packaging mirror update. Benefit: zero in 4 weeks. **Skip.**
- **Propagate the pattern to NEW specs instead:** entry-points become the canonical mechanism for §28 connectors and §30 handoffs. This is what Codex's recommendation enables for the right layer of abstraction (distribution-time plugin discovery for connectors) without touching the legacy that's about to be deleted.

### §2.3 `tinyassets/daemon_server.py` bounded-context mix (~3.2k lines)

**Codex recommendation:** split by storage context (accounts/auth, universes/branches/snapshots, requests/votes/runtime, notes/work-targets/priorities, goals/gates/leaderboards). Shared `_connect()` + migrations; narrow exported surfaces per context.

**Already addressed by the rewrite? YES, structurally.** Spec #25 schema does exactly what Codex recommends, at the Postgres-table level instead of the Python-module level:

- §1.2 `nodes` (universes/branches/snapshots analog).
- §1.3 `artifact_field_visibility` (privacy context).
- §1.4 `node_activity` (audit trail).
- §1.5 `host_pool` + §1.5b `capabilities` (runtime).
- §1.6 `request_inbox` + `ledger` (requests + settlements).
- §1.7–§1.9 `treasury_config` / materialized views / provider_plan_tiers.
- §2 RLS policies enforce bounded-context access boundaries structurally, not by helper-function convention.

The repository/service layering Codex identified as a debt in a monolithic Python file becomes **Postgres-enforced RLS + explicit RPCs per bounded context** in the rewrite. Strictly better — the seams are enforceable, not just documentary.

Additionally: accounts/auth move to Supabase Auth (not our code). Moderation (spec #36) is its own bounded context. Notes / work-targets / priorities: some become Postgres rows, some become host-local per §5 daemon-execution.

**Needs new work?** No. The rewrite's bounded contexts are already defined by schema + RLS + per-table RPCs.

**Legacy cleanup — interim daemon_server split? Decision: NO.** Reasoning:

- `daemon_server.py` serves the live legacy daemon. It's SQLite-backed + single-process-scoped by design. Any "bounded context" split would restructure a file that's scheduled for replacement with "Postgres + no single file."
- 3.2k lines is a maintainability burden, but it's maintained by one person (Codex) for ~4 more weeks. Interim cleanup cost (~2 dev-days for a clean split) > benefit (zero in 4 weeks).
- **Skip.**

**Post-launch hygiene note:** once the rewrite replaces the legacy, `tinyassets/daemon_server.py` becomes dead code. Launch + 2 weeks stabilization window → schedule the legacy-file deletion as a routine cleanup task, not a modularity refactor. Task #17 Rename Phase 2 already handles legacy-directory / brand residue; §§`tinyassets/daemon_server.py` etc. get deleted in that sweep's successor.

---

## §3. Impact on §70 MVP narrowing

**Validated.** Every modularity concern Codex raised is either:

- (a) Structurally addressed by the rewrite (§2.1 mega-surface via gateway, §2.3 bounded contexts via schema+RLS), OR
- (b) Shifted category — the legacy concern becomes moot, and the rewrite's analog (§2.2 entry-points for connectors/handoffs) gets picked up in the new specs rather than a separate legacy refactor.

**No new dev-days added to the MVP narrowing.** The ~21–24d w/2 devs recommended-cut holds. The connectors + handoffs exec specs (tasks #68, #69) will absorb the entry-points recommendation when they're drafted — that's ≤0.1 dev-day each for naming the entry-point group; no schema or architectural change.

**Impact on §10 Track D tray spec:** already correct. Spec #30 §1.1 says "Deprecate the local MCP as primary surface; keep as debugging tool" — this is Codex's mega-surface problem deferred by *retirement*, not splitting.

**Impact on §8 launch-readiness gates:** unchanged. None of the three Codex concerns is a launch-readiness gate; they're technical-debt concerns that become moot.

---

## §4. Post-launch legacy-cleanup posture

The three audited files have expected lifetimes tied to the rewrite cutover:

| File | Lifetime | Cutover trigger | Cleanup posture |
|---|---|---|---|
| `tinyassets/universe_server.py` | Live until MCP gateway (canonical `tinyassets.io/mcp`, Worker-routed to tunnel origin `mcp.tinyassets.io`) is stable + Claude.ai connector-catalog listing live | ~4.5 weeks (MVP) | Post-cutover: delete file + remove directory structure per Rename Phase 2 (task #17) |
| `tinyassets/discovery.py` | Live until domain-plugin discovery is moot (all node/branch/domain metadata moved to Postgres) | ~4.5 weeks (MVP) | Post-cutover: delete file; pattern re-appears in new Connectors + Handoffs specs via `workflow.connectors` + `workflow.handoffs` entry-point groups |
| `tinyassets/daemon_server.py` | Live until Supabase-backed control plane is stable | ~4.5 weeks (MVP) | Post-cutover: delete file; bounded contexts are now Postgres tables + RLS, not Python modules |

**Two-week stabilization window post-MVP recommended** before deletion, to catch any unforeseen fallback-dependency on the legacy. After that, a single cleanup commit removes all three legacy files and their tests.

This cleanup is ~0.25 dev-day of actual code deletion + git-mv work, not a refactoring effort. Track it as part of Rename Phase 2 or a successor task.

---

## §5. Propagation to new specs

Codex's recommendations, correctly generalized, become inputs to three in-flight spec drafts:

### §5.1 Task #68 Connectors exec spec

When dev drafts the connectors spec (§28), incorporate:

- **Entry-point discovery.** Define `workflow.connectors` entry-point group per PyPA spec. Third-party connector modules advertise themselves via `pyproject.toml` `[project.entry-points."workflow.connectors"]`. Filesystem scan of `TinyAssets/connectors/*/` is dev-mode fallback only. Cite `https://packaging.python.org/en/latest/specifications/entry-points/`.
- **Narrow exported surface per connector.** Each connector module exports exactly one `ConnectorProtocol`-implementing class. No side effects on import. Follows Codex's "bounded context with narrow exported surface" principle.

### §5.2 Task #69 Handoffs exec spec

Same pattern. Define `workflow.handoffs` entry-point group. Third-party handoff modules (e.g., venue-specific journal submission APIs, FDA submission processors from §30) advertise themselves via entry-points. Same narrow-surface discipline.

### §5.3 Task #67 Track N (vibe-coding authoring sandbox) exec spec

Less applicable — vibe-coded nodes are Postgres rows with the `concept` jsonb holding the code; they are not Python modules on disk and are not a plugin-discovery problem. But the spec should explicitly note: *vibe-coded node code runs in the Edge-Function sandbox; there is no entry-point or module-level plugin registration for user-authored nodes.* Clarifies the boundary.

---

## §6. Summary table

| Concern | Already addressed? | Needs new work? | Legacy cleanup interim? | One-line rationale |
|---|---|---|---|---|
| **§2.1 universe_server mega-surface** | YES — gateway spec #27 §3 capability-sharded mount + design §§26–31 bounded tool families | NO | **NO — defer to post-cutover deletion** | Rewrite replaces it whole; ~2d interim split produces code thrown away in 4 weeks. Live-traffic pain is minimal (1 host + user-sim). |
| **§2.2 discovery.py not real plugin boundary** | PARTIALLY — rewrite has no `domains/<>` package plugin contract, concern shifts category | YES — new Connectors (task #68) + Handoffs (task #69) specs adopt `workflow.connectors` + `workflow.handoffs` entry-point groups | **NO — defer, propagate to new specs** | Legacy discovery has one consumer (legacy daemon) scheduled for deletion. Entry-points pattern lives on in the right layer (distribution-time plugins for connectors/handoffs). |
| **§2.3 daemon_server.py bounded-context mix** | YES — schema #25 bounded-context tables + RLS enforces seams structurally (Postgres-enforced, not helper-convention) | NO | **NO — defer to post-cutover deletion** | Rewrite's bounded contexts are Postgres tables + RLS + per-table RPCs, strictly stronger than a Python-module split. Interim ~2d cleanup = wasted. |

**MVP narrowing validated.** No dev-days added. Navigator recommends: **hold legacy-cleanup, propagate entry-points pattern to new connector + handoff specs, delete legacy files 2 weeks post-MVP stabilization.**
