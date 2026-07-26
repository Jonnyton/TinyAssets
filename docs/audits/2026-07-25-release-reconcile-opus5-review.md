# Release-Reconcile Opus 5 Review

**Date:** 2026-07-25

**Reviewer:** Claude Opus 5, dispatched read-only through the peer-agent harness

**Reviewed range:** `4b5c7fce9520c71686936b0301bc51423c5a15f4..727eba16a600bf7966144b6321bd9ac6eef53566`

**Verdict:** `APPROVE`

Opus reported that no blocking defect remained for merge. It inspected the
workflows, exact-script harness, OpenSpec change, and proof artifact; reran the
focused tests and Ruff; AST-parsed all five embedded Python bodies after YAML
dedent; queried live GitHub history; and used six throwaway mutation probes.
Each mutation broke the intended guard.

## Prior blocking findings

- **Production Python 3.12 rejected indented `python3 -c` bodies:** fixed by
  dedenting both convergence programs. The exact suite was reproduced red on
  CPython 3.12.13 before the fix and green afterward.
- **The local interpreter substitution hid that runner incompatibility:** fixed
  by `.github/workflows/release-reconcile-regression.yml`, which pins Python
  3.12 and runs both release workflow contract modules in CI.
- **A failed deploy could trigger unbounded same-SHA production mutation:**
  fixed by allowing the normal chained failure one explicit retry, then
  deferring a failed same-SHA workflow-dispatch retry before another build or
  deploy. A later same-SHA success overrides the older failure.
- **The `Converge` action gate was unasserted:** fixed with an exact condition
  assertion.
- **The `git rev-parse` fallback failure was untested:** fixed with a
  PATHS-unreadable exact-script case.
- **Empty release history falsely rendered production current:** fixed by
  emitting the distinct deferred state and summary.

## Verification evidence

- `python -m pytest tests/test_release_reconcile_workflow.py -q`:
  `31 passed in 18.70s` on CPython 3.14.3.
- `uv run --python 3.12 --with pytest --with pyyaml pytest
  tests/test_build_image_workflow.py tests/test_release_reconcile_workflow.py
  -q`: `34 passed in 20.82s` on CPython 3.12.13.
- Surrounding release/uptime suite: `112 passed in 20.80s`.
- Ruff: clean.
- actionlint 1.7.7: clean for the three changed workflows.
- `openspec validate release-reconcile-event-trigger --strict`: valid.

## Non-blocking residuals

- A cancelled explicit deploy currently consumes the one retry without
  `deploy-prod` opening its failure issue. This is narrow and normally
  self-resolves when newer main work caused the cancellation; watch live use.
- A failed retry at SHA X can produce a deferred summary before a successful
  descendant deploy Y is recognized. This is safe but can understate in-sync
  status.
- The structural column-zero assertion covers the two convergence `-c` bodies;
  the pinned Python 3.12 CI job protects the decision-step bodies.
- The 1,000-arrival result is a deterministic one-running/one-replaceable-
  pending scheduler model plus two exact-script executions, not hosted-GitHub
  load.
- Historical manual-versus-push chain counts are a dated sample; the current
  live history still supports the same directional conclusion.
- A persistent image-build-only failure can repeat CI work, but cannot mutate
  production and remains red and visible.
- The decision helper appends to one output file; current two-execution proof
  remains correct, but a future third call should isolate output per run.

## Post-land evidence

Fresh production evidence on 2026-07-25:

- `Release reconcile regression` run
  [30152318306](https://github.com/Jonnyton/TinyAssets/actions/runs/30152318306)
  completed successfully on `main` under the pinned Python 3.12 job.
- Manually dispatched main-branch `Docker build smoke` run
  [30152319997](https://github.com/Jonnyton/TinyAssets/actions/runs/30152319997)
  completed successfully, including image build, container start, and MCP
  initialize smoke.
- Its completion created `Release reconcile` run
  [30152436780](https://github.com/Jonnyton/TinyAssets/actions/runs/30152436780)
  with event `workflow_run`. That run completed successfully and reported
  `in sync — deploy fdfde5f1 contains fdfde5f1`.
- The reconcile run was created at 09:13 UTC but waited behind the fixed
  concurrency group before executing around 10:02 UTC. This confirms event
  delivery and safe coalescing while reinforcing the documented absence of a
  dispatch-latency guarantee.

No real drift repair or failed explicit retry has occurred since landing. The
first production exercise of that path remains a STATUS monitoring item rather
than being claimed as proven clean use.
