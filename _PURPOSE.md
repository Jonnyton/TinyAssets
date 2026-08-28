# Worktree purpose

Purpose: session-credential-source
Provider: claude-code
Branch: claude/session-credential-source
Base ref: origin/main
Issue/PR: corrects #2624, which did NOT close the fixation Codex re-found
PLAN refs: auth / onboarding
Ship condition: handle reuse is licensed by the credential source; the bearer handle
  is never a filename
Abandon condition: n/a
Pickup hints: the #1 multi-user blocker is NOT this — it is in-process source
  execution (graph_compiler exec with os.environ reachable)
Memory refs: silent-failure-dispatch-and-tests
Related implications: docs/concerns/2026-08-23-byo-llm-refresh-token-store.md
Idea feed refs: (none)
