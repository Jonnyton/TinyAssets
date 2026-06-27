# TinyAssets Server Plugin

Packaged Claude plugin for the TinyAssets Server.

## Packaged Skills

- [premise/SKILL.md](skills/premise/SKILL.md)
- [progress/SKILL.md](skills/progress/SKILL.md)
- [status/SKILL.md](skills/status/SKILL.md)
- [steer/SKILL.md](skills/steer/SKILL.md)

## Structure

- `.claude-plugin/` - plugin metadata
- `runtime/` - packaged runtime files
- `skills/` - plugin-local slash-command docs

## Notes

- These skills are intentionally scoped to the packaged plugin experience.
- They should be read together as a plugin surface, not mixed into the main
  engineering skill graph.
