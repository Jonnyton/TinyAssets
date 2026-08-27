# Purpose: assigned consumer = the live worker (activation + visible refusal)
Lane source: STATUS.md Work row "Background executor"; OpenSpec change execute-assigned-queue-consumer § 5.
Live finding 2026-08-25 19:14Z: TINYASSETS_ASSIGNED_QUEUE_CONSUMER=1 applied on prod e17d8747; the one pending
task bt2_acab8c31 stayed pending/no_live_compatible_worker; refusal invisible; resume cannot activate.
Branch: claude/consumer-activation-visibility  Worktree: C:/Users/Jonathan/Projects/wf-consumer-activation
Review gate: Codex-as-builder; Claude reviews shape; no serial review loop (founder rule 2026-08-25).
Publish: PR to main (auto-merge), flag already live -> live-test via get_status + user-surface resume.
Memory refs: background-executor-carrier-path-implemented, no-review-loops-on-dark-mvp.
