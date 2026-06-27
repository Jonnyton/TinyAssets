---
status: active
---

# Storage-Layer Authority Refactor — Defense-in-Depth Auth

**Date:** 2026-04-25
**Author:** dev-2
**Status:** Design proposal. Closes the load-bearing gap from navigator's #65 pair-read finding — storage-layer is permissive today; authority enforced only at MCP perimeter.
**Builds on:** Task #47 §4 (variant-canonical authority model); Task #57 §5 (rollback_merge host-only assertion); navigator's #65 pair-read.
**Scope:** schema/contract design only. No code changes.

---

## 1. Recommendation summary

Add explicit `actor_id` arg to high-blast-radius storage helpers + introduce small policy module `tinyassets/storage/authority.py`. Each helper calls a `check_*_authority(base_path, actor_id, ...)` function at the top; `AuthorizationError` is raised on denial; MCP layer translates to structured error.

**Top tradeoff axis:** **least magic vs. least boilerplate.** Going least-magic — explicit args are easiest to test, debug, and audit. Boilerplate cost is bounded (~6 helpers in Phase 1).

**Concrete gap (verbatim from `daemon_server.py:2453-2475` `set_canonical_branch` docstring):**

> "Only the Goal author or a host-level actor may set canonical. **Caller must validate authority before calling this function.**"

The `set_by` arg today is for AUDIT TRAIL, not authorization. Today's storage layer trusts callers. This proposal closes that gap for high-blast-radius writes.

---

## 2. Schema sketch — `tinyassets/storage/authority.py`

```python
# tinyassets/storage/authority.py — NEW module
"""Defense-in-depth authority checks for storage-layer writes.

Today's storage helpers trust callers: docstrings say "caller must
validate authority." This module replaces that contract with explicit
checks at the storage boundary. Composes with MCP-layer perimeter
checks for defense in depth.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from workflow.daemon_server import get_goal


class AuthorizationError(Exception):
    """Raised when an actor lacks permission for a storage operation."""

    def __init__(self, actor_id: str, operation: str, reason: str):
        super().__init__(f"Actor {actor_id!r} cannot {operation}: {reason}")
        self.actor_id = actor_id
        self.operation = operation
        self.reason = reason


def _host_actor() -> str:
    """Single source of truth — reuses existing helper."""
    return os.environ.get("UNIVERSE_SERVER_HOST_USER", "host")


# ── Per-operation authority checks ────────────────────────────────────────────


def check_set_canonical_authority(
    base_path: str | Path,
    actor_id: str,
    *,
    goal_id: str,
    scope_token: str = "",
) -> None:
    """Raise AuthorizationError if actor cannot set this canonical.

    Authority rules (composes #47 §4 + current set_canonical):
    - scope_token=='' (default): actor must be goal.author OR host_actor
    - scope_token=='user:<id>': actor must match the scope_token's id
    - scope_token=='tier:<tier>': punted to #47 §6 Q1 (tier policy)
    - scope_token=='team:<id>': punted to #47 §6 Q2 (team policy)
    """
    from workflow.daemon_server import get_goal

    if scope_token == "":
        goal = get_goal(base_path, goal_id=goal_id)
        if actor_id != goal["author"] and actor_id != _host_actor():
            raise AuthorizationError(
                actor_id, "set canonical for goal",
                f"only goal author ({goal['author']!r}) or host can set default canonical",
            )
    elif scope_token == f"user:{actor_id}":
        return  # Self-binding always permitted
    elif scope_token.startswith("user:"):
        raise AuthorizationError(
            actor_id, "set canonical for goal",
            f"cannot bind canonical for another user's scope ({scope_token!r})",
        )
    elif scope_token.startswith(("tier:", "team:")):
        raise AuthorizationError(
            actor_id, "set canonical for goal",
            f"tier/team-scoped canonicals not yet supported (#47 §6 Q1/Q2)",
        )


def check_rollback_authority(
    base_path: str | Path,
    actor_id: str,
    *,
    branch_version_id: str,
) -> None:
    """Raise AuthorizationError if actor cannot rollback. Host-only per #57 §5."""
    if actor_id != _host_actor():
        raise AuthorizationError(
            actor_id, "rollback merge",
            f"rollback is host-only (per Task #57 §5); host actor is {_host_actor()!r}",
        )


def check_branch_definition_authority(
    base_path: str | Path,
    actor_id: str,
    *,
    branch_def_id: str,
    operation: str,  # "save" | "update" | "delete"
) -> None:
    """Raise if actor cannot modify this branch_definition.

    Author of branch OR host can modify. New saves: actor becomes author
    by definition (no existing row to check).
    """
    from workflow.daemon_server import get_branch_definition

    if operation == "save":
        return  # Initial create — caller becomes author
    try:
        branch = get_branch_definition(base_path, branch_def_id=branch_def_id)
    except KeyError:
        raise AuthorizationError(
            actor_id, f"{operation} branch_definition",
            f"branch_def_id {branch_def_id!r} not found",
        )
    if actor_id != branch["author"] and actor_id != _host_actor():
        raise AuthorizationError(
            actor_id, f"{operation} branch_definition",
            f"only author ({branch['author']!r}) or host may {operation}",
        )


def check_delete_goal_authority(
    base_path: str | Path,
    actor_id: str,
    *,
    goal_id: str,
) -> None:
    """Raise if actor cannot delete this Goal. Author OR host."""
    from workflow.daemon_server import get_goal

    goal = get_goal(base_path, goal_id=goal_id)
    if actor_id != goal["author"] and actor_id != _host_actor():
        raise AuthorizationError(
            actor_id, "delete goal",
            f"only author ({goal['author']!r}) or host may delete",
        )
```

The module is small, stdlib-only, no business logic beyond authority lookup. Each function is independently testable.

---

## 3. Tradeoff vs alternatives

| Axis | Explicit `actor_id` arg + policy module (recommended) | Authority-as-decorator | Authority-as-context-manager |
|---|---|---|---|
| **Auth visible at call-site** | YES — every call shows actor_id in args | Hidden behind decorator | Hidden inside `with` block |
| **Testability** | Each check is a pure function callable from tests | Decorator + decorated function couple | Context-manager state requires fixture setup |
| **Failure mode on forget** | Type error (missing arg) | Silent — decorator may not be applied | Silent — forgot to enter `with` |
| **Debuggability** | actor_id in stack frame at every step | Decorator wrapper hides actor_id | Thread-local; harder to inspect |
| **Per-helper boilerplate** | One `actor_id` arg + one check call | One `@requires_auth` line | Caller-side `with` boilerplate |
| **Composability with TYPE_CHECKING / lazy imports** | Trivial | Decorator chain complications | OK |

Going option 1. The "forgot to apply decorator / forgot to enter context" failure modes silently disable auth — exactly the defense-in-depth gap we're trying to close.

---

## 4. Phase 1 helpers (high blast radius — covered now)

Six helpers gain `actor_id` arg + `check_*_authority` calls:

| Helper | Location | Operation | Authority check |
|---|---|---|---|
| `set_canonical_branch` | `daemon_server.py:2453` | Set/unset goal canonical (default scope) | `check_set_canonical_authority(scope_token="")` |
| `set_canonical_binding` | NEW (per #47 Steps 2-3) | Write canonical_bindings row (any scope) | `check_set_canonical_authority(scope_token=row.scope_token)` |
| `update_branch_definition` | `daemon_server.py:2135` | Edit live branch def | `check_branch_definition_authority(operation="update")` |
| `save_branch_definition` | `daemon_server.py:1971` | Create new branch def | `check_branch_definition_authority(operation="save")` (no-op for create) |
| `delete_goal` | `daemon_server.py:2635` | Soft-delete goal | `check_delete_goal_authority` |
| `mark_branch_version_rolled_back` | NEW (per #57 implementation) | Roll back a published version | `check_rollback_authority` |

**Structural callout — `set_canonical_binding` is Phase 1 by definition.** It's the ONLY production write-path for the new `canonical_bindings` table. Auth lands at first-use, NOT as a retrofit. The story stays clean: every binding ever written goes through the new authority module.

### v2 deferral (lower blast radius)

| Helper | Why deferred |
|---|---|
| `update_goal` | Edits gate ladder, visibility flips. Important but not catastrophic. v2 covers. |
| `save_goal` | Initial create — caller becomes author by definition; nothing to check against. |
| `record_event` | Audit-log writes within-process; broad-trust, not security-load-bearing. |
| `save_node_definition` | Node-level edits; less load-bearing than branches; v2. |
| `update_run_status` | Run state transitions; trusted internal callers. v2. |

The v2 set follows the same recipe later — Phase 1 is the high-blast-radius slice that ships first.

---

## 5. Migration plan — 4-step additive

### Step 0 — define authority module

Create `tinyassets/storage/authority.py` with `AuthorizationError` + the 4 `check_*_authority` functions. Tests cover each rule in isolation:

- `check_set_canonical_authority` — actor=goal.author allowed, actor=host allowed, actor=stranger denied, scope=user:self allowed, scope=user:other denied, scope=tier:* denied (current).
- `check_rollback_authority` — actor=host allowed, actor=anyone-else denied.
- `check_branch_definition_authority` — operation=save no-op, operation=update author-or-host gated, missing branch_def_id raises clearly.
- `check_delete_goal_authority` — author-or-host gated.

### Step 1 — Phase 1 helpers gain optional `actor_id` arg

Each helper signature gains `actor_id: str = "host"` (backward-compat default). NEW callers pass real actor; OLD callers fall through with host privileges. Add deprecation warning emitted via `warnings.warn` whenever the default is used (logs to operator).

### Step 2 — Helpers call `check_*_authority` at the top

Each helper's first action (after `initialize_author_server(base_path)`) is to call its appropriate authority check. Rejected calls raise `AuthorizationError`; MCP layer's `_dispatch_*_action` wrappers translate to `{"status": "rejected", "error": str(exc), "authority_required": exc.operation}` per Q1 below.

### Step 3 — Flip default after callers migrated

Two-week sunset window. After all production callers (universe_server.py, scripts, tests) pass `actor_id` explicitly, remove the default. Callers must pass it; missing arg → `TypeError`.

**Rollback safety:** if Step 2 surfaces a regression (e.g., a forgotten internal caller), revert Step 2 only — Step 0 + Step 1 stay. Helpers ignore `actor_id` until Step 2 re-lands. No data loss.

---

## 6. Composition with sibling proposals

### Task #57 surgical rollback — defense in depth

`runs action=rollback_merge` enforces host-only at MCP layer (#57 §5). Storage-side helpers `mark_branch_version_rolled_back` + `repoint_canonical_to_parent` (both will land in #57 implementation) MUST call `check_rollback_authority(actor_id)`.

If the MCP layer is bypassed (direct `daemon_server` call from another process, test code that forgets to validate, future internal automation), storage-layer prevents the action. **The MCP-layer check is one barrier; storage-layer check is the second.** Defense-in-depth literal — both must hold for rollback to fire.

### Task #47 variant canonicals — lifts §4 authority model

`set_canonical_binding` (when implemented per #47 Steps 2-3) gains `actor_id` + calls `check_set_canonical_authority(actor_id, goal_id, scope_token)`. The authority rules in `check_set_canonical_authority` are a literal lift of #47 §4 authority model:

- `scope_token == ''` → goal author or host (current set_canonical behavior).
- `scope_token == 'user:<actor>'` → that actor only.
- `scope_token.startswith('tier:'/'team:')` → policy-pending; reject with informative error referencing #47 §6 Q1/Q2.

### Task #48 contribution ledger — orthogonal

`record_contribution_event(..., actor_id=...)` already requires the actor as a row field (event author). NOT auth-related at the storage layer — the ledger is append-only, every actor records their own events. `actor_id` for events is identity, not authorization.

### Task #66 TypedPatchNotes — orthogonal

`patch_notes.author_actor_id` is required (#66 §2). When patch_notes flow through gate evaluation, the storage helpers writing the resulting events read `notes.author_actor_id` for ledger field population. NOT auth-related — author identity, not write permission.

### Cross-process / federation — punt to v2

Today's daemon is single-process. Future multi-process / federated deployments (per `project_host_independent_succession`) need shared authority enforcement across daemons. This proposal does NOT design that. v2 covers. Note in §7 Q3.

---

## 7. Open questions

1. **AuthorizationError → MCP error class mapping.** RECOMMENDED: new `_format_authorization_error(exc)` helper in `tinyassets/universe_server.py` returning `{"status": "rejected", "error": str(exc), "authority_required": exc.operation, "actor_id": exc.actor_id}`. Standard MCP error shape; chatbot can render "you can't do X; <reason>." Closed.

2. **Host actor identification.** RECOMMENDED: keep using `os.environ.get("UNIVERSE_SERVER_HOST_USER", "host")` via `_host_actor()` helper in this module. Single source of truth; storage authority module imports the same env helper that universe_server.py + #57 use. Don't fork. Closed.

3. **Cross-process policy enforcement.** RECOMMENDED: punt to v2. Today's single-process daemon doesn't need it; federation work surfaces it. Doc in §6. Closed.

4. **Authority caching.** RECOMMENDED: recompute on every check. SQLite query to fetch `goal.author` is sub-millisecond; cache-invalidation complexity is not earned. Closed.

5. **(Truly open) Goal author transferability.** Today `goals.author` is immutable; if an author leaves, no one but host can change canonical for their goals. Should there be a `transfer_goal_authority` primitive? RECOMMENDED: defer — different concern (governance), shouldn't load-bear on this auth refactor. Surface as a separate proposal once a real user need surfaces. Open.

6. **(Truly open) AuthorizationError as engine signal.** When a sub-branch invocation raises AuthorizationError mid-graph (per Task #56), what's the parent's contract? Recommend: AuthorizationError is a subclass of ValueError-equivalent at the engine boundary; the parent's `on_child_fail` policy (from #56 §4) governs propagation — `propagate` default raises in parent context; `default` falls through; `retry` re-fires (will fail again, bounded by retry_budget). Open.

---

## 8. What this proposal does NOT cover

- **No code changes.** Design only; lead routes implementation as separate dispatch.
- **No v2-deferred helpers.** `update_goal` / `save_node_definition` / `record_event` / etc. — same recipe applies later.
- **No MCP-layer changes.** Existing perimeter checks at MCP handlers stay as-is. This proposal adds a SECOND layer; doesn't replace the first.
- **No federation / multi-process auth.** §6 Q3 deferral.
- **No goal author transferability.** §7 Q5 deferral.
- **No revocation / time-bounded authority.** Auth is current-state only; "actor X had auth at time T but lost it later" is not modeled. Future feature.
- **No cross-tenant isolation.** When tenants share artifact lineage, authority compositions get tricky; out of scope here.

---

## 9. References

- Pair-read finding source: navigator's #65 (pair-read on #57 surgical rollback) — flagged the storage-layer trust gap.
- Concrete gap quote: `tinyassets/daemon_server.py:2453-2475` (`set_canonical_branch` docstring "Caller must validate authority").
- Authority model lift: `docs/design-notes/2026-04-25-variant-canonicals-proposal.md` §4 (Task #47).
- Defense-in-depth target: `docs/design-notes/2026-04-25-surgical-rollback-proposal.md` §5 (Task #57 — `runs action=rollback_merge` host-only assertion).
- Sibling proposals (orthogonal but cited):
  - Task #48 contribution ledger — actor_id is identity, not auth.
  - Task #66 TypedPatchNotes — `author_actor_id` is identity, not auth.
- Phase 1 helper locations:
  - `set_canonical_branch` — `tinyassets/daemon_server.py:2453`
  - `update_branch_definition` — `tinyassets/daemon_server.py:2135`
  - `save_branch_definition` — `tinyassets/daemon_server.py:1971`
  - `delete_goal` — `tinyassets/daemon_server.py:2635`
- Companion principle: `project_user_builds_we_enable.md` — every helper that writes user content must verify the writer is authorized.
- Companion convention: `docs/design-notes/2026-04-25-design-proposal-pattern-convention.md` — this proposal follows the 5-move pattern (investigate → tradeoff → recommendation → opens → SHIP).
- Existing MCP-layer auth checks (perimeter that stays intact):
  - `tinyassets/universe_server.py:10648-10658` (`_action_goal_set_canonical` — actor vs goal author + host).
