# Worktree purpose

Purpose: source-approval-gate
Provider: claude-code
Branch: claude/source-approval-gate
Base ref: origin/main
Issue/PR: the #1 second-user blocker from the 2026-08-28 Codex multi-user review
PLAN refs: authority / execution
Ship condition: source approval is dark by default and limited to an explicit universe
  allowlist; the founder's universe is allowlisted on the droplet so nothing regresses
Abandon condition: n/a
Pickup hints: this is a GATE, not a sandbox. The real fix is running user code out of
  process; until then the capability is limited rather than confined.
Memory refs: source-code-nodes-cannot-run (NOW STALE — source_channel added a path)
Related implications: docs/concerns/2026-07-02-no-os-engine-sandbox.md
Idea feed refs: (none)
