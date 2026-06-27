---
status: active
---

# Memory Scope — Tiered Multi-Domain Rethink

**Status:** Planner rethink of Stage 2, host-refined 2026-04-15. Supersedes the Stage-2 proposal in `2026-04-14-memory-scope-defense-in-depth.md`. Stage 1 (`be84f7b` + `530a646`) stands as shipped. **Promotion-ready** pending review (all §9 Qs answered).
**Context:** Host reframe 2026-04-15 — scope is tiered, not single-axis; multi-domain (fantasy / science papers / archaeology / alt-archaeology / corporate private docs) is near-term, not speculative; cross-universe bleed is the load-bearing failure mode. Host's 2026-04-15 refinement: **universe membership is about knowledge-source purity, not access breadth** — see §2.5.

## Why the 2026-04-14 note is too narrow

The prior note framed Stage 2 as "tag every KG/vector row with `universe_id`." That's true — and insufficient. It treated universe as the only visibility axis and treated the problem as defense-in-depth against singleton bleed.

The real problem is that **every layer of the execution stack can narrow visibility**: a node can be configured with full-canon access or a narrow slice; a branch can expose subset of its goal's canon to downstream nodes; a goal can be private; a user's memory belongs to that user; a universe can be private to one actor or one company.

Row-tagging `universe_id` is necessary but insufficient. The engine needs a **scope composition layer** that the storage layer enforces as filter predicates — at every tier, not just universe.

## What changes vs the 2026-04-14 note

| Dimension | 2026-04-14 | 2026-04-15 rethink |
|---|---|---|
| Scope axis count | 1 (universe_id) | 5 tiers (node / branch / goal / user / universe) |
| Primary failure mode | Singleton bleed | Cross-universe bleed + unauthorized scope broadening |
| Mental model | "Tag rows with universe_id" | "Every tier carries a scope filter; storage enforces composition" |
| Node-level access modes | Not considered | First-class: `full_canon` vs `narrow_slice` declared per node |
| Universe privacy | Not considered | First-class: a universe marks itself `private`, access enforced at universe tier before query layer runs |
| `MemoryScope` type shape | universe/branch/author/user/session | **node_scope / branch_scope / goal_scope / user_scope / universe** — see §3 |
| Migration scope | ALTER TABLE add universe_id | ALTER TABLE add scope columns + scope composition interface + declarative node-scope config |
| Corporate use case | Out of scope | First-class design constraint |
| Universe membership definition | (not addressed) | **Source-purity, not access-breadth.** In-universe = draws only from universe canon. Out-of-universe = pulls from declared external sources. Breadth (full/narrow) is orthogonal. |
| Node-scope declaration site | (not addressed) | Separate manifest file per branch (host-chosen 2026-04-15) — `<branch>/node_scope.yaml`. |
| Actor identity | "user or daemon string" (loose) | User login only; daemons inherit (host-chosen 2026-04-15). |
| Stage 1 relation | Stage 2 = schema extension of Stage 1 | Stage 2 = **broader interface reshape**; Stage 1's post-query assertion remains and becomes one of N tier assertions |
| Flag name | `TINYASSETS_ROW_SCOPED_ARCHIVAL` | `TINYASSETS_TIERED_SCOPE` |

## 1. The five tiers

Each tier is a semi-independent filter; they compose multiplicatively at query time.

1. **Universe tier.** The tailored-canon container. Fantasy has invented canon; archaeology has real-world canon; alt-archaeology has a separate universe carrying alt-theories canon; corporate has Company A's private docs as the whole canon. Universes can be marked private; private universes reject all reads except from explicitly-authorized actors. **This tier is the strongest invariant — no query crosses it without explicit authorization.**

2. **User tier.** A user's memory belongs to that user. Within a shared universe, user A's private observations do not leak to user B. User-tier privacy is narrower than universe privacy (one universe can have many users; each user's slice is disjoint unless they share to a broader tier).

3. **Goal tier.** A goal is a shared multiplayer primitive (Phase 5). A goal can be public or private. A private goal constrains which branches (and which users) can read its canon extensions and claims.

4. **Branch tier.** A branch scopes work within a goal. Branch-tier scope controls which slice of goal/universe canon a branch sees — and, conversely, which slice of a branch's work other branches can see (relevant to #56 private-Branch visibility — this is the right home for that feature, not a column on `branch_definitions` alone).

5. **Node tier.** A node is the finest-grained scope. A node has two orthogonal attributes:
   - **Universe membership** (binary, in / out): is this node drawing *only* from the universe's canon, or does it pull from outside? See §2.5. In-universe is the common case; out-of-universe is the explicit exception.
   - **Canon breadth** (applies to in-universe nodes only): **full_canon** (everything the universe permits, subject to higher-tier constraints) or **narrow_slice** (specific facts, relationships, documents). Default `full_canon` for simplicity; narrow_slice is opt-in for nodes that benefit from reduced context (e.g. a tone-match node that only needs voice examples, not plot).

### Why these five and not six or ten

Session (in the current `MemoryScope`) collapses into node — a session is a node execution lifetime. Author (in the current `MemoryScope`) collapses into user — author is a user playing a specific role. Keeping the tier count to 5 keeps the ACL composition tractable; adding more tiers without a clear separate invariant multiplies the interaction matrix.

## 2. How the tiers surface as queryable filters

The storage layer must be able to answer: "for an actor X running node N in branch B of goal G in universe U, what rows are visible?"

Three filter-composition layers:

**Layer 1 — Universe gate (pre-query).** Before any query runs, the runtime checks universe privacy. If universe U is private and the actor is not authorized for U, the query never reaches storage. This is cheap and catches the catastrophic case (Company A daemon accidentally pointed at Company B universe). Implementation: thin authorization check at the router entry point; uses a `universe_acl` table listing `(universe_id, actor_id, permission)` tuples.

**Layer 2 — Scope WHERE composition (query-layer).** KG tables, vector tables, and notes get NOT NULL columns for `universe_id`, `goal_id`, `branch_id`, `user_id`, `node_id`. A row is visible if its scope is broader than or equal to the caller's scope. A row tagged `(universe=U, goal=None, branch=None, user=None, node=None)` is universe-public canon; any caller in universe U sees it. A row tagged `(universe=U, goal=G, branch=B, user=None, node=None)` is branch-scoped; only callers in branch B (of goal G, universe U) see it. The composition is a per-tier `IS NULL OR = caller.tier_id` conjunction — broader scopes subsume narrower ones.

**Layer 3 — Node-scope declaration (request-shape).** Each node declares its scope mode. `full_canon` nodes compose their query with the caller's branch/goal/user/universe context. `narrow_slice` nodes additionally pass a slice descriptor (entity-whitelist, relationship-type-whitelist, document-ID-whitelist) that intersects with the storage-layer filter. The node-tier "filter" isn't a column value — it's the shape of the query the node issues.

This means **not every tier is a column**. Universe/goal/branch/user are columns on rows (the data has that scope). Node is a query-shape attribute (the query has that scope). Mixing the two consistently is what the scope composition layer must do.

## 2.5. Universe membership is source-purity, not access-breadth

**Host clarification 2026-04-15:** whether a node is "in" a universe or "outside" it is not determined by how much of the universe's canon it can read. It's determined by what its *sources* are.

- A node is **in the universe** if every piece of knowledge it retrieves, cites, or reasons from comes from that universe's canon — even if its access is narrow (a single entity, three facts, one document).
- A node is **outside the universe** if it pulls from any source that isn't the universe's canon: another universe, system-wide knowledge, external APIs, web fetches, cross-universe joins. An outside source breaks the canon-purity contract by definition.
- **LLM base / training knowledge is ambient, not counted as an outside source.** The model's own weights are always present; the question is only what *retrieved* context is handed to it.

This is why membership is binary while breadth is graded. A narrow-slice node reading three facts from universe U is still a U-node — the alt-archaeology separation works because alt and mainstream are *separate universes*, not because they differ in how much canon nodes can access.

**Out-of-universe nodes must explicitly declare their external-knowledge sources.** This is an opt-in, not a default. Declared external sources: another `universe_id`, a named external API (`mcp_web_fetch`, `arxiv_api`, `court_docket`), a system-wide tool (`llm_meta_query`), or an explicit cross-universe join. Undeclared-outside-source reads are a bug the scope-composition layer must reject.

**Implication for corporate case:** a Company A node pulling from Company A docs is in-universe. A Company A node that summarizes Company A docs alongside public market data is OUT of universe-A and must declare `external_sources: ["market_data_api"]`. Company B cannot see in-universe nodes, regardless of ACL drift; out-of-universe nodes expose a clearer audit surface because their externality is declared.

## 3. Proposed `MemoryScope` redesign

Current (`tinyassets/memory/scoping.py`):

```python
@dataclass(frozen=True)
class MemoryScope:
    universe_id: str
    branch_id: str | None = None
    author_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
```

Proposed:

```python
@dataclass(frozen=True)
class MemoryScope:
    """The caller's position in the 5-tier scope hierarchy.

    universe_id is required. All other tiers are optional; None = "broader
    than this tier" (i.e., caller can see rows scoped to this tier or
    anything narrower the caller is authorized for).
    """
    universe_id: str              # REQUIRED. Strongest invariant.
    goal_id: str | None = None
    branch_id: str | None = None
    user_id: str | None = None
    node_scope: NodeScope | None = None   # see below


@dataclass(frozen=True)
class NodeScope:
    """A node's declared membership + breadth + external sources.

    universe_member: TRUE if the node draws ONLY from its caller's
    universe. FALSE if the node pulls from outside sources. Binary.

    breadth: applies only when universe_member=TRUE.
      FULL_CANON: node sees all rows visible at its (branch, goal, universe,
      user) position. Default.
      NARROW_SLICE: node sees only rows matching an explicit slice spec.
      Used by nodes that benefit from reduced context windows.

    external_sources: required when universe_member=FALSE. Enumerated list
    of declared outside-knowledge sources (other universes, external APIs,
    system-wide tools, cross-universe joins). Undeclared external reads
    are a bug the scope layer rejects.
    """
    universe_member: bool = True
    breadth: Literal["full_canon", "narrow_slice"] = "full_canon"
    slice_spec: SliceSpec | None = None   # required when breadth=narrow_slice
    external_sources: list[ExternalSource] | None = None  # required when universe_member=False


@dataclass(frozen=True)
class SliceSpec:
    entity_ids: list[str] | None = None
    relation_types: list[str] | None = None
    document_ids: list[str] | None = None
    # composed with AND when multiple fields set


@dataclass(frozen=True)
class ExternalSource:
    """A declared outside-knowledge source for an out-of-universe node."""
    kind: Literal["universe", "external_api", "system_tool", "cross_universe_join"]
    identifier: str   # e.g. another universe_id; or API name like "arxiv"
```

**Author/session deleted.** Author collapses into `user_id` (a user playing a role; roles tracked separately, not via scope). Session collapses into node execution; a node lifetime is the right session boundary.

**Orthogonal composition, not nested narrowing.** The 2026-04-14 `MemoryScope` used a nested `contains`/`narrow` model (universe contains branch contains user). That worked for a single-axis hierarchy. In the tiered multi-domain world, goals aren't strictly nested under universes (a goal in universe U is U-scoped, but two goals in U can be independent of each other) and users aren't strictly nested under anything. Treat each tier as an orthogonal filter: the composition is a conjunction of per-tier predicates, not a strict path-containment check.

## 4. Physical storage layer changes

### Schema (Stage 2)

**New table `universe_acl`:**
```sql
CREATE TABLE universe_acl (
    universe_id   TEXT NOT NULL,
    actor_id      TEXT NOT NULL,    -- user or daemon identity
    permission    TEXT NOT NULL,    -- 'read' | 'write' | 'admin'
    granted_at    REAL NOT NULL,
    granted_by    TEXT NOT NULL,
    PRIMARY KEY (universe_id, actor_id)
);
```
Public universes have no `universe_acl` rows (or a wildcard `actor_id='*'`). Private universes require explicit grant.

**Scope columns on archival tables.** KG tables (`entities`, `edges`, `facts`, `communities`) and LanceDB `prose_chunks` gain:
- `universe_id TEXT NOT NULL` (per 2026-04-14 note — keep this)
- `goal_id TEXT NULL` (NULL = universe-scoped canon)
- `branch_id TEXT NULL` (NULL = goal/universe-scoped)
- `user_id TEXT NULL` (NULL = non-user-private)

Indexes on `(universe_id, goal_id, branch_id)` for the common query path.

**Migration:** per-DB, infer `universe_id` from parent dir (per 2026-04-14); set other scope columns to NULL (= broadest scope); existing data becomes universe-scoped canon, visible to anyone in the universe. Zero semantic change for current fantasy-author usage; prepares for future narrower writes.

### Node-scope manifest (separate file, host-chosen 2026-04-15)

Node scope declarations live in a **separate manifest file per branch**, not inline in `graph_json` / `node_defs_json`. Rationale (host): "tagging all nodes in an area with the same universe is simple and clear to distinguish nodes in and outside of the universe."

Proposed location: `<branch-path>/node_scope.yaml` alongside the branch's other config, co-located with `branch_definition` files as Phase 7 migrates Branches to repo-file-as-canonical.

**Cross-reference:** the software-capabilities design (`2026-04-15-node-software-capabilities.md`) adds `requires:` and `capability_pattern:` to the same manifest. Same file; same reviewer surface. See that note for software-field specs.

Format:

```yaml
# Default for this branch unless overridden per-node.
default:
  universe_member: true
  breadth: full_canon

# Per-node overrides. Node id matches the node_def_id in graph_json.
nodes:
  tone_match:
    breadth: narrow_slice
    slice_spec:
      relation_types: [voice_example, dialogue_sample]

  market_summary:
    universe_member: false
    external_sources:
      - kind: external_api
        identifier: market_data_api
      - kind: system_tool
        identifier: llm_meta_query

  compare_universes:
    universe_member: false
    external_sources:
      - kind: cross_universe_join
        identifier: alt_archaeology_universe
```

The manifest is loaded at branch-registration time and cached. At node execution, the runtime composes `NodeScope` from `default` + per-node override + caller's tier position. A missing entry for a node = `default`; an explicit entry overrides. Manifest is validated on load (unknown fields reject; external_sources required when universe_member=false; slice_spec required when breadth=narrow_slice).

**Trap to avoid:** nodes without manifest entries silently inherit `default.universe_member=true`. That's the safe default (stays in-universe). The unsafe failure mode (accidentally becoming out-of-universe and pulling from elsewhere) requires an explicit manifest change — good.

### Write-site behavior

Every archival write site accepts a `MemoryScope` and sets the scope columns per the caller's position. A write from a branch-scoped caller tags the row with that branch_id; a write from a universe-wide canon-ingest tool tags only universe_id and leaves the rest NULL.

### Read-site behavior

Every archival read site composes the scope predicate:

```sql
WHERE universe_id = :caller_universe
  AND (goal_id IS NULL OR goal_id = :caller_goal)
  AND (branch_id IS NULL OR branch_id = :caller_branch)
  AND (user_id IS NULL OR user_id = :caller_user)
```

Plus Layer 3 (node slice) if `node_scope.mode == 'narrow_slice'`:

```sql
  AND (entity_id IN :slice.entity_ids OR :slice.entity_ids IS NULL)
  AND (relation_type IN :slice.relation_types OR :slice.relation_types IS NULL)
```

Post-query assertion from Stage 1 stays: any row leaking across a tier the caller wasn't authorized for → log loudly, drop the row. With all 5 tiers, this becomes `assert_scope_match(row, caller_scope)` for all tiers, not just universe.

### Private universes — enforcement path

1. Caller bound to universe U.
2. Router entry point calls `UniverseACL.check(universe_id=U, actor_id=caller, permission='read')`.
3. If universe U has ACL rows and caller not listed → raise `UniverseAccessDenied` before any DB query runs.
4. If no ACL rows on U → public universe, proceed.

This is Layer 1 and is the load-bearing guard for the corporate-docs case. It must run before any path-based lookup too — even if the caller somehow has the path, the ACL check rejects.

## 5. Does this collapse back to row-tagging + query abstraction?

Yes, largely. Once you adopt the tiered filter composition:
- The physical change is still "columns on rows + query WHERE clauses" (same shape as 2026-04-14's proposal, just 4 columns instead of 1).
- The interface change is larger: `MemoryScope` gains tier-aware composition, `NodeScope` becomes a first-class type, write/read paths all take scope and compose it.
- The `universe_acl` table is the only genuinely new concept — it lives above the row-tag layer and enforces authorization, which row-tags alone cannot express.

The answer to host's Q ("is this a tiered-ACL problem, not a row-tag problem?"): **both**. The data-visibility problem is row-tag-shaped at every tier; the authorization problem (who can even touch universe U) is ACL-shaped and sits above the data layer.

## 6. Stage 2 shape — concrete proposal

Ship behind `TINYASSETS_TIERED_SCOPE` flag. Three sub-stages:

**2a — Schema + ACL foundation.** Add the 4 scope columns to archival tables. Add `universe_acl` table. Migrate existing data (all NULL except `universe_id`). Update Stage 1's post-query assertion to check all 5 tiers. No behavior change for callers that still pass only `universe_id`. Backward-compatible; flag-gated.

**2b — `MemoryScope` redesign + write-site threading.** New `MemoryScope` shape (5 tiers, orthogonal composition). `NodeScope` type and `node_scope_mode` declaration site in node configs. Every archival write site threads the caller's full `MemoryScope`. Read sites compose the predicate. No new enforcement yet — rows still return at broadest scope by default.

**2c — Enforcement on.** Flip `TINYASSETS_TIERED_SCOPE` default. Private universes actually reject cross-universe reads. Node narrow-slice actually narrows retrieval. Stage 1 assertion becomes hard-fail instead of warn-and-drop.

Each sub-stage is independently shippable and testable. 2a is mostly schema work; 2b is API work; 2c is a one-line flag flip after sustained observation on a clean universe and a stress universe.

## 7. Multi-domain design checks

Each hypothetical domain the host named:

- **Fantasy authoring (current).** Universe = the invented world. Public universe. Scope columns on existing data default to NULL (universe-scoped canon). Zero user-facing change post-2a migration.
- **Science papers.** Universe = one subfield's canon (real-world). Public by default. Users scope their own drafts to `user_id` so co-author A doesn't see co-author B's pre-submission notes. Node scope: `narrow_slice` for citation-tracking nodes that only need specific papers; `full_canon` for the writing node.
- **Archaeology (real-world).** Universe = accepted archaeological canon. Public. Read-only for most users; `universe_acl` has `write` only for curators.
- **Alt-archaeology.** A SEPARATE universe from mainstream archaeology. Public read, curated write. Cross-universe bleed (alt → mainstream or vice-versa) is the core failure mode this design prevents. Layer 1 (universe gate) catches the accidental-read case; Layer 2 (row filter) catches the subtle "one daemon somehow bound to both" case.
- **Corporate private docs.** Universe = Company A's docs. **Private universe**, `universe_acl` restricts to Company A's user IDs. Layer 1 rejects Company B daemons cold. Node scope: most corporate workflows need `full_canon` (summarize everything relevant) but narrow_slice available for targeted analytics. The market-summary node that cites both Company A docs and public market data is explicitly **out-of-universe** and must declare `external_sources: ["market_data_api"]` in the branch's node-scope manifest — the audit trail becomes crisp.

All five fit without scope-axis additions. If a future domain needs a sixth tier, the orthogonal-composition shape absorbs it without reshaping the other four.

**Source-purity test per domain:** for each node in each domain, the manifest must answer "is this node in-universe or out?" before any retrieval runs. In-universe is simpler, the default, and the safer failure mode (a missed manifest entry keeps the node in-universe; no cross-universe bleed). Out-of-universe is explicit opt-in with declared sources; this is where the audit logs focus.

## 8. What's still the same as 2026-04-14

- Stage 1 landing (`be84f7b` + `530a646`) stands. Its post-query `universe_id` assertion stays; it becomes one of N tier assertions in 2a.
- Path-based per-universe DB isolation stays as a physical layer. Row-tagging is defense-in-depth ABOVE path isolation, not replacement.
- Per-universe KG / vector DB locations continue unchanged.
- Migration infers `universe_id` from parent dir; additional scope columns default to NULL.
- Recommendation to ship behind a flag, verify on a clean universe, then a messy one, before flipping default.

## 8.5. What's new in the 2026-04-15 host refinement

- **Source-purity membership model** replaces access-breadth membership (§2.5). A node is in/out of a universe based on where its retrieved context comes from, not how much it can access.
- **Separate `node_scope.yaml` manifest per branch** (§4) replaces the earlier "field on node_def" proposal. Simpler bulk-tagging, clearer in/out distinction.
- **`NodeScope` type extended** with `universe_member: bool` + `external_sources: list[ExternalSource]` (§3). Breadth becomes the sub-attribute it should have been.
- **Actor identity = user login, daemons inherit** (§9.1). No service-account scaffolding.
- **External sources are declared, not inferred** (§2.5). Undeclared outside-source reads are rejected at the scope-composition layer — a hard-fail, not a warning.

## 9. Open questions

### 9.1 Host-answered 2026-04-15

**Q1 — `universe_acl` actor identity model. ANSWERED: user login.** Daemons inherit ACLs from the user-on-whose-behalf they run. No service-account / per-daemon auth pattern in scope. If a future need surfaces (per-daemon permissions for the same user), that's a future extension — not scaffolded here. Implementation: `universe_acl.actor_id` stores user login; daemon-level checks resolve to "what user is this daemon running for?" and that user's ACL row.

**Q2 — Node scope declaration site. ANSWERED: separate file.** Node-scope manifest lives in its own YAML file per branch (see §4 "Node-scope manifest"), not inline in `graph_json`. Reasoning (host): "tagging all nodes in an area with the same universe is simple and clear to distinguish nodes in and outside of the universe." The separate-file shape makes bulk-tag-by-area possible and keeps graph authoring unchanged.

### 9.2 Still open (lower-priority)

3. **Universe-privacy policy inheritance.** If universe U is private, are U's goals automatically private? Or can a goal declare itself "publicly visible within a private universe"? Recommend: private universes are fully private, no public-within-private carve-outs. Keeps Layer 1 simple. Not blocking; default is simpler-is-better.
4. **`SliceSpec` extensibility.** Initial fields: `entity_ids`, `relation_types`, `document_ids`. Enough for v1? Likely need `tag_filters` or `scene_range` later. Recommend: start with the three, add fields as concrete nodes demand them.
5. **`ExternalSource.kind` enumeration boundaries.** Initial four: `universe`, `external_api`, `system_tool`, `cross_universe_join`. Enough? Recommend yes; new kinds added if a domain surfaces one that doesn't fit.
6. **Flag-flip criteria for 2c.** What's the acceptance bar? Recommend: 30 days clean on sporemarch + ashwater + one private-universe test fixture, with Stage 1's assertion firing zero times after 2b.

### 9.3 Resolution 2026-04-16 (navigator + lead)

Under "act then document" authority (design calls where we have enough context). All four §9.2 defaults landed as-recommended. §9.1 already host-answered; §7 is a closed domain-validation checklist, not a question set. Stage 2b is therefore unblocked.

- **Q3 — private-universe implies private-goal. LANDED: YES.** No public-within-private carve-outs. Layer 1 ACL check stays single-predicate. Override hook may be added later if a concrete counter-example surfaces; not scaffolded now.
- **Q4 — `SliceSpec` fields. LANDED: three (`entity_ids`, `relation_types`, `document_ids`).** Extend when a real node demands it. Matches PLAN.md "every scaffold is a falsifiable hypothesis."
- **Q5 — `ExternalSource.kind` enumeration. LANDED: four (`universe`, `external_api`, `system_tool`, `cross_universe_join`).** Extend on domain demand.
- **Q6 — 2c flag-flip criteria. LANDED:** 30 days clean on sporemarch + ashwater + one private-universe test fixture, with Stage-1 assertion firing zero times post-2b. Reversible — flag stays gated, can be un-flipped if the assertion rings.

**Implication:** §6 Stage 2b is ready for dev pickup. Exec plan: `docs/exec-plans/active/2026-04-16-memory-scope-stage-2b.md` (if/once drafted) or STATUS.md Work row.

## 10. PLAN.md alignment

- **§Retrieval And Memory** (L144): stays aligned — tiered scope is routing-policy-shaped.
- **§Multiplayer Daemon Platform** (L102): directly strengthens this. "Private per-user MCP sessions" becomes enforceable, not aspirational. Corporate use case becomes viable.
- **§State And Artifacts** (L112): scope columns ARE the artifact-level policy.
- **§Engine And Domains** (L210): tiered scope is domain-general; each domain consumes it by declaring its universe privacy and node scopes. Fantasy-author declares public universe + full_canon-default nodes; corporate declares private universe + whatever its nodes need. Zero engine bloat for fantasy; zero engine refactor to add corporate.

No principle conflict. This design MATCHES PLAN.md more directly than the 2026-04-14 version did.
