## MODIFIED Requirements

### Requirement: Scheduled release reconciliation uses deploy-run ancestry as its production proxy
The system SHALL declare release reconciliation with a `*/15 * * * *` schedule, manual dispatch, and a completed `workflow_run` trigger for `Docker build smoke` on `main`. The reconciliation job SHALL accept schedule and manual reconcile events, but it SHALL accept a `workflow_run` event only when the triggering run concluded successfully, its `head_branch` is `main`, its head repository is the current repository, and its upstream event is `push` or `workflow_dispatch`. The workflow SHALL retain a `release-reconcile` concurrency group whose `cancel-in-progress` value is false. That setting SHALL preserve an already running job and, under GitHub's default single-pending policy, SHALL coalesce a burst into at most one pending same-group run whose newer arrival can replace an older pending run; neither the declared triggers nor the group SHALL promise actual dispatch latency or one execution per event or schedule tick.

When executed, reconciliation SHALL check out current `main`, derive the newest release-relevant commit on `main` from the push-path list in `build-image.yml`, and fall back to current `HEAD` when that list cannot be read. A command failure while reading release history SHALL produce an explicit deferred result rather than being treated as empty history or in-sync evidence. Before dispatching, reconciliation SHALL enumerate queued or running main-branch `build-image.yml` and `deploy-prod.yml` runs. If any active run's `head_sha` contains the release-relevant commit by Git ancestry, it SHALL report that release work is already converging; an older active SHA that does not contain the relevant commit SHALL NOT suppress recovery. A failure to read active-run or successful-deploy state SHALL make no corrective dispatch and SHALL defer to a later wake-up. Deferred results SHALL render as no release decision and SHALL NOT render as production being current with `main`.

Reconciliation SHALL enumerate successful `Deploy prod` workflow runs filtered to `main`; when any returned run `head_sha` contains the release-relevant commit by Git ancestry it SHALL report in sync. Otherwise it SHALL dispatch `build-image.yml` on `main`, identify and wait for the resulting same-SHA workflow-dispatch run, and explicitly dispatch `deploy-prod.yml` with the built commit's 12-character immutable image tag only if current repository `main` still equals the built SHA and no active or successful same-SHA deploy already exists. A reconcile-initiated manual image build SHALL NOT cancel an active push image build; a newer push MAY still supersede older image work. Main advancement before run discovery or after build completion, and cancellation caused by newer main work, SHALL defer without stale deployment; other image-build failures SHALL remain visible as errors. Docker-smoke success SHALL be only a wake-up signal and SHALL NOT replace the deploy-ancestry decision. This current proxy SHALL NOT claim to read the live release receipt or prove that production still serves the returned deploy-run SHA.

#### Scenario: Trusted main Docker smoke wakes reconciliation
- **WHEN** own-repository `Docker build smoke` completes successfully for a `push` or `workflow_dispatch` event with `head_branch` equal to `main`
- **THEN** the reconciliation job is eligible and evaluates current `main`

#### Scenario: Pull-request, fork, failed, or non-main smoke cannot run the privileged job
- **WHEN** `Docker build smoke` completes for a pull request, a different head repository, a branch other than `main`, or a conclusion other than success
- **THEN** the reconciliation job does not execute

#### Scenario: Schedule remains a best-effort event-independent backstop
- **WHEN** no qualifying Docker-smoke completion wakes reconciliation
- **THEN** the `*/15 * * * *` schedule and manual dispatch remain declared
- **AND** the declaration makes no guarantee that GitHub starts a run within 15 minutes

#### Scenario: Current active release work suppresses duplicate dispatch
- **WHEN** a queued or running main image-build or deploy run's `head_sha` contains the newest release-relevant commit
- **THEN** reconciliation reports that release work is already converging and does not dispatch another build

#### Scenario: Stale active release work does not suppress recovery
- **WHEN** queued or running release work has a `head_sha` that does not contain the newest release-relevant commit
- **THEN** reconciliation continues its deploy-ancestry decision and may dispatch recovery for current `main`

#### Scenario: Unknown GitHub run state fails closed
- **WHEN** the active-run query or successful-deploy query fails
- **THEN** reconciliation records that no decision was made and performs no corrective dispatch
- **AND** the operator summary does not claim production is current

#### Scenario: Release-history command failure is not empty history
- **WHEN** `git rev-parse` or `git log` fails while deriving the release-relevant commit
- **THEN** reconciliation emits a deferred no-decision result with a warning
- **AND** does not report empty release-path history or production in sync

#### Scenario: Reconcile-initiated build reaches explicit deploy
- **WHEN** no active or successful release run contains the relevant commit, the requested main image build succeeds, and repository `main` still equals the built SHA
- **THEN** reconciliation explicitly dispatches `deploy-prod.yml` with the built SHA's 12-character image tag

#### Scenario: Existing same-SHA deploy suppresses duplicate dispatch
- **WHEN** an active or successful deploy already exists for the built main SHA
- **THEN** reconciliation performs no duplicate explicit deploy dispatch

#### Scenario: Main advancement suppresses stale image deployment
- **WHEN** repository `main` advances while a reconcile-initiated image build runs
- **THEN** reconciliation does not dispatch deployment of the older image and leaves the newer main for a later release evaluation

#### Scenario: Newer push supersedes recovery build without false alarm
- **WHEN** a newer push cancels the reconcile-initiated image build
- **THEN** reconciliation records benign supersession and performs no stale deployment
- **AND** a failed, timed-out, or otherwise non-successful build that was not cancelled remains a visible error

#### Scenario: Manual recovery build preserves active push build
- **WHEN** a reconcile-initiated manual image build enters the same concurrency group as an active push image build
- **THEN** the manual run does not cancel the active push run

#### Scenario: Smoke stampede coalesces without duplicate corrective dispatch
- **WHEN** one reconciliation is running and 999 same-group wake-ups arrive while its current-main image build becomes active
- **THEN** the running reconciliation remains active, the default concurrency policy retains at most the latest pending reconciliation, and the coalesced pending run observes the active build and performs no second corrective dispatch

#### Scenario: Later successful deploy contains the relevant commit
- **WHEN** a successful main-branch deploy run's `head_sha` is a descendant of the newest release-relevant commit
- **THEN** reconciliation reports no action even when later docs-only commits exist on `main`

#### Scenario: Empty release-path history is a no-op
- **WHEN** path extraction succeeds but no commit touching a release path is found
- **THEN** reconciliation reports no release-relevant history and does not dispatch

#### Scenario: Deploy-run metadata can be a false-green proxy
- **WHEN** a successful deploy run's `head_sha` contains the relevant commit but its published live receipt or current production state differs
- **THEN** this reconciler can still report in sync because it does not read either live source
