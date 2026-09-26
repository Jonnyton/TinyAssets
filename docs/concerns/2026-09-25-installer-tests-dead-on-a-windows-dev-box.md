# `test_host_uptime_installers.py` is mostly dead on a Windows dev box

**Filed:** 2026-09-25 · **Verified:** 2026-09-25 on `b976df9a`, Windows 11, `.venv` Python · **Severity:** P2

## Finding

The module that guards the host-uptime installer and the daemon watchdog cannot be run as one suite
locally. Its two halves need **different** `bash`, and each fails under the other's.

Measured on `b976df9a` with `python -m pytest tests/test_host_uptime_installers.py -q`:

| `shutil.which("bash")` resolves to | Result |
|---|---|
| Git Bash (`C:\Program Files\Git\usr\bin\bash.exe`) — the default | **21 failed, 40 passed, 1 skipped** |
| WSL (`C:\Windows\System32\bash.exe`, first on `PATH`) | **4 failed, 57 passed, 1 skipped, 1 error** |

`_BASH = shutil.which("bash")` (`tests/test_host_uptime_installers.py:54`) is whatever `PATH`
offers, so which half works is decided by the developer's `PATH` and is invisible in the result.

### The installer half needs WSL, for two reasons

1. **`flock`.** Every one of the 21 Git Bash failures is the same line:
   `[host-uptime-install] ERROR: missing command: flock`.
   `deploy/install-host-uptime-services.sh` requires it (in the command list at `:85-90`, used at
   `:134`), and Git Bash ships no `flock` at all. The installer exits before its first assertion, so
   those 21 tests assert nothing — they are not "failing", they never ran.
2. **Real mode bits.** The installer compares installed file modes (`stat -c %a`) to decide whether
   a release is already exact. Under WSL, `/mnt/c` is DrvFs and `stat -c %a` answers **777 for every
   file** whatever `chmod` did. pytest here runs from Windows, so `tmp_path` is *always* a DrvFs
   path — meaning even the WSL run cannot exercise that comparison. Verified directly: `chmod 644`
   then `stat -c %a` returns `777` under `/mnt/c`, and `644` under WSL-native `/tmp`.

### The watchdog half needs Git Bash

Under WSL bash the watchdog tests fail with
`bash: /daemon-watchdog.sh: No such file or directory` — `_run_watchdog` builds its command with
`wd_dir="$(cd <path> && pwd)"`, and that path translation does not survive WSL. A harness artifact,
nothing to do with `deploy/daemon-watchdog.sh`.

## Why it matters

Three release-critical scripts are covered by this module — `deploy/install-host-uptime-services.sh`,
`deploy/daemon-watchdog.sh`, `deploy/hetzner-bootstrap.sh` — and on the machine where they are
edited, a local run is not evidence in either direction. A contributor who reads the default (Git
Bash) result sees 21 red and has no way to tell that 21 of them never executed. CI is green on Linux
throughout, so nothing is broken in production; the loss is entirely in local feedback, which is
where a deploy-chain mistake is cheapest to catch.

This was worked around, not fixed, while landing #3989 and #3990: the idempotence tests were proven
by running the same test functions under WSL's `python3` against WSL-native `/tmp` with a minimal
`pytest` shim, and the watchdog tests under Git Bash. Both are manual and neither is repeatable by
anyone who does not know the trick.

## What would resolve it

`scripts/linux_oracle.py` already exists for exactly this and would run the whole module correctly
in one command — it needs a running Docker engine, and there was none on this box when the concern
was filed. So the first question is whether the oracle is simply the documented answer here (and
this concern becomes a line in the module's docstring pointing at it), or whether the harness should
additionally degrade honestly:

- **skip, do not fail,** when `flock` is absent — a test that cannot start is a skip with a reason,
  not a red. 21 silent non-runs is the actual defect;
- **skip the mode-comparison tests** when the install filesystem does not report real mode bits.
  `_require_meaningful_mode_checks` in `tests/test_host_uptime_installers.py` does this for the two
  idempotence tests added in #3989 and is the pattern to extend;
- **do not mock `flock`.** A stub that always succeeds was tried and rejected during #3989:
  `test_same_target_lock_timeout_is_red_before_systemd` needs the second concurrent installer to
  genuinely time out, so a permissive stub turns a real concurrency proof green while proving
  nothing.

Not proposed here: making the harness bash-agnostic. Both path-translation directions would need
rework, and the oracle may make that unnecessary.
