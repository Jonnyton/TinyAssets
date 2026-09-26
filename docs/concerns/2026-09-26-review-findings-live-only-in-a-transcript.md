# 25 open concerns keep their load-bearing finding only in a review transcript

**Filed:** 2026-09-26
**Severity:** P2
**Found by:** measuring `docs/reviews/` during the rulebook recut follow-up, before
sweeping it.

## What is true

`docs/reviews/` held 241 transcripts. 152 were cited by nothing a reader treats as
current and are deleted (they stay reachable in git history). **89 are cited**, so
they stay — but a citation is the problem, not the resolution: for 25 of them the
citing surface is an OPEN concern that records the finding by POINTING at the
transcript rather than stating it. The founder's process cut says review
transcripts do not live in the repo, so those 25 concerns are what stops
`docs/reviews/` from going away entirely.

Measured over 3,713 current-surface files (filename or stem match, so the doubtful
case counted as cited): 84 citations come from `openspec/changes/`, 26 from
`docs/concerns/`, plus `docs/host-actions.md`, two `tinyassets/api/` modules, two
tests and the packaging mirror.

The 25 with an open concern citing them, by concern:

- `2026-08-27-pending-request-mute-bypass`, `2026-08-27-served-provider-authority-is-converse-only` → `2026-08-27-codex-paste-deposit-review.md`
- `2026-08-29-background-loop-activation-is-fleet-era` → `2026-08-29-codex-background-loop-shape.md`
- `2026-08-29-subject-ids-scattered-across-stores` → `2026-08-29-codex-subject-migration-boundary.md`
- `2026-08-31-the-forge-table-is-platform-knowledge...` → `2026-08-31-codex-labelled-credential-fields.md`
- `2026-09-04-provider-compatibility-is-not-open` → `2026-09-05-provider-native-model-defaults-claude.md`, `2026-09-05-provider-portability-exploration-claude.md`
- `2026-09-08-workspace-hourly-cap-stalls-light-use` → `2026-09-08-attributable-storage-proof.md`, `2026-09-08-workspace-resource-policy-proof.md`, `2026-09-08-workspace-usage-diagnosis-claude.md`
- `2026-09-08-request-rail-refresh-erases-drafts` → `2026-09-08-request-rail-refresh-shape-claude.md`
- `2026-09-08-served-tool-capability-parity-gaps` → `2026-09-08-workflow-checklist-live-acceptance.md`
- `2026-08-31-workspace-admission-claims-are-narrower-than-stated` → `2026-09-08-workspace-admission-exact-head-claude.md`
- `2026-09-09-cross-user-deliverable-connections` → `2026-09-09-cross-user-delivery-existing-boundaries.md`, `2026-09-09-cross-user-node-shape-review.md`
- `2026-08-31-cancel-is-advisory-and-the-timeout-is-doing-its-job` → `2026-09-09-workflow-control-gaps-proof.md`, `2026-09-21-served-node-policy-deployment.md`
- `2026-09-14-peer-review-final-output-omits-deliverable` → `2026-09-14-model-setup-tools-shape-fable.md`
- `2026-09-15-automatic-source-health-followups` → `2026-09-15-automatic-source-recovery.md`
- `2026-09-08-scheduled-uptime-probes-remain-red` → `2026-09-19-hostless-monitor-contract-diagnosis.md`, `2026-09-19-monitor-classification-deployed-proof.md`, `2026-09-19-natural-scheduled-classification-proof.md`
- `2026-09-21-provider-tool-wait-observation` → `2026-09-21-provider-tool-wait-deployment.md`
- `2026-09-21-effect-edit-organic-use-watch` → `2026-09-21-served-effect-edit-deployment.md`
- `2026-09-22-owned-run-activity-clean-use` → `2026-09-22-owned-run-activity-acceptance.md`
- `2026-09-23-node-edit-organic-use-watch` → `2026-09-23-node-edit-parity-lead-review.md`

## Why it was not done in the sweep

Moving a finding means reading the transcript, deciding which claim is
load-bearing, and rewriting another lane's open concern. Twenty-five of those,
folded into a PR that also cut a doc and a skill, is where evidence gets stranded
by a hurried paraphrase — and the project's own rule is that a security or
correctness finding is never paraphrased forward carelessly.

## Fix

Per concern: read its cited transcript, state the finding IN the concern with its
date and the commit or sha it was found against, then delete the transcript and
lower the `docs/reviews/*` pin in `scripts/check_context_budget.py` by what was
removed. When the last one is done, the aggregate reaches zero and the directory
can be added to `FORBIDDEN` beside the two deleted procedure docs.

The 64 remaining cited transcripts are cited by `openspec/changes/` and code
comments; those citations can be retargeted or dropped with the same discipline
once the concern-backed ones are clear.
