# Brain subsystems deep-dive — 2026-05-03 snapshot

**Status: historical snapshot. Paths and line numbers in these files are falsified — do
not navigate by them.** The narrative (subsystem decomposition, design patterns, what was
wired vs experimental) is still useful orientation; the specifics are not.

## Provenance

Produced 2026-05-03/04 by a `cowork-busyclever` deep-dive run (four parallel agents plus a
synthesis pass) under the host directive to map "all spaghetti code, appendages and
upgrades and pieces and plumbing to the already existing brains." Recorded at
`.agents/activity.log:2468`.

These files were written to `outputs/drafts/brain-deep-dive/` — a drafts directory, never
a tracked location. They reached the repository **root** on 2026-07-22 UTC (2026-07-21 PDT) via `d4d279a0`
("chore(docs): recover 32 documents that existed only in one stale checkout", PR #1490),
which recovered files verbatim from a stale checkout whose layout no longer matched
`main`. This directory is where they should have landed.

The master synthesis of that same run — `CONSOLIDATION_MAP.md`, described in the activity
log as "the document to read if you only read one" — was **not** recovered and is not
here. If it is ever found, it belongs in this folder.

## Measured decay (verified 2026-07-21 against `origin/main`)

| Claim in these docs | Reality now |
|---|---|
| Code lives under `workflow/…` | Path does not exist; renamed to `tinyassets/…` |
| `workflow/api/wiki.py` is 1641 lines | `tinyassets/api/wiki.py` is 2583 lines (+57%) |
| Wiki `read` action at lines 319–347 | Line 319 is `_coerce_read_max_chars` |
| "42 modules, 12,306 lines, 100% production-wired" | Unverified at this date; predates the 2026-07 relay reshape |

Per `AGENTS.md` § Truth And Freshness — "audit docs decay too" — treat every specific in
these files as `historical:2026-05-03` and re-derive from code before acting on it.

## Contents

| File | Lines | What it is |
|---|---|---|
| `BRAIN_DEEP_DIVE_README.txt` | 262 | Index for the four-part `BRAIN_*` set |
| `BRAIN_CONSOLIDATION_SUMMARY.txt` | 315 | Executive summary — start here for the narrative |
| `BRAIN_SUBSYSTEMS_MAP.txt` | 600 | Per-module breakdown across the six subsystems |
| `BRAIN_MODULES_INDEX.txt` | 248 | Module inventory table + design patterns |
| `BRAIN_CODE_LOCATIONS.txt` | 246 | Line-number index — **wholly falsified**, see table above |
| `brain_surface_audit.txt` | 575 | Wiki + MCP action-surface audit (separate agent, same run) |
| `brain_surface_quick_reference.txt` | 166 | Action matrix companion to the surface audit |
