# Lane report — universe-visibility

Branch: `claude/osx-universe-visibility` (off `origin/main`). No PR opened
(cross-family review precedes any PR, per lane instruction).

## Salvage check
`feat/universe-visibility` is **128 behind / 0 ahead** of `origin/main` (merge-base
`e2a30f21`). Nothing committed to salvage; did not touch that branch or its worktree.

## Scope guard (open PRs)
- **#1554** `fix/private-goal-read-visibility` (DRAFT, DO NOT MERGE): a *different*
  capability — private **Goal** read visibility (`shared-goals-and-convergence`,
  `market.py`). No file overlap with universe existence/metadata/content; noted, not
  duplicated. #1550/#1583/#1549/#1592 — no overlap.

## What this change does (after the round-2 REJECT hardening)
The current model had one `public_read` bit that defaults undeclared → visible and
cannot express existence/metadata/content separately or per-page. `tinyassets/api/
visibility.py` decomposes the anonymous surface into `discover_existence` /
`read_metadata` / `read_content`, with two **structural** invariants:
- **Tighten-only by construction:** `visibility_permits = legacy_gate AND new_layer`.
  The new layer can never grant a read the legacy gate denies (an inconsistent row
  `public_read=False` + permissive explicit level is refused).
- **Fail closed by default:** `universe_visibility` returns the declared level or
  `CLOSED`; it never derives an open default from `public_read`. Undeclared / blank /
  null / unrecognized / wrong-type / malformed-JSON / non-object-metadata / corrupt →
  `private`. `backfill_universe_visibility()` is the deploy migration.

## Cross-family REJECT — every finding addressed
Verdict: `…/scratchpad/verdict-universe-visibility.md`. Fixes (structural, not per-probe):
1. **Additive claim false** → composition is now `legacy AND new` (tighten-only by
   construction). `TestTightenOnlyComposition` proves all three gates refuse the
   inconsistent forged row.
2. **Fail-open defaults / env opt-in** → removed the env flag; `universe_visibility`
   is unconditionally fail-closed on undeclared. Blank `""`, `null`, wrong-type,
   malformed/non-object metadata_json all → `CLOSED`. `TestResolutionFailClosed`
   encodes the reviewer's truth table row-by-row.
3. **Page exemption = auth not ACL** → `page_content_permitted(meta, universe_id)` now
   grant-based; authentication alone no longer bypasses. Fixed the test that codified
   the unsafe behavior.
4. **search/since leak private page content; list leaks path/title** → all three
   sibling read paths now filter restricted pages (`TestSiblingReadLeaks`).
5. **inspect leaks unlisted metadata** → `_action_inspect_universe` gates on
   `read_metadata` (existing universes).
6. **list note leaks hidden count + base path** → neutral "No universes are visible to
   you." note; no count/path.
7. **get_status("") leaks resolved private name** → blank-scope denials no longer echo
   the resolved id.

## Tasks
Completed: 1.1–1.4, 2.1–2.4, 3.1. Skipped-blocked: **3.2 live first-contact ui-test**
(needs deployed build + browser connector; verifier/host acceptance). Host-decision knob
recorded in design 1.3: the `create` default *value* (public vs private).

## Test + ruff evidence (2026-07-24, local Windows py3.11)
- `pytest tests/test_universe_visibility.py` → **52 passed**.
- Mutation spot-checks (throwaway plugin): forcing `visibility_permits`/
  `universe_visibility` open → **30 gate tests RED**; forcing `page_content_permitted`
  open → **6 page/sibling tests RED** (non-vacuous).
- Migrated legacy suites green: isolation/observability/multi-tenant/telemetry/word_count/
  ledger/mcp-structured-results/api_wiki/get_status_primitive → **270 passed** together.
- **Zero net new failures** (reviewer-reproduced): a deterministic `*universe*`/`*wiki*`/
  `*status*` file sweep produced `936 passed / 6 failed` at the branch base and
  `988 passed / 6 failed` at the branch head — the same six unrelated
  framing/metadata/treasury tests fail on both, i.e. zero net new failures and exactly
  52 added passes. (An earlier report cited a "32 → 29" origin/main delta that the
  reviewer could not reproduce; it is replaced by this reproducible base-vs-head sweep.)
- `ruff check` on all touched files → **All checks passed**.
- Plugin mirror rebuilt (`build_plugin.py` → 264 files, probe-ok). Diff scope: 4 api files
  (+ mirrors), `tests/conftest.py`, 6 test files, `design.md`, `tasks.md`, this report.
- No existing behavioral assertion was weakened/xfailed/skipped.

## Test-harness note (why conftest changed)
Fail-closed-by-default means an undeclared universe is refused at get_status/inspect/list.
Hundreds of pre-visibility tests create bare universes and were written for the
post-backfill world. `tests/conftest.py` gained an autouse fixture that **emulates the
deployed backfill** (undeclared → `public_read`-derived) for those legacy modules only —
`test_universe_visibility.py` is excluded and exercises the true strict resolver
un-emulated. Production code ships fully strict; this is the harness equivalent of the
one-time deploy migration the reviewer named as "the migration path."

## Round 3 — production-hardening (Codex ADAPT; security held)
Merged current `origin/main` into the branch first (clean, no conflicts) so the wiring
lands on the post-#1728 creation code. Two ADAPT items, both built as **runtime gates**,
not prose:

1. **Enforceable startup gate (`run_visibility_startup_gate`).** Runs at server boot — in
   the HTTP app's Starlette `lifespan` (fires under uvicorn/gunicorn regardless of
   launcher) and at the top of `main()` (covers sse/stdio). It runs the idempotent,
   deterministic `backfill_universe_visibility()` (derives each level from `public_read` —
   safe derivation, not policy) and then **refuses readiness** (`VisibilityStartupGateError`)
   if any universe stays undeclared, with the exact remediation command — so a strict-code
   deploy can never silently serve legacy universes as `CLOSED`. Prose deploy instructions
   were the config-text guard the reviewer flagged; this replaces them.
2. **Creation-time declaration.** `_action_create_universe` now writes an explicit
   `visibility` level at birth (both explicit `create_universe` and the converse/
   first-contact auto-birth route through it), on the create's critical path (a failure
   rolls back the partial create atomically). Default is the host-knob
   `DEFAULT_CREATE_VISIBILITY = "public"` (preserves the platform's public-draft-by-default
   stance, Hard Rule #12, and today's `public_read=1` default; the delta spec mandates only
   that an *explicit* level be written, not a value). A creator may pass `visibility=private`
   etc.; an invalid value fails the create loudly before any dir is made. **Value flagged
   for host arbitration** — the reviewer guessed `private`; I chose `public` with the
   evidence above rather than unilaterally invert the live commons default.

Also: fixed the page-restriction denial prose ("unauthenticated reader" → "a reader without
a grant on this universe") per the reviewer's nit.

New tests (in the strict, un-emulated `test_universe_visibility.py`): `TestStartupGate`
(declares undeclared universes; derives private from `public_read`; idempotent; **refuses
readiness on an undeclared remainder**) and `TestCreationDeclaration` (declares default;
honors explicit; rejects invalid without a partial dir). Suite now **59 passed**.

## Deploy note
The startup gate makes rollout ordering self-enforcing: the server backfills at boot and
refuses to serve if any universe stays undeclared. Per-page restriction of
`default-universe`'s engineering pages remains a runtime data step; the enforcement
mechanism is built + tested.

## Commits
Round 1 (model + first-cut enforcement): `a4f44195`, `93a02919`, `aecee0b8`.
Round 2 (tighten-only + fail-closed + leak fixes): `de64e5ab`, `8ab337bf`, `9f9ab716`.
Round 3 (merge origin/main + startup gate + creation declaration): to be committed + pushed
to the same branch. Do NOT open a PR — coordinator re-dispatches the Codex review.
