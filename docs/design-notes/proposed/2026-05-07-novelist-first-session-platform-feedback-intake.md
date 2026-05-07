---
title: Novelist First-Session Platform Feedback Intake
date: 2026-05-07
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 312
wiki_source: pages/design-proposals/design-002-novelist-first-session-platform-feedback-six-gaps-from-merid.md
scope: intake recovery only; no runtime code in this branch
---

# Novelist First-Session Platform Feedback Intake

## 1. Classification

Issue #312 is a project-design filing. It was auto-filed from a wiki design
page titled "Novelist first-session platform feedback: six gaps from
meridian-ashes continuity-engine test."

This note is not the real architectural answer to those six gaps. It is the
smallest safe project-design change available while the source design page is
missing: preserve the request, record the blocker, and define the minimum
source package needed before Workflow accepts design or implementation work
from this filing.

## 2. Verified Source Gap

Verified on 2026-05-07 UTC:

- Local repo search found no matching `design-002`, `meridian`,
  `meridian-ashes`, or `six gaps` design content.
- The referenced local path does not exist:
  `pages/design-proposals/design-002-novelist-first-session-platform-feedback-six-gaps-from-merid.md`.
- GitHub issue #312 contains request metadata and the wiki path pointer, but
  not the community-authored proposal body.
- GitHub raw content for the referenced path on `main` returned `404`.
- A prior remote draft branch for issue #312 also treated the source page as
  unavailable and drafted an intake-recovery note rather than guessing.

The title says "six gaps," but the six gap descriptions, first-session
transcript, evidence, and proposed remedies are not available in the repository
or issue body.

## 3. Recommendation

Treat WIKI-DESIGN / issue #312 as **blocked on source recovery**.

Do not infer the six gaps from adjacent novelist, fiction-memory, or
continuity-engine material. Workflow has relevant prior design work, but using
that material to reconstruct this specific community report would invent facts
and could send future implementation toward the wrong boundary.

The correct follow-up is to recover or re-file the missing wiki body, then
write a design note that maps each verified gap to one of these outcomes:

- existing primitive composition;
- fantasy-domain behavior;
- MCP/chatbot surface metadata;
- retrieval or memory policy;
- onboarding or discoverability;
- community-process or wiki-sync repair;
- explicit non-goal.

## 4. Required Source Package

Before PLAN.md changes, runtime code changes, or accepted design decisions,
the recovered source package should include:

1. The six observed gaps, each tied to the prompt or first-session step that
   exposed it.
2. Expected novelist-facing behavior in domain vocabulary.
3. Observed Workflow behavior, including whether the failure appeared in MCP
   tool discovery, daemon execution, retrieval/memory, domain API shape, or
   chatbot narration.
4. Evidence from the `meridian-ashes` continuity-engine test: transcript,
   trace, artifact paths, screenshots, or run identifiers.
5. A suggested classification per gap: engine primitive, fantasy-domain
   capability, chatbot-surface copy/tool metadata, retrieval/memory policy,
   onboarding/discoverability, or community-process issue.
6. Privacy notes for any story text, canon, or user-authored content included
   in the evidence.

## 5. Design Constraints For The Real Follow-Up

Any eventual design note should preserve the current PLAN.md scoping rules:

- `workflow/` remains goal-agnostic infrastructure.
- Fantasy or novelist behavior belongs in the fantasy domain, domain
  registration, or community-evolved composition before shared engine code.
- MCP clients are control stations; the daemon performs the creative or
  continuity work.
- Prefer small composable primitives over new overlapping tools.
- Generator behavior, evaluator behavior, and ground-truth evidence remain
  separate.
- Browser-only and local-app users both matter; a first-session novelist gap
  should name which capability tier and MCP host exposed it.

## 6. Rejected Alternatives

### Draft the six gaps from the issue title

Rejected. The repository contains adjacent novelist and fiction-memory design
material, but the actual six observations are not present. Guessing would turn
community feedback into agent-authored fiction.

### Change runtime code now

Rejected. The request is architectural/project-design, and no verified
implementation target is available.

### Close the request as unworkable

Rejected. The filing shape is valid and points at a concrete missing wiki
source. The useful project response is to preserve the lane and state exactly
what recovery evidence is needed.

### Add a new MCP action for novelist first sessions

Rejected for now. The missing source package does not establish a primitive
gap, and PLAN.md requires proposed tools/actions to pass minimal-primitives and
community-build checks before platform code.

## 7. Open Questions

1. Can the wiki-change-sync path recover the deleted or unsynced wiki page from
   the source store, event payload, branch artifact, or workflow logs?
2. Was `meridian-ashes` private story material that needs redaction or
   summary before landing in the public repository?
3. Should future wiki-sync design issues include a body snapshot so a missing
   wiki page does not erase the actionable proposal?
4. Should wiki-change-sync file a distinct `missing-source` issue when the
   referenced page cannot be fetched, instead of a normal project-design issue?
5. Once the source is restored, should the real follow-up be one design note or
   six smaller notes split by boundary?

## 8. Acceptance Gate For The Real Design

This intake note is complete when it lands as a placeholder and issue #312
remains blocked on source recovery. The real design response is complete only
after the missing source exists and a follow-up note maps each verified gap to
an accepted design boundary, composition path, or explicit non-goal.
