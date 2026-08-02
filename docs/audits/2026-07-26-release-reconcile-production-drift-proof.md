# Release-Reconcile Production Drift Proof

**Observed:** 2026-07-26 UTC

**Environment:** GitHub Actions and the production TinyAssets deployment

**Verdict:** Production release drift was detected and automatically repaired.

## Evidence chain

The convergence logic exercised here landed on 2026-07-25 in PRs #1749/#1750
(`e40be285`, `7cdfbea8`). This is its first production exercise through the
complete drift-to-build-to-explicit-deploy path. Drift detection itself
predates this logic; for example, run
[30085858876](https://github.com/Jonnyton/TinyAssets/actions/runs/30085858876)
detected drift on 2026-07-24 and dispatched build
[30085883600](https://github.com/Jonnyton/TinyAssets/actions/runs/30085883600),
but that older controller did not complete this newer explicit-deploy path.

1. Scheduled `Release reconcile` run
   [30188518485](https://github.com/Jonnyton/TinyAssets/actions/runs/30188518485)
   compared `main` with successful production deploy history. Its decision log
   reported:
   - `main HEAD`: `b759682fbcb226a7cd90b62092676ef7e3555e3f`
   - `last release-relevant`: `46ff5c5c6c716bd85cb7d035a60ee774b91d603b`
   - `DRIFT: nothing deployed contains 46ff5c5c`
2. The reconcile job executed its `Converge` step and dispatched `Build and
   publish image` run
   [30188530692](https://github.com/Jonnyton/TinyAssets/actions/runs/30188530692)
   for current `main`. The build completed successfully for
   `b759682fbcb226a7cd90b62092676ef7e3555e3f`.
3. The same convergence step explicitly dispatched `Deploy prod` run
   [30188600783](https://github.com/Jonnyton/TinyAssets/actions/runs/30188600783)
   for that exact SHA. The deploy completed successfully.
4. The deploy's successful job included:
   - daemon health;
   - cloud-worker running;
   - canonical-URL post-deploy canary;
   - exact-seven public MCP surface assertion;
   - Cloudflare Access direct-URL gate;
   - release-state receipt publication.

## What this proves

This is a real hosted production exercise, not a structural test or simulated
scheduler model. It proves the scheduled controller detected a deployed-state
gap and that the #1749/#1750 convergence logic dispatched the missing build,
explicitly dispatched the corresponding production deploy, and reached the
post-deploy acceptance checks.

The drift-repair half of the previously open STATUS monitoring premise is
resolved.

## Boundary

This evidence does not claim that a failed or cancelled explicit
reconcile-initiated deploy retry has occurred in production. The failure path
is covered by the pinned Python 3.12 regression workflow and its exact-script
test. The cancelled-deploy subcase is structural/code-reviewed evidence only;
the suite's cancelled case covers a build rather than a deploy. A production
failure or cancellation was not induced merely to exercise the cap, and both
residuals remain in the STATUS failure-proof concern shipped with this
evidence.

## Independent review

Claude Opus 5 reviewed the diff read-only against the workflow source, focused
tests, GitHub API, and primary run logs. Two `ADAPT` passes corrected the
historical "first drift" wording and separated failed-deploy exact-script proof
from the untested cancelled-deploy subcase. The final exact-diff review returned
`VERDICT: APPROVE` on 2026-07-26.
