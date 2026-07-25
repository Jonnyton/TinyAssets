Read-only review complete — no file edited. `openspec validate repair-first-contact-onboarding --strict` → **valid**; branch diff vs `origin/main` is 12 files, spec/docs/coordination only, zero runtime files. Skipping the usual Codex dispatch on purpose, same reason as both prior rounds: I am the opposite-provider gate for a Codex-authored packet, so routing it back to Codex would be same-family self-review.

---

VERDICT: ADAPT

I re-checked every prior finding against this head (`7e7fd9bb`) rather than trusting the claimed fixes.

**Round-1 C1–C3, I1–I9, M1–M3: all resolved.** Spot-verified the load-bearing ones: create mode now constrains *every* `write_graph` parameter (`spec.md:83-84` enumerates all 15 against the live signature at `universe_server.py:511-546` — complete, none missed); `limit=30` matches the shipped default (`universe_server.py:436`), so the observability defect is gone; source-code approval is now protected replacement-first (`spec.md:169`, `live-mcp-connector-surface/spec.md:60`) and consistent with `graph-execution-substrate/spec.md:77`.

**Round-2 C1 and I1–I8: all resolved.** Publish mode is real and owner-bound; `status='active'` is explicit at `spec.md:23/27/58`; the outbox now routes through a single `publish_branch_version` chokepoint; the protected-field invariant moved to the *shared staging helper* — correctly targeting `_apply_node_spec`, which today still does `author=raw.get("author") or _current_actor()` (`branches.py:1724`) and carries `approved`/`approved_by`/`approved_source_hash` forward on a self-consistency hash check (`branches.py:1693-1707`); the keyring is catalogued and fail-closed; pagination moved to immutable `(created_at DESC, branch_def_id ASC)` — and `branch_definitions.created_at` really exists (`daemon_server.py:325`), so the ordering key is available for backfill; BYOC is now required before any `run_graph` guidance.

I also checked two things that *could* have been fatal and are not: `_apply_node_spec` appends a `GraphNodeRef` alongside each `NodeDefinition` (`branches.py:1740-1743`), so a minimal V1 payload with no graph-topology field still passes `BranchDefinition.validate()`'s `entry_point in graph_nodes` check (`branches.py:244`) — the headline journey is buildable. And no other change claims the `branch-authoring-and-catalog` capability name.

One Critical remains, plus five Important. All are text fixes; the lane's fencing is right.

## Critical

**C1 — The packet asserts the legacy-retirement change is unclaimed. Its own diff contains the STATUS.md row proving otherwise, and that error disarms the replacement-first gate at the exact moment it is actionable.**

`proposal.md:27`, `design.md:7` and `:97`, `tasks.md:1.1`, and `docs/ops/…-gaps.md:97` all state that `retire-legacy-live-mcp-tools` is unclaimed as of 2026-07-25 and instruct "re-check at claim time." Current `STATUS.md:49` — in this branch — reads:

> `**Retire-legacy 2.1-2.3 caller inventory + BUG-018 close** … | openspec/changes/retire-legacy-live-mcp-tools/tasks.md, docs/ops/, … | - | claimed:fable-fleet-opus5 ACTIVE 2026-07-25`

`python scripts/claim_check.py` classifies it IN-FLIGHT at L49. The claimed scope is retire-legacy tasks **2.1–2.3**, and task 2.3 is precisely *"Inventory every repository import and direct Python caller of `universe`, `community_change_context`, `extensions`, `goals`, `gates`, and `wiki`; record a preserve-or-explicitly-migrate decision and focused coverage for each wrapper."* That inventory is the artifact where this packet's protection of `publish_version` and `approve_source_code` has to be recorded, because retire-legacy task 4.1 removes the `extensions` registration — and with it MCP reachability of both actions — whether or not the wrapper functions survive.

So the addressee exists right now and is editing the exact file, while the packet tells its readers there is no one to tell. This is not a wrong `SHALL` — the normative requirement at `live-mcp-connector-surface/spec.md:60` is correct and unchanged. It is a false coordination fact published as authority, contradicted by a file in the same commit, and it is the packet's own headline failure mode (a gate that never reaches the party who can honor it).

Correction: replace the four "unclaimed" statements with the actual owner and row; convert task 1.1 from *re-check later* to *act now* — notify `fable-fleet-opus5` and get the `publish_version` + `approve_source_code` replacement-first dependency written into `retire-legacy-live-mcp-tools/tasks.md` §2.3 and that row's `Depends` cell while it is open; add the reciprocal edge. Keep `broad-test` as-is — I confirmed it appears nowhere outside this packet.

## Important

**I1 — Publication authority is bound to a chokepoint that has non-request service callers; implemented literally it breaks the platform default selector.**
`specs/branch-authoring-and-catalog/spec.md:23`: *"Every V1 catalog-eligible publication SHALL flow through a connection-accepting `publish_branch_version` chokepoint, **which SHALL require the verified branch owner, reject service/environment principals**…"* — the relative clause attaches the authority test to the chokepoint itself. Task 3.6 then requires routing `branches.py`, `evaluation.py`, and `selector_dispatch.py` through it. But `ensure_default_selector_published` calls it at dispatch bootstrap with `publisher=DEFAULT_SELECTOR_PUBLISHER` and no request principal (`selector_dispatch.py:331`), and on failure `resolve_selector_branch_version_id` surfaces `default_selector_unavailable` (`selector_dispatch.py:319-355`). An implementer following the text disables selector dispatch. The following sentence ("Patch/evaluation/selector/service snapshots SHALL create no catalog-publication record") shows the intent, but the text does not carry it.
Correction: bind the verified-owner test to the *catalog-publication path inside* the chokepoint — i.e. it applies only when a `BranchCatalogPublication` is minted — and state that snapshot-only calls from patch/evaluation/selector remain permitted without a request principal and mint no publication. Add a scenario asserting default-selector bootstrap still succeeds and produces no catalog row.

**I2 — A normative requirement on the patch path has no task; the catalog goes stale on rename.**
`spec.md:23` requires *"Branch create **and patch** SHALL update their projection row in the same database transaction as the branch mutation."* Task 3.2 covers create only ("commit **create** state in one transaction"); task 3.5 hardens shared patch staging and never mentions the projection; task 3.7 implements and backfills it. Since `query` matches branch **names** (`spec.md:4`) and the projection holds "the allowed summary fields", a renamed or re-described branch keeps matching its old name — and reports a stale `updated_at` and stale counts — until "periodic maintenance" reconciles. Task 3.6 cannot land this truthfully as scoped.
Correction: extend task 3.5 (or add 3.8) with the patch-path projection write in the same transaction as the branch mutation, and add the corresponding failing test to task 2.4.

**I3 — `goal_id` is an exact-match filter and a disclosed summary field on an anonymous surface, with no goal-visibility predicate anywhere.**
`spec.md:4` admits `goal_id` as an optional exact-match filter; `spec.md:58` returns it in every `BranchSummaryV1`. Both are real: `branch_definitions.goal_id` is a Phase-5 column with an exact-match filter (`daemon_server.py:471-477`, `2485-2486`), and Goals carry `visibility` in `{public, private}` (`market.py:1151-1152`). On an anonymous catalog, an exact-match filter over an identifier is an existence oracle, and a public branch bound to a private Goal discloses that Goal's ID. The packet applies exactly this reasoning to wiki pages (`spec.md:71-76`: no "item, path, title, summary, boolean, match count, or existence evidence") and accepted the same argument for `query`/`tags` in round 1 (I6) — Goal binding is the one filter left unreasoned.
Correction: state normatively that a branch's Goal binding is public metadata by definition (and why), **or** fail closed — omit `goal_id` from the summary and reject the filter unless the referenced Goal is visible to the caller. Add a scenario either way.

**I4 — The cursor's nonce-prefix lease is a durable write inside a handle both this packet and canonical truth declare read-only.**
`spec.md:27`: the read path *"MUST NOT enqueue or mutate state under the handle's read-only contract."* `spec.md:31`: *"every issuer SHALL atomically lease a never-reused 32-bit nonce prefix in a durable table with unique `(kid, prefix)` constraint."* Nothing says *when* the lease is taken, so lazy allocation on first cursor issuance is a conforming reading — and it writes during `read_graph`, which is registered `readOnlyHint=True, idempotentHint=True` (`universe_server.py`) and pinned `R=T / I=T` by canonical `live-mcp-connector-surface/spec.md` §"Registered tools publish exact discoverability and behavior metadata".
Correction: require the lease to be acquired at issuer initialization, outside request handling, failing closed to `branch_catalog_unavailable` if unobtainable; or explicitly carve it out of `:27` and reconcile it against the metadata requirement's hint table.

**I5 — Task 5.1 rewrites `control_station` while another lane holds it.**
Task 5.1 rewrites all four registered prompt bodies including `control_station`; `spec.md:24` (connector delta) makes that normative. `STATUS.md:34` carries **control_station prompt truth fix** — `tinyassets/universe_server.py (control_station prompt region), tests/ (new invariant test)` — `claimed:fable-fleet-codex ACTIVE 2026-07-25`, whose own note draws the boundary "*spec-side onboarding stays with codex-gpt56-first-contact*". That lane is adding an invariant test (prompt names ⊆ `tools/list`) that overlaps task 5.4's drift tests. The packet names neither the lane nor the test.
Correction: add that lane to the STATUS row's `Depends` and to tasks 1.1/1.6, and state in task 5.1 whether it inherits or supersedes that lane's `control_station` text and invariant test.

## Minor

- **M1** Publish replay resolves before state lookup (`spec.md:106`), so after a rollback (`spec.md:25`) a retry returns `publication_state="published"` for a branch the catalog omits. Say that a replayed receipt reports the original command's outcome and is not evidence of current catalog eligibility — otherwise the rendered "rediscover it" acceptance step (`live-mcp-connector-surface/spec.md:68`) can be validated off a replay.
- **M2** `branch_write_failed` is in the closed error enum (`spec.md:208`) but no requirement states when it is returned. Give it a trigger or drop it.
- **M3** At `limit=100` the scan bound `min(4 * limit, 400)` (`spec.md:27`) permits up to 400 cross-store authoritative version/publication verifications per catalog read — `branch_versions` is a separate SQLite DB (`branch_versions.py:129`) — against 750 concurrent reads at p99 < 3s (`spec.md:231`). Declare the expected verification fan-out in the fixture's topology so the number is falsifiable.
- **M4** This packet's MODIFIED `Canonical Advertised Handle Set` drops the canonical baseline's `(verified by tests/test_universe_server_five_handles.py)` attribution and does not carry the retirement delta's two added scenarios (middleware-bypassed registry; `run_graph` round trip). Task 9.1 mandates manual reconciliation and is the only guard. Stating the merged target text inside 9.1 would make that reconciliation reviewable instead of reconstructed.

## Bottom line

The fencing is verified and correct: spec/docs only, no runtime file, exact seven handles preserved via new *parameters* on `read_graph`/`write_graph`, commons-only V1 that no longer contradicts PLAN, closed versioned DTOs with a complete parameter allowlist, real transaction seams, a genuine publication route that closes round-2 C1, and the live-wiki lane held behind a serialized writer with refreshed pre-images. Both prior reviews' findings are genuinely closed, not papered over — I checked each against code rather than against the claim.

It is not yet safe to publish as a blocked draft because C1 publishes a coordination fact its own commit falsifies, and that specific error routes the packet's replacement-first protection away from the owner who is editing the file where it belongs, right now. Fix C1 and I1–I2 (both are correctness at implementation time), fold in I3–I5, and this is publishable. I'll re-review the amended head on request.
