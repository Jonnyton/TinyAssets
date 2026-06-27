# Quarantined: default-universe canon cross-universe contamination

**Date:** 2026-04-13
**Found during:** #6 / #47 investigation (stuck-worldbuild diagnosis, canon quarantine).
**Origin:** `output/default-universe/canon/`

## What this is

Sixteen canon markdown files that were found in the `default-universe` canon
directory but whose content belongs to the **Ashwater** universe (aka the
"Upper Reach" / "Durnhollow" setting with characters Corin, Ryn, Daeren,
Wren, Lyra, Ashka, Davan Thel). They leaked into the wrong universe's canon
directory some time before 2026-04-09.

Markers that identified these as Ashwater content:
- 92 occurrences of `Ashwater`, `Durnhollow`, `Greywater`, `Vael Reach`, or
  `Ashmark` across the 15 grep-hit files (character_wren.md had no explicit
  markers but its content — Thessmark cover, Upper Reach exhaustion,
  ritual scar-lattice — is the same Ashwater setting).
- The only legitimate default-universe file remaining in
  `output/default-universe/canon/` is `location-the-gyre.md`, which is
  consistent raft-city/drowned-age worldbuilding.

## Why quarantined here

- File move only — no code changes.
- Preserved verbatim for forensic reference on how content crossed universes.
- Keep out of default-universe so future daemon runs don't keep training
  on wrong-universe context.

## What this did NOT fix

The quarantine addresses **artifacts**, not **root cause**. See
`STATUS.md` Concerns [2026-04-13 dev-3 / #15 / #47]:

- File-write paths are clean. Every `canon_dir` construction in
  `domains/fantasy_author/phases/{commit,worldbuild,select_task,orient}.py`
  and `tinyassets/universe_server.py` uses `Path(universe_path) / "canon"`
  with `universe_path` threaded from the daemon's `_universe_path` state
  field — no bare `Path("canon")`, no cwd-based writes.
- The leak therefore happened at the **content-generation layer**, not the
  file-write layer. The writer model was fed cross-universe context
  (retrieval, memory, or prior uploaded canon) and produced Ashwater prose
  while the write target was correctly `default-universe/canon/`.
- Task #15 tracks the chat-side / retrieval-isolation half of the fix.

## Files moved

```
artifact-the-cylinder.md
artifacts.md
ashwater_drainage.md
character-corin-ashmark.md
character-daeren.md
character-lyra.md
character-ryn.md
character_ashka.md
character_ashka_physical.md
character_davan_thel.md
character_wren.md
characters-durnhollow-villagers.md
compact_upper_reach_assessment.md
environment_upper_reach.md
location-durnhollow.md
location-greywater.md
```

## Files deliberately kept in default-universe/canon/

```
INDEX.md              — legacy index; likely stale after quarantine
location-the-gyre.md  — legitimate default-universe content (raft-city setting)
universe.json         — infrastructure
```

`INDEX.md` should be regenerated the next time the daemon runs worldbuild
on this universe, but that's not urgent.
