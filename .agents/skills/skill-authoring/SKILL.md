---
name: skill-authoring
description: Creates or updates project-local agent skills with TinyAssets conventions. Use when adding a new skill, merging overlapping skills, tuning trigger descriptions, optimizing a skill for discovery, testing a skill, or updating provider mirrors.
---

# Skill Authoring

## Overview

Create skills that fit this repo's conventions. Don't vendor external skills raw
when the project already has overlapping skills or stronger local patterns —
adapt the ideas, not the file layouts.

## Project Conventions

- Canonical source: `.agents/skills/<skill-name>/`. Mirrors in
  `.claude/skills/` and `.codex/skills/`, refreshed by
  `powershell -ExecutionPolicy Bypass -File scripts/sync-skills.ps1`.
- Default to a single `SKILL.md`. Add `references/` or `scripts/` only when
  repeated detail or deterministic logic justifies it.
- Frontmatter is **only** `name` + `description`. Names lowercase-hyphenated;
  `name` must equal the folder. Descriptions say both what the skill does and
  when to use it (include a "Use when" trigger — the validator requires it).
- When adapting an external repo, record source URL, commit, audit date,
  license, and what was intentionally not imported.
- Don't add `README.md`/`CHANGELOG.md`/`CONTEXT.md` unless the repo adopts them.

## TinyAssets

1. **Audit overlap first.** Decide: new specialist skill, extension to an
   existing one, or a router concern for `using-agent-skills`. Keep routers thin.
2. **Define the job boundary** — primary job, triggers, hand-offs, what it does
   NOT own. If two skills would trigger on the same requests, narrow descriptions
   until the handoff is obvious.
3. **Draft** `.agents/skills/<name>/SKILL.md`: concise frontmatter, short
   overview, procedural project-specific steps, verification. Avoid background
   theory unless it changes execution.
4. **Add resources only when they earn their cost.** `references/` for
   repo-specific schemas/checklists or staged context (light design docs early,
   heavy checklists only at implementation); `scripts/` for deterministic
   helpers. For large skills keep `SKILL.md` as the routing workflow and split
   heavy material by downstream consumer (design / API reference / asset
   protocol / implementation checklist / verification).
5. **Update the router** (`using-agent-skills/SKILL.md`) if discovery changes.
6. **Mirror and verify:** `sync-skills.ps1` → `python scripts/validate_skills.py`
   → `git diff --check` on the skill dirs → spot-check a mirrored copy.

## Skill Discovery Optimization

Skills are auto-selected from their `description` and name, so optimize for
triggering:

- **Rich description = triggering conditions only**, not a workflow summary
  (agents may follow the summary instead of reading the skill). Start with "Use
  when…", describe the problem/symptoms, cover keywords a user would say, third
  person. Don't mention a technology unless the skill is specific to it.
- **Descriptive, specific names** (`conditional-edge-testing`, not `testing`).
- **Token efficiency.** SKILL.md is loaded often — keep it lean. Reference
  `--help` instead of documenting every flag; reference other skills instead of
  repeating their workflow; prefer minimal examples. Heavy material → `references/`
  loaded on demand.

## Skill types

**Technique** (how-to with concrete steps) · **Pattern** (a mental model/rule) ·
**Reference** (API/schema lookup). Match the form to the failure: a
discipline-enforcing skill needs an Iron Law + rationalization table + red
flags; a how-to needs clear steps; a reference needs scannable structure.

## Testing skills

Treat a skill like code: it has a job and can fail. Before relying on a new or
edited skill, test it — ideally dispatch a fresh subagent against a realistic
scenario and see whether the skill triggers and produces the right behavior, then
close loopholes the subagent exploited. See
[testing-skills-with-subagents.md](testing-skills-with-subagents.md) and
[anthropic-best-practices.md](anthropic-best-practices.md). For
discipline-enforcing skills, build the rationalization table from the excuses
the subagent actually used.

## Merge Guidance

When two skills overlap: keep the narrower workflow as a specialist; keep
`using-agent-skills` as dispatcher; merge only when both files truly own the same
job. If one is repo-specific and the other generic, prefer the repo-specific one
and import only the useful heuristics. (You cannot create/modify the user's saved
Cowork skills from a session — those live in Settings > Capabilities.)

## Red Flags

A router teaching every specialist workflow · two skills with near-identical
triggers · copying an external skill's layout against repo norms · description
that summarizes the workflow instead of triggers · resources no one loads ·
forgetting to sync mirrors · skipping `validate_skills.py`.

## Verification

- [ ] Folder is `.agents/skills/<name>/SKILL.md`; frontmatter only name+desc with a "Use when"
- [ ] Descriptions trigger cleanly and don't collide
- [ ] Extra resources exist only when justified; skill tested if non-trivial
- [ ] `using-agent-skills` updated if discovery changed
- [ ] Mirrors refreshed; `python scripts/validate_skills.py` passes; `git diff --check` clean
