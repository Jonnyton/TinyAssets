## Context

OpenSpec intentionally manages Markdown artifacts, not git workflow or team WIP.
TinyAssets currently has 34 active change directories and 834 unchecked tasks,
but `STATUS.md` mentions only 22 of those changes. The existing coordination
tools separately understand STATUS claims, worktrees, and provider context;
none exposes the delivery flow across OpenSpec and STATUS.

This change is development tooling under the Harness & Coordination module. It
must stay read-only, stdlib-only, fast on Windows, and useful to every provider.
It must not reinterpret an aspirational target change as currently authorized
implementation.

## Goals / Non-Goals

**Goals:**

- Produce one deterministic text/JSON inventory joining active changes, task
  progress, STATUS ownership, global/provider WIP, and recent
  admission/archive counts.
- Make complete-but-unarchived and small finish-first candidates obvious.
- Check a named change before build admission against a small task ceiling and
  one-active-change-per-exact-session-identity policy.
- Ratchet the same rules into OpenSpec config, AGENTS.md, and the shared skill.
- Grandfather existing WIP as reported debt so the tool can land before cleanup.

**Non-Goals:**

- Mutate, split, sync, archive, claim, or delete any change.
- Replace `openspec` CLI validation.
- Estimate task duration or score provider productivity.
- Automatically decide PLAN priorities or P0 exceptions.
- Clean up the 374 registered worktrees.

## Decisions

### 1. Parse repository artifacts directly

The inspector will parse `openspec/changes/*/tasks.md` checkboxes and the
`STATUS.md` Work table with Python's standard library. It will use git only for
optional recent admission/archive counts.

This avoids a hard runtime dependency on the platform-specific `openspec.cmd`
shim and keeps the tool useful when the CLI is temporarily unavailable.
OpenSpec validation remains a separate required command.

Alternative: shell out to `openspec list --json`. Rejected as the sole source
because Python subprocess resolution of command shims differs across Windows
providers and the CLI does not join STATUS ownership.

### 2. Separate observation from admission

Default `audit` mode always reports current debt and exits zero when it can read
the repository. A named `check-change` mode exits 2 when the candidate exceeds
12 total task checkboxes or the exact requesting session-specific provider
identity already owns another active OpenSpec delivery change. Both modes
report global WIP. Renaming or minting a provider suffix to evade the limit is
a process-review violation. Umbrella/full-vision terms produce a warning
because intent cannot be judged reliably from keywords alone; the
cross-provider rule remains the hard semantic gate.

This lets the guard land in a repository whose legacy state already violates
the new ceiling without blessing or blocking all unrelated work.

Alternative: fail CI on every oversized active change immediately. Rejected
because it would freeze the repository behind 23 pre-existing violations and
encourage mechanical task reshuffling instead of delivery.

### 3. Map ownership conservatively

For each active change, the inspector searches each STATUS Work row for the
exact change name. Every matching claimed/in-flight row contributes its owner
to that change so dependency-cell mentions cannot cause an ordering-dependent
WIP bypass; pending/dev-ready rows make it queued only when no active row
matches; absent names make it untracked. A row that names multiple active
changes counts all of them against its provider's WIP.

This intentionally exposes brace/glob bundle claims rather than trying to
interpret them as one delivery unit.

Provider identity is the exact value after `claimed:` or `in-flight:` in the
STATUS row. Sessions sharing a provider family do not silently share a slot,
but every report includes global WIP so multiplying session suffixes remains
visible and reviewable.

### 4. Recommend finishing, not starting

The default recommendation order is:

1. zero-remaining complete-but-unarchived changes;
2. claimed changes with the fewest remaining tasks;
3. queued changes with the fewest remaining tasks;
4. untracked changes are reported for triage, not recommended for build.

Dependency impact remains a human/PLAN judgment in this slice. The report
provides the evidence without inventing a graph from prose.

### 5. Keep policy in canonical cross-provider surfaces

The one-intent/one-owner/one-PR/12-task rule and the ban on bulk vision
conversion will live in AGENTS.md first, then `openspec/config.yaml` and the
canonical `.agents/skills/openspec/SKILL.md`, synced to provider mirrors.

The rules specify that full vision remains in PLAN/design/audits and that
incidental findings go to the idea feed unless required for the current
acceptance contract.

Audit mode runs on demand during dispatch/triage. Admission mode runs after
scaffolding and before claiming or building a change. This deliberately does
not extend the mandatory session-start ritual.

## Risks / Trade-offs

- **Task count is an imperfect size proxy.** → Treat 12 as a dated 2026-07-28
  admission backstop, not a productivity metric; review on 2026-08-11 against
  cycle-time evidence and current model capability.
- **STATUS prose may mention a change without owning it.** → Report the matched
  row and classification in JSON so a provider can inspect false positives.
- **Providers may game the ceiling by combining work into fewer checkboxes.** →
  Keep the semantic one-intent and independently verifiable-task rules in
  AGENTS/config; review still gates the plan.
- **Providers may game WIP by minting identity suffixes.** → Always expose
  global WIP and treat suffix-renaming for capacity as a review violation.
- **Legacy target programs remain visible.** → Classify them as untracked or
  oversized and resist mechanical splitting until a real slice is selected.
- **A strict per-provider rule can block urgent work.** → Allow an explicit
  P0/security override in process text that names the displaced WIP; do not
  silently exceed capacity.

## Migration Plan

1. Land the read-only inspector, tests, and policy text.
2. Run it in advisory mode against current main and record a baseline.
3. Use audit mode during dispatch/triage and `check-change` after scaffolding
   but before claiming or building future OpenSpec delivery changes.
4. After legacy WIP is below policy, consider a separate change to wire
   admission checking into CI.
5. Rollback is removal of the script/rules; no product or user data migration
   exists.

## Open Questions

- Whether target-only future programs should move outside active changes.
- What global WIP limit, if any, observed cycle-time data justifies.
- Whether shared coordination files need row-scoped collision atoms.
- Whether worktree inspection needs a batched/fast redesign.
