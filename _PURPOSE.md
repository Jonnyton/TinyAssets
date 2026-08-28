# Worktree purpose

Purpose: webhook-delivery-proof
Provider: claude-code
Branch: claude/webhook-delivery-proof
Base ref: origin/main
Issue/PR: closes the one gap stripe_go_live.py admitted it could only warn about
PLAN refs: billing
Ship condition: `--check` refuses when no webhook signature has ever verified in the
  current Stripe mode
Abandon condition: n/a
Pickup hints: the marker is written BEFORE the livemode check on purpose — a mode
  mismatch is refused, but the signature verifying is the fact being proven
Memory refs: silent-failure-dispatch-and-tests
Related implications: docs/host-actions.md step 4
Idea feed refs: (none)
