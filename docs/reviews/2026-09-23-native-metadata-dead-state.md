# Native metadata process-tree cleanup: `/proc` state `X` adjudication

Date: 2026-09-23 UTC. Reviewer/builder: Claude Opus, worktree
`wf-cloud-authority-remaining`, PR #3921 draft, head `79be0d7d`.
Scope: hosted required run 35810702840 / job 107021638166, one new failure,
`tests/test_native_metadata_process_tree.py::test_launcher_and_inherited_pipe_child_are_cleaned_without_losing_result[launcher_exited]`.

## Verdict: AGREE

Accepting the exact state token `X` as terminated preserves the
no-live-child / no-pipe-leak / no-lock-leak contract. The failure is a
defect in the test's terminal-state predicate, not in the cleanup path.

## Evidence

1. **The failure is in the test oracle, not the code under test.** Both
   `tests/test_native_metadata_process_tree.py` and
   `tinyassets/providers/native_jsonrpc_discovery.py` are byte-identical to
   base `16e6f0bf` on this head (`git diff --stat 16e6f0bf..HEAD --` on both
   paths is empty). Nothing in this PR's cloud-runtime guards touches the
   metadata transport. The failing assertion rejects the observed dead state.
   This proves a classification defect, not that all other timing/load inputs
   were identical between the green base run and the failing run.

2. **`X` is a documented dead state, not a live child.**
   [proc_pid_stat(5)](https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html)
   (read 2026-09-23) documents
   field 3 `state` as including `Z  Zombie` and `X  Dead (from Linux 2.6.0
   onward)`, plus `x  Dead (Linux 2.6.33 to 3.13 only)`. CI read uppercase
   `X`. Accepting that exact token corrects the no-live-child predicate. The
   resource-release assertions remain separate; this citation is not a kernel
   teardown-order audit or proof of every cleanup property.

3. **The test does not rely on the state token alone for the two properties
   that matter.** The integration test asserts
   `processes[0].returncode is not None` (the launcher really exited), and
   takes `fcntl.flock(..., LOCK_EX | LOCK_NB)` on the file the
   grandchild held exclusively — a non-blocking acquire that fails loudly if
   any process still holds it. Launcher exit alone is not proof of inherited
   pipe EOF. The existing process-group, cancellation and pipe-cleanup tests
   remain unchanged and must execute on hosted Linux.

4. **`_close_metadata_process` is the behaviour being protected and it is
   unchanged by this repair.** `native_jsonrpc_discovery.py:34-40`
   `killpg`s the session created by `start_new_session`, targeting the
   original group id rather than re-resolving a possibly recycled PID, so the
   inherited-pipe grandchild dies even when the launcher was already reaped
   (`launcher_exited` is exactly that mode); lines 41-53 bound the reap wait
   and close the transport in `finally`. The observed dead process is a valid
   terminal observation; it should not be mistaken for a still-live child.

## What the correction must not do

- Not a skip, not a quarantine, not a retry, no runtime or gate edit.
- Not blanket exception acceptance: only `FileNotFoundError` /
  `ProcessLookupError` (the process vanished entirely, i.e. reaped) stay
  accepted. `PermissionError` and any other I/O error keep propagating.
- Exact token recognition, not a prefix match. The prior
  `startswith("Z")` would accept any token merely beginning with `Z`;
  the fix compares the parsed state field for equality against the
  accepted set, so live states (`R`, `S`, `D`, `T`, `t`) and unknown
  tokens still fail.

## Residuals / deliberate omissions

- **Lowercase `x` is rejected on purpose.** proc_pid_stat(5) scopes it to
  Linux 2.6.33-3.13 only; CI reads uppercase `X`. Encoding an accept for a
  kernel range we do not run would add a state we cannot exercise, and
  asserting its rejection would be a dated fuse. It is left as an unknown
  token: if a run ever reads `x`, it fails loudly with the token visible.
- The `") "` split in the helper is left as-is (a `comm` containing `") "`
  would mis-parse). Out of scope here, and the `comm` in this fixture is
  always the test interpreter.
- **Hosted Linux stays required.** The mocked state-helper tests prove only
  the predicate. The two real-process tests need a POSIX session, `killpg`,
  `fcntl.flock` and `/proc` — none of which Windows supplies — so they skip
  locally and the hosted Linux job remains the only place the actual
  no-leak contract is executed. A local green run is not evidence that the
  contract holds.

## Verification and independent lead corrections

Opus17981 completed250s/terminal0. It demonstrated the old predicate rejecting
the CI-observed X and accepting malformed Zz, then obtained14passed/7skipped
on Windows. No production/runtime/gate/quarantine changes.

Codex independently reproduced the X rejection on clean basee389505b via a
Mock passed to `_assert_reaped_or_zombie` (AssertionError, exit1). Candidate
`python -m pytest -q tests/test_native_metadata_process_tree.py -p no:randomly
-p tests.skip_census_plugin --skip-census-out <lead-output>/pr3921-dead-state-census.json
--basetemp C:/Users/Jonathan/AppData/Local/Temp/ta-pr3921-dead-state-review-20260923
--tb=short -rs` =>14passed/7skipped,0.30s, terminal0. The seven POSIX cases remain
unverified locally, not passing. Independent source review confirms their bodies,
the cleanup runtime and the quarantine ledger are unchanged.

The lead narrowed unsupported claims in the original adjudication: unchanged
source does not prove identical scheduling inputs, and launcher returncode plus
a lock probe must not be relabeled as direct pipe-EOF evidence. These wording
corrections do not change the test repair or waive hosted Linux verification.
