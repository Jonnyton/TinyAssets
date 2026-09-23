# Cloud application admission integration

Local candidate, 2026-09-22 UTC, Windows/Python3.14.3, isolated
wf-cloud-admission-negative/TinyAssets. Not pushed, deployed or accepted live.

Opus startup builder88199 finished exit0/620s. Its new tests failed11/passed4
before guards. Startup now refuses before writers/workers, preserving seal-first;
direct ASGI lifespan admission covers main bypass. Outermost origin middleware
uses only cached evidence, rejects unknown/noncloud with sanitized503, and keeps
admitted authentication and canary-only readback unchanged. No production service
was started. Root inspected the runtime diff and ran its tests independently.

Root recovery tests failed2/passed1 before guards: direct start could scavenge
credentials and poll could perform maintenance without process admission.
Both now call the shared require helper before any such effects. Existing
registration does not grant access; queued work remains pending on refusal.
The recovery + existing consumer suites passed39 tests before helper consolidation;
the consolidated helper is covered by the integrated cohort below.

Diagnostics now identify application_admission/enforced=true, not the obsolete
observation_only mode. This describes application guards ONLY, not attestation,
exclusive credential custody, all-worker coverage, binary freshness or full
boundary closure. The reporter still accepts the old observation-only mode for
rollout and never changes receipt-gate exit semantics. Pulse specs reflect503
before a handler on unadmitted origins and unchanged401 on admitted origins.

## Checks

All commands used C:/Users/Jonathan/Projects/TinyAssets/.venv/Scripts/python.exe.
`pytest -q ... -p no:randomly --tb=short`, basetemps outside the repo:

- startup/recovery/provenance/readback/deployed_sha:119passed,8 dependency warnings
  (`ta-cloud-admission-mode-20260922`).
- eleven direct-negative/admission/provenance/preparation modules:136passed,
  16 dependency warnings (`ta-cloud-integrated-negative-20260922`). Explicit
  `-p tests.skip_census_plugin --skip-census-out` report:136collected/136passed,
  zero skips; `scripts/skip_census.py --assert-max-platform-skips 0` passed.
- SSE keepalive, seal, hardened webhook, wiki-canary transport, workspace wiring:
  candidate114passed; the same cohort at cleana468232c114passed (same interpreter,
  `-p no:randomly`, separate temp roots). The initial unadapted run also had one
  non-admission workspace pending-row failure; it did not recur in either paired
  run. No root-cause claim for that single observation.
- Focused Ruff, `git diff --check`, strict OpenSpec validation passed.
- Opus23451 completed exit0/589s: the five existing startup/auth/discovery/webhook
  test modules passed61 checks after explicit fixture opt-ins. No assertions,
  skips, auth rules or production guards were changed.
- Fifteen direct caller modules initially132fail/311pass; after explicit
  module-local fixtures (and a unittest-local observation),442pass/1fail. The
  same cohort at cleana468232c also442pass/1fail: JUnit failure-set delta0. The
  remaining failure is Windows symlink privilege in shared-self conversation
  paging. JUnit files `ta-cloud-caller-{base,fixed}-20260922.xml` are under the
  user's local Temp directory. No quarantine/skip added. That file's11 existing
  Ruff findings also match base exactly; no new Ruff finding was introduced.
- Eight nested caller modules (background agents, branch runner, engine startup,
  HTTP inference, native discovery/model execution, workflow agent and allowance)
  initially53fail/164pass. Explicit module fixtures restore217pass, matching the
  identical217pass base cohort; no assertion/skip edits. JUnit files are
  `ta-cloud-nested-{base,fixed}-20260922.xml` under local Temp.
- Plugin builder rebuilt499 files, import probe passed. Final staged mirror
  parity remains a commit gate, not inferred from this build output.

## Remaining release questions

Linux oracle is unavailable: prior attempt found no Docker engine. Do not start
Docker Desktop/WSL, whose unrelated auto-start containers have not been cleared.
No Linux result or pre-push exception is claimed. Review and required hosted
tests, verified deployment, rendered acceptance and spec closeout remain open.

Watchdogs restart the same container/unit; release-reconcile dispatches hosted
deployment, not an alternate desktop executor. Guarded startup covers that boot.
Stale-runtime retirement is a manual plan/apply operation cancelling specifically
approved old tasks; it does not select a successor. Independent review must
assess coverage against the no-unadmitted-successor requirement without falsely
describing explicit admin cancellation as preserved pending work.

Cloudflare browser observation found one connected Linux cloud origin and no
listed desktop connector. Hosted connector read was401/unknown; custody and SSH
host trust remain unverified. This patch does not resolve those external facts.
Free-user onboarding remains unattempted until the generalized path is ready.

## CI contract integration, September 23 UTC

Draft PR3919 head c20ab0cd: hosted packaging35800404593 failed two handshake
tests (32 passed) because the actual launcher refused unadmitted startup with
exit78/platform_not_cloud. Opus91106 corrected the test contract, preserving
an unmodified-launcher refusal test and real staged stdio enumeration through
an explicitly simulated process-observation fixture. Focused Windows test
file36passed; root corrected the reported interpreter to Python3.14.3.
No production admission flag, launcher override or guard weakening was added.

Docker smoke35800404480 failed container readiness; --rm removed the exited
container's logs, so its specific exit cause was not observed. CI now retains
and tests an unmodified image's refusal (network disabled, no state/credentials)
and separately mounts an image-excluded, read-only test fixture supplying
simulated admission for authenticated loopback-only HTTP/catalog verification.
The actual Docker entrypoint, server and auth are unchanged. The fixture is
not cloud provenance or deployed acceptance. Three local fixture/structural
tests pass; actual container execution and workflow lint remain hosted gates.

Root verification September23 00:21UTC, Windows/Python3.14.3:
`python -m pytest -q tests/test_packaging_build.py tests/test_docker_admission_fixture.py
--junitxml=<outside-repo-temp>/ta-cloud-packaging-20260922.xml` passed39tests,
8warnings,108.77s. Focused Ruff passed. Local actionlint is absent (hook SKIPPED)
and Linux oracle cannot connect to the absent engine; neither is a pass. No
Docker Desktop/WSL was started. Hosted checks still gate this candidate.
