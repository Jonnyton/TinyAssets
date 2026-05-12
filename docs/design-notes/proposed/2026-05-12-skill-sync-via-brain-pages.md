---
title: Skill Sync Via Brain Pages
date: 2026-05-12
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 826
wiki_source: pages/patch-requests/pr-106-pr-116-skills-should-sync-between-host-project-folder-loop-r.md
wiki_type: patch_request
scope: design-only; no runtime code in this branch
builds_on:
  - AGENTS.md#project-skills
  - PLAN.md#scoping-rules
  - PLAN.md#retrieval-and-memory
  - PLAN.md#harness-and-coordination
---

# Skill Sync Via Brain Pages

## Recommendation

Use brain pages as the portable skill-sync record between three projections:

1. Host project folders, currently `.agents/skills/*/SKILL.md`.
2. Loop runtime skill state, used by daemon/community-loop workers.
3. User forks, where contributors may add, edit, or review skills before a
   project maintainer folds them back.

Do not add a substrate-Python intermediary that becomes a fourth authority for
skill content. The durable record should be plain brain/wiki pages plus a small
manifest contract. File-system folders and runtime caches are projections that
can be regenerated or checked from those pages.

This is a design note only. It does not change the current canonical source
declared in `AGENTS.md`; adopting this would require a later accepted PLAN /
AGENTS update and implementation branch.

## Problem Shape

Workflow skills currently have a clear repo-local convention:
`.agents/skills/` is canonical for project-visible agents and
`.claude/skills/` is a Claude Code mirror refreshed by
`scripts/sync-skills.ps1`. That works inside one checkout, but it does not
fully cover the community-loop target shape:

- a host project folder can drift from the loop runtime's active skill set;
- a user fork can improve a skill without the loop seeing it as structured
  brain state;
- a loop-learned skill update can remain trapped in runtime state instead of
  becoming reviewable project knowledge;
- another sync script can silently become the place where skill semantics live.

The request is architectural, not a bug report. The smallest useful change is
to define the sync contract before adding code.

## Sync Contract

Each portable skill record should have one brain page with:

- `skill_id`: stable identifier, matching the folder name when projected.
- `source_path`: preferred repo projection path, usually
  `.agents/skills/<skill_id>/SKILL.md`.
- `version`: monotonic integer or content-addressed revision.
- `content_sha256`: hash of the normalized `SKILL.md` body.
- `status`: `proposed`, `accepted`, `deprecated`, or `superseded`.
- `applies_to`: project, domain, host, or runtime scope.
- `projected_paths`: expected materializations such as `.agents/skills/...`
  and `.claude/skills/...`.
- `review_gate`: whether opposite-family review is required before runtime
  adoption.
- `body`: the skill text or a lossless pointer to an attached body page.

The brain page is the exchange format and audit trail. It should be readable
and editable by the same community/wiki flow that handles patch requests and
brain updates. A folder projection is valid only when its normalized body hash
matches the accepted brain-page revision it claims.

## Projection Rules

The three projections should obey the same authority model:

| Projection | Allowed to do | Not allowed to do |
|---|---|---|
| Host project folder | Materialize accepted skill pages into `.agents/skills/`; produce review diffs | Invent skill revisions without a matching brain page |
| Loop runtime | Load accepted skill revisions by hash; report active skill set | Mutate skill semantics only in runtime cache |
| User fork | Propose skill pages or folder diffs; run local checks | Force project adoption without review/foldback |

Current `.claude/skills/` remains a harness mirror, not a separate source.
If this design is adopted, `scripts/sync-skills.ps1` should become a projection
checker/materializer over accepted skill records, not the semantic owner of the
sync model.

## No Substrate-Python Intermediary

"No substrate-Python intermediary" means there should not be a new Python
service or hidden Python state file that decides what a skill means between the
brain and the repo/runtime projections.

Acceptable implementation later:

- deterministic materialization from brain page content into files;
- hash verification of projected files;
- existing git diffs and review gates for foldback;
- runtime cache files that declare the brain page revision they loaded.

Rejected implementation:

- a Python-only registry that stores canonical skill bodies outside brain pages
  and repo files;
- a sync daemon that rewrites skills without leaving reviewable brain-page
  revisions;
- provider-specific memory as the only record of a skill update;
- runtime-only learning that never becomes a page or patch.

Python may still be used as a mechanical checker or materializer if needed, but
it must be replaceable from the brain-page manifest plus file contents. The
architecture must not depend on Python as the semantic source of truth.

## Minimal Adoption Path

1. Define the brain-page schema for skill records and add one canary skill page
   that mirrors an existing low-risk skill.
2. Add a read-only checker that compares accepted skill pages with
   `.agents/skills/*/SKILL.md` and `.claude/skills/*/SKILL.md` projections.
3. Teach the loop runtime to report the brain-page revision/hash for each skill
   it loads.
4. Only after checker evidence is stable, allow accepted brain skill pages to
   materialize repo projections through normal review.

This keeps the first implementation below the public MCP-action line. A new
chatbot-visible "sync skills" action is not justified for v1; existing page
read/write, git diff, and review primitives should compose the workflow.

## Verification Gates

A later implementation should prove:

- Brain-to-folder: accepted skill page materializes byte-for-byte or normalized
  hash-equivalent into `.agents/skills/<skill_id>/SKILL.md`.
- Folder-to-brain: a fork's edited skill can produce a proposed brain page
  with content hash and review gate intact.
- Runtime-to-brain: the loop runtime logs active `(skill_id, version, hash)`
  values and refuses silently divergent skill bodies.
- Mirror check: `.claude/skills/` still matches `.agents/skills/` after the
  projection path runs.
- Conflict path: two proposed skill revisions with the same parent require
  explicit review resolution, not last-writer-wins sync.
- Absence proof: a daemon claiming "no accepted update exists" uses the
  brain/wiki cursor or enumeration fallback, not search-only evidence.

Because this affects agent behavior, any runtime adoption should require an
opposite-family checker before merge.

## Open Questions

1. Should accepted skill pages become canonical immediately, or should
   `.agents/skills/` remain canonical until the first checker/materializer is
   proven? Recommendation: keep `.agents/skills/` canonical until tooling
   exists, then promote brain pages through an explicit PLAN / AGENTS change.
2. Should skill bodies live inline in one page or as a manifest page plus body
   page? Recommendation: inline for small skills; split only if page-size or
   review UX requires it.
3. Should runtime load directly from brain pages or from projected files?
   Recommendation: load from projected files for v1 and require hash evidence
   linking them back to brain pages.
4. How should private/local-only skills behave? Recommendation: local-only
   skills can have local brain pages or fork-local manifests, but platform
   commons only stores public-by-definition skill records.

## References

- Issue #826: PR-116 skill sync request.
- `pages/patch-requests/pr-106-pr-116-skills-should-sync-between-host-project-folder-loop-r.md`
- `AGENTS.md` Project Skills.
- `PLAN.md` Scoping Rules.
- `PLAN.md` Retrieval And Memory.
- `PLAN.md` Harness And Coordination.
