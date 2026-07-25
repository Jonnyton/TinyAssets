# Lane report — universe-visibility

Branch: `claude/osx-universe-visibility` (off `origin/main`). No PR opened
(cross-family review precedes any PR, per lane instruction).

## Salvage check
`feat/universe-visibility` is **128 behind / 0 ahead** of `origin/main` (merge-base
`e2a30f21`). Nothing committed to salvage; did not touch that branch or its
worktree.

## Scope guard (open PRs)
- **#1554** `fix/private-goal-read-visibility` (DRAFT, DO NOT MERGE): a *different*
  capability — private **Goal** read visibility (`shared-goals-and-convergence`,
  `market.py`, goals surface). No file overlap with universe existence/metadata/
  content. Interaction is conceptual only ("read visibility"); noted, not duplicated.
- #1550 (wiki discovery split), #1583 (write_page commons residual), #1549/#1592
  (credential fail-closed) — no overlap with visibility files.

## What this change does
The current model had one `public_read` bit that **defaults undeclared → visible**,
which the delta spec (Requirement 1) explicitly reverses to fail-closed, and which
cannot express existence/metadata/content separately or per-page. Added an
**additive** layer (`tinyassets/api/visibility.py`) that only ever *tightens* the
existing gate:
- `VisibilityLevel` triple + presets: `public` / `metadata_only` / `unlisted` /
  `private` (fail-closed = `private`).
- `universe_visibility()` resolves explicit level → legacy `public_read` compat →
  fail-closed on undeclared(strict)/unrecognized/corrupt/blank.
- Grant exemption: an ACL-granted reader is never bound by anon visibility.
- `page_content_permitted()` narrows content per-page (a page can't widen).
- `backfill_universe_visibility()` declares each existing universe from its current
  `public_read` bit (no visibility flip) so strict mode only ever bites broken state.
- `set_universe_visibility()` writer.

Wired three surfaces (`universe.py` enumeration, `status.py` get_status metadata,
`wiki.py` read + per-page); the declared level is reported in `list`/`inspect`
(spec Req 4).

## Tasks
Completed (checked in tasks.md): 1.1, 1.2, 1.3 (mechanism; value is a host knob),
1.4 (dispositions + backfill; per-page data edit is a deploy step), 2.1, 2.2, 2.3,
2.4, 3.1.

Skipped-blocked:
- **3.2 live first-contact ui-test** — requires a deployed build + browser connector
  through `https://tinyassets.io/mcp`. Verifier/host acceptance step after review +
  deploy; not runnable in a builder lane. Left unchecked.

Host-decision knobs (recorded in design.md, not silently flipped):
- 1.3 `create` default level (conservative `private` vs public-commons `public`).
- Full-strict rollout: `TINYASSETS_VISIBILITY_STRICT_UNDECLARED=on` after backfill.

## Test + ruff evidence (2026-07-24, local, Windows, py3.11)
- `pytest tests/test_universe_visibility.py` → **36 passed**.
- `pytest tests/test_universe_server_isolation.py tests/test_universe_list_observability.py tests/test_multi_tenant_isolation.py` → **70 passed** (no regression).
- `ruff check` on all 5 touched files → **All checks passed**.
- Plugin mirror rebuilt (`build_plugin.py` → 264 files, import probe-ok);
  `visibility.py` now staged in the runtime mirror. Diff scope verified: only the
  4 api files (+ mirrors), design.md, tasks.md, test file — no kitchen-sink diff.
- No existing assertion was weakened/xfailed/skipped.

## Commits pushed
- `a4f44195` feat(visibility): model — 3 separate anon-reader capabilities, fail-closed
- (enforcement) feat(visibility): enforce existence/metadata/content gates + per-page + tests

## Cross-family review gate (pending, before any PR)
This is a security-relevant read-path change; it warrants an adversarial Codex
review before a PR. Deliberately NOT dispatched inline from this lane: the lane
contract routes review as a separate pre-PR gate, and the Windows `codex_review.py`
path has documented misfire modes. Claims a reviewer should try to refute:
(1) the additive layer never *loosens* the existing gate; (2) fail-closed truly
covers undeclared/unrecognized/corrupt/blank; (3) grant exemption can't be spoofed
by the "public universes return read" convention; (4) per-page narrowing can't widen.
