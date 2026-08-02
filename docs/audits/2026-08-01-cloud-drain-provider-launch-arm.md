# Cloud drain provider launch-arm evidence

Date: 2026-08-01 America/Los_Angeles
Environment: Windows 11, Python 3.14
Branch: `codex/cloud-drain-launch-effect-20260801`

## Scope

The requester-owned provider ledger now performs the durable pre-launch arm
required before any credential, quota, or provider access. A server/runtime
carrier presents the exact reserved invocation snapshot; one transactional
transition revalidates its active receipt, unexpired claim lease, and current
requester-owned provider binding, then changes only that reservation to
`launch_started`.

Concurrent or restarted equivalent arms converge on one applied transition and
replay the same armed record. Revoked bindings, stale claims, changed digests,
or foreign reservation identities fail closed while the reservation remains
`reserved`. The record is still non-bearer and no provider, credential, GitHub,
queue-consumer, or tray-cutover behavior is enabled by this increment.

## Verification

- RED: `py -m pytest -q tests/test_provider_work_authority.py -k "launch_arm"`
  failed collection because `ProviderInvocationLaunchRequest` did not exist.
- GREEN: the two launch-arm tests passed, including eight concurrent arms and
  binding revocation before arm.
- `py -m pytest -q tests/test_provider_work_authority.py` — 42 passed.
- Related continuation, epoch-2, outbound-boundary, and GitHub reconciliation
  suite — 223 passed.
- Ruff lint/format, both strict OpenSpec changes, 306-file mirror parity,
  cross-provider drift, and `git diff --check` — clean.

## Remaining boundary

The next increment must carry this exact armed tuple into the existing provider
router, dereference only its bound requester-owned credential under assignment
admission, and settle the reservation from typed provider evidence. Exact
outbound pull-request reconciliation and epoch-2 activation remain dark.

## CI recurrence discovered after review

The PR's Windows lifecycle job reproduced the earlier non-terminal cleanup
after the exact installer flow had also passed in 43 seconds on a fresh rerun.
The outer supervisor used `subprocess.run(..., timeout=...)` for `taskkill`;
Python's timeout path kills and then waits for that cleanup process without a
second deadline, so a wedged Windows cleanup command could outlive the declared
supervisor and job bounds. A RED behavioral regression test now forbids that
path. Cleanup uses `Popen.wait(timeout)` and, on expiry, kills without another
unbounded wait before continuing the already-bounded root cleanup.
