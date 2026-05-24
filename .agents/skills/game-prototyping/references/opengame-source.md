# OpenGame Source Notes

Source audited: `https://github.com/leigest519/OpenGame`

Commit audited: `c54307e` (`2026-04-22T12:50:54+08:00`)

Audit date: `2026-05-01`

License observed in the source checkout: Apache License 2.0.

## What Was Imported

This skill adapts concepts from OpenGame's Game Skill stack rather than
vendoring its files raw:

- Template-first game creation.
- Debug protocol with reusable signatures and proactive checks.
- GDD-style downstream contract.
- Asset planning and key-consistency checks.
- Archetype packs for platformer, top-down, grid logic, tower defense, and
  UI-heavy games.
- Context staging: light design/capability docs first, heavy implementation
  docs only when coding.

## What Was Not Imported

- OpenGame's Qwen runtime assumptions.
- `generate_game_assets`, `generate_tilemap`, or other OpenGame-specific tool
  names as required commands.
- Phaser template source files.
- Provider-specific environment variables.
- Large raw archetype manuals.

## Additional Candidates Found

These were found in the broader repo scan and are worth considering only when
Workflow has a concrete need:

- Physics-first classifier: `packages/core/src/tools/game-type-classifier.ts`.
  The decision tree is already reflected in `archetype-packs.md`; a tool is
  only worth building if we repeatedly classify game requests.
- GDD generator: `packages/core/src/tools/generate-gdd.ts`. The useful pattern
  is auto-loading core rules plus design rules plus template capability docs.
  That pattern is now reflected in `gdd-contract.md` and `context-engineering`.
- Asset pipeline: `generate-assets.ts`, `assetImageService.ts`,
  `assetAudioService.ts`, `assetVideoService.ts`, background removal, and frame
  extraction. Worth revisiting if we need repeatable local game-asset output
  instead of ad hoc image generation.
- Tilemap pipeline: `generate-tilemap.ts`, `auto-tiler.ts`, and
  `tileset-processor.ts`. Worth copying as a deterministic helper if we build
  several tile-based games.
- Copy-template tool: `copy-template.ts`. The key idea is safe scaffold copying
  that does not overwrite existing files.
- Skill manager: `packages/core/src/skills/skill-manager.ts`. Mostly overlaps
  our existing `validate_skills.py`; no import needed now.
- OpenGame-Bench: README describes dynamic playability evaluation across build
  health, visual usability, and intent alignment, but the pipeline is not
  released in this checkout. Good future inspiration for browser-game
  acceptance probes.

Future sessions should treat these references as Workflow-local guidance. If
we later vendor source templates, preserve Apache-2.0 notices and document the
source commit next to the copied files.
