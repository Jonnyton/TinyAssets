---
title: Cowork Substrate Primitive Audit Intake
date: 2026-05-08
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 439
wiki_source: pages/notes/pages-notes-cowork-substrate-primitive-audit-2026-05-05.md
scope: design-only; no runtime code in this branch
builds_on:
  - docs/design-notes/2026-04-26-engine-primitive-substrate.md
  - docs/design-notes/2026-04-26-minimal-primitive-set-proposal.md
  - docs/design-notes/2026-05-04-operating-model-and-four-agent-topology.md
  - PLAN.md#scoping-rules
  - PLAN.md#harness-and-coordination
---

# Cowork Substrate Primitive Audit Intake

## 1. Classification

Issue #439 is a **project-design** request. It should not change runtime code
from the sync stub alone. The smallest useful project change is to define how
Cowork-authored substrate audit findings enter the existing substrate design
contract.

The referenced wiki page was not present in this checkout, and the GitHub
issue body only contains the auto-sync metadata. This note therefore does not
claim to accept specific Cowork findings from that page. It defines the intake
gate those findings must clear before they can become canonical design truth or
implementation work.

## 2. Recommendation Summary

Treat Cowork substrate primitive audits as recurring evidence against the
existing engine substrate contract, not as automatic requests for new
primitives.

The current substrate contract is the eight-primitives model in
`2026-04-26-engine-primitive-substrate.md`:

1. graph compile + execute
2. typed state + reducer
3. persistent checkpoint
4. provider routing
5. retrieval
6. evaluator
7. catalog
8. dispatcher

A Cowork audit finding should be mapped to one of four outcomes:

| Outcome | Meaning | Next artifact |
|---|---|---|
| Existing-substrate gap | One of E1-E8 is missing behavior or proof. | Bug, patch request, or design note scoped to that primitive. |
| Composition-layer gap | MCP/API/daemon/ops code needs to compose E1-E8 differently. | Patch request or ops design; no substrate change. |
| Community-build pattern | The finding is useful but can be expressed as wiki guidance, rubric, or remix pattern. | Wiki/docs/idea entry; no platform primitive. |
| Candidate ninth primitive | E1-E8 cannot compose the capability without fragile or impossible glue. | New proposed design note with irreducibility proof and opposite-family review. |

This keeps the minimal-primitives rule intact while still letting Cowork audits
surface real substrate pressure.

## 3. Intake Gate

Every Cowork substrate audit item should answer these questions before it is
promoted into `PLAN.md`, `STATUS.md`, or runtime work:

1. **Observed pressure:** What concrete failure, missing capability, or repeated
   manual workaround was observed?
2. **Layer:** Is the pressure in substrate E1-E8, the tool/API composition
   layer, ops/coordination, or community-authored guidance?
3. **Composition attempt:** How would a chatbot, daemon, or contributor compose
   the desired behavior from E1-E8 today?
4. **Failure mode:** If composition fails, is it structurally impossible,
   unreliable across providers, too many reasoning steps for a competent
   chatbot, or simply undocumented?
5. **Smallest response:** Is the response a test, doc, wiki pattern, ops
   runbook update, composition-layer patch, or substrate evolution?
6. **Proof gate:** What evidence would prove the response worked?

Items without these answers remain audit observations. They should not become
implementation tickets just because they mention primitives.

## 4. Promotion Rules

### Existing-substrate gap

If the audit shows a defect inside E1-E8, file or update a bug/patch request
against the owning primitive. Examples:

- E4 provider routing cannot report a recoverable provider-exhaustion class.
- E8 dispatcher can claim work but cannot replay a known-fixed terminal handoff.
- E7 catalog cannot represent a public commons artifact needed by multiple
  domains.

The design response should name the primitive and avoid broad platform
language. The implementation response must include focused tests for that
primitive.

### Composition-layer gap

If E1-E8 can already express the capability, but the current MCP/API/daemon
surface does not expose or orchestrate it correctly, keep the substrate stable.
The implementation target is the composition layer. This includes tool metadata,
daemon loops, GitHub Actions sweeps, runbooks, packaging, and connector UX.

### Community-build pattern

If a chatbot can compose the behavior from primitives in fewer than five
reliable reasoning steps, the platform should not ship it as a new primitive.
Capture it as wiki guidance, a rubric, a remixable branch pattern, or an idea
feed item. This is the normal expected outcome for many substrate audits: the
audit teaches the commons, not the runtime.

### Candidate ninth primitive

A ninth primitive requires a separate proposed design note. That note must
show:

- the failed E1-E8 composition attempt
- why the failure is structural rather than missing docs or tests
- why the capability is domain-agnostic
- why it belongs below MCP/API/daemon composition layers
- what existing primitive, if any, becomes smaller or collapses after adoption
- the migration and compatibility impact on domain skills

Without that proof, the default answer is "extend one of E1-E8 or document a
composition pattern."

## 5. Coordination Contract For Cowork Findings

Cowork-authored substrate audits are valuable because they come from a
different provider family exercising the same system. They still enter the
same coordination spine as every other durable change:

- Design truth goes to proposed design notes first, then `PLAN.md` only after
  host acceptance.
- Live actionable work goes to `STATUS.md` only when there is a concrete file
  boundary and next step.
- Runtime code changes require a Claude/Codex writer and opposite-family
  checker under the request contract.
- Research-derived or provider-derived conclusions should be rechecked by a
  different provider before they gate implementation or launch.

This prevents provider memory, wiki sync stubs, and audit notes from becoming
parallel architecture sources.

## 6. Decision Asks

1. Should Cowork substrate audits use the four-outcome intake table above as
   the standing triage shape?
2. Should accepted substrate-audit outcomes be folded into the existing
   quarterly substrate audit cadence from
   `2026-04-26-engine-primitive-substrate.md`?
3. If the missing wiki page contains concrete primitive candidates, should each
   candidate become its own proposed design note rather than one bulk substrate
   rewrite?

## 7. Non-Goals

- No new MCP action is proposed.
- No ninth substrate primitive is proposed.
- No runtime code, packaging mirror, or connector behavior changes are implied
  by this note.
- No claim is made that the unavailable Cowork wiki page has been accepted or
  rejected.

