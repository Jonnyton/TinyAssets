---
title: Brain-Friction Catalog Roll-Up
date: 2026-05-08
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 487
wiki_source: pages/patch-requests/pr-050-brain-friction-catalog-roll-up-promote-8-catalogued-events-t.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#retrieval-and-memory
  - PLAN.md#harness-and-coordination
  - PLAN.md#uptime-and-alarm-path
  - docs/specs/loop-outcome-rubric-v0.md
---

# Brain-Friction Catalog Roll-Up

## 1. Classification

Issue #487 is a project-design request. It asks Workflow to promote eight
catalogued brain-friction events into substrate fixes for the recursive
community loop.

This response is design-only. It does not change runtime code because the
source wiki page named by the issue is not present in this checkout, and the
GitHub issue body exposes only request metadata plus the wiki path. The safe
smallest useful change is therefore the promotion contract: how catalogued
brain-friction events become bounded substrate-fix lanes once their event
records are available.

## 2. Context

Workflow already has the architectural pieces this request should compose:

- `PLAN.md` scoping rules require minimal primitives, community-build first,
  commons-first placement, and capability-tier portability before platform code
  ships.
- `PLAN.md` Retrieval And Memory treats memory as a routed evidence system, not
  a single backend.
- `PLAN.md` Harness And Coordination makes provider/worktree coordination part
  of the architecture, not private chat state.
- `PLAN.md` Uptime And Alarm Path says witnessed failure classes graduate into
  encoded self-heal or alarm layers only after their remedy is known.
- `docs/specs/loop-outcome-rubric-v0.md` defines evidence classes for loop
  claims: `trigger`, `claim`, `parent-run`, `child-run`, `child-output`,
  `release`, `observation`, and `rollback`.

The roll-up should use those contracts. It should not create a parallel
escalation process and should not generate eight implementation tasks until
each event has a stable source pointer, class, missing function, and proof
gate.

## 3. Decision

Treat a brain-friction event as a first-class learning signal only after it
passes promotion triage.

1. **Event record exists.** The event has a stable pointer, user-visible
   symptom, observed surface, date, actor/client, and evidence handle.
2. **Friction class is named.** The event is classified by the failed system
   function, not by the agent who noticed it.
3. **Existing substrate is checked first.** The triager checks whether an
   existing primitive, runbook, watchdog, rubric field, or workflow composition
   already handles the class.
4. **Smallest missing function is isolated.** The promoted fix names the
   minimum missing platform function that would prevent recurrence across
   future events in the same class.
5. **Proof gate is declared before build.** Every promoted fix declares the
   evidence class it must produce or validate.
6. **Review ownership is explicit.** Runtime/substrate work requires
   opposite-family checking. Design-only rows can be reviewed as documentation,
   but cannot authorize implementation by themselves.

## 4. Promotion Table Shape

Before any code work starts, roll the eight events into this compact table:

| Event | Friction class | Existing substrate checked | Smallest missing function | Proposed artifact | Proof gate |
|---|---|---|---|---|---|
| `<source pointer>` | `<failed system function>` | `<primitive/runbook/rubric/composition>` | `<substrate gap>` | `<design note/spec/STATUS row>` | `<evidence class + command/user path>` |

A row with no stable source pointer remains analysis-only. A row whose missing
function is actually a chatbot composition should become wiki guidance, an
idea-feed entry, or a docs cleanup, not platform code.

## 5. Friction Class Vocabulary

Use system-function classes so multiple incidents can converge on one substrate
fix:

| Class | Meaning | Likely artifact |
|---|---|---|
| Intake failure | User or chatbot could not file the request correctly. | Wiki guidance, intake validation, or trigger evidence fix. |
| Claim failure | A daemon could not see, classify, or claim eligible work. | Dispatcher/claim evidence fix. |
| Scope failure | Work exceeded or could not prove its file boundary. | Claim-check, base-ref, or branch-purpose guard. |
| Evidence failure | The loop could not prove what happened. | Rubric field, trace handle, or observation gate. |
| Memory write-back failure | The brain learned something but did not persist it durably. | Brain/wiki promotion or context-feed checkpoint. |
| Review failure | A checker could not verify because inputs or gates were missing. | Review packet/schema/gate fix. |
| Recovery failure | A known-fixed blocker did not replay or unstick old work. | Replay, watchdog, or alarm-path fix. |
| User-surface failure | The live chatbot/user path could not confirm recovery. | `ui-test`, connector, or post-fix clean-use evidence fix. |

This vocabulary is deliberately small. Add a class only when an event cannot be
represented by an existing system function.

## 6. Selection Rules

- Prefer fixes that make the next event of the same class succeed without
  Codex, Cowork, Claude, or host manual intervention.
- Prefer evidence plumbing over policy prose when the failure was "we could not
  know what happened."
- Prefer scope and base-ref guards over reviewer memory when the failure was
  "the hand edited more than intended."
- Prefer write-back and durable pointer fixes when the failure was "the brain
  learned something but could not remember it."
- Prefer watchdog, replay, or alarm-sink escalation when the failure was "the
  body stopped moving and nobody was paged."
- Do not ship convenience MCP actions for a single event. If existing
  primitives plus a wiki composition can handle the case, document the
  composition.

## 7. Implementation Gate

A follow-on implementation lane is valid only when all of these are true:

1. The event row has a stable source pointer.
2. `python scripts/check_primitive_exists.py` has been run for any proposed MCP
   action, cited `BUG-NNN`, or pinned sha.
3. `python scripts/claim_check.py --check-files "<files>"` is clear or the row
   has an explicit dependency on the conflicting lane.
4. The row names the exact files it will write.
5. The row names the focused verification command and, for public surfaces, the
   rendered chatbot `ui-test` path.
6. Runtime writers are Claude/Codex and the checker is the opposite family.

## 8. Non-Goals

- No runtime code changes in this design response.
- No new MCP action names are proposed here.
- No attempt to reconstruct the eight event records from memory.
- No bypass around `STATUS.md`, worktree metadata, or opposite-family review.

## 9. Next Step

Populate the promotion table from the source wiki page when it is available.
Then split only rows with a real, non-composable missing function into separate
bounded work items. Rows already handled by existing substrate should become
documentation, wiki cleanup, or idea-pipeline updates rather than code.
