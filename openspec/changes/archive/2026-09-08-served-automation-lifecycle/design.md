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
   with a write-context identity, not the broad connector dispatcher. The
   adapter enforces authentication and resource ACL, not the capability tuple
   itself. Preserve
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

Initial Linux CI run 34207195677 on runtime commit `31b696d5` exercised all
six focused files: **187 passed, 0 skipped** (JUnit artifact 10048762141),
including all 19 new lifecycle tests. The overall required gate correctly failed
for one new documentation-index failure: this PR's two concern reports lacked
committed README links. Commit `25d844ec` adds those links without changing
runtime or tests; required CI 34269667494 is rerunning. Do not treat the initial
focused passes as an overall green CI result. The first exact-head reviewer
process disappeared before delivering a verdict (session 24e251c9); a fresh
review is running on corrected head `25d844ecfc99896785d24c10379cf28a86298ba9`.

Exact-head Claude review completed (wrapper exit 0, 281 seconds) and APPROVED
`25d844ecfc99896785d24c10379cf28a86298ba9` with no pre-live blockers. Reviewer
independently ran all 19 new tests. Summary and qualified post-live findings:
`docs/reviews/2026-09-08-served-automation-exact-head-claude.md`. The write-context
wording above is corrected per the reviewer: ACL, not identity capabilities,
is the enforced authorization boundary. Consumer-run readback remains to verify.

Readback follow-up: `python -m pytest -q
output/test_served_automation_run_readback.py` on 2026-09-08 passed (1 test) after
explicitly naming the synthetic local dev-auth principal. It creates only a
temporary queued run with the consumer's `universe:<uid>` actor, then calls the
real served `read_graph` and adapter under the bound owner; the queued result
is readable and untrusted-enveloped. This narrows the review uncertainty but
does not prove OAuth, live consumer launch, terminal readback or cancellation.

The ready-for-review event superseded CI 34269667494 (cancelled, not a new test
failure). Required run 34270207709 on the same approved head completed SUCCESS:
zero new failures, zero stale quarantine entries. Its broad suite had 14,673
passes, 54 skips, 9 known failures and 2 known collection errors; do not call
the whole repository suite green. PR #3447 merged as
`4a1877f0044a974585ba0daaacf2d190256bf76e`.

## Deployment and pending rendered acceptance — 2026-09-08 19:59 UTC

Image build 34271720339 and deployment 34271996544 succeeded. The latter passed
authenticated public `--assert-handles` canary and protected revision containment;
at 19:58:53 UTC its receipt reports production `4a1877f0044a`, containing the full
merged SHA above. Commands ran in authorized CI; no local bearer was printed.

The initial existing-tab ownership blocker was resolved by the owner's explicit
permission to open a new tab. At 20:19 UTC Chrome tab 1346517476 opened the same
saved app conversation and received only `Retest your workflow checklist`.
Its rendered 13:20 PDT response confirms deploy `4a1877f0044a`, seven checklist
passes, exhausted-wait refusal OPEN and exact webhook FAIL 404. It independently
confirms the heartbeat automation is paused and the last scheduled run failed;
the automation remains attached. Future-trigger readback is now proven, not
retirement, a fresh pause mutation or in-flight cancellation. Lifecycle write
evidence remains the reviewed real-adapter tests, not this live retest. No private
workflow/automation was edited by Codex, and no organic post-fix use is claimed.
The shipped delta is synced into the main user-owned-automations spec.
