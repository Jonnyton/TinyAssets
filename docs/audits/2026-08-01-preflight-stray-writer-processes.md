# Preflight Stray-Writer Process Reconciliation — 2026-08-01

## Outcome

Immutable build run `30676789461` published current-main revision
`a6301200b668976ccf8960104cb0c50da0f9fdd9` as digest
`sha256:2b3f2755a8f8a50f54477ff2b4915a641c5aa49d990c96b92043fda091feba10`.
Its automatic normal deployment, run `30676899240`, failed closed in preflight
before any production host write. Rollback was not attempted because cutover
never started; the prior receipt remained unchanged.

## Bounded Production Evidence

Downloaded artifact
`retire-cheat-loop-task-2-1-30676899240-1` contained:

- `preflight.json`: `safe=false`,
  `error=pre-mutation stray writer process risk is nonzero`,
  `stale_state_ignored=true`.
- `fence-status.json`: prior run `30674978746-1`, phase `restored`, no masks,
  no current-run match, and `current_run_cutover_started=false`.
- `receipt_snapshot_before.json`: `null`, consistent with refusal before the
  snapshot-bearing mutation path.

Issue `#2034` records the same safe tuple:
`false/not_attempted/not_run/pre_host_write_failure`, emergency cleanup
mutation false, and no production host write.

The bounded journal diagnosis run `30677022506` covered
`2026-08-01T00:55:00Z` through `2026-08-01T01:03:00Z` and returned
`derived_state=no_container_stage`, no failure classes, no stages, and
`input_truncated=false`. That corroborates that deployment never reached a
Compose startup stage; it does not identify the process candidate.

## Root Cause In Current Code

`preflight()` captures Docker-owned PIDs, then calls
`_stray_writer_processes()` and immediately refuses when the preliminary list
is non-empty. A container may spawn a process between those two observations,
so a genuine exact-container PID can be absent from the first snapshot and
appear as an apparent stray.

`observe_fleet()` already closes this exact race: after the preliminary scan it
calls `_confirm_stray_writer_processes()` with the captured exact container
IDs. The helper takes a fresh Docker PID snapshot, discards exited or newly
proved exact-container-owned candidates, and retains live unowned candidates.
Normal preflight omitted that confirmation.

## Required Repair

Use captured nonempty exact IDs in both the initial exclusion and confirmation
snapshots. Trust only successful complete per-identity Docker PID output, bind
each candidate to its `/proc` process-generation token to reject numeric PID
reuse, and refuse candidate 101 instead of truncating the risk inventory. Do
not loosen writer markers, receipt/environment/mount checks, or fixed private
refusal classes. Same-name replacement, failed/partial Docker lookup, changed
generation, overflow, and every live host writer remain fail-closed before
mutation. Exact 100/101 boundary tests supply the uptime §14 concurrency/load
proof.

## Release Gate

No retry of digest `sha256:2b3f2755…feba10`. The repair must land on current
main, produce a new immutable digest, pass one complete normal-fence deploy,
and preserve exact fleet, canary, cleanup, and terminal receipt evidence before
rendered OAuth/custom-agent acceptance resumes.

## Test-Driven Repair Evidence

On Windows/Python 3.13 at exact pre-implementation head `a4613146`, the focused
matrix produced 8 expected failures and 1 control pass. Failures covered raw
preflight rejection, mutable-name initial ownership, numeric PID reuse,
malformed/partial Docker output, failed Docker lookup, and candidate-101
truncation. The exact 100-candidate test was also applied to detached head
`a4613146` and failed with `AttributeError` because the fixed candidate-bound
contract did not yet exist.

Independent review of implementation head `7aa97b22` returned ADAPT: empty
expected/extra IDs were filtered out of both ownership snapshots and only
refused after durable state and restart-policy mutation. Tests-only head
`36906a1f` then reproduced both paths as 2 expected failures while unreadable
and malformed process-generation controls passed 2/2. The repair now rejects
any inspected expected, extra, or admitted-sidecar identity that is not a
nonempty string, using one fixed private refusal before either PID snapshot,
durable state, or host mutation.

After adaptation, the focused identity/generation matrix passed 4/4, including
public generation-stripped risk for missing and malformed `/proc/<pid>/stat`.
The complete fence file passed 211/211. The complete recovery/deploy matrix
passed 450/450 in 15.65 seconds. Changed-file Ruff was clean.
