## Context

The connector routes automation lifecycle to `api.automations.automations`.
The served engine wrapper rejects this target, while branch deletion tells the
agent to remove attached automations first. A generic pending request merely
records an answer; it cannot mount tools or perform an automation mutation.
The live owner's approved cleanup therefore reaches a dead end.

PLAN's cross-client capability principle requires an equivalent reachable path,
not a direct database workaround. Independent shape guidance is recorded in
`docs/reviews/2026-09-08-served-capability-audit-claude.md`.

## Goals / Non-Goals

Goals: inspect and control the owner's existing automation lifecycle from the
served app, preserve current authority/concurrency rules, and return truthful
readback so an agent can tell whether a trigger is paused or retired.

Non-goals: changing private workflows or automation rows during development;
new scheduler/storage/provider logic; broad connector pass-through; raw-secret
tools; owner self-approval; global capabilities; other inventory rows; changing
the existing cooperative cancellation contract or claiming all checklist rows pass.

## Decisions

1. Add `automations`/`automation` reads and an automation selector to the existing
   served `read_graph`. Route them directly to the existing adapter, binding the
   runtime actor and pinning its universe. Never forward a caller-supplied graph,
   actor or owner. Keep the existing uniform foreign-record miss and ACL check.
   Read output follows the existing projection; no provider credential is added.

2. Add `target=automation` with create/pause/resume/delete to served `write_graph`,
   with explicit automation ID and expected revision. Reuse the existing adapter
   with narrow write capability, not the broad connector dispatcher. Preserve
   current owner/admin, revision CAS, retired-record and creation preflight checks.
   Unknown operations refuse before dispatch. Bound payload size and malformed
   JSON/type handling remain structured. No hidden fallback to another operation.

3. These are direct-agent controls, as independently reviewed: the agent already
   runs workflows under the bound owner. Creation uses fail-closed engine
   admission and existing store limits. Pause/delete do not start work or need a
   provider to be available; avoid tying them to execution budget or creation
   readiness. Resume restores an existing schedule under its current policy and
   ownership, without mutating its branch/provider. Keep the existing served
   universe enablement gate. A later owner-confirmation policy would require an
   explicit executable rail action, not a generic answered request.

4. Preserve control receipts and revision readback. A retired row no longer
   blocks branch deletion under the existing dependents query. Pausing/retiring
   future triggers does not claim an already-running job stopped; descriptions
   must say this. Do not retroactively execute the app's old approved request.

5. Add bounded relational coverage for the newly documented targets/operations:
   check shared provider allowlists and actual handler dispatch with pinned
   identity/scope, including refusal paths. Inventory-wide availability-map work
   is separate unless required to prevent a new false instruction in this slice.
   Do not invent per-provider or per-workflow tools.

## Risks / Trade-offs

- A selector could cross universes: verify both wrapper pin and real adapter
  refusal, including an actor who owns more than one universe.
- A stale revision could mutate a newer row: retain store CAS and test conflict.
- A paused/retired trigger could be mistaken for a stopped run: explicit receipts
  and tool caveat; do not silently cancel or promise a join barrier.
- Tool descriptions can drift from runtime: extract their documented operation
  vocabulary in tests and exercise every listed path, including invalid payloads.
- New automation creation can recur: preserve existing admission, ceiling,
  ownership, runtime provider resolution and budget, never bypass them.
- Existing broader provider compatibility limits remain: exposing management does
  not establish arbitrary-provider support or connection-local model selection.

## Migration Plan

No migration or private-state edits. Baseline/focused tests, independent
implementation review, draft PR and required Linux CI, plugin mirror, immutable
deploy with public canary and protected containment. Then send exactly
`Retest your workflow checklist` in the existing app; do not coach it to clean up
specific rows. Record any unexercised control as unproven. Rollback is the previous
healthy image; canonical connector controls and stored rows remain unchanged.

## Open Questions

Implementation must verify the exact least-privilege capability set and whether
any JSON projection field can carry user-authored untrusted instructions. Review
those at the boundary rather than treating the whole projection as instructions.
Implementation uses a separate branch after this change's context/tasks are
complete. The workspace receipt PR's reviewed head remains unchanged while its
CI runs; this follows delivery-flow's review pipeline without mixing intents.
The automation PR must be based on the landed receipt tree before its own
exact-head review and landing.

## Implementation verification — 2026-09-08

Windows working tree based on main `0e485ba0add1`: focused pytest across
`test_served_automation_lifecycle`, `test_automations_api`,
`test_engine_mcp_server`, `test_engine_mcp_write_graph_patch`,
`test_removal_is_reachable_from_the_served_surface` and
`test_branch_delete_is_first_class`: **184 passed, 3 skipped**. Ruff passed for
the two runtime modules and the two changed test files. Runtime plugin build
is required before commit; Linux required CI and exact-head review remain gates.
The new tests call the real automation adapter and SQLite store, exercising
bound identity, owner/admin/write-collaborator ACLs, cross-universe misses, CAS,
retirement dependency removal, stopped-provider controls, payload refusals, and
the actual FastMCP tool schema. Foreign-owner projected text is wrapped as data.
The operation allowlist is explicit: future connector actions are not exposed
automatically. Documentation and the reviewed operation set are tested together.
