# Delivery flow — WIP discipline

Canonical procedure for OpenSpec change admission and review pipelining.
`AGENTS.md` § *Spec-driven development* keeps the invariants and points here.
Reviewed 2026-08-11; review-pipelining rule added by the host 2026-08-24.

---

- **Delta-first, never vision conversion.** One intent, one owner, one branch,
  one PR, explicit acceptance, ≤12 task checkboxes. Vision belongs in
  PLAN/design docs; park incidental findings in the idea feed.
- **One delivery change per exact session identity.** Before claiming/building
  a scaffolded change: `python scripts/openspec_flow.py check-change <name>
  --provider <session-specific-provider>`. Minting a new provider suffix to
  evade the limit is a review violation. A P0/security exception must name
  the exception and the WIP it displaces.
- **Finish before starting.** At dispatch/triage: `python
  scripts/openspec_flow.py audit` — prefer complete-but-unarchived, then
  smallest unblocked in-flight, then smallest P0/uptime dependency-removal
  slice, before admitting new work.
- **Backlog is bounded.** The live `openspec/changes/` inventory is a WIP
  queue, not an archive of ambitions: when it exceeds what active sessions are
  actually building, triage it (premise-verify → archive dead/landed changes)
  before proposing new ones. Legacy oversized changes are grandfathered for
  visibility, not blessed — pick concrete slices, don't fan out child changes.
- **Reviews pipeline; never idle on one [all sessions, host 2026-08-24].** A
  dispatched cross-family/peer review (or any background agent) runs on the
  peer's budget and re-invokes you when it returns, so it gates LANDING
  (merge/deploy/flip-on), NOT your forward progress. The standard build pipeline
  for every session: build slice A → dispatch its review in the **background**
  (`peer_agent.py` / `codex_review.py`, `run_in_background`) → **immediately pick
  up the next lane** → fold each verdict in when it lands (fix findings →
  re-review → land). A pending review is a wait state, not a stopping point: do
  NOT stop, sit idle, or ask the host "should I wait?" while one runs. This
  complements *Finish before starting* — the review IS part of finishing the
  slice, so you advance the pipeline while it runs rather than blocking on it.
  (Only genuine external blockers — a host-only secret/decision, a broken
  harness, an unresolved review verdict on THE lane you'd advance into — stop a
  lane; pick a different lane instead of idling.)
