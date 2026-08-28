# Worktree purpose

Purpose: universe-create-gate
Provider: claude-code
Branch: claude/universe-create-gate
Base ref: origin/main
Issue/PR: founder rule 2026-08-28 — no universe may exist unbound to a WorkOS user
PLAN refs: authority / billing
Ship condition: signup gets one universe free; additional ones require a paid tier;
  anonymous and unreadable-state both fail closed
Abandon condition: n/a
Pickup hints: gated at the PUBLIC surface, not in _action_create_universe — that
  primitive has 23 legitimate internal callers with no authenticated subject
Memory refs: every-user-is-founder-of-own-universe
Related implications: gives the paid tier its first concrete capability
Idea feed refs: (none)
