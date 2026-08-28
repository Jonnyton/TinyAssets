# Worktree purpose

Purpose: golive-check-accuracy
Provider: claude-code
Branch: claude/golive-check-accuracy
Base ref: origin/main
Issue/PR: fixes a misleading message in scripts/stripe_go_live.py; files the
  assigned-queue error loop
PLAN refs: billing
Ship condition: the delivery check names the path it read and says when the answer is
  "not visible from here" rather than "never happened"
Abandon condition: n/a
Pickup hints: the script is NOT in the deployed image — it runs from a checkout
Memory refs: unavailable-often-means-unconfigured
Related implications: docs/concerns/2026-08-28-assigned-queue-consumer-hot-error-loop.md
Idea feed refs: (none)
