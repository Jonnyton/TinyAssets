# Game Design Contract

Use this compact GDD format before coding a game or game-like prototype. The
point is not a long design document; it is a downstream contract that prevents
asset, config, scene, and implementation drift.

## Core Principles

- Config-first: numeric tuning belongs in config or constants, not scattered
  through gameplay code.
- Template-first: use existing engines, templates, hooks, and components before
  inventing custom systems.
- Behavior-first: compose movement, combat, interaction, and UI behaviors when
  the archetype already has a pattern.
- Concrete values: no "some enemies", "appropriate speed", or "nice effect".
- Exact keys: scene IDs, asset keys, animation keys, config paths, and route
  names must be spelled exactly once and reused consistently.

## Required Sections

### 0. Technical Architecture

Consumer: scene registration, engine boot, routing, build setup.

Must include:

- Engine/library choice.
- Archetype and any hybrid split.
- Resolution/aspect ratio.
- Scene flow, with exact scene key strings.
- First playable slice.
- Files likely touched.

### 1. Visual Style And Asset Registry

Consumer: asset creation, asset manifest, animation definitions, preloader.

Must include an asset table:

| type | key | use | prompt/style note | verification |
|---|---|---|---|---|

Use stable keys. Every asset key planned here must later exist in the manifest
or be removed from code/config before verification.

### 2. Game Configuration

Consumer: config files, constants, balancing.

Must include complete values for:

- Screen/camera settings.
- Player/input stats.
- Enemy/puzzle/wave/content stats.
- Economy, score, timers, cooldowns, or win/loss thresholds.
- Feature flags or debug settings.

### 3. Entity And Scene Architecture

Consumer: source files, templates, hooks, class/component boundaries.

Must include:

- Base class/component to extend.
- Existing behavior/system to reuse.
- Hooks to override, with exact names if known.
- Event names and ownership.
- Data ownership: scene state, entity state, global state, URL state.

### 4. Level And Content Design

Consumer: levels, maps, puzzle data, dialogue, waves, encounters.

Must include:

- Level order.
- Spawn points or board layout.
- Content data structures.
- Difficulty progression.
- Minimum content needed for the first playable slice.

### 5. Implementation Roadmap

Consumer: task list and code edits.

Write file-level operations:

```text
1. UPDATE src/gameConfig.* with the Section 2 values.
2. UPDATE scene registration with [ExactSceneKey].
3. COPY/CREATE scene/entity files from [template/source].
4. IMPLEMENT hooks [hook names].
5. ADD tests/browser checks for [specific behavior].
```

### 6. Verification Plan

Consumer: tests, browser checks, debug protocol.

Must include:

- Build/typecheck command.
- Test command, if available.
- Dev server command and URL.
- Browser interactions to perform.
- Asset/animation/scene/config consistency checks.
- Canvas-pixel or screenshot checks for nonblank rendering.

## Forbidden In The GDD

- "Implement from scratch" when an existing template/library covers it.
- Unspecified numbers.
- Asset keys that are not listed in the registry.
- Scene transitions to unregistered scene keys.
- Custom engine systems for mechanics already handled by a library.
- Copying external code without adapting it to the project conventions.
