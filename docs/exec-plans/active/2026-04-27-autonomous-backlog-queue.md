# Autonomous Backlog Queue (Codex)

Date: 2026-04-27
Owner: codex-gpt5-desktop
Mode: continuous, claim-safe, docs/plan/spec heavy until core locks clear

## Goal

Keep shipping without waiting on prompts by repeatedly:

1. finding remaining ambiguity in promoted backlog items,
2. converting ambiguity into execution artifacts,
3. updating pipeline/inbox links so handoff is instant.

## Claude team memory guardrails applied

This queue follows the Claude Code team-memory constraints the host asked us to
reuse:

- Developer memory: do not touch `tinyassets/*` while #18/#23 and plugin mirrors
  are locked; build docs/specs/cards only.
- Navigator memory: run the irreducibility test before proposing any new
  primitive; prefer community/wiki composition unless a structural blocker is
  proven.
- Navigator memory: audit and status citations can be stale; verify artifact
  existence and current consumers before dispatching follow-up work.
- Dev-2 memory: verify examples against shipped artifacts and keep file
  boundaries concrete enough for `claim_check.py --check-files`.

## Queue

1. **User-sim verification bundle for promoted backlog items**
   Status: landed

2. **Methods-prose wiki rubric starter pack**
   Status: landed

3. **Trust-graduation query examples + dashboard sketch contract**
   Status: landed

4. **CONTRIBUTORS maintenance runbook (conflict + hygiene rules)**
   Status: landed

5. **Cross-algorithm parity wiki publication checklist**
   Status: landed

6. **Refresh queue with next ambiguity slices**
   Status: landed

7. **Continue autonomous burn-down (new slices discovered each pass)**
   Status: in-progress

8. **Runtime memory graph schema + contradiction policy lock**
   Status: landed

9. **Next discovery pass for remaining future-session ambiguity**
   Status: landed

10. **Hyperparameter importance execution hardening (fixtures + cards)**
    Status: landed

11. **Late-promoted artifact user-sim coverage**
    Status: blocked by Mission 10 `user-sim` claim
    Scope: add scripts for runtime memory graph, hyperparameter importance,
    trust observability, and agent-team scoping after `claimed:user` clears.

12. **Reference integrity pass for completed-note moves**
    Status: no-op verified 2026-05-01
    Scope: `docs/notes/completed/` does not exist yet; current references still
    point at live `docs/notes/` artifacts. Re-open only after a completed-note
    move actually lands.

13. **Continue autonomous burn-down (discover and land next slices)**
    Status: landed 2026-05-02
    Scope: current pass used Claude navigator memory guardrails, found a
    non-overlapping docs-only slice, moved landed Arc B plans to completed,
    refreshed Arc C prep now that Arc B is complete, and removed the temporary
    STATUS claim rows.

14. **Continue autonomous burn-down (next safe slice)**
    Status: waiting for new non-overlapping slice after 2026-05-02 pass
    Scope: remaining concrete work found in this pass is #18-blocked,
    Mission-10-blocked, loop-owned, host/admin-owned, date-gated, or historical
    audit context that should not be rewritten.

## Stop conditions

- A queue item touches files currently locked by in-flight rows.
- New P0/P1 concern appears requiring reroute.
- Host requests priority override.
