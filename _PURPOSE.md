# Worktree purpose

Purpose: pending-cancellation-visible
Provider: claude-code
Branch: claude/pending-cancellation-visible
Base ref: claude/billing-lifecycle-correction (stacked; rebase to main once #2610 lands)
Issue/PR: resolves docs/concerns/2026-08-28-a-cancelled-subscription-looks-uncancelled.md
PLAN refs: billing / onboarding app surface
Ship condition: after cancelling, a reload shows "Paid · ends <date>" and clicking it
  does not offer a second cancellation; proven live through the webapp
Abandon condition: n/a
Pickup hints: ends_at is DISPLAY ONLY — get_tier remains the entitlement authority
Memory refs: syntax-check-is-not-reachability (all new JS at indent 2 = script scope);
  never-game-the-gate-with-xfail
Related implications: stacked on #2610; do not merge before it
Idea feed refs: (none)
