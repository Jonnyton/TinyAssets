# Template Evolution

Use this when a completed game/prototype reveals reusable structure. The goal
is to accumulate useful templates without bloating the skill with one-off
project details.

## Promotion Criteria

Promote a pattern only when at least one is true:

- It has been useful in two or more projects.
- It prevents a repeated failure.
- It captures a stable engine/archetype boundary.
- It reduces future implementation steps without hiding important decisions.
- It can be verified with a checklist, test, or browser probe.

Do not promote one-off game content, licensed art, generated story text, or
theme-specific names.

## Evolution Pipeline

1. Collect: list files, commands, assets, config, and tests from the completed
   project.
2. Classify: identify the archetype and any hybrid boundaries.
3. Extract: find reusable base classes, hooks, config schema, assets patterns,
   directory structure, and verification checks.
4. Abstract: replace game-specific names and numbers with placeholders or
   config fields.
5. Merge: update the relevant reference pack or template with minimal new text.
6. Verify: run skill validation and, if code/templates were added, run the
   project's build/test/browser checks.

## What To Store

Good template material:

- Directory skeletons.
- Config schemas.
- Hook lists.
- Event contracts.
- Asset key conventions.
- Verification checklists.
- Small starter files that are clearly placeholders.

Bad template material:

- Full generated games.
- Brand/IP-specific assets.
- Huge implementation manuals no one will load.
- Untested snippets.
- Commands that assume unavailable tools.

## Where It Goes

- Reusable game workflow: `game-prototyping/SKILL.md`.
- Archetype-specific design/capability guidance:
  `game-prototyping/references/archetype-packs.md`.
- Asset rules: `game-prototyping/references/asset-protocol.md`.
- Debug signatures/checks: `game-prototyping/references/debug-protocol.md` or
  the broader `debugging-and-error-recovery` skill if not game-specific.
- Cross-provider process rules: `AGENTS.md`, only when every provider needs to
  know the convention outside this skill.
