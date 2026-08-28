# Worktree purpose

Purpose: status-storage-cache
Provider: claude-code
Branch: claude/status-storage-cache
Base ref: origin/main
Issue/PR: capacity work for the 1000-user goal (2026-08-28)
PLAN refs: capacity / storage
Ship condition: the storage walk leaves the per-request path; status reads stop being
  O(files on disk); snapshot stays correct and per-root
Abandon condition: n/a
Pickup hints: measured on the live box — 19% of a status read today, and the ONLY part
  of the request whose cost grows with the platform. The 19% is not the reason.
Memory refs: silent-failure-dispatch-and-tests
Related implications: 1 vCPU box saturates at ~13 req/s; this is one lever of several
Idea feed refs: (none)
