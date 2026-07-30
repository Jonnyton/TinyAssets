# Cloud-drain current-main prerequisite audit

Freshness: 2026-07-29 America/Los_Angeles. Initially audited
`origin/main@eff97a1e5734bc7166e0381069a713ede0a06743`, then rebased and
reconciled against
`origin/main@71cf1a82aa3c2b86bd30ad6fcabd61212fa19bbb`, after production
recovery run
[`30515117371`](https://github.com/Jonnyton/TinyAssets/actions/runs/30515117371).
The canonical `https://tinyassets.io/mcp` returned HTTP 200 after that
recovery. This artifact is diagnostic current-state evidence, not a new design
owner.

## Verdict

The cloud drain is not blocked on a missing cloud host, daemon supervisor,
durable scheduler, Branch snapshot mechanism, or GitHub PR effector. Those
seams exist. It is blocked on joining them under one requester-owned,
server-derived authority chain and on one production credential-rename gap.

Runtime activation must stop at the unresolved PLAN decision between the
epoch-1 file-lock claimer and epoch-2 transactional claiming. Safe prerequisite
repairs, inventories, typed models, dark stores, and tests may continue.

The shortest path is:

1. restore the already-existing GitHub PR capability to production by
   validating the one pre-rename repository secret and narrowing it to the
   exact `Jonnyton/TinyAssets` destination before installation;
2. complete the background authority inventory/interfaces/types/store protocol
   and logical keys in dark mode;
3. approve epoch-2 transactional claiming as the single live mutation
   authority, retaining epoch 1 only as a bounded compatibility drain;
4. bind Jonathan's private main-universe activation to a universe-scoped
   provider authority, immutable Branch version, exact repository grant, and
   one server-owned attempt;
5. activate single-flight PR-only execution, then prove phone control and the
   required 24-hour computer-off run.

## Current-main matrix

| Prerequisite | Current-main evidence | Current gap / owner | Disposition |
|---|---|---|---|
| Cloud compute and supervision | `deploy/compose.yml` runs supervised Codex and Claude cloud workers; `tinyassets/cloud_worker.py` publishes health and restarts work. | Existing workers consume the legacy file queue; cloud-worker epoch-2 consumption is disabled. | Reuse; do not build another cloud runner. |
| Persisted trigger and continuation | `tinyassets/scheduler.py` persists schedules/subscriptions in the universe database, catches up after restart, and exposes pause/unpause. | `tinyassets/api/runtime_ops.py` accepts caller-supplied `owner_actor`, and list calls can omit it. Synthetic scheduler actors are not request-derived execution authority. Owned by `harden-background-branch-execution-authority` (0/77 tasks). | Reuse persistence; replace authority derivation before activation. |
| Collision-safe task reservation | `tinyassets/branch_tasks_v2.py` and `tinyassets/storage/request_admissions.py` implement transactional admission, leases, recovery, worker descriptors, and integrity checks. | `EPOCH2_QUEUE_CONSUMER_READY = False`; the adapter correctly states that a queue claim is only a scheduling reservation, not execution/provider authority. PLAN still has two candidate live mutation owners. | PLAN decision required before live integration. |
| Background Branch authority | Reviewed change `harden-background-branch-execution-authority` landed in PR #1805. Its tasks 1.1-1.5 explicitly permit inventory/model/dark work before the PLAN gate. | No `BackgroundBranchBinding`, `BackgroundBranchAttempt`, authority store, or server-derived attempt claim is implemented (0/77 tasks). | First authority implementation lane after the deploy repair. |
| Background provider authority | `tinyassets/credential_vault.py` resolves universe-scoped Codex/Claude subscription material and per-universe provider environment overlays. Reviewed target `harden-background-provider-execution-authority` landed in PR #1803. | Target implementation is 0/33 tasks. Production has Claude OAuth, but recovery evidence showed no Codex bundle and no proof that the shared Claude token is bound as Jonathan-universe authority. Ambient/shared auth cannot substitute for a user binding. | Implement exact universe/provider binding and fail-closed launch receipt; no maintainer or market fallback. |
| Tier-1 provider setup | `tinyassets/api/universe.py` has internal engine configuration and the vault supports typed records. | `activate-requester-host-engines` does not exist. Current setup asks the host and the legacy path can carry raw secret material through chat, contrary to the approved phone-only design. `retire-mcp-provider-secret-deposit` is 5/42 complete. | Cloud MVP may bind an existing Jonathan-owned subscription server-side; phone-safe add/rotate remains required before general availability. |
| Branch access | `harden-branch-access-authority` has 31 completed and 10 open tasks; authenticated subject helpers and several read/mutation protections have landed. | Run execution and adjacent surfaces still have separate pending authority owners. | Use only a private Jonathan-owned Branch and the guarded path; keep general activation gated. |
| Immutable Branch versions | `tinyassets/branch_versions.py` provides write-once snapshots and version lookup/listing. | `tinyassets/api/evaluation.py` accepts caller-supplied `publisher` and reads lack the target owner gate. The named `harden-branch-evaluation-access-authority` change does not yet exist. | Add server-derived owner/version access before phone evolution and activation. |
| GitHub PR effect and receipts | `tinyassets/effectors/github_pr.py` enforces soul authority, exact destination secret resolution, consent, atomic reservation, remote reconciliation, and PR materialization. `tinyassets/storage/external_write_receipts.py` persists reserve/finalize/reconcile states. | Repository secret inventory on 2026-07-29 showed only the pre-rename `WORKFLOW_GITHUB_PR_CAPABILITIES` source. Deploy did not consume it, and runtime resolution prefers canonical `TINYASSETS_GITHUB_PUSH_CAPABILITIES` over the legacy `..._PR_...` key. Recovery run 30515117371 skipped the deploy job, so it is service-health evidence, not secret-mismatch evidence. Consent's optional `granted_by` is also caller-influenced. | Immediate collision-free repair: validate the single encrypted source, install only `{Jonnyton/TinyAssets: token}` under the canonical push key, delete the legacy runtime key, and revoke both keys on absence/invalid input. Then bind consent/authority to the authenticated owner. |
| Canonical phone controls | The existing `extensions` handle already advertises schedule/list/pause/unpause, Branch version operations, consent operations, and authoring inspect/edit/test/publish. | Their underlying authority is not consistently server-derived, and no activation CAS/health projection joins them. | Reuse canonical handles; add no new top-level MCP action. |
| Single-active tray/cloud cutover | Approved cloud-drain design defines one `(universe_id, automation_id)` CAS record with epoch, executor, version, lease, and state. | No activation record/store exists. The local tray must remain the only active drain until cloud activation is fenced and proven. | Implement after the authority/store decision; never run tray and cloud concurrently. |

## Exact collision and dependency result

- No current `STATUS.md` claim overlaps the deploy repair files
  `.github/workflows/deploy-prod.yml` and
  `tests/test_deploy_prod_workflow.py`.
- The broad background-authority row overlaps many active platform seams and
  remains dependency-blocked. It must be executed as narrow task/file slices,
  starting with its isolated new model/protocol module and focused tests.
- Draft PR #1877 duplicated the merged cloud-drain change and was closed as
  superseded by PR #1893.
- The active contradictory design choice is explicit, not inferred:
  `STATUS.md` already holds the host decision for one live scheduling/task
  claim authority, while `deploy/compose.yml` describes epoch-1 file locking
  and `branch_tasks_v2.py` provides the inactive transactional successor.

## Recommendation on the PLAN gate

Choose epoch-2 transactional claiming as the single live scheduling/task-claim
mutation authority. It already provides the database transaction boundary,
conditional claim, lease generation, worker descriptor, recovery, and
integrity seams required by the approved cloud-drain design. Treat epoch-1
file-lock claiming only as a bounded compatibility drain during migration;
never allow both to admit or mutate the same active automation.

This recommendation requires explicit host approval before `PLAN.md` changes
or production persistence integration.

## Delivery estimate from this audit

- Production GitHub capability repair: less than one focused day, including
  tests, review, merge, deploy, and a non-mutating capability canary.
- First inactive single-flight cloud slice: 3-6 additional focused days if the
  PLAN decision is approved promptly and no independent review blocker is
  found.
- “Done”: 5-8 calendar days from this audit because acceptance itself includes
  a mandatory 24-hour computer-off interval, a worker restart, rendered
  phone-chatbot control/evolution proof, and an organic-use check. Use 10 days
  as the contingency bound.
