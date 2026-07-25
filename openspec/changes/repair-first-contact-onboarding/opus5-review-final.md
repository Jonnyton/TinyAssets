Read-only review complete. No file edited. `openspec validate repair-first-contact-onboarding --strict` → valid (17 requirements / 42 scenarios, matching the STATUS row's "strict 42/42"). Branch diff vs `origin/main` is 11 files, spec/docs/coordination only — no runtime file touched.

Skipping the usual Codex dispatch on purpose, same reason as the prior round: I am the opposite-provider gate for a Codex-authored packet, so routing it back to Codex would be same-family self-review.

---

VERDICT: ADAPT

I re-verified every prior C1–C3, I1–I9, M1–M3 against this head rather than trusting the claimed fixes. **C1, C2, C3, I1, I2, I3, I4, I6, I7, I8, I9, M2, M3 are genuinely resolved.** I5 is resolved by a different mechanism than I asked for (generation-stale restart instead of an immutable sort key) and that mechanism is sound — but it introduces I7 below. M1 is now a freshness-stamped basis line in `design.md:3`.

One new Critical blocks publication, plus eight Important items. All are normative-text fixes; the lane's fencing is correct.

## Critical

**C1 — There is no canonical publication route, publication is an undisclosed side effect of patching, and `publish_version` is left unprotected from retirement.**

The default catalog scope requires "an active published version" (`specs/branch-authoring-and-catalog/spec.md:6`), and create returns `publication_state="unpublished"` (:160). Every writer of that store is: `branches.py:2687` and `:2702` (patch_branch mints a pre- and post-patch snapshot on *every* patch), `evaluation.py:863`, `selector_dispatch.py:331`, and hidden `extensions action=publish_version` (`extensions.py:747`). `_ext_branch_build` mints none.

Consequences, all live-verified:
- A V1-created branch is invisible in `published` forever unless the author patches it, at which point it silently becomes catalog-listed with no publication intent anywhere in the request.
- The only user-facing publish affordance is the `set_published` patch op (`branches.py:2515-2522`), which writes `branch_definitions.published` — the exact boolean this delta declares non-authoritative (":22", "The platform `branch_definitions.published` boolean alone MUST NOT establish publication"). So the affordance a chatbot will reach for is spec'd into a no-op for discovery.
- `retire-legacy-live-mcp-tools` task 4.1 removes all six legacy registrations. The delta protects the legacy *approval* action from that (":128") but says nothing about `publish_version`, so after retirement no deliberate publication route exists at all.

This is the same defect class the change exists to repair — a journey that cannot complete through advertised handles — and it lands in `openspec/specs/` as as-built truth.

Correction, pick one and state it normatively: **(a)** add a third `publish` mode to the closed write union that mints a version bound to the verified principal, and require `set_published` to either drive it or be rejected; or **(b)** declare publication out of V1 scope explicitly — V1-created branches appear only under `mine` until published — extend the replacement-first requirement (`specs/live-mcp-connector-surface/spec.md:51`) to name `publish_version` alongside `approve_source_code`, add a scenario asserting that a patch-minted snapshot does not silently flip `publication_state` (or disclose that it does), and file a STATUS Concern. Either way, task 3.6's "publication outbox" needs to say which event is the publication.

## Important

**I1 — Sync conflict with canonical `live-mcp-connector-surface`, unaddressed.** `openspec/specs/live-mcp-connector-surface/spec.md:38` states each handle "is a thin shape/target router that delegates to an existing `tinyassets.api.*` handler **without changing that handler's behavior**." This delta mandates a new hardened catalog owner and changed staging behavior (tasks 3.1/3.4/3.6). The delta contains only ADDED requirements for that capability, so syncing yields canonical text asserting thin-unchanged delegation next to requirements that forbid it — the same structural hazard as prior I9, one requirement over. Add a MODIFIED delta for "Canonical Advertised Handle Set" scoping the thin-router clause, and note in task 9.1 that `retire-legacy-live-mcp-tools` also MODIFIEs that same requirement (ordering matters).

**I2 — "Active published version" is undefined against the store.** `branch_versions` has `status TEXT NOT NULL DEFAULT 'active'` plus `rolled_back_at/by/reason` (`branch_versions.py:60-63`), but `list_branch_versions` does not filter on it (`:393-397`), so today's `_ext_branch_list` counts a rolled-back version as published (`branches.py:581-585`). Define "active published version" as `status='active'` explicitly in :22 and :41, or the rollback bug becomes a public-catalog correctness bug.

**I3 — The outbox obligation falls on writers the packet never enumerates.** ":22" says "Publication writers SHALL emit a durable projection outbox event," but the four in-repo writers include `evaluation.py:863` and `selector_dispatch.py:331`, outside any file this lane's tasks or STATUS write-set name. Task 3.6 cannot land truthfully as scoped. Enumerate the call sites, or route emission through a single chokepoint in `publish_branch_version` and say so. Related and load-bearing: `extensions.py:551` sets `"publisher": os.environ.get("UNIVERSE_SERVER_USER", "anonymous")` — the catalog's authoritative-publication check now consumes rows whose publisher is env-derived, so the ":112" prohibition on `UNIVERSE_SERVER_USER` as positive authority should cover the publication seam too, not just create.

**I4 — Protected-field hardening is scoped to the wrong layer.** ":127" binds the invariant to "Every `write_graph(target="branch")` patch operation." The defect lives in the shared helper `_apply_node_spec` (`branches.py:1724` `author=raw.get("author") or _current_actor()`; `:1693-1707` carries `approved`/`approved_by`/`approved_source_hash` forward on a self-consistency hash check), which stays reachable through the still-registered hidden `extensions action=patch_branch` (canonical spec :56 keeps legacy tools dispatchable, and this packet requires they stay). The packet already gets this right for the wiki leak — ":55" names `get_branch`, `describe_branch`, *and their shared helper*. Apply the same shape: put the requirement on the shared staging helper so every alias inherits it.

**I5 — The new key material has no catalog, rotation owner, or fail-closed-when-absent rule.** ":24" requires versioned AES-256-GCM cursor keys with key IDs; ":139" requires a versioned HMAC secret with retained versions. Nothing names an env var, an entry in `scripts/secrets_keys.txt`, `docs/reference/environment-variables.md`, or what happens when no key is configured — and `read_graph` is anonymous-callable, so an absent key must fail closed to `branch_catalog_unavailable`, never to an unauthenticated cursor. The project convention exists: STATUS already carries a `host-action` row for `TINYASSETS_IDENTITY_FINGERPRINT_KEY` and the sibling scoped-wiki-canary lane is "rotation-catalogued." Add the key names, catalog task, fail-closed requirement, and a `host-action` dependency — otherwise tasks 3.2/3.3 are not completable.

**I6 — Patch mode rejects a parameter the shipped docstring calls "Required."** ":68" requires empty `idempotency_key` in patch mode, but `write_graph`'s live docstring reads "idempotency_key: **Required** 16-128 character request idempotency key" (`universe_server.py:545`), with no target scoping. An LLM caller will supply it on a branch patch and get `branch_write_mode_invalid` on a path that works today. Either accept-and-ignore it in patch mode, or make task 4.4 explicitly re-scope that description per-target and add a drift test for it.

**I7 — One global catalog generation makes pagination starvable.** ":24" increments a single branch-catalog generation on every projection create/patch/publication/unpublication/deletion, and ":26" turns any change into `branch_cursor_stale`. On a commons with concurrent authors, any unrelated write invalidates every in-flight cursor, so a reader may never finish page 2. Scope the generation per (scope, normalized filter set), or keep it global but state a bounded-restart contract. Task 6.3 / ":185" assert stale *behavior* but never that pagination can *complete* under concurrent mutation — add that assertion, or the fixture cannot detect this.

**I8 — First-contact guidance teaches `run_graph` without the BYOC prerequisite.** `design.md:70` and `specs/live-mcp-connector-surface/spec.md:32` route the starter journey through create → inspect → **run**, while STATUS carries the P0 "Newborn contact has no BYOC/market authority path; never use maintainer quota" and this packet's own ":181" scenario confirms creation grants no provider quota. The delta forbids *overclaiming* (":43", ":160") but never requires the guide to state that running needs the user's own attached provider. That re-creates the instructional defect this change exists to fix, one step later. Add it to the ":20" guidance requirement with a scenario.

## Minor

- **M1** The commons-only filter mechanism is unstated. ":6" says `mine` admits "platform-commons branches" but never names the predicate; the only mechanism is the pre-existing `branch_definitions.visibility` column (`daemon_server.py:2384-2385`) that `PLAN.md:63` calls an anti-pattern. State the fail-closed predicate, and record in `design.md` §6 that the column is pre-existing Phase-6.2.2 drift the packet consumes but does not extend.
- **M2** `domain_id` defaults to `""` in the DTO (":85") but `_staged_branch_from_spec` substitutes `"workflow"` for empty (`branches.py:2091`). Harmless under ":41" ("may be empty"), but say which value the summary reports.
- **M3** `mine` on an anonymous call returns `branch_authentication_required` as tool JSON (":15"); `read_graph` is deliberately anonymous-callable with no 401 challenge (canonical spec :81), so nothing launches OAuth. Require the message to name the remedy.
- **M4** `has_source_nodes` (":41") is a new notion; the existing seam computes `has_sandbox_nodes` from `requires_sandbox` (`branches.py:592`). State the mapping so an implementer doesn't reuse the wrong field.
- **M5** `_ext_branch_patch` accepts `force=true` to mutate a non-author's branch (`branches.py:2616-2629`). Unreachable from `write_graph` (which passes no `force`) but reachable via the hidden tool — worth one line next to ":127" so the patch-authority claim is scoped honestly.

## Bottom line

The fencing is right and verified: spec-only diff, no runtime file, exact-seven preserved (new *parameters*, no new handle), commons-only V1 that no longer contradicts `PLAN.md` §4, closed versioned DTOs, a real transaction seam replacing the invented ledger, and the wiki lane correctly held behind a serialized writer with refreshed pre-images. Prior C1–C3 are genuinely closed, not papered over.

It is not yet safe to publish as a blocked draft because C1 leaves the headline journey one step short in a way that syncs into as-built truth — a user can create a branch but has no advertised way to make it discoverable, while the mechanism that actually publishes is an undisclosed side effect of an unrelated verb, and the legacy verb that would have covered it is left exposed to retirement. Resolve C1 and I1–I2 (both are sync-time correctness), fold in I3–I8, and the packet is publishable. I'll re-review the amended head on request.
