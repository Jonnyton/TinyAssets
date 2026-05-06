---
name: game-prototyping
description: Builds playable browser games and game-like interactive prototypes with template-first, asset-aware, archetype-specific workflows. Use when creating, refactoring, or debugging games, Phaser/Canvas/Three.js interactions, arcade or puzzle prototypes, generated game assets, or game design documents.
---

# Game Prototyping

## Overview

Build playable browser games and game-like interactive prototypes without
letting the agent improvise a whole engine from scratch. This skill adapts the
useful parts of OpenGame's Game Skill into Workflow conventions: staged
context, template-first implementation, explicit asset contracts, archetype
packs, and systematic runtime debugging.

Do not assume OpenGame-only tools such as `generate_game_assets` exist in this
repo. Use the available project stack and harness tools. If an asset or game
tool is unavailable, state that plainly and pick a reversible fallback.

## When To Use

- The user asks for a game, playable prototype, arcade interaction, puzzle, or
  game-like demo.
- A frontend task includes sprite animation, canvas/Phaser/Three.js mechanics,
  levels, scoring, combat, grid logic, or wave/path systems.
- You need generated or curated visual/audio assets for an interactive
  experience.
- A browser game build fails because of assets, scene wiring, config drift, or
  runtime canvas errors.

Do not use this for ordinary dashboard/product UI unless it has real game-loop
or game-asset behavior.

## Workflow

### 1. Classify The Archetype

Pick the dominant archetype before designing:

- `platformer`: side-view gravity, jumping, platforms, melee/ranged action.
- `top-down`: overhead movement, aiming, pathfinding, arena or tilemap worlds.
- `grid-logic`: discrete board state, puzzles, tactics, match, roguelike turns.
- `tower-defense`: paths, waves, economy, tower placement, target priority.
- `ui-heavy`: dialogue, cards, quizzes, menus, battles, story choices.
- `hybrid/custom`: combine packs deliberately and name which one owns each
  subsystem.

Use `references/archetype-packs.md` for the design constraints, asset rules,
and verification risks.

### 2. Write A Downstream-Aware Spec

Before coding, write a compact GDD-style contract using
`references/gdd-contract.md`. Each section must name the downstream consumer:
asset plan, config, scene registration, entity/hooks, levels/content, and
verification.

No vague values. Numeric tuning, scene keys, asset keys, and control schemes
must be concrete enough to implement and test.

### 3. Choose Existing Engines And Templates

Use a proven engine/library for the core loop when available:

- Phaser for 2D browser games.
- Three.js for real 3D scenes.
- Existing project components/templates before new abstractions.

Prefer hook overrides, behavior composition, config edits, and copied template
files over rewriting base systems. Only add a new engine subsystem when no
local template/library covers the required mechanic.

### 4. Plan Assets Before Generating Or Coding

Use `references/asset-protocol.md` to create an asset registry first. Keep keys
stable across the asset manifest, animation definitions, config, and code.

Generate assets in small batches with one style anchor. Verify each asset loads
in the browser before declaring the game playable.

### 5. Stage Context Loading

Keep early context light:

1. Read the archetype design rules and GDD contract.
2. Read the asset protocol when planning visuals.
3. Read template/API references when deciding implementation files.
4. Read full source/templates only immediately before editing.
5. Read the debug protocol only when verifying or fixing failures.

This avoids filling the context with heavy implementation manuals before the
design and asset contract are stable.

### 6. Implement Thin Playable Slices

Build the first playable loop before adding breadth:

1. Boot screen/scene.
2. Player/input or primary interaction.
3. One enemy/puzzle/wave/content unit.
4. Win/lose or completion condition.
5. HUD feedback.
6. Asset polish.

Each slice must leave the game runnable.

### 7. Verify Like A Game, Not A Static Page

Follow `references/debug-protocol.md`:

- Build/typecheck first.
- Run tests if the project has them.
- Start the dev server in the background.
- Use browser verification for canvas pixels, console errors, input, animation,
  layout, and asset loading.
- Record repeated failures as protocol entries or proactive checks.

For Three.js, also follow this repo's frontend instruction to verify canvas
pixels across desktop and mobile viewports.

### 8. Capture Reusable Patterns

After a successful game/prototype, decide whether it produced a reusable
template, check, asset convention, or archetype rule. If yes, update this skill
or its references through `skill-authoring`. If the same failure recurs across
sessions, use `auto-iterate`.

## Reference Map

- `references/opengame-source.md`: source audit and adaptation boundary.
- `references/gdd-contract.md`: downstream-aware game spec format.
- `references/asset-protocol.md`: asset planning, naming, prompts, and checks.
- `references/archetype-packs.md`: platformer, top-down, grid, tower defense,
  and UI-heavy packs.
- `references/debug-protocol.md`: game-specific verification and failure
  protocol.
- `references/template-evolution.md`: when and how to promote reusable game
  templates.

## Handoffs

- `frontend-ui-engineering`: non-game UI polish, accessibility, responsive
  layout.
- `browser-testing-with-devtools`: runtime browser verification.
- `debugging-and-error-recovery`: root-cause debugging outside game-specific
  checks.
- `spec-driven-development`: larger product specs and acceptance criteria.
- `skill-authoring`: updating this skill or adding reusable references.
