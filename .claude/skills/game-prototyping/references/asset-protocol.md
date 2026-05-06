# Asset Protocol

Plan game assets as a contract before generating or coding them. The most
common game-agent failures are key drift and missing assets, not a lack of
visual imagination.

## Asset Registry

Create an asset table before generation:

| type | key | file/output | used by | style/prompt | checks |
|---|---|---|---|---|---|

Rules:

- One stable `key` per loadable asset.
- The same key must appear in the asset manifest, animation definitions,
  config, and code.
- Prefix keys by role when useful: `player_`, `enemy_`, `bg_`, `tile_`,
  `icon_`, `sfx_`, `bgm_`.
- Record whether an asset is final, placeholder, generated, searched, or hand
  drawn.

## Asset Types

### Background

Use for full-screen or level backdrops. Prefer 16:9 or the actual viewport
aspect. Do not request transparency unless the background is a layer.

Checks:

- Fills the viewport without unintended stretching.
- Does not hide gameplay entities.
- Loads before gameplay starts or has a clear loading state.

### Tileset Or Tile Pattern

Use only when the engine actually consumes tiles. If the game uses code-defined
grids, do not create a tileset just because the archetype is grid-like.

Checks:

- Tiles align to the configured tile size.
- Tile edges are clean and repeat without visible seams.
- Legend or tile IDs match the map data.

### Animation Or Sprite Frames

Use for moving characters, enemies, effects, and projectiles. Prefer fewer,
consistent frames over many inconsistent frames.

Checks:

- Frame keys exist in the manifest.
- Animation keys exist in the animation definition file.
- Code references animation keys, not raw frame filenames.
- Side-view sprites face the same default direction; use flipping in code.

### Image, Sprite, Icon, Or Portrait

Use for static game objects, UI, portraits, cards, towers, projectiles, and
inventory items.

Checks:

- One object/character per image unless the asset is intentionally a group.
- Transparent or plain background when the object should be composited.
- Clear silhouette at final display size.

### Audio

Use for primary feedback only at first: action, hit, collect, win, lose, menu,
and one background loop.

Checks:

- File format is supported by the target browser.
- Duration is short enough for the interaction.
- Volume is balanced against other sounds.
- Playback is gated by user interaction when the browser requires it.

## Map And Tilemap Protocol

Use map data when level layout matters. Do not bury level geometry in scene
code unless the game is a tiny prototype.

### ASCII Layouts

ASCII maps are useful for platformers, top-down tilemaps, grid puzzles, and
tower-defense paths. Each symbol needs a legend:

```text
########
#P..E..#
#..##..#
#....G.#
########
```

Example legend:

```yaml
"#": wall_or_ground
".": empty_or_floor
"P": player_spawn
"E": enemy_spawn
"G": goal
```

Rules:

- All rows must have the same width.
- Object markers such as player/enemy/goal should not become solid tiles by
  accident.
- Keep collision layers and visual layers separate when the engine supports
  it.
- Name tilemap layers exactly; layer names are usually case-sensitive.

### Dual Tilesets

Top-down tilemaps often need separate floor and wall visuals. Treat these as
two asset keys and two layers unless the engine template expects otherwise.

Checks:

- Walkable floor is visually calm.
- Walls/blocked cells have stronger contrast.
- Collision applies to the wall/blocked layer, not decorative floor.

### 3x3 To 7x7 Expansion

OpenGame's tooling expands a simple 3x3 tileset into a fuller blob tileset for
auto-tiling. If Workflow later builds local game tooling, this is a good
candidate to implement as a deterministic helper:

- Input: 3x3 tiles for corners, edges, and center.
- Output: 7x7 blobset with repeated edges, center fills, and inner corners.
- Pair with an 8-neighbor bitmask auto-tiler.

## Prompting Rules

Use one style anchor for a batch:

```text
Style anchor: 16-bit pixel art, high-contrast silhouettes, readable at 64px,
consistent palette, no text baked into the image.
```

Character prompts should specify:

- View angle: side, top-down, front, or three-quarter.
- Facing direction.
- Full body vs bust.
- Action pose and limb/body position.
- Props that must stay consistent.
- Background treatment: transparent, plain white, or full environment.

Generate in small batches. If the batch is large, split by role:

1. Core player/enemy/UI assets.
2. Environment/background/tile assets.
3. Effects/audio/polish assets.

## Archetype View Rules

- Platformer: side view, usually facing right, full body.
- Top-down: overhead or three-quarter overhead; include directional variants
  when movement direction matters.
- Grid logic: readable tokens from top-down or orthographic view.
- Tower defense: top-down towers, enemies, projectiles, obstacles, path/slot
  markers.
- UI-heavy: front or three-quarter portraits, static expressions, cards and
  panels optimized for readability.

## Verification Checklist

Before coding:

- [ ] Every planned asset has a unique key.
- [ ] Style anchor is consistent across the batch.
- [ ] Character orientation matches the archetype.
- [ ] Placeholder assets are labeled as placeholders.

Before final verification:

- [ ] Every key referenced in code/config exists in the manifest.
- [ ] Every animation key referenced in code exists in animation definitions.
- [ ] Browser console has no missing texture, failed image, or failed audio
      errors.
- [ ] The game renders nonblank visuals on desktop and mobile viewports.
- [ ] The user can distinguish player, obstacles, enemies, interactive items,
      and feedback effects at actual game size.

If no asset-generation tool is available, do not invent one. Use existing
assets, create simple local placeholders with clear labels, or record the asset
gap as an explicit follow-up.
