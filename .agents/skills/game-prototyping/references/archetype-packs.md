# Archetype Packs

Use these packs to constrain design, assets, and verification before coding.
They are intentionally compact: load only the pack that matches the game.

## Platformer

Use for side-view gravity games with jumping, platforms, hazards, melee/ranged
attacks, collectibles, or bosses.

Design contract:

- Define jump height, gravity feel, movement speed, attack range, health,
  enemy count, checkpoints, and win/loss conditions.
- Start with one short level and one enemy type.
- Keep level geometry simple enough to test manually.
- Use predefined or simple ASCII/layout plans before coding collision.

Asset rules:

- Side-view sprites, usually facing right.
- Full-body player/enemy frames.
- Background should not obscure platforms.
- Platform/ground visual must contrast with hazards and collectibles.

Implementation patterns:

- Separate player, enemy, level scene, and UI/HUD.
- Use existing physics/collision helpers.
- Keep movement/combat behavior configurable.
- Prefer one ultimate/special ability implemented through an existing behavior
  pattern over several bespoke systems.

Checks:

- Player can move, jump, land, and cannot fall through ground.
- Enemy collision and damage work.
- Camera follows without hiding hazards.
- Scene transition fires exactly once at win/loss.
- Animation keys exist for idle/run/jump/attack/hit/death as needed.

Common failures:

- Tile layer name case mismatch.
- Platform collision on the wrong layer.
- Animation key drift between generated files and code.
- Invulnerability or death state never reset.

## Top-Down

Use for overhead movement, twin-stick shooters, stealth, maze, arena survival,
tilemap rooms, or exploration.

Design contract:

- Choose arena mode or tilemap mode.
- Define movement speed, camera behavior, aiming model, enemy AI, projectile
  rules, obstacle behavior, and level boundaries.
- State whether directional sprites are required.

Asset rules:

- Top-down or three-quarter overhead.
- Directional variants if facing direction matters.
- Obstacles and walls must be visually distinct from walkable floor.
- Projectiles must read at small size.

Implementation patterns:

- Use velocity/vector movement, not platform gravity.
- Keep player/enemy animation direction derived from facing or velocity.
- Register all scenes and level order explicitly.
- Use depth sorting when sprites overlap vertically.

Checks:

- Movement respects world bounds and obstacles.
- Aiming/shooting direction matches input.
- Enemy AI can reach or intentionally fail to reach the player.
- Projectiles spawn, collide, and clean up.
- Camera and depth do not hide the player.

Common failures:

- Side-view art used in an overhead game.
- Missing directional animation definitions.
- Obstacles drawn but not colliding.
- Projectiles not destroyed after collision or leaving bounds.

## Grid Logic

Use for discrete board games: Sokoban, sliding puzzles, tactics, roguelikes,
match games, mines, word/number puzzles, or turn-based board interactions.

Design contract:

- Pick the subtype first: puzzle, tactics, match, roguelike, or arcade grid.
- Define board dimensions, cell size, entities, turn rules, movement rules,
  undo scope, win/loss condition, and randomization constraints.
- Keep the first level small and solvable.

Asset rules:

- Readable tokens at cell size.
- Distinct cell backgrounds, blockers, goals, hazards, and player pieces.
- Avoid detailed art that makes state hard to scan.

Implementation patterns:

- Board state is the source of truth; rendering follows board state.
- Keep turn resolution deterministic.
- Use an animation queue when movement is visual but logic is discrete.
- Snapshot all mutable state if undo exists.

Checks:

- Invalid moves do not mutate state.
- Valid moves update board state once.
- Undo restores board, score, cooldowns, inventory, and timers when relevant.
- Win/loss detection happens after state settles.
- Random boards are seeded or testable.

Common failures:

- UI sprite moves but board state does not.
- Board state changes twice for one input.
- Undo restores positions but not secondary state.
- Generated levels are unsolvable.

## Tower Defense

Use for path-and-wave games with tower placement, enemy waves, economy,
upgrades, obstacles, and a defended target.

Design contract:

- Define path waypoints, grid/cell system, buildable cells, blocked cells,
  economy, wave list, tower types, enemy types, target health, and upgrade
  rules.
- Start with one path, two tower types, and two enemy types.
- State target priority rules: first, nearest, strongest, weakest, or custom.

Asset rules:

- Top-down towers, enemies, obstacles, target, projectiles, and slot markers.
- Distinct projectile images per tower type when projectiles are visible.
- Path and buildable cells must be unambiguous.

Implementation patterns:

- Wave manager owns spawning.
- Economy manager owns spend/reward.
- Tower grid owns occupied cells.
- Tower fire logic should use existing targeting/projectile helpers.
- Obstacles should be data-driven, not hardcoded into draw calls.

Checks:

- Enemies follow the path in waypoint order.
- Towers can only be placed on valid empty cells.
- Spend/reward cannot go negative unless intentionally allowed.
- Projectiles hit or miss according to speed/range rules.
- Wave completion and next-level transition work.

Common failures:

- Buildable cells overlap the path.
- Towers placed on already occupied cells.
- Projectile data read after the projectile is destroyed.
- Enemy type strings in waves do not match factory mappings.
- Level order never advances.

## UI-Heavy

Use for dialogue, cards, quizzes, menus, story choices, turn battles,
relationship systems, or interactive fiction with heavy visual UI.

Design contract:

- Define scene flow, dialogue data, card/deck data, quiz/question data,
  battle rules, ending conditions, and save/progress state.
- Start with one complete interaction loop: choose, resolve, show feedback,
  continue/end.
- Specify keyboard/mouse/touch controls.

Asset rules:

- Portraits are front or three-quarter view.
- Use expression variants when dialogue needs emotion.
- Cards/icons must be legible at actual UI size.
- Avoid putting essential text inside generated images.

Implementation patterns:

- UI state transitions should be explicit.
- Dialogue, cards, and questions should live in data structures.
- Modal depth/z-index must not hide feedback that should be visible.
- Clean up dynamic UI elements between rounds/scenes.

Checks:

- Dialogue character IDs match registered characters.
- Cards/questions have all fields used by render and resolution logic.
- Buttons are keyboard accessible when the project UI supports it.
- Scene transitions use registered keys.
- Round state resets before a new round starts.

Common failures:

- Instantiating static helper UI classes instead of using their static methods.
- Importing invented type names.
- Overriding hooks that do not exist.
- Hiding HP/status changes under a modal overlay.
- Forgetting to complete the enemy/opponent turn.

## Hybrid Guidance

For hybrids, assign each subsystem to one owner pack. Example:

```text
Top-down owns movement/combat.
UI-heavy owns dialogue and card rewards.
Grid-logic owns inventory puzzle rooms.
```

Do not merge all pack rules into one giant design. Load only the packs that
own real subsystems, and write explicit boundaries between them.
