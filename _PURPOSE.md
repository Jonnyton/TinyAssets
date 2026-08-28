# Worktree purpose

Purpose: checkout-lease-build
Provider: claude-code
Branch: claude/checkout-lease-build
Base ref: claude/checkout-session-lease (stacked on #2616)
Issue/PR: resolves docs/concerns/2026-08-28-the-checkout-claim-is-not-tied-to-its-session.md
PLAN refs: billing
Ship condition: the three money races are closed and mutation-checked; live activation
  is no longer gated on this
Abandon condition: n/a
Pickup hints: start-over is DEFERRED by design — resuming the open session closes the
  lockout without adding a race around expiring a session the user may have just paid in
Memory refs: two-authorities-for-one-fact; never-game-the-gate-with-xfail
Related implications: stacked on #2616; retarget to main once that lands
Idea feed refs: (none)
