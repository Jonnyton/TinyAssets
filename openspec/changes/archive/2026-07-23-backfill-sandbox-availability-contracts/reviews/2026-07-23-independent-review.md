# Independent Review Record

- **Change:** `backfill-sandbox-availability-contracts`
- **PR:** #1632
- **Final reviewed head:** `c7477e72`
- **Date/environment:** 2026-07-22 PT / 2026-07-23 UTC, Windows, Python 3.14
- **Verdict:** APPROVE after adaptation by three independent reviewers

## Review Paths

### Requirement-to-source and control-flow review

Initial verdict: ADAPT.

Findings corrected before approval:

- Added the production `deploy-prod.yml` consumer under
  `uptime-and-alarms`.
- Preserved the strict `elapsed_ms < 5000` quick-exit boundary.
- Limited the status catch to preventing that lookup failure from aborting
  assembly.
- Completed the detached diagnostic exports, exact `to_dict` shape, four
  signatures, and `TimeoutExpired` propagation.
- Completed stripped/lowercased branch filtering, including empty and unknown
  values.
- Narrowed retry behavior to caught `VerifyError` failures and preserved the
  missing-reason fallback.

Final verdict: APPROVE at `c7477e72`.

### Ownership and whole-diff review

Initial verdict: ADAPT.

Findings corrected before approval:

- Removed the false claim that PR #1626 owned sandbox-status wording.
- Narrowed the design goal from every shipped sandbox surface to the surfaces
  reconciled by this change.
- Removed an unrelated hyperparameter STATUS edit during proposal review; the
  final coverage foldback then made that residual part of the audit scope, so
  STATUS was corrected with the reviewed canonical owner while retaining the
  future science-domain pre-spec as target-only.
- Confirmed the detached `tinyassets.sandbox` API belongs under
  `distributed-execution` because active task 7.1 groups it with the shipped
  runner seam.
- Confirmed the post-deploy verifier complements rather than duplicates the
  scheduled LLM-binding canary.

Final verdict: APPROVE at `1d6fd717`; the later `c7477e72` commit only applied
the source reviewer's narrower verifier wording.

### Coverage and verification review

Initial verdict: APPROVE for the four original owners, followed by a broader
reverse audit that required the fifth uptime owner.

Final conclusions:

- The delta contains exactly seven requirements and 26 scenarios across five
  canonical capabilities.
- The four legacy branch-list failures are stale fixtures: they omit `scope`
  after the default became `published`, so their unpublished rows never reach
  the sandbox filter. Direct `scope=all` probes confirm all filter cases.
- The full-coverage audit must retain two post-backfill shipped residuals:
  credential-vault and `HyperparameterImportanceEvaluator`; the future
  science-domain pre-spec is not the shipped evaluator owner.

Final verdict: APPROVE at `1d6fd717`; verifier wording was subsequently
narrowed without changing coverage.

## Post-Sync Review

All three reviewers independently approved the archived foldback:

- Each of the seven approved delta bodies appears exactly once in its
  canonical owner, with 26 scenarios total.
- The only pre-existing canonical prose edit is the planned
  `distributed-execution` Purpose expansion for the detached diagnostic API.
- The final inventory is 26 capabilities, 263 requirements, 759 scenarios,
  and 13 active changes; active work remains 172 proposed requirements and
  302 tasks with 51 checked.
- The full-coverage audit and STATUS consistently retain credential-vault and
  hyperparameter importance as the two shipped residuals.
- Final strict validation passed 39/39, mirror parity matched 255 files,
  cross-provider drift and diff checks were clean, and no collision with the
  future distributed-execution or engine-sandbox owners remains.

## Evidence

- `openspec validate backfill-sandbox-availability-contracts --strict`:
  passed.
- `openspec validate --all --strict`: 40/40 passed before archive.
- Focused local evidence: 143 tests passed across provider, graph, branch,
  status, diagnostic, deployment-verifier, and approval suites.
- Reviewer reruns: 159 tests with 6 deselected; 73 tests; and 19 verifier tests
  all passed on their respective final-review heads.
- Direct probes passed for scope-eligible `none`, `any`, empty, and unknown
  branch filters and for early no-home status omission.
- `python scripts/invariants_run.py --check mirror-parity`: 255 canonical files
  matched.
- `python scripts/check_cross_provider_drift.py`: clean.
- `git diff --check`: clean.

No product runtime changed. The Windows layer-2 uptime canary was not run
because this change reconciles existing contracts and that canary is
explicitly prohibited on this host.
