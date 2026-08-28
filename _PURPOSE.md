# Worktree purpose

Purpose: refresh-session-hardening
Provider: claude-code
Branch: claude/refresh-session-hardening
Base ref: origin/main
Issue/PR: closes the session-fixation half of
  docs/concerns/2026-08-23-byo-llm-refresh-token-store.md
PLAN refs: auth / onboarding
Ship condition: a new sign-in never adopts a caller-supplied handle; token files are
  0600 and the store directory 0700
Abandon condition: n/a — this blocks a second real user
Pickup hints: the encryption-at-rest half is NOT here; a Codex review is open on
  whether env-held-key encryption buys anything against an in-process reader
Memory refs: never-infer-identity-from-adjacent-tables
Related implications: the per-universe LLM credential vault is plaintext too
Idea feed refs: (none)
