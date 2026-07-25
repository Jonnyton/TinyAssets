Read-only review complete — no file edited. `openspec validate repair-first-contact-onboarding --strict` → **valid**; `retire-legacy-live-mcp-tools --strict` → **valid**; `git diff origin/main...HEAD` is 14 files, spec/docs/coordination only, zero runtime files, and the retire-legacy edit is exactly 4 lines (2.3a + 4.0). Skipping the usual Codex dispatch on purpose, same reason as all three prior rounds: I am the opposite-provider gate for a Codex-authored packet, so routing it back to Codex would be same-family self-review.

---

VERDICT: ADAPT

I re-checked all three prior rounds against this head (`3bbe0e44`) rather than trusting the claimed fixes, then ran my own passes.

**Round-3 C1 and I1–I5: all resolved.** Verified each against current state, not against the claim. `STATUS.md:44` now reads `pending` with the first-contact gates written into its `Depends` cell, and `#1772` really did land inventory v4 into `retire-legacy-live-mcp-tools/tasks.md` on main — so the "unclaimed" wording is now accurate and the replacement-first gate reaches the right file (2.3a/4.0). The chokepoint authority test moved onto the `catalog_publish` intent with an explicit carve-out for `snapshot` (`spec.md:28`) plus a default-selector-bootstrap scenario (`:138`) — necessary, because `selector_dispatch.py:331` really does call `publish_branch_version(publisher=DEFAULT_SELECTOR_PUBLISHER)` with no request principal. The patch-path projection write now has a task (3.5), a scenario (`:57`), and a test (2.4). `goal_id` is gone from filter, projection, and summary — fail-closed, the safer of the two options I offered. The nonce lease moved to initialization-before-request-handling with a no-durable-write scenario (`:52`), reconciling with `readOnlyHint=True` at `universe_server.py:501-507`. `control_station` ownership is named (`fable-fleet-codex`) with inherit-not-overwrite in 5.1 and extend-not-duplicate in 5.4.

Round-1 and round-2 findings remain closed. I re-confirmed the two load-bearing ones: `write_graph`'s 15 parameters at `universe_server.py:511-527` are each constrained by `spec.md:98-102` with none missed, and `read_graph`'s 10 at `:426-437` are likewise complete (`limit=30` at `:436` matches). `_apply_node_spec` still does `author=raw.get("author") or _current_actor()` (`branches.py:1724`) and still carries `approved`/`approved_by`/`approved_source_hash` forward on a self-consistency hash check (`:1693-1707`), so the shared-staging requirement at `spec.md:189` is aimed at a live defect.

Two Critical remain, three Important, six Minor.

## Critical

**C1 — `BranchCreateDefinitionV1` cannot express a branch that passes `BranchDefinition.validate()`. The headline first-contact journey is unimplementable as written, and no scenario would catch it.**

`spec.md:144` fixes the closed top-level allowlist; `spec.md:152` defines an ordinary edge as *"exactly string `from` and string `to`"*; `spec.md:156` bounds structural identifiers to the declared `node_defs` IDs. Nothing in the DTO requirement mentions the reserved `START`/`END` sentinels (`branches.py:542`, `RESERVED_NODE_IDS = {"START", "END"}`), and nothing requires any node to terminate.

I ran the actual staging seam the create path maps onto (`_staged_branch_from_spec` → `validate()`):

```
A: node_defs=[step1], edges=[],                    → ['Nodes in cycle without exit condition: step1.']
B: node_defs=[step1], edges=[{from:step1,to:END}]  → []            (valid)
C: 2-node chain ending at END                      → []            (valid)
```

`validate()` computes `all_node_ids = seen_graph | RESERVED_NODE_IDS` (`branches.py:1074`) and then `_nodes_that_cannot_reach("END", …)` (`:1130`). So `END` is *mandatory* as an edge target, and it is *not* a declared node — the exact identifier a closed-DTO implementer following `spec.md:152` would reject. Both readings fail the journey: enforce "edge endpoints ∈ declared node IDs" and **every** V1 create returns `branch_validation_failed`; omit the terminal edge and the same. The same gap applies to conditional edges (`spec.md:152`, *"mapped to target-node identifier strings"*) — I confirmed `{"done": "END"}` is required and valid.

There is a second undocumented rule on the same path: every `{ident}` in `prompt_template` must resolve via that node's `input_keys` or a `state_schema` field name, or `validate()` fails (case D returned *"prompt_template references '{topic}' but it is not declared…"*). `spec.md:144-156` admits `prompt_template`, `input_keys`, and `state_schema` as mutually independent optional fields with no stated cross-constraint — so the spec's own "prompt-template starter format" is under-specified for the guide task 5.1 must write.

The reason no reviewer caught this earlier is structural: **the spec contains no scenario in which a concrete create succeeds.** `spec.md:230` opens *"WHEN a public branch create succeeds"* — it asserts the result shape, never that any definition can reach it. Task 2.2's failing tests are written from the spec, so they inherit the gap. Round 3 checked `entry_point ∈ graph_nodes` and stopped one predicate short.

Correction: in `spec.md:144`/`:152`, admit `START` and `END` as reserved edge/conditional-edge endpoints distinct from declared `node_defs` IDs (and keep them rejected as `node_id` values); state normatively that every node must reach `END`; state that each `prompt_template` placeholder must be declared in that node's `input_keys` or in `state_schema`. Add a scenario pinning a literal minimal definition — one node, `edges:[{"from":"step1","to":"END"}]`, `entry_point:"step1"`, `state_schema:[]` — that MUST create successfully, and add the matching failing test to task 2.2. Then make task 5.1's starter example that exact definition.

**C2 — The packet writes "user-controlled storage" into a normative requirement, pre-committing a private-data custody question `PLAN.md` reopened on 2026-07-25 and explicitly told lanes not to settle.**

`PLAN.md:65-67` (host-approved **today**): *"Private-data custody is an OPEN RESEARCH QUESTION … The custody modes to research, **none of them ruled in or out**: host machine, private universe brain, vault, and **platform-held** (we store it, under stated boundaries)."* Its How-to-apply is directive: *"do not encode either custody answer as settled. **Do not ship a design that assumes the platform can never hold private content**, and do not ship platform private storage or private catalog rows as though that question were already answered — name the custody mode your lane assumes, scope the lane to it, and record the assumption."*

The packet does the second half correctly (no platform private row, no `is_private` substitute) and then violates the first half in five places, one of which is normative:

- `specs/branch-authoring-and-catalog/spec.md:240` — ADDED requirement *V1 creation is commons-only*: *"Private authoring requires a later PLAN-approved **user-controlled storage and routing contract**."*
- `spec.md:6` and its scenario title at `:18` (*"User-controlled private content is outside the catalog"*)
- `design.md:25` (Non-Goals), `design.md:66` (Decision 6), `design.md:107` (Open Questions)
- `tasks.md:5` (1.3), `docs/ops/…-gaps.md:99`

Because `openspec/specs/` is as-built truth and this delta syncs there on land, that sentence would encode into canonical spec the assumption that the platform can never hold private branch content — exactly the shape PLAN forbids, on the day PLAN reopened it. AGENTS.md § Orient item 4 is unambiguous: a PLAN conflict is not implemented, it is filed.

Correction: keep V1 commons-only (that scoping is correct and PLAN-compliant), but strip the forward custody commitment. In `spec.md:240` say *"Private authoring requires a separate change that names its custody mode and receives PLAN-approved design"*; rename the `:18` scenario to *"Private content held outside the commons is outside the catalog"* and phrase `:6` as "any private store" rather than "private user-controlled store"; in `design.md:25/66/107` record the assumption in PLAN's own words — this lane assumes **commons/platform-public** custody only and takes no position on which of the four modes serves private branches.

## Important

**I1 — The action this packet instructs retire-legacy to preserve is itself owner-unchecked and publisher-spoofable, and the manifest describes it wrongly.**

`docs/ops/…-gaps.md:42` states *"The legacy publication seam derives `publisher` from `UNIVERSE_SERVER_USER`."* It does not. `_action_publish_version` (`evaluation.py:842-877`) takes `publisher = (kwargs.get("publisher") or "anonymous").strip()` — a fully caller-supplied string — loads the branch via `get_branch_definition`, and calls `publish_branch_version` with **no branch-ownership check anywhere in the chain**. The only gate is `_dispatch_scope_error` → `require_action_scope("extensions", "publish_version")` (`extensions.py:243-260`), a write-*scope* check (`auth/provider.py:562`), not an ownership check. So any caller with write scope can mint a version snapshot on *any* branch under *any* publisher name.

The normative text at `spec.md:121` already forbids caller-supplied publisher fields for the canonical route, so the contract is right. The problem is the coordination instruction: retire-legacy task **2.3a** now says *"preserve `extensions(action="publish_version")` MCP reachability until canonical branch publish is deployed"* — this packet is directing another lane to keep an unauthorized, spoofable write path alive, on the strength of an evidence line that mis-states its authority model. New catalog state is protected (that path mints no `BranchCatalogPublication`), but a preserved defect should be preserved knowingly.

Correction: fix `gaps.md:42` to the actual behavior (caller-supplied `publisher`, no owner authorization, write-scope only). Amend retire-legacy 2.3a to record that the preservation is a known-risk decision, and add the compensating requirement — canonical publish mode must not read `branch_versions.publisher` as authorship evidence for any catalog decision, since arbitrary callers can have written it.

**I2 — Three changes now hold concurrent MODIFIED text for `Canonical Advertised Handle Set`, and this packet widens the divergence by renaming a scenario the other delta preserves.**

Baseline `openspec/specs/live-mcp-connector-surface/spec.md:36-54` has 3 scenarios and the `(verified by tests/test_universe_server_five_handles.py)` attribution. `retire-legacy-live-mcp-tools/specs/live-mcp-connector-surface/spec.md:3-33` has 5 (adds *Middleware-bypassed registry* and *run_graph completes a live MCP-to-storage round trip*). This packet's `live-mcp-connector-surface/spec.md:81-104` has 4 (adds *A canonical handle routes through the shared hardened owner*), drops the test attribution, **and renames** the shared baseline scenario *A canonical handle routes to its existing API **handler*** → *…existing API **owner***, rewording its THEN. Whichever syncs second silently drops the other's scenarios; the rename converts a mechanical 3-way merge into a judgment call, on the requirement backing Hard Rule #11.

Task 9.1 mandates manual reconciliation and is the only guard — it enumerates what to preserve but never states the target text, so the merge is reconstructed at land time rather than reviewed now.

Correction: restore the baseline scenario name and THEN wording verbatim (add your shared-owner scenario alongside rather than editing an existing one), restore the test attribution, and inline the merged target text — all seven scenarios in order — into task 9.1 so the reconciliation is reviewable today.

**I3 — Task 1.6's future claim list omits four files task 5.2 requires writing, so 5.2 cannot land as scoped.**

Task 1.6 enumerates the eventual runtime claim as *"exact canonical, `tinyassets/branch_versions.py`, `tinyassets/api/{branches,evaluation,selector_dispatch}.py`, secret-catalog, migration, packaging, `tests/test_branch_authoring_catalog.py`, `tests/test_mcp_instruction_surfaces.py`, `tests/load/test_branch_catalog_concurrency.py`."* Task 5.2 requires editing `tinyassets/api/{prompts,branches,wiki,universe,market}.py` and `tinyassets/universe_server.py`; task 5.4 adds `WORKFLOW_DESIGN_HANDOFF_FOR_POLSIA.md`. `prompts.py`, `wiki.py`, `universe.py`, `market.py`, and the handoff doc appear in no claim list. All four `api/*.py` files are inside the live `control_station` row's Files cell (`STATUS.md:25`) alongside `branches.py`, so this is precisely the collision task 1.1 exists to prevent — and the pre-claim guard would not fire on files that were never declared.

Correction: extend 1.6's claim list with `tinyassets/api/{prompts,wiki,universe,market}.py` and `WORKFLOW_DESIGN_HANDOFF_FOR_POLSIA.md`, and note that all of them sit under the `control_station` lane's boundary so 1.1's release covers the whole set, not just `universe_server.py`'s prompt region.

## Minor

- **M1 (round-3 M1, unresolved)** `spec.md:121` still has publish replay return the stored result *"even if the branch was later … rolled back, or deleted"*, and `BranchPublishResultV1` carries `publication_state="published"` (`:127`). Add one sentence: a replayed receipt reports the original command's outcome and is not evidence of current catalog eligibility.
- **M2 (round-3 M2, unresolved)** `branch_write_failed` is still in the closed enum at `spec.md:228` with no requirement stating when it is returned. Give it a trigger or drop it.
- **M3 (round-3 M3, partially)** `design.md:108` now says evidence must name "hardware and topology," but neither `spec.md:251` nor task 6.3 declares the expected cross-store verification fan-out. At `limit=100` the `min(4 * limit, 400)` window (`spec.md:32`) permits 400 `branch_versions` lookups per catalog read — a separate SQLite DB (`branch_versions.py`) — against 750 concurrent reads at p99 < 3s. Name the expected fan-out so the threshold is falsifiable.
- **M4** `mine` (`spec.md:6`) matches the verified actor against `branch_definitions.author`, a free-text column defaulting to `'anonymous'` (`daemon_server.py:313`) that legacy rows populated from `_current_actor()` — which itself falls back to `os.environ.get("UNIVERSE_SERVER_USER", "anonymous")` (`engine_helpers.py:192`). A verified subject string colliding with a legacy author value would see that actor's *unpublished* commons work under `mine`. Scope is commons-only so no confidentiality boundary breaks, but state the identity-binding rule (subject-format namespacing, or exclude rows whose author is not a verified-subject form).
- **M5** The scenario at `spec.md:22-25` has two WHENs (*supplies a non-default `goal_id`* / *lists a public branch whose Goal is hidden*) but a THEN that only answers the first. Split it, or move the disclosure assertion into its own scenario.
- **M6** `STATUS.md:24` (wiki audience backfill) says *"use exact-path proof + dry-run + **CAS**"*, while this packet correctly establishes at `live-mcp-connector-surface/spec.md:49` that `expected_sha256` (`wiki.py:1153`, `:1272`) is a race-prone precondition and **not** CAS. Two rows contradict on the same mechanism, and both lanes plan writes to public wiki pages. Reconcile the other row's wording; the serialized-writer gate in task 8.2 is the shared prerequisite and should be named there too.

## Bottom line

The fencing is verified and correct: spec/docs only, no runtime file, exact seven handles preserved by adding *targets and parameters* rather than tools, real transaction and chokepoint seams that match the code they name, a genuine owner-bound publication route, and the live-wiki lane held behind a serialized writer with refreshed pre-images. Round 3's C1 and I1–I5 are genuinely closed — I checked each against code and current STATUS rather than against the claim — and the packet correctly hard-blocks itself on the `_related_wiki_pages` leak, which I confirmed still scans every page and draft with no visibility filter (`branches.py:1032-1082`, reached from `get_branch` at `:460` and `describe_branch` at `:1168`).

It is not yet safe to publish as a blocked draft. C1 means the one journey this change exists to enable cannot be built from its own contract, and the packet has no scenario that would ever reveal that. C2 puts a sentence into a normative requirement that contradicts a PLAN principle reopened the same day, in a file that becomes as-built truth on sync. Both are text fixes. Fix C1 and C2, fold in I1–I3, and this is publishable — I'll re-review the amended head on request.
