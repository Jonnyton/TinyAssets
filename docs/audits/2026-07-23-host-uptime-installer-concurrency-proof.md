# Host uptime installer concurrency proof

**Status:** structural candidate proof; disposable-host and post-merge production
evidence remain pending
**Verified:** 2026-07-23 on the rebased implementation/spec tree through
`c2f0923e` on `codex/converge-host-uptime-installers` in
`C:\Users\Jonathan\Projects\wf-openspec-conformance-audit2`
**Environment:** Windows 11, Python 3.14.3; Ubuntu WSL2 kernel
6.6.87.2, systemd 255

## Result

The candidate implements the bounded convergence contract from
`2026-07-23-host-uptime-installer-convergence.md`:

- One installer owns the exact five service/timer pairs and their runtime
  closure.
- Bootstrap, post-deploy reconciliation, and restart-with-install all obtain
  the manifest from that installer and invoke it.
- Source preflight precedes destination mutation. Installation uses a
  content-addressed release, an atomic `current` pointer, atomic unit
  replacement, a validated atomic sudoers file, and rollback.
- Same-root callers wait under a bounded per-target lock; distinct roots do
  not share mutation state.
- Every successful call reloads systemd, enables and starts all five timers,
  and verifies their enabled and active states.
- Timer pausing and service-quiescence inspection fail closed. Active,
  activating, reloading, and deactivating services are never replaced;
  inspection errors and unknown states are red.
- Both watchdog units stay installed and scheduled on a newborn host but use
  `ExecCondition` to skip recovery until `TINYASSETS_IMAGE` is configured.

## Section 14 concurrency evidence

The following test command ran the real Bash installer through a fake,
stateful `systemctl` boundary:

```text
python -m pytest \
  tests/test_host_uptime_installers.py::test_bounded_distinct_target_burst_is_isolated \
  tests/test_host_uptime_installers.py::test_same_target_burst_waits_and_each_caller_verifies \
  tests/test_host_uptime_installers.py::test_same_target_lock_timeout_is_red_before_systemd -q
```

Result: **3 passed in 71.78s**.

The distinct-target scenario starts 64 concurrent installations with a unique
runtime marker per fake host. All 64 calls succeed; every root receives the
exact unit/runtime manifest and its own marker, proving no cross-root
contamination.

The same-target scenario starts 32 callers against one root. All 32 wait and
succeed. The mutation log contains exactly 32 unique, contiguous caller
blocks, proving that no installation mutation interleaves and every waiter
performs its own final convergence verification.

The bounded-timeout scenario holds the same-root lock, sets the wait budget to
zero, and proves the losing invocation returns red before any systemd
mutation. Normal callers use the bounded 300-second default.

## Installed runtime closure

The audit names 11 direct runtime files. The installer also carries the two
package markers required to invoke those files from the release rather than a
checkout, for 13 installed runtime files total:

```text
deploy/daemon-watchdog.sh
deploy/backup.sh
scripts/__init__.py
scripts/watchdog.py
scripts/mcp_public_canary.py
scripts/disk_watch.py
scripts/disk_autoprune.py
scripts/rotate_run_transcripts.py
scripts/backup_ship_gh.py
scripts/backup_prune.py
tinyassets/__init__.py
tinyassets/storage/__init__.py
tinyassets/storage/rotation.py
```

`tinyassets/__init__.py` retains the public convenience API through lazy
imports, so importing `tinyassets.storage.rotation` does not require the full
application graph. The packaged Claude-plugin runtime mirror carries the same
initialization behavior.

## Verification matrix

| Gate | Evidence |
|---|---|
| Installer suite | `python -m pytest tests/test_host_uptime_installers.py -q` → **23 passed in 130.29s** |
| Affected suites | Installer, bootstrap, disk-watch, prune, backup, deploy workflow, import graph, discovery, registry, and data-dir suites after rebasing onto `85c91087` → **221 passed, 5 skipped in 149.90s** |
| Runtime logic suites | Watchdog, public MCP canary, and GitHub backup shipping → **51 passed in 0.68s** |
| Python lint | Ruff on all changed Python files → **passed** |
| Shell syntax | `bash -n` on installer, bootstrap, and daemon watchdog → **passed** |
| Shell lint | ShellCheck on the same scripts, excluding sourced-file lookup `SC1091` → **passed** |
| Workflow lint | actionlint on install-host-services and restart-daemon → **passed** |
| OpenSpec | Archived delta synced into the canonical uptime spec; `openspec validate --all --strict` → **41 passed, 0 failed** |
| Whitespace | `git diff --check` → **passed** (Git emitted only an LF/CRLF worktree notice) |
| systemd | Disposable `--root` verification of all five service/timer pairs with dependency stubs → **`verified=10`** |

The full repository suite was attempted twice by the independent verifier. It
exceeded 15-minute and 30-minute bounds without reporting a failure, so this
artifact does **not** claim a full-suite pass.

## Evidence still required after landing

The candidate has not yet run from its exact landed commit on a disposable
Debian 12 host. That acceptance must prove absent-unit bootstrap, installed
hashes, five enabled/active timers, repair after manual disable/stop, safe
oneshot invocation with disposable fixtures, systemd results, and the public
MCP canary.

After merge, production evidence must show the real host-install workflow and
subsequent watchdog, disk-watch, backup, and prune executions using the landed
artifacts. Until both evidence sets exist, `STATUS.md` must retain a monitoring
item and no report should claim proven clean live use.
