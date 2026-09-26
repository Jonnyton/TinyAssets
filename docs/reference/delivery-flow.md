# Delivery flow — WIP discipline

Canonical procedure for OpenSpec change admission. `AGENTS.md`
§ *Spec-driven development* keeps the invariants and points here.

---

- **Delta-first, never vision conversion.** One intent, one owner, one branch, one
  PR, explicit acceptance, ≤12 task checkboxes. Vision belongs in PLAN.md or a
  design note; incidental findings go to `ideas/INBOX.md`.
- **One delivery change per session identity.** Before claiming or building a
  scaffolded change: `python scripts/openspec_flow.py check-change <name>
  --provider <session-specific-provider>`. Minting a suffix to evade the limit is
  a review violation.
- **Finish or archive, before starting.** At dispatch:
  `python scripts/openspec_flow.py audit` — prefer complete-but-unarchived, then
  the smallest unblocked in-flight slice. A change idle 14 days is not in flight;
  archive it and re-propose when it is real. Archiving is free and reversible,
  because git holds it.
- **The inventory is a WIP queue, not an archive of ambitions.** When it exceeds
  what active sessions are building, triage it (premise-verify, then archive dead
  or landed changes) before proposing new ones. Pick concrete slices.
- **Reviews pipeline; never idle on one.** Build slice A, dispatch its review in
  the background, pick up the next lane, fold the verdict in when it returns. Only
  a genuine external blocker — a host-only secret or decision, a broken harness, an
  unresolved verdict on the lane you would advance into — stops a lane; take a
  different lane instead of idling.
