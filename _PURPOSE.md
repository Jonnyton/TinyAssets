# Worktree purpose

Purpose: branch-run-read-check
Provider: claude-code
Branch: claude/branch-run-read-check
Base ref: origin/main
Issue/PR: blocker #3 from the 2026-08-28 Codex multi-user review
PLAN refs: authority / runs
Ship condition: running a branch requires read access to it; an unreadable branch is
  reported as absent
Abandon condition: n/a
Pickup hints: the permissive `_resolve_branch_id` is unchanged on purpose — passing an
  unresolvable selector through is right for NAMING, wrong for LOADING
Memory refs: permissive-helper-used-as-restrictive
Related implications: #2629 (source approval gate), #2627 (session credential source)
Idea feed refs: (none)
