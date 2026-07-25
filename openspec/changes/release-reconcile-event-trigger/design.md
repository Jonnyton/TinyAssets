## Context

`Release reconcile` declares a 15-minute schedule or can be dispatched
manually, then compares deploy-run ancestry with the newest release-relevant
commit on `main`. Live GitHub history sampled by Opus 5 on 2026-07-25 showed 29
scheduled intervals with a 96.8-minute median and 212.7-minute maximum, so the
schedule is an independent best-effort backstop rather than a latency bound.

`Docker build smoke` exercises Docker build, import, and MCP initialize paths
on pushes, pull requests, and manual dispatches. A `workflow_run` trigger can
shorten re-evaluation latency after a trusted main-branch smoke, but the
downstream workflow has `actions: write`, so pull-request provenance must never
start its privileged job.

GitHub runs `workflow_run` workflows from the default branch and exposes the
triggering workflow's event, repository, branch, and conclusion. GitHub
concurrency permits one running and, by default, one pending run per fixed
group; a newer arrival replaces an older pending run while
`cancel-in-progress: false` preserves the active run.

The current corrective action dispatches `build-image.yml` with
`GITHUB_TOKEN`. GitHub suppresses implicit `workflow_run` chaining from
token-created runs; sampled history found only 1 of 22 manually dispatched
image builds had a same-SHA deploy, versus 61 of 75 push builds. The reconciler
therefore must wait for its requested image build and dispatch `deploy-prod.yml`
explicitly. It must also avoid cancelling an already-working push build:
`build-image.yml` currently uses a shared main concurrency group with
`cancel-in-progress: true`.

## Goals / Non-Goals

**Goals:**

- Re-evaluate immediately after a trusted successful `Docker build smoke` run
  on `main`.
- Preserve the scheduled and manual recovery paths.
- Keep one active reconciliation and coalesce any burst into at most one
  pending reconciliation.
- Preserve a queued or running release chain that already contains the relevant
  commit; fail closed when GitHub run state is unreadable.
- Make a reconcile-initiated image build explicitly reach deploy without
  cancelling active push work or deploying an image after `main` advances.
- Prove the exact decision and converge scripts under a 1,000-arrival
  scheduler model.

**Non-Goals:**

- Treating Docker smoke success as deployment or live-receipt proof.
- Triggering privileged reconciliation from pull-request or non-main runs.
- Guaranteeing that every queued event receives its own execution.
- Making workflow-run metadata equivalent to the live release receipt.

## Decisions

### Authorize provenance at the privileged job boundary

The workflow declares `workflow_run` for `Docker build smoke`, `completed`, and
`branches: [main]`. The reconcile job also requires a successful conclusion,
`head_branch == 'main'`, own-repository `head_repository.full_name`, and an
upstream event of `push` or `workflow_dispatch`; schedule and manual reconcile
events remain eligible.

The trigger filter avoids irrelevant runs, while the job condition is the
authorization boundary for a workflow with `actions: write`. Branch name alone
was rejected because a fork's default branch can also be named `main`.
Requiring only `push` was rejected because a successful write-authorized manual
smoke on `main` is equally valid build evidence; enumerating `push` and
`workflow_dispatch` excludes pull-request provenance.

### Continue reconciling current main

Checkout remains pinned to `ref: main`; the workflow does not check out the
event SHA. The upstream completion is only a wake-up signal. The
ancestry-based reconciler remains the authority for deciding whether any action
is necessary.

### Preserve active release work and fail closed on unknown state

Before reading successful deploys, reconciliation enumerates queued or running
`build-image.yml` and `deploy-prod.yml` runs on `main`. When a run's `head_sha`
contains the relevant commit by Git ancestry, it reports that the release chain
is already converging and does not dispatch. A stale active run does not
suppress a newer relevant commit. Failure to query either active or successful
run state, or to read release history, yields an explicit deferred result with
no corrective action. Deferred results have a distinct operator summary and
never claim production is current. Empty release-path history is also
indeterminate rather than evidence that production is current.

The main-build workflow keeps one group but makes cancellation conditional on
the new run being a push. New pushes may still supersede older work; a manual
reconcile dispatch cannot cancel an active push build. This is the structural
backstop for the narrow query-to-dispatch race.

### Explicitly deploy a reconcile-initiated image

When drift remains, reconciliation dispatches `build-image.yml` on `main`,
finds the newly created same-SHA workflow-dispatch run, and waits for it to
succeed. It then re-reads the repository's current `main` SHA. If `main`
advanced or that check fails, it does not deploy the older image. Otherwise it
checks for an active or successful same-SHA deploy and skips duplicate work
when one exists; only then does it dispatch `deploy-prod.yml` explicitly with
the built commit's 12-character immutable image tag. A failed normal
`workflow_run` deploy permits one explicit reconciliation retry. If a
same-SHA `workflow_dispatch` deploy has already failed, later wake-ups defer
before rebuilding, capping automated production mutation at one reconcile
retry per SHA while the deploy workflow's existing failure issue remains the
durable alarm. This uses the reconciler's existing `actions: write` permission
and adds no grant to the image builder.

### Keep the existing fixed reconcile concurrency group

The workflow retains `group: release-reconcile` and
`cancel-in-progress: false`. Under GitHub's single-pending default, a burst
leaves the active reconciliation running and coalesces later arrivals into at
most one pending run. A per-SHA group was rejected because it would permit
parallel dispatch races. A queued-all policy was rejected because every
reconciliation reads current `main`, making intermediate executions redundant.

### Section 14 concurrency/load proof

Focused tests load the exact YAML scripts. A harness executes the production
decision script against a temporary Git history and shared fake GitHub run
state. Under a 1,000-arrival one-running/one-replaceable-pending model, the
first run dispatches once and the coalesced last run observes the same relevant
build as active and defers without dispatching again. Complementary cases prove
a stale active SHA does not suppress recovery, failed GitHub/history queries do
not mutate release state, and deferred output cannot render as in sync.

The converge-script harness proves one image dispatch, one wait, and one
explicit deploy for unchanged main, while advanced main suppresses deploy. A
durable artifact records command, environment, date, result, and the
scheduler-model limitation. The exact scripts also run in a dedicated CI job
pinned to Python 3.12, matching the system interpreter used by the production
Ubuntu runner and preventing newer local parser behavior from hiding invalid
embedded programs.

## Risks / Trade-offs

- **A smoke completion can arrive while production is already current** →
  Reconciliation is idempotent and exits without dispatch when deploy ancestry
  already contains the relevant commit.
- **A `workflow_run` event can be delayed or suppressed** → The nominal
  15-minute schedule remains an independent best-effort backstop, but GitHub
  does not guarantee schedule latency and observed intervals are materially
  longer.
- **A newer pending run replaces an older pending run** → This is intentional;
  every run reconciles current `main`, so the newest wake-up subsumes older
  pending wake-ups.
- **The Docker-smoke and release path sets differ** → The event trigger reduces
  latency only for their intersection; the schedule still covers
  release-relevant paths with no smoke trigger.
- **Main advances while a reconcile build is dispatched, discovered, or runs**
  → Run discovery and the post-build main-SHA check treat the newer main as
  benign deferral and never deploy the older image.
- **A deploy repeatedly fails for the same SHA** — The normal chained attempt
  may receive one explicit reconcile retry. A failed workflow-dispatch attempt
  then defers all later same-SHA wake-ups before another build or deploy;
  deploy-prod's failure issue is the alarm and newer main resets the cap.
- **A newer push cancels the reconcile-initiated image build** → Cancellation
  is benign supersession and defers; non-cancellation build failures remain
  visible as errors.
- **Workflow metadata is not live production truth** → The existing spec
  caveat remains unchanged; this trigger only changes when the proxy is
  evaluated.

## Migration Plan

Land the spec, exact-script tests, proof artifact, and two workflow edits
atomically. Validate with pytest, actionlint, strict OpenSpec checks, and Opus 5
review. Rollback is a direct revert of the trigger/guard/converge changes and
the conditional build cancellation; schedule/manual behavior remains available
throughout.

## Open Questions

None.
