# Host uptime installer concurrency proof

**Status:** accepted structural, disposable-host, and exact-merge production
proof
**Verified:** 2026-07-24 against production merge
`a18751dc3b8544d048a745304b1823dfdd9fbb11`, GitHub Actions Ubuntu runners,
the production Debian host, and a Windows 11/Python 3.14.3 isolated restore
validation environment

## Result

The landed implementation satisfies the bounded convergence contract from
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
- Production deploy preserves verified host-owned backup authority; an
  exact-source installer reuses it, and an explicit backup proof requires
  fresh primary archives, both GitHub assets, and no invocation-scoped
  warning/error.
- GitHub retention reconciles eventual-consistency views under one bounded
  wall-clock deadline and preserves unrecognized audit releases.

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
| Fresh-host backup configuration | `python -m pytest tests/test_fresh_host_backup_config.py -q` → **1 passed in 0.25s** |
| Installer suite | `python -m pytest tests/test_host_uptime_installers.py -q` → **22 passed in 120.86s** |
| Affected suites | Installer, bootstrap, disk-watch, prune, backup, deploy workflow, import graph, discovery, registry, and data-dir suites after rebasing onto `74e2600a` → **314 passed, 5 skipped in 158.85s** |
| Runtime logic suites | Watchdog, public MCP canary, and GitHub backup shipping → **51 passed in 0.68s** |
| Python lint | Ruff on all changed Python files → **passed** |
| Shell syntax | `bash -n` on installer, bootstrap, and daemon watchdog → **passed** |
| Shell lint | ShellCheck on the same scripts, excluding sourced-file lookup `SC1091` → **passed** |
| Workflow lint | actionlint on install-host-services and restart-daemon → **passed** |
| OpenSpec | Archived delta synced into the canonical uptime spec; `openspec validate --all --strict` → **41 passed, 0 failed** |
| Whitespace | `git diff --check` → **passed** (Git emitted only an LF/CRLF worktree notice) |
| systemd | Disposable `--root` verification of all five service/timer pairs with dependency stubs → **`verified=10`** |
| Disposable full DR | Exact landed run [`30066361115`](https://github.com/Jonnyton/TinyAssets/actions/runs/30066361115) on Debian 13 restored state, passed MCP probes, and deleted the drill Droplet |
| Final focused suite | 2026-07-24, Windows 11/WSL: backup ship/restore, DR invariants, host installer, and deploy workflow → **185 passed, 3 skipped in 143.65s** |
| Exact production backup | Run [`30075565479`](https://github.com/Jonnyton/TinyAssets/actions/runs/30075565479), source `a18751dc`: existing configuration verified, five timers converged, fresh brain/full primary uploads, two GitHub assets, terminal completion, no invocation warning/error |
| Archive integrity | `tinyassets-{brain,data}-2026-07-24T07-28-29Z.tar.gz`: downloaded SHA-256 matched GitHub digests; both tar streams and path confinement passed |
| Isolated restore | Full archive extracted outside production; 14 SQLite databases returned `PRAGMA integrity_check=ok`; `ledger.json` parsed |
| Retention | Private backup repository after the exact run: **30 recognized backup releases + 1 permanent audit release** |
| Deploy preservation | Exact-source deploy [`30076034679`](https://github.com/Jonnyton/TinyAssets/actions/runs/30076034679) passed health/public/five-handle/CF Access gates; automatic installer [`30076156783`](https://github.com/Jonnyton/TinyAssets/actions/runs/30076156783) reported configuration already verified and reconverged five timers |
| Independent review | Final implementation `c12730fd` and merge resolution `be77063f` → **APPROVE** |

The full repository suite was attempted twice by the independent verifier. It
exceeded 15-minute and 30-minute bounds without reporting a failure, so this
artifact does **not** claim a full-suite pass.

## Acceptance disposition

No acceptance evidence remains outstanding for the convergent host-service
and backup-preservation change:

- Disposable-host bootstrap/full restore proof is green.
- The exact production merge ran the installed two-tier backup and produced
  independently validated archives.
- Retention converged to its documented recognized-release ceiling.
- A subsequent production deploy stayed green and the automatic post-deploy
  installer reused the preserved backup authority.

The scheduled timers provide continuing operational evidence. A future
failure should open a new dated concern with its run/invocation identifier;
this completed lane should not remain in `STATUS.md` as historical narrative.
