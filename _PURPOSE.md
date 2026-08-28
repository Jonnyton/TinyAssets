# Worktree purpose

Purpose: effect-quota-dark
Provider: claude-code
Branch: claude/effect-quota-dark
Base ref: origin/main
Issue/PR: extracts the metering half of #2598; addresses
  docs/concerns/2026-08-28-the-paid-tier-buys-nothing.md
PLAN refs: metering / tiers
Ship condition: lands DARK (TINYASSETS_USAGE_ENFORCEMENT unset) with no behaviour
  change provable by test; the flip is a founder decision on the free allowance
Abandon condition: n/a
Pickup hints: the tier authority is subscription_state.get_tier, NOT the copy that
  used to live in usage_ledger — that copy is deleted here
Memory refs: no-review-loops-on-dark-mvp; silent-failure-dispatch-and-tests
Related implications: docs/host-actions.md "Decide what the $20 actually buys"
Idea feed refs: (none)
