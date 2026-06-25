# Fantasy-architecture residue audit (de-privileging plan)

**Filed:** 2026-06-24 · **Environment:** origin/main checkout (worktree
`defantasy-and-mcp-readpath`), verified by direct file reads.
**Trigger:** founder-led live connector session 2026-06-25 (Issue 1) + host
hypothesis: "the platform may still be acting like the old fantasy-only
single-pipeline architecture, not just reading like it."

**Status:** diagnostic. No code changed by this audit. Tier-A/B fixes touch the
production worker spawn path and the universal LLM-call seam → they require the
opposite-provider (Codex) review gate per AGENTS.md before any code lands.

---

## Verdict

The hypothesis is correct. Fantasy is **not** yet one goal indistinguishable
from "research paper" or "legal brief" in the code — it is the hardcoded
default, fallback, and only-executable runtime. The general seams exist and
work (`workflow/providers/`, `graph_compiler`, soul-declared loops,
`DomainNeutralUniverseState`), but the engine still reaches *back into the
fantasy domain folder* for its most fundamental primitive (the LLM call), and
the production entrypoints still spawn the fantasy daemon directly instead of
the universe's declared loop.

The good news: almost none of this is "build new." The general homes already
exist. The work is **relocate the primitive + invert the dependency + route
execution through the soul-declared loop that's already there.**

---

## Tier A — Dependency inversion: the engine imports its LLM primitive from the domain (CORE)

`domains/fantasy_daemon/phases/_provider_stub.py` is, by its own docstring, a
general *"Provider bridge for graph nodes... Routes all LLM calls through the
real `ProviderRouter`"* — a thin synchronous wrapper over
`workflow.providers.router.ProviderRouter`. Its docstring even claims "This
module lives in `nodes/` (graph-core's directory)" — a stale relic of an
earlier location; it now sits inside the fantasy domain. The general provider
package **already exists and is complete**: `workflow/providers/` (router.py,
base.py, claude/codex/gemini/grok/groq/ollama_provider.py, quota.py).

Yet the general engine imports `call_provider` / `last_provider` / `_FORCE_MOCK`
from the fantasy-located shim across the whole platform:

| Engine module (general) | Site | Imports from fantasy domain |
|---|---|---|
| `workflow/api/runs.py` | `:542`, `:1110`, `:1520` | `_provider_stub.call_provider` (the general `run_branch`/run path) |
| `workflow/api/selector_dispatch.py` | `:733` | `_provider_stub.call_provider` |
| `workflow/evaluation/editorial.py` | `:119` | `_provider_stub.call_provider` |
| `workflow/ingestion/extractors.py` | `:259`, `:260` | `_provider_stub.call_provider` **and** `phases.worldbuild._write_canon_file` |
| `workflow/retrieval/agentic_search.py` | `:182`, `:381`–`:387` | `_provider_stub` + `phases._paths.resolve_kg_path` |
| `workflow/memory/reflexion.py` | `:205`, `:260` | `_provider_stub.call_provider` |
| `workflow/knowledge/raptor.py` | `:333` | `_provider_stub.call_provider` |
| `workflow/checkpointing/sqlite_saver.py` | `:172` | `domains.fantasy_daemon.graphs` (graphs, not provider — scope separately) |

**Why this is the "single fantasy pipeline" signal:** the general platform was
carved out of the fantasy daemon, but the LLM-call seam was never relocated.
Every general subsystem (runs, evaluation, ingestion, retrieval, memory,
knowledge, selector) depends on a domain package to talk to a model.

**Fix (atomic, no-shims per `feedback_no_shims_ever`):**
1. Move the provider bridge to the general home, e.g. `workflow/providers/call.py`,
   wrapping `ProviderRouter` exactly as today. **Expose an explicit API**
   (`set_provider_router()` / `call_provider()` / `get_last_provider()`), NOT
   bare module globals. Two traps the relocation must preserve (Codex review):
   - **Daemon router injection.** `DaemonController.start()` overwrites
     `stub._real_router` with its fully-configured instance — today via the
     star-import shim `fantasy_daemon/nodes/_provider_stub.py`. The move must
     keep the daemon-injected router the one `call_provider()` actually uses;
     add a test proving it. Naively relocating the module can sever this.
   - **`last_provider` is a string snapshot, not a live binding.**
     `from ... import last_provider` binds a value; later reassignment in the
     bridge never reaches callers (e.g. `ingestion/extractors.py:259`). Replace
     with an accessor (`get_last_provider()`) or response metadata in the move.
2. Repoint every engine import above to the general module in the same arc.
3. Delete `domains/fantasy_daemon/phases/_provider_stub.py`; the fantasy domain
   imports the general primitive like any other domain would.
4. `checkpointing/sqlite_saver.py:172` (imports `domains.fantasy_daemon.graphs`)
   is a separate engine→domain inversion — read its usage and scope its own
   fix; do not bundle blindly.

**Additional residue surfaced in review (Codex 2026-06-24) — fold into the move:**
- `workflow/exceptions.py:8` — the *entire* platform exception hierarchy
  inherits from a base class named `FantasyAuthorError` ("Every exception in the
  system inherits from FantasyAuthorError"). Rename to a neutral base
  (e.g. `WorkflowError`) with the fantasy name as a same-arc alias only.
- `workflow/registry.py:13` — imports `FantasyAuthorDomain` (registration site).
- `workflow/memory/episodic.py:27` — `FANTASY_DOMAIN_ID = "fantasy_author"` +
  `WORKFLOW_EPISODIC_SCHEMA_MIGRATION` flag (fantasy-keyed episodic schema mid-
  migration to neutral — coordinate with that migration, don't fork it).

Risk: medium. Mostly relocation + import repoint, behavior-preserving — but the
router-injection and `last_provider` traps above make it NOT a blind move.
Covered by the existing provider/router test surface plus the two new tests
above.

---

## Tier B — Execution hardwired to fantasy (PRODUCTION PATH — review-gated)

Two production entrypoints refuse to run anything but fantasy:

- **`workflow/__main__.py:164`** — the general CLI hard-gates:
  `if args.domain != "fantasy_author": ... "Only fantasy_author domain is fully
  operational in this phase" ... return 1`. The comment admits it: *"Phase 5
  bridge: for now, delegate to fantasy_daemon.__main__.DaemonController... Once
  the runtime is extracted, this will build and execute the domain's graph
  directly."* The extraction never happened — non-fantasy domains can be
  *registered* but not *executed*.
- **`workflow/cloud_worker.py:359 / 516 / 533 / 535`** — the production
  supervisor loop default-spawns `_spawn_fantasy_daemon` for every universe
  ("Spawn fantasy_daemon against the universe"). This is the live 24/7 worker.

**Fix — activate + harden the path that already exists (do NOT build a second
runner).** Codex review surfaced that the soul-loop execution path is already
written and ships dark: `fantasy_daemon/__main__.py:154`
`_soul_loop_dispatch_enabled()` (`WORKFLOW_SOUL_LOOP_DISPATCH`) runs a souled
universe's declared `loop_branch_def_id` (resolved via `_universe_loop_dispatch`)
through `execute_branch` — the same path that runs claimed BranchTasks, so it
inherits heartbeat, leases, producer pumping, status files, runtime
registration, and finalize semantics. There is an existing activation plan:
`docs/design-notes/2026-06-03-soul-loop-dispatch-activation-plan.md`. The Tier-B
work is to **harden and default-on that flagged path**, then make
`__main__.py:164` / `cloud_worker.py` route through it — NOT to write a new
graph runner that would bypass those invariants (re-introducing the
double-finalize / wedged-loop class from the 2026-06-25 incident noted in
`_dispatcher_startup`).

Risk: HIGH — live worker spawn path. Per AGENTS.md: opposite-provider review
before code lands (done — see Review record), §14 concurrency/load proof + a
public canary after rollout, and staged behind the universe's soul so existing
soulless/legacy universes keep running unchanged during cutover.

---

## Tier C — Fantasy-as-default fallback (compat seams, lower risk)

- **`workflow/api/universe.py:337`** — soul-less universe falls back to
  `LEGACY_FANTASY_LOOP_BRANCH_DEF_ID` (caveat: *"keeping the existing fantasy
  loop only until the universe is migrated to a soul-declared loop"*). The
  fallback for *any* domain-less universe is the fantasy loop.
- **`workflow/producers/goal_pool.py:197`–`200`** — *"Fantasy seed always
  available"* unconditionally injects `fantasy_author/universe-cycle` and
  `fantasy_author:universe_cycle_wrapper` into the goal-pool slug set.

**Fix:** make the fallback domain-neutral (no declared loop → explicit
`NO_LOOP` / require-soul, not silent fantasy) and make any always-available
seed configurable rather than fantasy-hardcoded. Follows Tier A/B.

---

## Tier D — Fantasy vocabulary baked into validated primitives (NOT a prose edit)

This is the subtlest residue: probe-origin words that became *enforced engine
contract*, so they cannot be scrubbed in docs without code/data migration.

- **`worldbuild` is a validated enum, not a label.** It is a member of
  `VALID_PHASES` in both `workflow/branches.py:256` and
  `workflow/api/extensions.py:214`, enforced at node registration
  (`extensions.py:764`, `branches.py:412`) and on the advertised control-station
  surface (`workflow/universe_server.py:321`). It also names a **persisted
  artifact** — `worldbuild_signals.json` (`workflow/ingestion/core.py:474`) —
  and threads through `notes.py`, `packets.py` (`worldbuild_signals`),
  `api/universe.py:308` (`daemon_worldbuild`). Removing it from the advertised
  enum without changing `VALID_PHASES` creates doc/code drift; removing it from
  `VALID_PHASES` breaks existing nodes and orphans persisted signal files.
  → **Migration, not a string edit:** introduce a domain-neutral phase name,
  dual-accept during a deprecation window (note: violates no-shims unless the
  alias is removed same-arc — scope deliberately), migrate persisted
  `worldbuild_signals.json`, then drop the old name.
- **`premise` / `canon` are first-class universe-state fields**, surfaced as
  workflow MCP tools (`get_premise` / `set_premise` / `add_canon`) and legacy
  tool-list text (`universe_server.py:791`, `:793`). Renaming is a state-schema
  migration, not a doc rewrite.

**Done in the companion docs pass (safe, prose-only — no code/data contract):**
- `PLAN.md:13` — removed the "fantasy is the first playful benchmark domain"
  framing; replaced with a no-privileged-domain principle + pointer here.
- `README.md:32` — reframed `fantasy_daemon/__main__.py` as the *current
  reference runtime* (goal-agnostic loop via `graph_compiler`) + pointer here,
  instead of presenting it as the canonical/only run loop.

**Deliberately NOT touched (would create drift or hit host-curated state):**
- `worldbuild` / `premise` / `canon` validated primitives — migration track
  above, not prose.
- `STATUS.md` fantasy rows (Castles II / Echoes — BUG-038/039) are live work
  items, host-curated; not positioning contamination.
- Remaining `PLAN.md` vocabulary (worldbuild/scene/chapter in module specs)
  follows the primitive migration, since the prose describes real enum/state
  names.

**Fix ordering:** the validated-primitive migration rides with Tier A/C (it is
state + enum surgery), and must not be faked as a doc scrub.

---

## Suggested sequencing

1. **Tier A** first — relocate the provider bridge + repoint imports + add the
   `workflow/** !-> domains.fantasy_daemon` import-boundary guard. Behavior-
   preserving; unblocks honest generality and prevents regression.
2. **Tier D** (live wire vocab) alongside the docs rewrite — cheap, stops the
   re-infection loop.
3. **Tier C** — neutralize the fallbacks.
4. **Tier B** last and review-gated — extract the runtime so `__main__` /
   `cloud_worker` execute the universe's soul-declared graph. Production worker
   path: Codex review + concurrency proof + post-rollout canary required.

## Prevention (stop the residue from returning)

Add an architectural import-boundary test/lint: nothing under `workflow/` may
`import domains.fantasy_daemon` (or any `domains.*`). The engine depends on the
domain registry interface, never on a concrete domain. This guard makes "engine
acting like the fantasy pipeline" a failing test instead of a discovered
surprise.

**Stage it (Codex review):** a broad guard fails immediately on every Tier-A/C
site still present (`registry.py`, `sqlite_saver.py`, `extractors.py`,
`agentic_search.py`, …). Land it as a **ratcheted guard with an explicit
shrinking allowlist** of known-remaining offenders, or move those sites first —
so the guard goes green as each tier lands and can never regress, rather than
being a single all-or-nothing flip.

## Review record (opposite-provider gate — SATISFIED)

Per AGENTS.md (architecture-derived change → opposite-provider review): this
audit (Claude Code) was reviewed by **Codex on 2026-06-24**, which independently
re-verified every Tier A–D file:line against the checkout.

**Verdict: ADAPT** — core finding confirmed and judged *understated*. The six
adaptations above are folded in: (1) added residue (`exceptions.py`
`FantasyAuthorError`, `registry.py:13`, `memory/episodic.py` migration);
(2) explicit `set_provider_router`/`get_last_provider` API + preserve daemon
router injection; (3) `last_provider` snapshot bug; (4) staged/ratcheted import
guard; (5) Tier B = harden the existing dark `WORKFLOW_SOUL_LOOP_DISPATCH` path,
not a new runner; (6) README wording softened. Tier-A/B code may proceed under
these adaptations; each lands with its own tests + (Tier B) the §14 proof +
canary.

**Companion write-path review (Issue 3) — CONFIRMED.** Codex confirmed
"No approval received" is absent from server source, `submit_request` has no
approval handshake, and anonymous public-universe writes succeed by design.
Adaptation: do **not** blanket-flip `openWorldHint`. `write_graph`
`openWorldHint=False` is a defensible experiment (bounded, non-destructive
Workflow-state write); public wiki/gates/extensions ("publishes outside the
caller's account") may keep `True`. The flip is also a test-contract change
(`tests/test_universe_server_five_handles.py:32` pins it) and is gated on a
host-watched `ui-test` that captures the connector approval prompt, then an A/B
deploy of only `write_graph.openWorldHint=False` re-tested through the rendered
chatbot. If the bare error still precedes `tools/call`, it is connector-side —
file upstream with the transcript.
