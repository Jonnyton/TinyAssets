---
title: workflow/daemon_registry.py — daemon identity substrate
date: 2026-05-02
author: dev (claude-code)
status: reference (post-implementation public design note)
audience: contributors, reviewers, future spec authors
implements:
  - PLAN.md "Daemons are the public agent identity" L143
  - PLAN.md "Daemon identity is platform-wide, not domain-specific authoring" L144
  - PLAN.md "Multiplayer Daemon Platform" L208-225
  - PLAN.md "Host daemon fleets are capacity-bounded, not product-capped" L147
  - PLAN.md "Soul eligibility" L217 + "Soul-guided dispatch" L219
companion:
  - .claude/agent-memory/verifier/reference_daemon_registry_shape.md (verifier-internal review notes; this file is the public counterpart)
  - docs/design-notes/2026-05-01-hostless-byok-cloud-daemon-capacity.md (forward-pointing extension target)
  - docs/vetted-specs.md "Per-node/gate soul_policy field" (5-mode shape)
canonical_source: workflow/daemon_registry.py @ origin/main 0dfeea6 (~654 LOC, 18 defs)
canonical_tests: tests/test_daemon_registry.py @ origin/main (12 tests, 271 LOC)
---

## 1. Purpose

`workflow/daemon_registry.py` is the project-wide daemon identity facade. It presents daemon/soul language at the public API while the underlying SQLite still uses transitional `author_*` tables. Per the file's own docstring: "Public callers use daemon_id, while storage can move later without changing the caller contract."

This module is the implementation of three PLAN.md commitments:

- **L143 — Daemons are the public agent identity.** Summonable, forkable, defined by durable soul files. Soul changes create new forks rather than overwriting.
- **L144 — Daemon identity is platform-wide, not fantasy-author-specific.** The `author_*` substrate is preserved (soul, fork, fingerprint, runtime concepts) but exposed under daemon naming. Content provenance still uses `author_id` + `author_kind`; daemon identity is runtime / eligibility / personality.
- **L147 — Host daemon fleets are capacity-bounded, not product-capped.** Hosts may run as many daemons as they can afford, including same-provider; second+ same-provider summons emit warning-only capacity guidance, no platform gate.

This is the seam through which the upcoming **capacity-grant / control-intent / executor-backend** three-concept split will flow (per `docs/design-notes/2026-05-01-hostless-byok-cloud-daemon-capacity.md`). Today's surface is "daemon identity + summoning"; capacity-grants, activation outboxes, and scoped write proxies are the next-layer concepts that haven't shipped yet.

## 2. Data model + public types

### 2.a. Module-level constants

| Constant | Value | Purpose |
|---|---|---|
| `SOULLESS_SOUL_TEXT` | `"Default soulless daemon. Uses the platform dispatcher policy."` | Sentinel string. `_soul_mode(row)` falls back to text-match if `daemon_soul_mode` metadata is missing. |
| `VALID_SOUL_MODES` | `{"soul", "soulless"}` | The 2-mode discriminator at the **daemon-identity** level. NOT to be confused with the 5-mode soul-eligibility shape at the **node/gate** level — see §4. |
| `PROJECT_LOOP_FLAG` | `"project_loop_default"` | Metadata key marking a daemon as the project's autonomous-loop default. Only soul-bearing daemons honor this flag. |
| `RUNTIME_CONTROL_STATUSES` | `{pause: paused, resume: provisioned, restart: restart_requested}` | Maps control actions to terminal runtime statuses. `banish` is its own path via `retire_runtime_instance`. |

### 2.b. Identity translation

The translation layer lets the registry present `daemon::X` IDs while storage emits `author::X`:

- `_daemon_id_from_author_id(s)` / `_author_id_from_daemon_id(s)` — `author::X` ↔ `daemon::X` namespace flip. Bidirectional, lossless.
- `legacy_author_id` is exposed in every public daemon dict so callers that need to interop with the storage layer can do so without re-translating.

This is **not a shim** in the project's no-shims sense (`feedback_no_shims_ever`). The substrate translation is permanent — `daemon_id` is the canonical identity name; `author_id` remains canonical for content provenance per `project_author_id_canonical_not_rename_leftover`. Both names co-exist forever.

### 2.c. Public surface (curated)

| Function | Purpose |
|---|---|
| `create_daemon(base_path, *, display_name, created_by, soul_mode, soul_text, domain_claims, lineage_parent_id, metadata)` | Mint a daemon identity. `soul_mode='soul'` requires non-empty `soul_text`; computes `soul_hash = sha256(soul_text)`. |
| `list_daemons(base_path)` | All daemons in this universe substrate, soul-text excluded. |
| `get_daemon(base_path, *, daemon_id, include_soul=False)` | One daemon by ID; `include_soul=True` opts into the full soul_text payload. |
| `summon_daemon(base_path, *, daemon_id, universe_id, provider_name, model_name, ...)` | Spawn a runtime instance bound to an existing daemon. Enforces model-binding gate (§3.b). |
| `banish_daemon(base_path, *, runtime_instance_id)` | Retire a runtime instance. Daemon identity persists; only this runtime is gone. |
| `list_runtime_instances(base_path, *, universe_id=None)` | All currently-known runtime instances, optionally filtered. |
| `control_runtime_instance(base_path, *, runtime_instance_id, actor_id, action)` | Apply ownership-scoped control: `pause | resume | restart | banish`. Returns `effect: applied | queued | refused`. |
| `update_daemon_behavior(base_path, *, daemon_id, actor_id, behavior_update, apply_now)` | Versioned behavior policy update; queueable as proposal or applied immediately. |
| `daemon_control_status(base_path, *, actor_id, daemon_id, runtime_instance_id, universe_id)` | Ownership-scoped read for chat/web surfaces. Filters daemons + runtimes by actor authority. |
| `select_project_loop_daemon(base_path, *, include_soul=False)` | Picks the latest soul-bearing daemon flagged `project_loop_default`. Returns None if no such daemon exists; the autonomous loop falls back to soulless. |
| `provider_capacity_warning(provider_name, *, running_count)` | **Advisory only.** Returns `{severity: 'warning', can_override: True, ...}`; never blocks. See §3.d. |
| `build_requester_directed_daemon_assignment(base_path, *, daemon_id, requester_id, patch_request_id, instruction)` | Validate authority + return proposal-only routing metadata for patch-request pickup. Always `scope: 'proposal_only'`; never affects acceptance/release/merge. |

### 2.d. Returned daemon dict shape

```python
{
    "daemon_id": "daemon::lab-navigator::ab12cd",
    "legacy_author_id": "author::lab-navigator::ab12cd",
    "display_name": "Lab Navigator",
    "soul_hash": "<sha256 hex>",
    "soul_mode": "soul" | "soulless",
    "has_soul": bool,
    "domain_claims": ["scientist", "literature-review"],
    "owner_user_id": str,
    "tenant_id": str,
    "lineage_parent_id": "daemon::..." | None,
    "reputation_score": float,
    "created_at": iso8601,
    "metadata": dict,        # may carry: project_loop_default, current_llm,
                             # delegated_hosts, behavior_policy, behavior_updates,
                             # daemon_wiki, ...
    # only when include_soul=True:
    "soul_text": str,
}
```

### 2.e. Returned runtime dict shape

```python
{
    "runtime_instance_id": str,
    "daemon_id": str,
    "legacy_author_id": str,
    "universe_id": str,
    "provider_name": str,
    "model_name": str,
    "branch_id": str | None,
    "status": "provisioned" | "paused" | "restart_requested" | "retired",
    "created_by": str,
    "owner_user_id": str,
    "tenant_id": str,
    "created_at": iso8601,
    "updated_at": iso8601,
    "metadata": dict,        # carries daemon_id, daemon_soul_hash,
                             # daemon_soul_mode, domain_claims, last_control_*
}
```

## 3. Key invariants future SHIP-gates must preserve

These are the load-bearing invariants. Any patch that adds a write path or extracts a fast-path must keep all of them.

### 3.a. Duplicate `soul_hash` requires `lineage_parent_id`

Test: `test_duplicate_soul_hash_requires_lineage`. `create_daemon` rejects a soul-bearing daemon whose `soul_hash` collides with an existing daemon UNLESS the new daemon explicitly cites `lineage_parent_id`. This is the fork-or-rename invariant — copying a soul without recording the lineage breaks fork attribution and the contribution ledger.

**Guard:** any code path that writes a soul row must run through `create_daemon`, OR replicate the duplicate-check logic verbatim. Don't extract a "fast" insert path.

### 3.b. Model-binding gate at summon

Test: `test_summon_rejects_model_mismatch_for_bound_daemon`. When a daemon's metadata pins a model identity (any of `current_llm` / `fixed_llm` / `pinned_llm` / `active_llm` / `allowed_llms`), `summon_daemon` raises `ValueError("daemon model identity mismatch: ...")` if the requested `model_name` isn't in that list. Pinned daemons can only run on their declared LLM(s).

**Guard:** any new runtime-instance creation path that bypasses `summon_daemon` must replicate this gate — or it's adding a way to run a daemon on a model its soul wasn't authored against.

### 3.c. Authority scope is REFUSED, not RAISED

`control_runtime_instance`, `update_daemon_behavior`, and `build_requester_directed_daemon_assignment` all return `effect="refused"` for unauthorized actors instead of raising. This keeps caller-side error handling uniform and lets the control surfaces compose into ownership-scoped UI without per-call try/except.

**Guard:** don't promote refused → raised without a wide-scope review. The four control responses (`applied | queued | refused | <other>`) ARE the contract.

### 3.d. `provider_capacity_warning` is advisory, NOT blocking

`can_override: True` is part of the contract. The function returns advisory text with explicit override permission. **Workflow does not cap host fleet size** per host directive 2026-05-01 (PLAN.md L147).

**Guard:** any patch that promotes this to a hard cap regresses the host-directed product decision. The shape of the warning dict can evolve; the `can_override: True` semantics cannot.

### 3.e. All public functions call `daemon_server.initialize_author_server(base_path)` first

The transitional storage backend requires it. Any extracted helper must keep that initialization step or risk hitting a half-initialized substrate.

### 3.f. Mirror parity required

`workflow/daemon_registry.py` ↔ `packaging/claude-plugin/plugins/workflow-universe-server/runtime/workflow/daemon_registry.py` must stay 0-line diff per `feedback_run_build_plugin_after_canonical_edits`. As of 2026-05-01 audit: 0-line diff confirmed.

## 4. 5-mode soul-eligibility shape (node/gate level, NOT here)

This module owns the **2-mode** discriminator at the daemon-identity level: `soul | soulless`. The **5-mode** soul-eligibility lives at the **node and gate** level — it's the per-work declaration of which souls are eligible to claim that work. From PLAN.md L217 + `docs/vetted-specs.md` "Per-node/gate soul_policy field":

| Mode | Shape | Behavior |
|---|---|---|
| `allow_host_soul` | allowed | Default. Daemon's soul is permitted; prompt composes daemon soul + node body. |
| `forbid_daemon_soul` | forbidden | Daemon soul stripped from prompt. Node runs as-if soulless regardless of which daemon claimed it. |
| `insist_node_soul` | required | Only soul-bearing daemons may claim. Soulless daemons are filtered out at dispatch. |
| `append_node_header` | combined | Daemon soul retained AND a temporary node-supplied soul header is prepended. Non-persistent; per-node only. |
| `hybrid` | replaced | Node ships its own `node_soul: str` that fully replaces the daemon's soul for this node only. |

Plus optional `domain_requirements` (e.g., `scientist | legal | artistic | local-model-only | <community-defined>`) on any of those modes — claim-time verification checks the daemon's `domain_claims` against the node's requirements.

**Why this lives at node/gate, not on the daemon:** the daemon declares what it IS (one identity, one soul, with claimed domains). The node/gate declares what it WANTS. Pushing soul-eligibility into the daemon would force every daemon to enumerate every node it can run; pushing it into the node lets nodes filter the daemon space declaratively.

This module's `domain_claims` field on the daemon dict is the input side of that match; the corresponding output side (the node/gate's soul_policy + domain_requirements) lives in `docs/vetted-specs.md` "Per-node/gate soul_policy field" and has not yet shipped to code.

## 5. Extension points (forward-pointing)

The substrate is deliberately incomplete. The following extensions are promised by adjacent design notes and have not yet shipped:

### 5.a. Capacity grants (per `2026-05-01-hostless-byok-cloud-daemon-capacity.md`)

A user-side "I authorize Workflow's cloud capacity to run my daemons under these constraints" object: bounded budgets, schedule windows, allowed providers/keys, max spend/concurrency, kill switches. Today's `daemon_registry.py` has no concept of "where this daemon's capacity comes from"; capacity-grants will be the new substrate that resolves this for cloud-executed BYOK daemons.

**Extension hook:** `summon_daemon` is the natural seam — its `provider_name` + `model_name` + `created_by` arguments will gain a `capacity_grant_id` parameter that resolves to a tenant-bounded permission object. The model-binding gate (§3.b) becomes one of N constraints under the grant.

### 5.b. Control intents (per same)

Today's `control_runtime_instance` is a synchronous direct-write. The hostless-byok design splits this into "control intent" (an owner-scoped command record, durable) + "activation" (the executor-backend's pickup of the intent). This becomes important when the executor backend is cloud-executed and the user's authoring chat is async to the runtime.

**Extension hook:** `control_runtime_instance` would gain a return shape that says `effect: queued` more often and `effect: applied` less often, and a separate poll surface would surface "your last 5 control intents and their pickup status."

### 5.c. Executor backends (per same)

Today the registry is implicitly bound to one backend (the local `daemon_server` substrate). The hostless-byok proposal abstracts this: cloud-executed BYOK and local-tray are TWO backends behind one daemon-identity surface.

**Extension hook:** `summon_daemon` would gain `executor_backend: 'local-tray' | 'cloud-byok' | <future>` parameter; the runtime dict gains the same field; control-intents route by backend.

### 5.d. Soul-guided dispatch (per PLAN.md L219)

Today's daemon does not have a "decision step" between work units — it claims via the dispatcher and runs. The future shape: a soul-bearing daemon, after finishing a node/gate, returns to a decision step listing all eligible work (per soul + domain claims + grant + offer) and chooses by soul-encoded preferences (highest money, public-good impact, refusal, etc.).

**Extension hook:** `daemon_registry.py` doesn't change for this; it provides the inputs (`soul_text`, `domain_claims`, `behavior_policy`). The decision step will live in a new module that consumes the registry's daemon dict.

## 6. Tests as contract pins

`tests/test_daemon_registry.py` (12 tests, 271 LOC on origin/main) pins the public contract. Patterns:

- **`tmp_path`-scoped, no shared SQLite.** Per-test daemon creation. Each test gets a fresh substrate.
- **Positive + ValueError pair for each new invariant.** Tests that name an invariant in their function name (`test_duplicate_soul_hash_requires_lineage`, `test_summon_rejects_model_mismatch_for_bound_daemon`) carry both directions.
- **Round-trip tests:** create → list → get → summon → banish.
- **Authority-scoped tests** assert `effect` strings (`applied | queued | refused`) rather than raising, matching §3.c.
- **`metadata.daemon_soul_hash` round-trip** confirms soul provenance carries through to runtime.

The test file is itself documentation: when proposing a patch that changes any public function, read the corresponding test first.

## 7. Out of scope (not this module's job)

- **Runtime activation orchestration.** Whether a runtime instance's `provider_name` actually gets a process running is the executor backend's job (today: tray; future: cloud worker). The registry tracks identity + status, not process lifecycle.
- **Soul authoring UX.** Where soul.md files live on disk, how they're edited, how the host curates a roster — `docs/plan-drafts/2026-04-22-daemon-identity-and-economics.md` + the deferred "Daemon roster + soul.md authoring surface" spec own this.
- **Paid-market bidding mechanics.** `build_requester_directed_daemon_assignment` is `scope: 'proposal_only'`; it never affects ledger settlement. The full bid/claim/settle path lives in `workflow/bid/` (per Module Layout L116).
- **Node-level soul_policy + domain_requirements.** §4 shape, lives at node/gate level. Not yet shipped.
- **Capacity grants, control intents, executor backends.** §5. Forward-pointing only.
- **Chat-surface presentation of daemon control state.** `daemon_control_status` returns the data; how chat renders it is a separate UX layer.

## 8. Scoping Rule 1 audit (minimal-primitives lens)

Scanning the public surface for fields/methods that look like convenience-over-primitive — flagged for future cleanup, NOT for immediate change:

- **Three near-duplicate "control intent" emitters** — `control_runtime_instance`, `update_daemon_behavior`, `build_requester_directed_daemon_assignment` all share `_control_result(...)` shape and authority-check pattern. When the §5.b control-intent abstraction lands, these three could collapse into one dispatch over a typed control-intent enum. Today: three explicit functions are clearer; future: one primitive.
- **`PROJECT_LOOP_FLAG` is one of three project-loop signals** — `_is_project_loop_daemon` checks `project_loop_default` flag OR (`project_default` AND `loop_primary`). Three keys mean three migration paths; the spec answer is one canonical key. Cleanup target when the host-curated roster surface lands.
- **`_daemon_model_binding` reads four metadata keys for the same concept** — `current_llm`, `fixed_llm`, `pinned_llm`, `active_llm` plus `allowed_llms` list. This is the same convenience drift; canonicalize to one key (probably `allowed_llms: list[str]`) when the model-binding contract is next touched.
- **`reputation_score` is in the daemon dict but no public function writes it.** Reads exist (it's exposed at `_daemon_from_author`), writes presumably live in the patch-request / paid-market settlement path. If reputation is part of the daemon contract, the write surface should also live in this module. Otherwise demote to "metadata-only field" and remove from the typed return.

None of these are bugs. All are minimal-primitives debt that becomes worth paying as adjacent features land.

---

**Cross-refs:**
- Verifier-internal review notes: `.claude/agent-memory/verifier/reference_daemon_registry_shape.md`.
- Forward-pointing extension target: `docs/design-notes/2026-05-01-hostless-byok-cloud-daemon-capacity.md`.
- Soul-eligibility 5-mode spec: `docs/vetted-specs.md` "Per-node/gate soul_policy field".
- PLAN.md principles: L143-147 (daemon identity), L208-225 (multiplayer platform), L217-219 (soul eligibility + dispatch).
- Memory cross-link: `project_daemon_identity_platform_wide.md`, `project_many_daemon_fleets_warning_only.md`, `project_daemons_are_multi_tenant_by_design.md`, `project_daemon_souls_and_summoning.md`.
- Canonical commit chain: `f96d18f` → `dcedcc9` → `bdac185` → `6e65a3f` → `6b87879` → `aa4ea2d` → `0e44688` → `e1a93a1` (8 commits, 2026-04 → 2026-05).
