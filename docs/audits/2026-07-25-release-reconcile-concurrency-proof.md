# Release-Reconcile Concurrency and Load Proof

**Date:** 2026-07-25

**Branch:** `codex/release-reconcile-event`

**Source base:** `44990a9b3071296f40b68ea37b84a5919f53e52e`

## Command and environment

```text
python -m pytest tests/test_release_reconcile_workflow.py -q
```

Result: `18 passed in 10.79s`.

Surrounding release/uptime regression command:

```text
python -m pytest tests/test_build_image_workflow.py tests/test_deploy_prod_workflow.py tests/test_uptime_canary_workflow.py tests/test_uptime_canary_concurrency.py tests/test_release_reconcile_workflow.py -q
```

Result: `99 passed in 13.05s`.

Environment:

```text
Microsoft Windows NT 10.0.26200.0
Python 3.14.3
git 2.53.0.windows.1
GNU bash 5.2.37 (Git for Windows)
actionlint 1.7.7
```

## Executed production surface

The proof loads `.github/workflows/release-reconcile.yml` and executes the exact
shell bodies of:

- `Compare main against the last successful deploy`
- `Converge`

The decision script runs inside a temporary real Git repository with two
release-relevant commits. A shell-level `gh` function supplies shared GitHub run
state while leaving the production script unchanged. The converge script uses
the same harness to record image dispatch, run discovery, run waiting,
post-build main verification, and deploy dispatch.

The proof also loads `.github/workflows/build-image.yml` and asserts that only a
new push can cancel in-progress image work; a reconcile-initiated manual build
cannot cancel an active push build.

## 1,000-arrival result

The scheduler model walks all 1,000 same-group arrivals while maintaining one
running and one replaceable pending slot. Each arrival after the first replaces
the pending slot, deriving arrivals `0` and `999` as the only executions. The
first exact decision-script execution sees drift and emits one `dispatch`.
Shared state then exposes that same relevant SHA as an active image build. The
coalesced final execution emits `none`.

Proved outcomes:

- one corrective dispatch across the modeled stampede;
- no second dispatch while current release work is active;
- a stale active SHA does not suppress current-main recovery;
- active-run and successful-deploy query failures produce no corrective action;
- completed and unrelated workflow runs are excluded by the production JSON
  selector and do not suppress recovery;
- successful deploy ancestry produces no action;
- missing deploy ancestry produces dispatch;
- unchanged main yields one image dispatch, one same-SHA build wait, and one
  explicit deploy using the 12-character immutable image tag;
- an already active same-SHA deploy suppresses duplicate explicit dispatch;
- advanced main before or after build discovery emits no stale-image deploy;
- a cancelled/superseded image build defers without red failure, while a failed
  image build remains a visible non-zero failure.

## Scheduler-model limitation

This is a deterministic model of GitHub's documented fixed-group behavior: one
running run plus one replaceable pending run with `cancel-in-progress: false`.
It does not execute GitHub's hosted scheduler, prove event-delivery latency, or
prevent GitHub from suppressing/delaying schedule and `workflow_run` events.
The exact workflow trigger remains inert until the file lands on the default
branch. Real-run history and post-land monitoring are therefore still required;
this proof establishes decision safety and bounded dispatch under the declared
policy, not hosted-scheduler timing.
