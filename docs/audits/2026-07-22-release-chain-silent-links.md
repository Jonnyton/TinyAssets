<!--
Provenance: carried verbatim from `output/s2-gate/deploy-chain-silent-links.md` (lane report,
2026-07-21 18:33). The lane produced this report but never opened a PR, so it
existed only on disk. Body below is the report unmodified; only this
comment was added.
-->

# Release-chain silent-links audit — 2026-07-22

## Scope and evidence

Read-only audit of all 30 workflows in `.github/workflows/` at commit `220a1fc8c69d3ae07b7673494e30d1267a220f69`.

Live GitHub and production evidence sampled 2026-07-22 UTC:

- Branch protection: `strict=true`; required contexts are only `policy` and `Diff scope declared`.
- Production `get_status.release_state.git_sha`: `1605349e888c918dc9ef8fd1452cb40d83a5dc51`.
- Latest successful deploy run `29882303754` advertises `head_sha=1437b30a4dade0b52bb3cadb9096c5629e281754`.
- Release reconcile run `29882999785` declared production current using that deploy-run SHA.
- Open `p0-outage` issue #1461 has remained red since July 15.
- `p0-outage-triage.yml` has not run since June 27.

GitHub documents that `GITHUB_TOKEN`-generated events do not create new workflow runs except `workflow_dispatch` and `repository_dispatch`. It also documents that `workflow_run` runs use the latest default-branch commit as `GITHUB_SHA`, not the triggering workflow’s deployed source SHA. [GITHUB_TOKEN behavior](https://docs.github.com/en/enterprise-cloud@latest/actions/concepts/security/github_token), [workflow event semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).

## Executive verdict

The new release reconciler still has a false-green path: it compares current main to the metadata SHA of a successful `Deploy prod` workflow run, not to the live release receipt. Current production already proves those values can differ.

Three complete chains remain silently severed:

1. `p0-outage` issue creation → P0 auto-triage.
2. Merged Cloudflare Worker change → live Worker deployment.
3. Merged React site change → live Pages deployment.

In addition, strict merge enrollment still lacks reconciliation; the DNS and LLM canaries cannot reach their advertised two-red alarm threshold; scheduled canary cadence is 10–40 times slower than declared; and branch-janitor operation failures return green.

## Findings

### P0-1 — Release reconcile trusts the wrong SHA and can certify stale production

Affected: `release-reconcile.yml`, `deploy-prod.yml`.

Inputs:

1. Image build completes for commit A.
2. Main advances to B before the `workflow_run`-triggered deploy starts.
3. Deploy correctly selects A from `github.event.workflow_run.head_sha`.
4. GitHub records the deploy workflow run itself with `head_sha=B`, because a `workflow_run` workflow’s SHA is the latest default-branch commit.
5. Reconcile queries successful deploy runs and tests B’s ancestry.

What silently does not happen: reconcile never reads `get_status.release_state.git_sha` or the deployed image digest. It reports B live and dispatches nothing although production is running A.

This is observed, not theoretical:

- [Deploy run 29882303754](https://github.com/Jonnyton/TinyAssets/actions/runs/29882303754) reports `head_sha=1437b30a`.
- The live receipt written by that run reports `git_sha=1605349e`.
- [Reconcile run 29882999785](https://github.com/Jonnyton/TinyAssets/actions/runs/29882999785) returned green using “deploy 1437b30a contains 8c70b5f0.”

Required correction: reconcile desired release SHA/digest against the live release receipt. Workflow-run metadata is evidence about the workflow checkout, not deployed state.

### P0-2 — Uptime-created P0 issues cannot trigger P0 auto-triage

Affected: `uptime-canary.yml`, `p0-outage-triage.yml`.

Inputs:

1. Uptime canary observes consecutive reds.
2. `actions/github-script` creates an issue carrying `p0-outage` using `GITHUB_TOKEN`.
3. `p0-outage-triage.yml` waits for `issues: labeled`.

What silently does not happen: GitHub suppresses the `issues:labeled` workflow event because the label was applied with `GITHUB_TOKEN`. No SSH diagnosis, restart, rollback classification, or `needs-human` transition occurs.

Live proof:

- [Issue #1461](https://github.com/Jonnyton/TinyAssets/issues/1461) has been red since July 15 and continued receiving red comments through this audit.
- The latest P0 triage run is still [June 27](https://github.com/Jonnyton/TinyAssets/actions/runs/28279692641).

Required correction: make triage a scheduled reconciliation of open `p0-outage` issues and triage receipts, or dispatch it directly with `workflow_dispatch`/`repository_dispatch`. A label event cannot be load-bearing.

### P0-3 — Actions-app merges of Worker changes deploy neither immediately nor eventually

Affected: `deploy-worker.yml`, `release-reconcile.yml`.

Inputs:

1. A PR changes `deploy/cloudflare-worker/**`.
2. Auto-merge merges it using `GITHUB_TOKEN`.
3. The resulting `push` event is suppressed.

What silently does not happen: `deploy-worker.yml` never runs, Wrangler never publishes the new Worker, and no red check or issue exists.

The daemon release reconciler does not close this gap. Because `build-image.yml` includes `deploy/**`, it may build and deploy a new daemon image, then declare production current while the independently deployed Cloudflare Worker remains old.

Required correction: reconcile the desired Worker source hash against a deployed Worker version/digest, then dispatch an idempotent Worker deployment when they differ.

### P1-4 — Strict auto-merge still has no convergence mechanism

Affected: live branch protection, `auto-enroll-merge.yml`.

Inputs:

1. Multiple current PRs are enrolled.
2. One merges.
3. `strict=true` makes every remaining PR `behind`.
4. No PR-head `synchronize` event occurs merely because main advanced.

What silently does not happen: no workflow updates the branches or disables strictness. Enrollment is event-only, and its `gh pr merge --auto` failure path is explicitly swallowed; the job remains green and creates no issue.

Live protection still reports:

```json
{"strict":true,"contexts":["policy","Diff scope declared"]}
```

An existing non-draft main PR, #1397, was `BEHIND` with no auto-merge request during the audit.

Required correction: either disable strictness as intended, or periodically reconcile every eligible main PR by updating its branch and asserting `autoMergeRequest != null`.

### P1-5 — DNS and LLM canaries can stay red forever without an issue or red workflow

Affected: `dns-canary.yml`, `llm-binding-canary.yml`.

Both implement:

1. Probe step uses `continue-on-error: true`.
2. Alarm sink checks whether the previous workflow run concluded `failure`.
3. No later step fails the probe job when `overall=red`.

Inputs: DNS or LLM probe fails repeatedly.

What silently does not happen: each run still concludes success, so every invocation sees the previous conclusion as success and calls itself “first-red.” The advertised second-red issue is unreachable. There is no issue, alarm, or red workflow check.

Required correction: add an explicit final failing step on red, or persist consecutive-red state independently of workflow conclusion.

For DNS specifically, resolution alone is also not desired-state reconciliation: a wrong but resolvable IP/CNAME remains green.

### P1-6 — The declared 5/15-minute alarm latency is false in production

Affected: `uptime-canary.yml`, `dns-canary.yml`, `community-loop-watch.yml`.

Measured scheduled-run gaps over the preceding 48 hours:

| Workflow | Declared | Median gap | Maximum gap |
|---|---:|---:|---:|
| uptime-canary | 5 min | 93.3 min | 210.3 min |
| dns-canary | 15 min | 98.3 min | 218.1 min |
| community-loop-watch | 15 min | 94.0 min | 216.3 min |
| llm-binding-canary | 6 h | 329.5 min | 456.3 min |

GitHub explicitly warns that scheduled jobs may be delayed or dropped under load. [GitHub troubleshooting](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows).

What silently does not happen: missed ticks create no run and therefore no red check. `community-loop-watch` cannot provide independent scheduler-liveness evidence because its own schedule is delayed by the same substrate.

Required correction: maintain an externally witnessed heartbeat with an alarm on missed deadlines. Workflow schedules can perform probes but cannot be their own only liveness witness.

### P1-7 — The live website has no merge-to-production loop, and its observers watch the retired site workflow

Affected: `deploy-site-react.yml`, `deploy-site.yml`, `community-loop-watch.yml`, `announce-patch.yml`.

Inputs: a React-site PR merges through auto-merge.

What silently does not happen:

- `deploy-site-react.yml` is manual-only, so Pages remains on the old revision.
- `community_loop_watch.py` monitors `deploy-site.yml`, the retired Svelte rollback workflow, with no maximum age. Its June success can remain green indefinitely.
- `announce-patch.yml` also watches `deploy-site`, not the React deploy.
- `announce-patch`’s fallback `push` trigger is suppressed for Actions-app merges.

Live Actions reports zero `announce-patch` runs.

Required correction: publish a Pages deployment receipt and reconcile the live Pages commit against desired React main. Point monitoring and announcement consumers at that receipt.

### P1-8 — Release reconciliation dispatches work but does not reconcile terminal failure

Affected: `release-reconcile.yml`, `build-image.yml`.

Inputs:

1. Reconcile sees drift.
2. It dispatches `build-image.yml`.
3. The build fails, times out, or is repeatedly cancelled.

What silently does not happen: reconcile does not wait for or record the child outcome. Its own run is green once dispatch is accepted. Build failure produces only a separate red Actions run—no issue or alarm—and the next tick merely dispatches again.

`build-image.yml` also uses `cancel-in-progress: true`; a cold build exceeding the reconcile interval can be repeatedly cancelled by newer dispatches.

Required correction: persist a per-desired-SHA release attempt with build/deploy terminal state, retry budget, age, and alarm. “Dispatch accepted” is not convergence.

### P1-9 — Branch janitor reports successful runs even when deletion or issue writes fail

Affected: `branch-janitor.yml`, `scripts/branch_janitor.py`.

Inputs:

- `git push origin --delete <branch>` fails; or
- rolling issue creation/update fails.

What silently does not happen: the process does not exit nonzero. `delete_branch()` returns a `"FAILED ..."` string, `upsert_issue()` is explicitly best-effort, and `main()` always returns zero. The rolling report is generated before deletion and contains no operation result.

Thus the scheduled workflow is green while branches were not deleted and the issue may not have been updated.

Required correction: make requested mutations and the tracking-issue write checked invariants. A reconciliation loop may tolerate temporary failure, but it must remain red until desired state is reached.

### P2-10 — Rollback is signalled, but not represented truthfully as durable release state

Affected: `deploy-prod.yml`.

A normal post-deploy failure with an available previous image does produce:

- a red deploy workflow,
- a rollback attempt,
- a rollback canary,
- a `deploy-failed` issue.

Therefore “rollback is wholly unnoticed” is not a finding.

Remaining gaps:

- The issue body says “Rolled back to” regardless of whether the rollback step ran or succeeded.
- No rollback receipt replaces or annotates `/data/release-state.json`.
- Manual deployment of an old `image_tag` can succeed while the workflow run’s `head_sha` is current main, creating the P0-1 false-green.
- Reconcile ignores the live receipt and cannot distinguish current, rolled-back, manually overridden, or receipt-stale production.

Required correction: publish a terminal deployment receipt with `outcome`, attempted digest, active digest, rollback outcome, rollback canary, and source SHA after every path.

### P2-11 — Secondary operational lanes have red-check-only or no-event failure paths

Affected:

- `announce-patch.yml`: app merge push suppressed; obsolete workflow dependency; zero runs.
- `build-bundle.yml`: main push and action-created release events can be suppressed; no release-asset reconciliation.
- `actionlint.yml` and `docker-build.yml`: token-driven main pushes skip their push checks; PR checks usually reduce exposure.
- `claude-auth-keepalive.yml`, `codex-auth-keepalive.yml`: weekly failure creates only a red Actions run.
- `restart-daemon.yml`: manual-only, no issue on failure, and verifies only the public handshake rather than the full uptime bundle.
- `install-host-services.yml`: observed `workflow_run` trigger works, but installation failure has no issue and installed timer state is not periodically reconciled.
- `secrets-expiry-check.yml`: secrets marked `non_expiring`, including Pushover credentials, are skipped without checking presence or validity.
- `dr-drill.yml`: failures before the probe do not open `dr-failed`; successful drill-log `git push` failures are swallowed with `|| true`.

## Suppression inventory

Events directly exposed to `GITHUB_TOKEN` suppression:

| Workflow | Trigger at risk | Consequence |
|---|---|---|
| `p0-outage-triage.yml` | `issues:labeled` | Proven auto-triage outage |
| `deploy-worker.yml` | `push` | Worker changes never publish |
| `announce-patch.yml` | `push` | No announcement |
| `build-image.yml` | `push` | Covered only partially by release reconcile |
| `build-bundle.yml` | `push`, `release:published` | No main/release artifact run |
| `docker-build.yml` | `push` | No main smoke |
| `actionlint.yml` | `push` | No main workflow lint |
| `community-loop-watch.yml` | filtered `push` | Delayed until another trigger/schedule |
| `auto-enroll-merge.yml` | PR events created by automation | Enrollment may not happen |
| `daemon-request-policy.yml`, `pr-scope-guard.yml` | automated label changes | Required checks may retain stale label state |

Observed `workflow_run` links—build→deploy, deploy→uptime, deploy→host-service installation—do fire. Their remaining defect is state provenance, not trigger suppression.

## Required and path-filtered checks

Live required checks:

| Required context | Workflow | Path-filtered? |
|---|---|---|
| `policy` | `daemon-request-policy.yml` | No |
| `Diff scope declared` | `pr-scope-guard.yml` | No |

Therefore there is currently no path-filtered required-check deadlock.

Path-filtered but non-required checks are:

- `lint` — `actionlint.yml`
- `Stage + import-probe both bundle and plugin` — `build-bundle.yml`
- `build-smoke` — `docker-build.yml`
- Worker PR dry-run — `deploy-worker.yml`
- React preview — `preview-worker.yml`

They must remain non-required unless converted to unconditional workflows with internally skipped/no-op jobs.

## Workflow coverage

Every workflow was inspected:

- Release/merge: `auto-enroll-merge`, `daemon-request-policy`, `pr-scope-guard`, `actionlint`, `build-image`, `docker-build`, `build-bundle`, `deploy-prod`, `release-reconcile`.
- Public surfaces: `deploy-worker`, `deploy-site`, `deploy-site-react`, `preview-worker`, `announce-patch`.
- Uptime/alarm: `uptime-canary`, `dns-canary`, `llm-binding-canary`, `community-loop-watch`, `p0-outage-triage`, `pushover-test`.
- Host/DR: `restart-daemon`, `install-host-services`, `dr-drill`, `tier3-oss-clone-nightly`, `branch-janitor`, `claude-auth-keepalive`, `codex-auth-keepalive`, `secrets-expiry-check`.
- DNS operations: `emergency-dns`, `site-dns-cutover`.

## Remediation order

1. Reconcile against the live release receipt/digest, never deploy-run `head_sha`.
2. Replace issue-label-triggered P0 triage with scheduled/open-issue reconciliation or explicit dispatch.
3. Add Worker and React-site desired-state reconcilers.
4. Remove `strict` or reconcile behind/enrollment state continuously.
5. Fix DNS/LLM red-state accounting.
6. Add an independent missed-tick witness.
7. Make branch-janitor mutation failures nonzero.
8. Add terminal release-attempt state and rollback receipts.
