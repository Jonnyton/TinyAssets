---
title: Issue 537 Coordination Note Dispatch Classification
date: 2026-05-08
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 537
wiki_source: pages/notes/codex-response-cowork-mcp-architectural-collapse-plan-2026-05-06.md
scope: classification-only; no runtime code in this branch
builds_on:
  - docs/ops/wiki-bug-sync-runbook.md
  - docs/exec-plans/active/2026-04-30-live-community-reiteration-loop.md
  - PLAN.md#harness-and-coordination
---

# Issue 537 Coordination Note Dispatch Classification

## Recommendation

Treat Issue #537 as a dispatch-classification artifact, not as a project
implementation request.

The referenced wiki source is a `pages/notes/*` coordination response about
sequencing existing implementation lanes (`PR-047`, `PR-063`, `PR-064`, and
`PR-065`). It is brain context for those explicit patch requests. It is not a
new design contract, patch packet, feature request, or runtime change request.

Close or hold any automated PR produced directly from Issue #537 unless that PR
maps back to a separate explicit request artifact.

## Existing Design And Fix State

Freshness stamp: 2026-05-08, local checkout
`design-note-draft/issue-537-codex-2556869956` against `origin/main`.

- `docs/ops/wiki-bug-sync-runbook.md` already says ordinary
  `pages/notes/*` coordination artifacts are ignored by sync.
- `scripts/check_primitive_exists.py bug BUG-071` reports commit
  `cd341965` on `origin/main`: "BUG-071: Coordination notes can be synced as
  daemon-request project-design work (#566)".
- That landed fix updates `scripts/wiki_bug_sync.py` so non-builder
  `pages/notes/*` entries return no request kind.
- The same commit adds regression coverage in `tests/test_wiki_bug_sync.py`
  for a coordination note with architectural language and for the builder-note
  exception.

## Classification Rule

For community-loop dispatch, a wiki note is not request authority just because
its title uses design, architecture, sequencing, or collapse-plan language.

Dispatch authority requires one of these:

- an explicit patch, feature, bug, docs/ops, branch-refinement, or
  project-design request artifact;
- a builder note that enters the branch-refinement lane;
- a promoted plan/concept whose shape is intentionally classified by
  `wiki_bug_sync.py`.

Everything else under `pages/notes/*` remains context. Agents may read it while
working on the real lane, but they should not create runtime changes or design
branches from it directly.

## Non-Goals

- Do not modify MCP actions, daemon runtime, wiki storage, or GitHub workflow
  behavior for Issue #537.
- Do not redesign the underlying PR-047/PR-063/PR-064/PR-065 lanes here.
- Do not add another classifier rule unless a new failing source shape appears;
  BUG-071 already covers the source class named by this issue.

## Verification

Run the existing focused classifier regression:

```bash
python -m pytest tests/test_wiki_bug_sync.py -q
```

No `python -m ruff check` invocation is required for this branch unless Python
files are touched.
