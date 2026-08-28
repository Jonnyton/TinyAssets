# Worktree purpose

Purpose: billing-refusal-status
Provider: claude-code
Branch: claude/billing-refusal-status
Base ref: origin/main
Issue/PR: follow-up to #2601 (billing subscribe/cancel); found by the live user-path test
PLAN refs: billing / onboarding app surface
Ship condition: checkout refusals answer 4xx and carry their own reason; a resolved
  checkout releases its claim so a cancel-then-resubscribe is not locked out for 15
  minutes; both proven live through the webapp after deploy
Abandon condition: n/a — both defects were observed in production
Pickup hints: docs/concerns/2026-08-28-worker-swallows-every-origin-5xx-body.md holds
  the half NOT fixed here (the edge Worker still discards any origin 5xx body)
Memory refs: syntax-check-is-not-reachability (JS scope, checked: all new symbols at
  indent 2 = script scope); live-test-finds-what-tests-cannot
Related implications: docs/concerns/2026-08-28-worker-swallows-every-origin-5xx-body.md
Idea feed refs: (none)
