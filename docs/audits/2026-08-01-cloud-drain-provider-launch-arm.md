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
second deadline. A RED behavioral regression test now forbids that path, and
cleanup uses `Popen.wait(timeout)` without another wait after kill. However,
fresh PR CI at exact head `195ab197c83ef34f282523a4ea65b46d0a07526c`
still exceeded the 300-second supervisor bound. That contradicts the initial
claim that the `subprocess.run` path was the complete root cause.

A subsequent RED Windows regression run proved the remaining capture fault:
`--max-capture-bytes-per-stream 4096` bounded only replay, while the live child
wrote directly into the temporary capture file. The synthetic noisy child
produced at least 200,037,743 captured bytes in two seconds. A five-minute CI
timeout could therefore create tens of gigabytes of temporary output before
cleanup began.

The supervisor now drains stdout and stderr concurrently through pipes,
retains at most the configured bytes per stream, discards overflow without
back-pressuring the child, and preserves the total observed byte count for the
truncation warning. Live checkpoints bracket child wait, timeout cleanup,
taskkill, root wait, capture replay, and supervisor exit. On 2026-08-01 Windows
11 / Python 3.14, the bounded-writer RED test and real noisy-child lifecycle
test passed, and the complete desktop release workflow test file passed 15/15
in 2.62 seconds. Exact-head PR CI run `30731211289` then passed on GitHub's
`windows-latest` environment: the exact unsigned installer lifecycle completed
install, health probe, repair, and uninstall in 51 seconds. Independent Codex
review at `429233537d56848c95e0da8e5f89f941ee1a6e3e` returned APPROVE after
Claude's limit-hit attempt returned no verdict. The launch arm remains dark;
the next boundary is carrier/effect integration.
