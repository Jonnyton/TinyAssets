# Brain-Friction Catalog Roll-Up

Status: Proposed
Date: 2026-05-06
Request: WIKI-DESIGN / Issue #487
Source wiki path: `pages/patch-requests/pr-050-brain-friction-catalog-roll-up-promote-8-catalogued-events-t.md`

## Context

Issue #487 asks for a project-design response to a catalog roll-up: eight
catalogued "brain friction" events should be promoted into substrate fixes for
the recursive community loop. The filed wiki page is not present in this
checkout, and the public GitHub issue exposes only the request metadata and
wiki path. This note therefore records the architectural promotion contract,
not an implementation plan for the eight individual events.

The existing operating model already names the relevant system boundary:
wiki/open-brain is the learning surface, the loop is the action body, and
substrate primitives are the functions the loop gains so future manual
interventions become unnecessary. The loop outcome rubric also requires typed
evidence before a loop variant or fix can be promoted. A catalog roll-up should
reuse those contracts rather than introduce a separate escalation path.

## Classification

This is a project-design request. It is not a runtime bug fix and should not
change `workflow/*` code until a specific promoted substrate fix has its own
bounded work item, files, evidence gate, and opposite-family review path.

## Decision

Treat a brain-friction event as a first-class learning signal only after it
passes a promotion triage:

1. **Event record exists.** The event has a stable pointer, user-visible
   symptom, observed surface, date, actor/client, and evidence handle.
2. **Friction class is named.** The event is classified by the failed system
   function, not by the agent who noticed it. Examples: intake could not file,
   dispatcher could not claim, investigation could not write back, branch could
   not prove scope, reviewer could not verify, shipped change could not be
   observed, or user could not confirm recovery.
3. **Existing substrate checked first.** The triager checks whether an existing
   primitive, runbook, watchdog, rubric field, or workflow composition already
   handles the class. If yes, the fix is routing/documentation, not new
   substrate.
4. **Smallest missing function is isolated.** The promoted fix names the
   minimum missing platform function that would prevent recurrence across
   future events in the same class.
5. **Proof gate is declared before build.** Every promoted fix declares the
   evidence class it must produce: trigger, claim, parent-run, child-run,
   child-output, release, observation, rollback, or a new proposed evidence
   class if none of those fit.
6. **Review ownership is explicit.** Runtime/substrate work requires
   opposite-family checking. Design-only notes can be reviewed as docs, but
   cannot authorize implementation without a follow-on work item.

## Promotion Output Shape

Each of the eight events should be rolled into a compact table before any code
work starts:

| Event | Friction class | Existing substrate | Missing function | Proposed artifact | Proof gate |
|---|---|---|---|---|---|
| `<source pointer>` | `<system function that failed>` | `<primitive/runbook/rubric checked>` | `<smallest substrate gap>` | `<design note/spec/work row>` | `<evidence class + command/user path>` |

The table is the handoff between catalog learning and implementation. A row
with no stable source pointer remains analysis-only. A row whose missing
function is actually a chatbot composition should become wiki guidance or an
idea-feed entry, not platform code.

## Substrate-Fix Selection Rules

- Prefer fixes that make the loop handle the next event of the same class
  without Codex/Cowork/host manual intervention.
- Prefer evidence plumbing over policy prose when the failure was "we could not
  know what happened."
- Prefer scope and base-ref guards over reviewer memory when the failure was
  "the hand edited more than intended."
- Prefer write-back and durable pointer fixes when the failure was "the brain
  learned something but could not remember it."
- Prefer watchdog/alarm-sink escalation when the failure was "the body stopped
  moving and nobody was paged."
- Do not ship convenience MCP actions for a single event. If the event can be
  handled by existing primitives plus a wiki composition, document the
  composition.

## Relationship To Existing Design

- `PLAN.md` scoping rules still apply: minimal primitives, community-build
  first, commons-first storage, and capability-tier portability.
- `docs/specs/loop-outcome-rubric-v0.md` remains the vocabulary for proof
  claims. If the eight events reveal a missing evidence class, propose the
  evidence-class addition before using it.
- `docs/design-notes/2026-05-04-operating-model-and-four-agent-topology.md`
  remains the model for why friction events become substrate functions instead
  of one-off process reminders.
- `.agents/skills/loop-uptime-maintenance/` remains the incident-log pattern
  for cases where the loop cannot process its own emergency filing.

## Non-Goals

- No runtime code changes in this design response.
- No new MCP action names are proposed here.
- No attempt to reconstruct the eight event records from memory. The missing
  wiki page or its canonical event records must provide those details.

## Next Step

Populate the promotion table from the source wiki page when it is available.
Then split only the rows with a real, non-composable missing function into
separate bounded work items. Rows that are already handled by existing
substrate should become documentation or wiki cleanup, not code.
