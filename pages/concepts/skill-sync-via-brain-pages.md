---
title: Skill Sync Via Brain Pages
type: concept
status: proposed
created: 2026-05-12
source_issue: 826
supersedes_pr: 828
tags: [skills, brain, community-loop, user-buildable]
---

# Skill Sync Via Brain Pages

## Purpose

Skills should be shareable across the host project folder, the community-loop
runtime, and user forks without creating another hidden source of truth. Brain
pages are the durable exchange record; local skill folders and runtime caches
are projections.

This page covers portable skill text. Runtime capabilities that skill text
depends on, such as MCP servers and LSP-backed tools, are tracked separately in
[[capability-provisioning-via-brain-pages]] so a skill can declare what it
needs without making one runtime's plugin wrapper canonical for every host.

This page preserves the useful design content from closed PR #828 in the brain
surface instead of `docs/design-notes/proposed/`.

## Recommendation

Use one brain page per portable skill record, with a manifest that can
materialize or verify these projections:

- host project folder: `.agents/skills/<skill_id>/SKILL.md`
- Claude Code mirror: `.claude/skills/<skill_id>/SKILL.md`
- loop runtime cache: the skill body actually loaded by writer/daemon workers
- user fork proposal: a proposed skill revision awaiting review

Do not add a substrate-Python registry that decides what a skill means between
the brain and those projections. Python scripts may mechanically validate or
materialize records, but the semantic record must be the brain page plus normal
review history.

## Skill Page Contract

Each portable skill page should include:

- `skill_id`: stable skill name, matching the folder when projected
- `source_path`: preferred repo projection path
- `version` or `parent_sha256`: revision relationship
- `content_sha256`: normalized body hash
- `status`: `proposed`, `accepted`, `deprecated`, or `superseded`
- `applies_to`: project, domain, host, runtime, or user fork
- `projected_paths`: expected file materializations
- `review_gate`: required checker family or review rule before adoption
- `requires_capability`: optional list of capability IDs defined by accepted
  or proposed capability pages
- `body`: inline skill text, or a lossless pointer to a body page

## Projection Rules

The current repo rule remains active until an implementation changes it:
`.agents/skills/` is canonical and `.claude/skills/` is a mirror. Brain pages
are the target exchange format, not an immediate silent authority change.

Adoption path:

1. Add a canary accepted skill page for one low-risk skill.
2. Add a read-only checker that compares skill pages with `.agents/skills/`
   and `.claude/skills/`.
3. Teach the loop runtime to report the `(skill_id, page, hash)` for each
   loaded skill.
4. Only after checker evidence is stable, allow accepted brain skill pages to
   materialize repo projections through normal PR review.

## Verification Gates

- Brain-to-folder: an accepted page materializes to the expected skill file.
- Folder-to-brain: an edited skill can produce a proposed skill page with hash
  and review metadata.
- Runtime-to-brain: the loop logs which page/hash it loaded for each skill.
- Mirror check: `.claude/skills/` still matches `.agents/skills/`.
- Conflict path: competing revisions require explicit review, not
  last-writer-wins.
- Absence proof: "no accepted update exists" uses a cursor or enumeration
  path, not search-only evidence.

## Current Guardrail

The community-loop writer should read `.agents/skills/using-agent-skills/SKILL.md`
and then load the relevant `.agents/skills/<skill>/SKILL.md` files before
editing. For project-design filings, it should not create
`docs/design-notes/proposed/` drafts by default; it should update brain pages
under `pages/concepts/` or `pages/plans/`, implement the smallest runtime
guardrail, or leave a no-change explanation.

## References

- GitHub issue #826
- Closed PR #828
- `pages/patch-requests/pr-106-pr-116-skills-should-sync-between-host-project-folder-loop-r.md`
- `pages/notes/cowork-checker-key-pr828-reject-plus-writer-prompt-gap-2026-05-12.md`
- `pages/notes/codex-response-cowork-writer-prompt-gap-pr097-status-and-pr633-ready-2026-05-12.md`
