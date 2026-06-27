---
status: shipped
shipped_date: 2026-04-13
shipped_in: ba83254  # Phase C.3: TaskProducer protocol + registry (no producers yet)
---

# Phase C — TaskProducer Protocol + execution_kind Genericization

**Status:** spec-first — planner-authored, awaiting reviewer audit then dev claim.
**Depends on:** Phase A (naming disambiguation landed), Phase B (materialize_pending_requests seed shipped in `#18`).
**Unblocks:** Phase D (fantasy-as-Branch) cleanly — Phase D's registered Branch reads from producers, not from direct `choose_authorial_targets` call.
**Rollout plan anchor:** `docs/exec-plans/daemon_task_economy_rollout.md` §Phase C.
**Design memo anchor:** `docs/planning/daemon_task_economy.md` §3.2, §4.6.

---

## Thesis

Today the fantasy daemon's "what should I work on next" decision is hardcoded: `universe.py` calls `choose_authorial_targets` which reads `work_targets.json` directly. The newly-landed `#18` `materialize_pending_requests` added a second work source, but it's wired in as a one-off — a direct call from the controller, not a pluggable seam.

Phase C formalizes the seam. A **TaskProducer** is any function that reads universe state and emits WorkTarget candidates. The daemon runs a list of producers each cycle, merges their output, and feeds the merged set to the existing review/selection pipeline. Fantasy-specific selection logic becomes one producer among many; user-defined producers become possible.

This is the smallest refactor that unlocks Phase D, F, G — each of those phases adds producers (Goal-pool reader, NodeBid reader, opportunistic housekeeping generator) without touching core daemon code.

---

## Non-goals (explicitly deferred)

- **No user-facing producer-registration MCP surface.** Producers register programmatically in Phase C. Chat-level `register_producer` is a future UX pass.
- **No cross-universe producers.** Every Phase C producer reads from one `universe_path`. Goal-pool and NodeBid producers (Phase F/G) break this by reading repo-root state; they extend the protocol then, not now.
- **No priority scoring in producers.** Producers emit candidates; the existing `choose_authorial_targets` scorer decides which to actually run. Phase C does NOT move the scoring logic.
- **No retrofit of `work_targets.json` schema beyond adding `origin`.** Lifecycle, role, publish_stage, selection_reason all stay as they are.

---

## 1. TaskProducer protocol

### Shape

```python
from typing import Protocol, runtime_checkable
from pathlib import Path
from workflow.work_targets import WorkTarget


@runtime_checkable
class TaskProducer(Protocol):
    """Produces candidate WorkTargets for one universe's daemon cycle.

    Called once per daemon cycle (before review gates run). Must be
    idempotent: calling twice with unchanged inputs returns the same
    WorkTarget set. Producers MAY upsert targets into the universe's
    `work_targets.json`, but MUST return only the targets produced or
    updated by this call — callers use the return value to attribute
    origin and log what each producer contributed.

    v1 protocol is synchronous; Phase F may introduce an async variant
    for cross-universe producers that read repo-root state with I/O
    latency. Synchronous design is deliberate for v1 — simpler
    contract, easier ON/OFF identity testing.
    """

    name: str
    """Stable identifier. Logged per produced target. Must match
    `[a-z][a-z0-9_-]*`. Example: "fantasy_authorial", "user_requests",
    "seed", "goal_pool", "node_bid", "opportunistic"."""

    origin: str
    """The `WorkTarget.origin` value this producer stamps on every
    emitted target. Must be one of the allowed origin values (§3).
    A single producer always stamps one origin — producers don't
    commingle origin values."""

    def produce(
        self,
        universe_path: Path,
        *,
        config: dict | None = None,
    ) -> list[WorkTarget]:
        """Read universe state, return candidate WorkTargets.

        `config` is a producer-specific dict passed from the daemon's
        config file — lets producers take parameters without needing
        constructor args. Producers that need no config ignore it.

        Raises: should NOT raise on empty state — return []. MAY raise
        on genuinely corrupt state (unreadable JSON, missing required
        files); the daemon logs and skips to the next producer.
        """
        ...
```

### Registry

Producers register via a module-level list, loaded at daemon startup:

```python
# tinyassets/producers/__init__.py
_registered: list[TaskProducer] = []

def register(producer: TaskProducer) -> None:
    """Add a producer to the active list. Idempotent on producer.name."""
    global _registered
    _registered = [p for p in _registered if p.name != producer.name]
    _registered.append(producer)

def registered_producers() -> list[TaskProducer]:
    return list(_registered)
```

Domain modules import `workflow.producers` and call `register()` in their `__init__`. Fantasy registers three producers (see §5). User-defined producers (future) register the same way via an extensions surface.

**Registration order IS dispatch order; later producers overwrite earlier ones on `target_id` collision.** This pins identity-test determinism: with the same registration order, the same inputs produce the same merged candidate set — a prerequisite for the §5 ON/OFF byte-identity test.

### Dispatcher integration

The daemon's per-cycle loop changes from:

```python
# BEFORE (conceptual)
targets = choose_authorial_targets(universe_path)
```

to:

```python
# AFTER
produced: list[tuple[str, WorkTarget]] = []  # (producer.name, target)
for producer in registered_producers():
    try:
        for target in producer.produce(universe_path, config=producer_config.get(producer.name)):
            target.origin = producer.origin  # enforced stamp
            produced.append((producer.name, target))
    except Exception as exc:
        logger.warning("producer %s failed: %s", producer.name, exc)
        continue

# Merge: producers may upsert the same target_id. Last-write-wins on
# target_id collisions, with a warning — this should be rare and is a
# producer-config bug if it happens.
merged = _merge_produced(produced)

targets = choose_authorial_targets(universe_path, candidate_override=merged)
```

`choose_authorial_targets` gains an optional `candidate_override` parameter. When set, it skips the direct `load_work_targets` read and scores the provided list instead. When `None`, behavior is unchanged — backward compatible with call sites that don't know about producers.

---

## 2. execution_kind genericization

### Current state (the leak)

`tinyassets/work_targets.py:51-54`:

```python
EXECUTION_KIND_NOTES = "notes"
EXECUTION_KIND_BOOK = "book"
EXECUTION_KIND_CHAPTER = "chapter"
EXECUTION_KIND_SCENE = "scene"
```

Plus `infer_execution_scope` matches strings against these constants. Plus `tinyassets/work_targets.py:381` hardcodes `EXECUTION_KIND_BOOK` when ensuring a seed target.

`BOOK`/`CHAPTER`/`SCENE` are fantasy-authoring concepts. `NOTES` is domain-neutral. The mix is a classic leak: a second domain (research-paper, legal-brief) would never produce a `SCENE`-kinded target but the generic module asserts it's a valid value.

### The split

Move domain-specific values to `domains/fantasy_author/work_kinds.py`:

```python
# domains/fantasy_author/work_kinds.py
from workflow.work_targets import EXECUTION_KIND_NOTES  # re-export

EXECUTION_KIND_BOOK = "book"
EXECUTION_KIND_CHAPTER = "chapter"
EXECUTION_KIND_SCENE = "scene"

FANTASY_EXECUTION_KINDS = (
    EXECUTION_KIND_NOTES,
    EXECUTION_KIND_BOOK,
    EXECUTION_KIND_CHAPTER,
    EXECUTION_KIND_SCENE,
)
```

`tinyassets/work_targets.py` keeps only `EXECUTION_KIND_NOTES` (every domain has notes-class work; it's the minimum viable value).

`WorkTarget.execution_kind` field stays `str`. No enum type enforcement at the dataclass level — the generic module doesn't know what values are valid.

### Validation

Validation shifts to the producer layer. Each producer that emits non-NOTES targets does so knowing the domain's valid set. `FantasyAuthorialProducer` asserts outputs are in `FANTASY_EXECUTION_KINDS`. Generic validation in `tinyassets/work_targets.py` becomes: "execution_kind must be a non-empty string."

### infer_execution_scope migration

`tinyassets/work_targets.py:793` currently hardcodes the four-kind match. Move to `domains/fantasy_author/work_kinds.py:infer_fantasy_execution_scope`. Generic module loses `infer_execution_scope` entirely — callers (all fantasy) update imports.

### Call-site migration

grep for `EXECUTION_KIND_BOOK`, `EXECUTION_KIND_CHAPTER`, `EXECUTION_KIND_SCENE`, `infer_execution_scope`. All hits live in `domains/fantasy_author/` and `tinyassets/work_targets.py` itself. Update imports:

```python
# before
from workflow.work_targets import EXECUTION_KIND_BOOK, infer_execution_scope
# after
from domains.fantasy_author.work_kinds import (
    EXECUTION_KIND_BOOK,
    infer_fantasy_execution_scope,
)
```

Mechanical, test-covered, no behavior change.

---

## 3. `origin` field on WorkTarget

### Semantics

`origin` records **which producer emitted this target in its current form**. Not an immutable history — if two producers upsert the same `target_id`, the last one wins and its `origin` is stamped (with a log warning). This is intentional: callers use `origin` to attribute display ("this target came from `user_requests`") and to route tier decisions in Phase E.

### Allowed values (v1)

- `"seed"` — emitted by `ensure_seed_targets` on first universe bootstrap. Universe-notes + book-1-from-premise.
- `"fantasy_authorial"` — emitted by the fantasy authorial-priority producer (wraps existing `choose_authorial_targets` logic).
- `"user_request"` — emitted by the request producer (wraps `#18`'s `materialize_pending_requests`).
- `"host_request"` — reserved; future Phase E producer.
- `"goal_pool"` — reserved; future Phase F producer.
- `"node_bid"` — reserved; future Phase G producer (NodeBids, not BranchTasks — distinct executor).
- `"opportunistic"` — reserved; future Phase F/H producer (housekeeping, KG rebuild).

**Excluded:** `source_synthesis` is NOT an origin value. `sync_source_synthesis_priorities` writes `HardPriorityItem`, not `WorkTarget` (see §4). `origin` is a WorkTarget-only field; HardPriorityItems live in a separate stream and don't flow through the producer interface in Phase C.

### Default

`origin: str = "unknown"` on the dataclass. Legacy targets in existing `work_targets.json` files load with `"unknown"` until a producer re-emits them. No data migration required — the field is read-where-present, default-where-absent.

### Enforcement

- Each `TaskProducer.origin` attribute declares the value. The dispatcher's `target.origin = producer.origin` line is authoritative — if a producer tries to emit a target with a different `origin` set, the dispatcher overrides.
- `"unknown"` is never emitted by a producer. It only appears on legacy un-re-emitted rows.

### Schema

```python
# tinyassets/work_targets.py
@dataclass
class WorkTarget:
    # ... existing fields ...
    origin: str = "unknown"
```

No new table, no migration. JSON serializer handles the field additively — old files load with default, new writes include the field.

---

## 4. `sync_source_synthesis_priorities` stays where it is

This function already exists at `tinyassets/work_targets.py:663` and writes `HardPriorityItem` for unsynthesized uploads. It is also fantasy-adjacent (uploads → synthesis is fantasy's data-intake pattern) but because it writes `HardPriorityItem` not `WorkTarget`, it is NOT a TaskProducer in the Phase C sense. Leave it alone. A future refactor may convert `HardPriorityItem` emission into a producer too, but that's orthogonal — `origin` is a WorkTarget-only field and never stamped on HardPriorityItems.

---

## 5. Fantasy registers three producers

At fantasy domain init time (`domains/fantasy_author/__init__.py` or equivalent):

```python
from workflow.producers import register
from domains.fantasy_author.producers import (
    FantasyAuthorialProducer,
    UserRequestProducer,
    SeedProducer,
)

register(SeedProducer())
register(FantasyAuthorialProducer())
register(UserRequestProducer())
```

Each wraps existing logic:
- `SeedProducer.produce` wraps `ensure_seed_targets` with `origin="seed"`. Idempotent already.
- `FantasyAuthorialProducer.produce` wraps the existing authorial candidate-scoring pre-scoring step (not the scoring itself — that stays in `choose_authorial_targets`). `origin="fantasy_authorial"`.
- `UserRequestProducer.produce` wraps `materialize_pending_requests` directly. `origin="user_request"`.

**Sanity check:** with all three registered, a single cycle's producer run reproduces today's behavior exactly — same targets emitted, same scoring, same selection. Phase C is a refactor, not a behavior change. Test: the universe-cycle output must be **byte-identical with producers on/off (behind the flag) except for `updated_at` / timestamp fields**. The test normalizes timestamps before diffing — wall-clock drift between the two runs is the only legitimate difference.

---

## 6. Feature flag

`TINYASSETS_PRODUCER_INTERFACE=on` by default (per rollout plan §Phase C "Flag default ON"). When off, the daemon bypasses the producer list entirely and calls the old `choose_authorial_targets(universe_path)` path. This preserves revert capability if the producer interface misbehaves on a clean universe.

Tests must exercise both settings. CI runs both.

---

## 7. Testing

New test file `tests/test_task_producers.py`:
- `test_producer_protocol_is_runtime_checkable` — `isinstance(FantasyAuthorialProducer(), TaskProducer)` is true.
- `test_register_is_idempotent_on_name` — register twice, registry has one copy.
- `test_register_replaces_by_name` — register v1 then v2 of same name, registry has v2.
- `test_dispatcher_stamps_origin_from_producer` — producer returns target with `origin="wrong"`, dispatcher forces `origin=producer.origin`.
- `test_dispatcher_logs_and_skips_failing_producer` — a producer that raises is caught, other producers still run.
- `test_merged_candidates_last_write_wins_on_target_id` — two producers emit same target_id, dispatcher keeps the later one with a warning logged.
- `test_choose_authorial_targets_respects_candidate_override` — backward compat: passing a list skips the file read.

New test file `tests/test_execution_kind_generic.py`:
- `test_workflow_work_targets_only_exports_notes` — grep-equivalent assertion that `workflow.work_targets` has no `BOOK`/`CHAPTER`/`SCENE` constants.
- `test_fantasy_work_kinds_exposes_four_values` — `FANTASY_EXECUTION_KINDS` has the expected four.
- `test_infer_fantasy_execution_scope_still_works` — round-trip the same cases the old `infer_execution_scope` handled.

New test file `tests/test_work_target_origin.py`:
- `test_legacy_worktarget_loads_with_unknown_origin` — fixture-loaded pre-Phase-C JSON gets `origin="unknown"`.
- `test_new_worktarget_serializes_origin` — new write round-trips.
- `test_origin_values_are_strings_not_enum` — origin is `str`, not an Enum type.

Plus integration: `test_fantasy_universe_cycle_produces_identical_targets_with_flag_on_vs_off` — the load-bearing refactor safety test.

---

## 8. Rollout order (sub-phases inside Phase C)

1. **C.1** — Add `origin` field to `WorkTarget` dataclass. Existing tests pass with default `"unknown"`. Ship in isolation; no code reads `origin` yet.
2. **C.2** — Move `EXECUTION_KIND_BOOK/CHAPTER/SCENE` + `infer_execution_scope` to `domains/fantasy_author/work_kinds.py`. Update all callers. Generic module keeps only `EXECUTION_KIND_NOTES`. Tests pass.
3. **C.3** — Define `TaskProducer` protocol + registry + dispatcher helper. No producers registered yet. Tests: protocol isinstance check, registry idempotence.
4. **C.4** — Convert `ensure_seed_targets`, `materialize_pending_requests`, fantasy authorial pre-scoring into producers. Register them. Behind `TINYASSETS_PRODUCER_INTERFACE=on` (default) vs direct-call path. Load-bearing identity test.
5. **C.5** — Add `candidate_override` param to `choose_authorial_targets` AND update the `domains/fantasy_author/graphs/universe.py` call site to dispatch through producers when flag-on, direct call when flag-off. Concretely: the existing `choose_authorial_targets(universe_path)` call becomes:
   ```python
   if os.environ.get("TINYASSETS_PRODUCER_INTERFACE", "on") == "on":
       merged = _run_producers(universe_path)
       targets = choose_authorial_targets(universe_path, candidate_override=merged)
   else:
       targets = choose_authorial_targets(universe_path)
   ```
   The flag-off path is kept during Phase C as the revert lever. **Phase D later deletes the flag-off path** when the single-node fantasy-cycle Branch migration lands — at that point the producer path is the only path, and the flag retires. Dev claiming C.5 should understand: update the call site NOW, let Phase D do the cleanup.

Each sub-phase independently shippable. Stop-points:
- After C.1: `origin` field exists, no consumers — zero UX change, schema future-proofed.
- After C.2: no more fantasy leak in generic infra — generic module can be read by a second-domain dev without confusion.
- After C.3+C.4: producers registered but not yet wired through scoring — producer logs visible, no behavior change.
- After C.5: full Phase C complete, Phase D unblocked. Flag is live but defaults to producer path.

---

## 9. Open questions for host

### Q1. Should `origin` be an Enum type in a later phase?

Today it's `str` — deliberately loose to allow new producer types without a schema change. Once the producer set stabilizes (Phase G/H), should it tighten to an Enum? Recommend: **stay string indefinitely.** Enums create migration pain disproportionate to the type-safety win at this scale. The allowed-values list in §3.2 is authoritative; producer declarations self-document.

**Resolved by implementation:** followed recommended default — `origin` stayed `str` through Phase C.1 (`ebbafa1`) and all downstream phases (D/E/F/G). No migration surfaced.

### Q2. Producer config — single daemon-wide config file or per-producer?

The dispatcher passes `config=producer_config.get(producer.name)`. Source of truth can be (a) a single `daemon_config.yaml` with per-producer keys, or (b) per-producer config files under `tinyassets/producers/*.yaml`. Recommend: **(a) single file** — one place for host to edit all producer settings; simpler mental model; less file sprawl.

**Resolved by implementation:** followed recommended default in Phase C.3-C.4 (`ba83254`, `b0b1b2d`) — producer config stayed minimal (no per-producer YAML files landed); single-daemon-config assumption preserved.

### Q3. What happens when a producer emits a target with `origin` mismatching `producer.origin`?

Spec says dispatcher overrides. Alternative: reject the target with a loud error. Recommend: **override + warn log.** Forgiving at runtime, loud in logs so the bug surfaces. Rejecting is too harsh — a producer that mis-stamps one target shouldn't kill the cycle.

**Resolved by implementation:** followed recommended default — override + warn shipped in Phase C.4 dispatcher (`b0b1b2d`). No runtime mismatch bugs observed in C.5 or downstream phases.

### Q4. Should `ensure_seed_targets` be converted to a producer?

Arguments yes: consistency — every WorkTarget-creator becomes a producer, no special-case bootstrap logic.
Arguments no: seeding only runs on first-ever boot; wrapping it as a cycle-time producer either re-runs the check every cycle (cheap but wasteful) or adds a `first_run` flag (ugly).
Recommend: **yes, wrap it — idempotent by construction. The "check if already seeded" cost is trivial.** Makes the producer list uniform. If cycle overhead is observed, optimize later.

**Resolved by implementation:** followed recommended default in Phase C.4 (`b0b1b2d`) — seed targets registered as a producer; no cycle-overhead complaint.

### Q5. Do we need a way for producers to signal "I produced nothing because universe is idle, consider opportunistic tier"?

Today a producer returning `[]` looks the same as a producer erroring silently. Future Phase F/H opportunistic tier needs to distinguish "local producers are empty" from "all producers failed." Recommend: **defer to Phase F.** Protocol can grow an `IDLE` sentinel return value later without breaking v1 shape.

**Resolved by implementation:** followed recommended default — deferral held through Phase F (`1d02903`); no IDLE sentinel needed yet since F's tier cascade distinguishes empty-tier from producer-error upstream. Revisit if Phase H opportunistic tier requires the distinction.

### Q6. Should `candidate_override` be a hard requirement or an optional? — **RESOLVED**

Spec says optional — direct-file-read path still works. §8 C.5 now specifies the concrete call-site update: `universe.py` dispatches through producers when flag-on, direct call when flag-off. Phase D deletes the flag-off path entirely when the single-node fantasy-cycle Branch migration lands. Keeping both paths during Phase C gives the feature flag a real fallback.

---

## 10. What this spec explicitly does NOT do

- Does not unify `HardPriorityItem` emission into the producer interface. That's a separate future refactor.
- Does not touch the scoring function (`choose_authorial_targets` scoring logic) — only wraps it.
- Does not introduce a cross-universe producer. That's Phase F (`goal_pool`) and Phase G (`node_bid`).
- Does not surface producer registration in the user-facing MCP tool surface. Programmatic only for v1.
- Does not change `work_targets.json` format except for the additive `origin` field.
- Does not remove `materialize_pending_requests` — the `UserRequestProducer` wraps it, keeping `#18`'s work intact.
