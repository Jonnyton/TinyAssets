# Worktree purpose

Purpose: checkout-session-lease
Provider: claude-code
Branch: claude/checkout-session-lease
Base ref: origin/main
Issue/PR: toward "ready to activate Stripe for real users"
PLAN refs: billing
Ship condition: `scripts/stripe_go_live.py --check` names every remaining blocker and
  none of them is ours; no cross-mode entitlement is possible
Abandon condition: n/a
Pickup hints: the checkout-lease redesign (the double-billing races) is NOT in this
  commit — it is awaiting a Codex design verdict and lands separately
Memory refs: automerge-can-land-a-stale-head (every commit independently safe)
Related implications: docs/concerns/2026-08-28-the-checkout-claim-is-not-tied-to-its-session.md
Idea feed refs: (none)
