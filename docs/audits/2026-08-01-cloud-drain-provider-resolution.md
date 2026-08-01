# Cloud-drain provider resolution slice

Date: 2026-08-01 America/Los_Angeles
Environment: Windows worktree `wf-cloud-drain-provider-resolution-20260801`

## Verdict

This slice closes two authority gaps without enabling a provider launch. A
production binding service can persist only a seed returned by a runtime-checked
server-owned assignment resolver. A prepared cloud continuation can resolve one
currently claimed background attempt into one bounded `universe_work` provider
receipt only while the continuation, cloud activation, background binding,
attempt lease, immutable Branch version, and requester-owned provider binding
all remain current.

The receipt is non-bearer. It cannot resolve credentials, enter the provider
router, launch a subprocess, or authorize a GitHub effect. The local watchdog
therefore remains the live bridge and the cloud consumer remains disabled.

## Closed behavior

- Caller-supplied binding seeds are not a production write path. The issuance
  service accepts a nominal owner/universe/provider root, asks its injected
  canonical resolver for the seed, rejects missing or cross-root resolution,
  and calls only the store's private insertion seam.
- Concurrent/restarted equivalent binding issuance replays the same
  content-addressed record; a changed assignment conflicts rather than widening
  authority.
- Provider receipt resolution requires the exact persisted continuation, the
  next active activation epoch on executor class `cloud`, the same immutable
  Branch version, the exact active background binding snapshot, and a claimed
  or running cloud attempt with an unexpired lease.
- The attempt principal, universe, Branch definition/version/content digest,
  provider binding generation/digest, allowed operation/role, and all budgets
  must match the immutable work definition. Receipt expiry is the earlier of
  the attempt lease and provider binding expiry.
- Receipt persistence revalidates the provider binding under the provider
  ledger transaction. Activation/background changes after resolution cannot
  launch work from this receipt; the later carrier must revalidate them again
  immediately before `launch_started`.

## Fresh verification

Verified 2026-08-01 in the worktree above:

- RED: the two focused modules failed collection because the production binding
  root and prepared-continuation resolver did not exist.
- `python -m pytest tests/test_provider_work_authority.py tests/test_cloud_automation_continuation.py -q` — 63 passed.
- Ruff lint on the five changed Python files — clean.
- Ruff formatting on the five changed Python files — clean.
- `git diff --check` — clean.

## Remaining gates

- The canonical provider-assignment/credential-custody owner must implement the
  resolver adapter; this slice does not accept raw secret material or invent an
  assignment.
- A server-owned activation service must atomically activate the prepared
  continuation, enqueue the activation-bound epoch-2 task, and issue/claim the
  corresponding background attempt without allowing epoch-1 admission.
- Provider carrier `launch_started`, credential dereference, settlement,
  reconciliation, outbound PR effect, phone controls, deployment, and the
  24-hour computer-off proof remain required before cloud cutover.
