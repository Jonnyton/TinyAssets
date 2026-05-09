---
title: Brain Update 003 Completeness Cursor And Enumeration Fallback
date: 2026-05-08
author: codex-wiki-docs
status: proposed
request_id: WIKI-DOCS
github_issue: 657
wiki_source: pages/concepts/brain-update-003-completeness-cursor-enumeration-fallback.md
wiki_type: brain_update
scope: design-only; no runtime code in this branch
priority: loop-discipline
builds_on:
  - PLAN.md#retrieval-and-memory
  - PLAN.md#harness-and-coordination
  - pages/notes/cowork-codex-enumeration-replaces-search-for-counterpart-completeness-2026-05-08.md
  - pages/notes/cowork-step-4-consensus-codex-canary-verification-accepted-timestamp-lint-corrections-applied-2026-05-08.md
---

# Brain Update 003 Completeness Cursor And Enumeration Fallback

## 1. Recommendation Summary

Treat counterpart-note completeness as a cursor and integrity problem, not a
search-ranking problem. A daemon that reads brain/wiki updates should advance
from the last fully consumed `(change_seq, page_version)` cursor, detect gaps
before trusting the new window, and fall back to path enumeration when the
cursor stream is incomplete or suspicious.

This is a loop-discipline update, not ordinary docs backlog. It addresses the
repeated miss class where counterpart notes existed but were skipped because a
provider relied on search terms, date filters, or "recent enough" heuristics.
The accepted behavior is: enumerate the authoritative paths when completeness
matters, then use search only as a convenience layer over that complete set.

## 2. Problem Shape

The observed failure class has four parts:

1. A counterpart note exists in the wiki/brain surface.
2. The daemon tries to find it through search, recency filters, or a guessed
   title pattern.
3. The query misses the note or returns a partial set.
4. The daemon proceeds as if the partial result were complete.

That is not a model-quality issue. It is an integrity-contract issue. Search is
allowed to rank or narrow known content, but it cannot prove that no matching
counterpart exists. Completeness needs either a monotonic cursor over changes
or a full path enumeration fallback.

## 3. Cursor Contract

The brain/wiki change stream should expose a monotonic `change_seq` and a
per-page `page_version`.

- `change_seq` orders every committed wiki/brain mutation in one stream.
- `page_version` increments for each changed page and lets readers distinguish
  stale cached content from the current page body.
- A reader stores the highest contiguous `change_seq` it has fully processed,
  plus the `page_version` observed for every path it uses as evidence.
- A reader must not advance its durable cursor past a missing `change_seq`.
- A reader that sees a duplicate, regression, or version mismatch treats the
  window as suspect and runs the enumeration fallback before making a
  completeness-sensitive claim.

The cursor is a proof boundary: "I consumed all changes through sequence N" is
valid only when every sequence between the old cursor and N was observed and
validated.

## 4. Gap Detection

Gap detection should be mechanical and conservative:

| Condition | Required behavior |
|---|---|
| Next `change_seq` is greater than expected | Stop cursor advancement and enumerate paths before proceeding |
| Next `change_seq` is less than or equal to processed cursor | Ignore as already consumed unless `page_version` contradicts cache |
| Same path has lower `page_version` than cached | Treat as stale source; re-read canonical page before using it |
| Same path has higher `page_version` without a matching change event | Treat as stream gap; enumerate paths and refresh that page |
| Path required for a counterpart decision is absent from the cursor window | Enumerate the relevant path prefix before claiming absence |

The safe response to an integrity anomaly is not a broader search query. It is
to switch to path enumeration and reconcile the local cursor state from the
authoritative path list.

## 5. Enumeration Fallback

Path enumeration is the integrity fallback. It should be used when:

1. A daemon makes a completeness-sensitive claim, such as "no counterpart note
   exists" or "all accepted canary notes have been read."
2. Cursor gap detection reports an incomplete window.
3. The daemon is starting from an empty or unknown local cursor.
4. A reviewer or canary requires proof that a specific note family was checked.

Enumeration does not need to replace search for ordinary discovery. The rule is
that search cannot be the only proof for absence or completeness. For a scoped
note family, enumerate the relevant prefix, filter paths mechanically, then
read exact paths and compare `page_version` before summarizing.

## 6. Minimal Implementation Boundary

V1 should stay below the public MCP-action line unless current wiki primitives
cannot expose the required data. The preferred order is:

1. Extend the existing wiki listing or change-feed internals to include
   `change_seq`, `page_version`, and enough path metadata for reconciliation.
2. Add daemon-side cursor storage and focused tests for gaps, duplicates,
   stale page versions, and enumeration fallback.
3. Update loop prompts/runbooks so counterpart-note checks require cursor or
   enumeration evidence.
4. Add a canary that plants a counterpart note whose title is not discoverable
   by the old search/date heuristic and proves the daemon still finds it.

Do not add a chatbot-visible "find counterpart notes" convenience tool for v1.
If a new primitive is unavoidable, it should be a general integrity primitive
for wiki changes and path enumeration, not a policy-specific counterpart-note
action.

## 7. Verification Gates

A build that implements this update should prove:

- Fresh-reader path: empty cursor enumerates the relevant prefix before making a
  completeness-sensitive claim.
- Normal cursor path: contiguous `change_seq` advances without enumeration.
- Gap path: missing `change_seq` blocks cursor advancement and triggers
  enumeration.
- Version path: unexpected `page_version` refreshes exact page content before
  evidence is cited.
- Counterpart canary: a counterpart note missed by search/date heuristics is
  found through cursor/enumeration behavior.
- Regression guard: daemon prompts or runbooks no longer present search as
  sufficient evidence for absence.

Because the request is loop-discipline work, final acceptance should include an
opposite-family checker before any runtime merge. The checker should inspect
both the implementation evidence and a rendered or logged daemon loop that
uses cursor/enumeration proof instead of search-only proof.

## 8. Open Questions

1. Where is the authoritative `change_seq` assigned: wiki storage, sync bridge,
   or the brain-update feed? Recommendation: assign it at the write boundary
   that already serializes committed page mutations.
2. Should enumeration be global or prefix-scoped? Recommendation: prefix-scoped
   for normal daemon work, with global enumeration reserved for repair/audit.
3. How long should per-path `page_version` evidence be retained? Recommendation:
   keep it with the daemon's local cursor until a later full enumeration
   supersedes it.
4. Should the wiki page itself remain the canonical brain-update artifact?
   Recommendation: yes. This proposed note is a repository-side bridge because
   the `pages/concepts/...` source is not present in this checkout and the wiki
   droplet is currently claimed by loop-dev.

## References

- Issue #657: BrainUpdate BU-003
- `pages/concepts/brain-update-003-completeness-cursor-enumeration-fallback.md`
- `pages/notes/cowork-codex-enumeration-replaces-search-for-counterpart-completeness-2026-05-08.md`
- `pages/notes/cowork-step-4-consensus-codex-canary-verification-accepted-timestamp-lint-corrections-applied-2026-05-08.md`
- `PLAN.md` Retrieval And Memory
- `PLAN.md` Harness And Coordination
