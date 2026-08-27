# The scheduled tripwire has been red continuously, so it carries no signal

**Filed:** 2026-08-27
**Severity:** P2 — no production impact, but it is a blind spot in the test surface

> The job was named `full-tests` when this was filed and is `heavy-tests` as of
> PR #2576 (2026-08-27). The finding below is stated against `full-tests`
> because that is what was measured; the Update at the bottom carries the
> post-rename numbers, which supersede the 135 count here. Filename kept so
> existing links resolve.

## The finding

`full-tests` was the "complete test surface" job in `.github/workflows/tests.yml`.
It is **not** a required check; it ran on push to `main` and hourly, and exists
as a post-merge tripwire.

It has failed on **every** commit checked:

| Commit | `full-tests` |
|---|---|
| `6dad3c42`, `07d5151a` | failure |
| `a44aed2c`, `20b317c0` | failure |
| `d513db80`, `d6d51015` | failure |
| `e4180697` (push and scheduled) | failure |

`e4180697` predates the 2026-08-27 work, so this is **not** a regression from
the harness reset or the lean pass. It was already red.

**135 distinct failures**, concentrated in a few files:

```
278 hits  tests/test_deploy_prod_workflow.py
 34 hits  tests/test_retire_cheat_loop_deploy_fence.py
 12 hits  tests/test_host_uptime_installers.py
 10 hits  tests/test_integration.py
  6 hits  tests/test_backup_script.py
```

## Why it matters

A permanently-red check is the same failure as a permanently-green one: **nobody
can tell a new break from the standing noise.** This repo spent 2026-08-26/27
removing checks that could not fail (`policy`, vacuous 100/100;
`cross-provider-drift`, unconditionally clean). This is that shape inverted, and
it deserves the same treatment.

It compounds with `.github/heavy-test-files.txt`: files listed there are excluded
from the required lane and run *here*. So the heaviest tests are routed into a
job whose result nobody can read.

## What the failures look like

A mix, and the mix is the point — several are CI-environment, not product:

- `Xlib.error.DisplayNameError: Bad display name ""` — no X display
- `shellcheck backup.sh: assert 1 == 0` — shellcheck not installed on the runner
- `assert 154.884967026 < 154.877550865` — a timing flake, ~7 ms over
- `assert result == (Path.home() / ".workflow").resolve()` — host-path assumption

Environment failures and real failures are indistinguishable in the current
output, which is why the job has been ignorable.

## What would resolve this

Either make it green (install `shellcheck` and a virtual display on the runner,
quarantine the genuine flakes, fix or retire `test_deploy_prod_workflow.py`), or
retire the job and stop routing `heavy-test-files.txt` into it. **Leaving a red
tripwire in place is the one option that should not survive** — it reads as
coverage while providing none.

Not attempted here: 135 failures across a deploy-workflow suite is a real piece
of work, and doing it badly would mean quarantining assertions to get green,
which this repo explicitly forbids.

---

## Update 2026-08-27: the job was renamed, the red was not fixed

`full-tests` is now `heavy-tests` (PR #2576). That change removed the
DUPLICATION -- the old job re-ran the 10,700 tests `required-tests` had already
passed minutes earlier -- but it did **not** make the tier readable.

Cross-family review measured the baseline precisely, and rated it a blocker:

| Measure | Value |
|---|---|
| Heavy tests run | 2,236 |
| Failures | 114 |
| **Unquarantined** failures | **107** |
| Stale quarantine entries | 10 |

So the quarantine path now applies (it did not under raw pytest) and still does
not help: 107 of 114 failures are not in the ledger.

**The rename was landed anyway, deliberately.** It is strictly better than what
it replaced -- same redness, minus a duplicated 10,700-test run per merge, and
a red now means "a heavy file broke" rather than "something in 13,865 tests".
It is not required, so it blocks nothing. But nothing here is fixed.

**What resolving this actually needs**, from the Linux junit rather than a local
run: 105 of the 132 whole-suite failures are two files.
`tests/test_deploy_prod_workflow.py` (88) asserts a `workflow_dispatch` input
that no longer exists -- PR #2442 rewrote that workflow from 2,762 lines to 134
-- and `tests/test_retire_cheat_loop_deploy_fence.py` (17). Those need per-test
triage against the current design, NOT deletion: the failure causes are mixed,
and one references `TINYASSETS_CODEX_AUTH_JSON_B64` missing from a step, which
may be a real drop from that 2,628-line deletion rather than a stale assertion.

Until then `heavy-tests` is a red tripwire, and the 10 stale quarantine entries
should be drained via `scripts/quarantine_oracle.py` as a cheap first step.
