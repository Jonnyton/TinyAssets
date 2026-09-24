# Resume exact-admission slice — review and test evidence

Branch `codex/resume-exact-definition` (isolated worktree, base `3f62ed53`).
Scope: the bounded prerequisite documented in
`openspec/changes/consolidate-platform-resource-policy/design-amendment-resume-exact-definition.md`.
**Committed on this branch only — nothing pushed, no PR, nothing deployed from
this lane.**

## Verdict: pre-merge Linux oracle green; root owns push and exact-head review

| Evidence | Result |
|---|---|
| Independent cross-family review (Claude66315, source read only) | **APPROVE**, 4 non-blocking notes — full report `output/resume-envelope-final-review-peer.md` (worktree `0a7f`) |
| Cloud pre-push Linux oracle, run `35960544895`, 2026-09-24 05:35:25 UTC, base `3f62ed53c1b3fc3d53cdb875269245888ba23906` + patch `83c44c1fd63cb1afc9fccd3ee83812c65f89da185326c6fefa36765c5bc31db4` (121126 bytes) | **SUCCESS — 122 passed, 0 failed, 0 errored, 0 skipped** across the nine targeted files |
| Earlier oracle run `35959680983` (patch `0ef21f0b…50eca459f3b1a27212c0cc1f`, 118729 bytes) | **FAILURE — 119 passed, 3 failed.** Superseded; cause and fix below |

### The three earlier failures were a test-fixture defect, not runtime behaviour

All three were in `tests/test_resume_admission_identity.py`, one shared cause:
the `admitted_run` fixture stubbed `_invoke_prepared_branch` but not the
*dispatch*. `execute_branch_async` submits the worker to a real thread pool and
returns `queued` within milliseconds (`tinyassets/runs.py:5375-5395`), so the
pool thread resolved `_invoke_prepared_branch` as a module global after the
`with` block had already exited. The fixture branch declares no entry point, so
the real body wrote `failed` — clobbering the status the fixture then set — and
the identity guard under test was never reached:

- `test_resume_never_runs_an_edited_definition` — `ResumeError: Run '8611cf8287ea4c2f' is 'failed', not 'interrupted'`
- `test_resume_hands_the_worker_the_admitted_execution_choices` — `ResumeError: Run '91a107dc8109429e' is 'failed', not 'interrupted'`
- `test_corrupt_envelope_refuses_and_never_falls_back` — `assert 'not_interrupted' in {'admission_not_reconstructable'}` (same cause, surfaced through the refusal-reason assertion)

**Fix: `tests/test_resume_admission_identity.py` only — no runtime change.**
Dispatch is forced onto the calling thread with the `_InlineExecutor` already in
the file (`patch("tinyassets.runs._get_executor", return_value=_InlineExecutor())`,
the pattern `tests/test_resume_execution_choices.py:180` already uses), so the
stub provably owns the dispatch and no worker outlives the patch. Two
initial-state diagnostics were added to the fixture: the admitted run must read
`queued` before it is interrupted, and `get_future(run_id)` must be `None`-or-done
— the second is the discriminating one, since under real pool dispatch the status
still reads `queued` while the worker is live. A future regression of this shape
now reports as a fixture defect rather than as a resume-guard failure. No
assertion was weakened and the poisoned `branch_lookup` is unchanged.

### What these identity tests do and do not prove

**Correction to the prior finalizer's record, which claimed the fixture "never
sets `interrupted` by hand".** It does. `tests/test_resume_admission_identity.py`
is a seam test by construction:

- the fixture admits a real run through `execute_branch_async` with a real
  admission envelope, then **manually** writes `interrupted`
  (`update_run_status(..., status=RUN_STATUS_INTERRUPTED)`);
- every resume case stubs `tinyassets.runs._has_checkpoint` to `True` and
  replaces `_invoke_graph_resume` with a recorder.

So this file proves the **dispatch-seam identity contract** — which definition,
recursion limit and concurrency budget resume hands the worker, and that the
mutable `branch_lookup` is never consulted. It does **not** exercise a real
checkpoint or a real compile/invoke, and **none of this is an actual full live
resume.** The real interrupt → checkpoint → compile → invoke path is covered by
`tests/test_resume_lifecycle_integration.py` and
`tests/test_resume_execution_choices.py`, which stub neither `resume_run`,
`_invoke_graph_resume`, nor `_has_checkpoint` (they assert the real
`runs._has_checkpoint` after a real interrupt). End-user proof through the live
connector is still unperformed — see the remaining tasks.

## Review notes folded in (source, not behaviour)

- Peer note 1 — **applied.** `_require_int`'s docstring asserted
  `BranchDefinition.validate()` "does not constrain `concurrency_budget` at
  all". False since #3940 (`validate_concurrency_budget`, `type(...) is int`,
  `> 0`, under `SQLITE_MAX_INT64`). The docstring now states that this is an
  *authoring-time* field validator, not an admission ceiling, and that the
  decoder stays deliberately wider — `0` verbatim, no upper bound. **Codec
  compatibility logic is unchanged**; only the comment moved.
- Peer note 4 — **specified.** The admitted `recursion_limit` is re-applied as
  the recursion **cap for the resumed segment**, not as a remaining-step budget
  carried from the interrupted segment. Strictly better than the prior path,
  which silently took LangGraph's stock default on resume. `_invoke_graph_resume`
  still emits no `recursion_limit_applied` event, so `get_run` does not surface
  the cap for a resumed segment — cosmetic, recorded, not fixed here.
- Peer note 3 — **specified.** If the settle path is itself unable to complete
  (storage, or the execution-authority guard, concurrently unavailable), the
  reserved row MAY remain `queued`. It is **never dispatched** in that state, so
  the failure stays closed.
- Peer note 2 — recorded, not acted on: a malformed branch budget now refuses at
  encode time, before any run row exists, where the old path reserved a run and
  failed visibly at compile. `api/runs.py:1127-1129` classifies it; unreachable
  once #3940's validator fronts it.

## Spec sync

`openspec/specs/graph-execution-substrate/spec.md` — the resume requirement only
(`+68 / -2`), renamed to `…owner, status, checkpoint, and admitted-definition
guards`. Previously synced text is preserved: the `recover_in_flight_runs`
sweep paragraph and all four pre-existing scenarios are kept alongside the five
new ones. The change directory's unrelated legacy delta (workspace storage
observation) was **not** copied.

## Post-merge re-verification (Windows host, supporting evidence only)

Slice committed as `1a4096ca`; `origin/main` `d98d1ae7` (#3940 + #3938) merged
non-destructively as merge commit `64216e78` — **no conflicts**, the main spec's
resume requirement (line 444) and #3940's execution-choice requirements (lines
976, 990) both survive intact. On that head:

- the same nine oracle-targeted files → **122 passed, 0 failed, 0 skipped** in
  15.85s (external basetemp, `-p no:randomly`) — the same 122 the cloud collected;
- `ruff check` on every file this slice touches → **All checks passed!** (the 28
  repo-wide `E501`s are in untouched files: `daemon_server.py`, `api/market.py`,
  `rollback.py`, `api/branches.py`);
- `packaging/claude-plugin/build_plugin.py` → 501 runtime files staged,
  `probe-ok`, **no mirror diff** (mirror already byte-parity; `mirror-parity`
  pre-commit hook also passed).

A Windows run is not an oracle. The Linux proof is cloud run `35960544895`, which
predates the merge; a post-merge oracle run has **not** been performed.
Root subsequently merged reviewed main6b8b7226 (PR3941) non-destructively,
without conflicts. The final integration needs its own Linux result; older
proof is not relabelled as a test of this combined head.

## Remaining tasks

- [x] T1 Diagnose the three Linux-only failures on the exact head — fixture dispatch race, no runtime guess.
- [x] T2 Re-run the cloud oracle on the corrected head — run `35960544895`, SUCCESS, 122 passed / 0 skipped.
- [x] T3 Commit the scoped runtime / mirror / tests / spec / design / evidence set with normal hooks.
- [x] T4 Merge latest `origin/main` (`d98d1ae7`, #3940 + #3938) non-destructively; additive spec resolution only.
- [x] T5 Re-run the targeted files post-merge with an external temp root; `ruff check`; `build_plugin.py` mirror parity.
- [ ] T6 Root owns push, PR, and final exact-head approval.
- [ ] T7 `python scripts/deployed_sha.py --assert-contains <sha>` before any shipped claim.
- [ ] T8 `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp` and a rendered `ui-test` conversation — the only end-user proof; no live resume has been exercised yet.
- [ ] T9 Decide whether `_invoke_graph_resume` should emit `recursion_limit_applied` (peer note 4, cosmetic).
- [ ] T10 `tests/test_def_run_admission_pin.py:107,263,313` has the same unbounded-dispatch shape and is green only because its assertions read the envelope rather than the status — latently flaky, left alone per scope.

Out of scope and unchanged: public resume advertisement, any automatic replay or
auto-resumer, any new grant or table. The umbrella change
`consolidate-platform-resource-policy` is **not** archived.
