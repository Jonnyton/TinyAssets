# Knowledge Schema

TinyAssets uses two complementary knowledge surfaces:

- `knowledge.db` for machine-facing retrieval and runtime state
- `knowledge/` markdown for human-readable compiled understanding

## Rule 1: Raw Sources Stay Raw

Put immutable external inputs in `data/`, exports, or other source-specific
surfaces. Do not silently rewrite raw source material.

## Rule 2: Knowledge Pages Are Compiled

Put interpreted durable understanding in:

- `knowledge/pages/`
- `knowledge/syntheses/`

These pages should:

- cite source files or docs
- link to related notes
- separate evidence from interpretation

## Rule 3: Keep The Graph Connected

Whenever you add a knowledge page:

1. link it from `knowledge/INDEX.md`
2. append the event to `knowledge/LOG.md`
3. add sideways links to related notes when they exist
