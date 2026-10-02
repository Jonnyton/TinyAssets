## 0. Gate

- [x] 0.1 Q1 decided by the lead (2026-10-02): per-command-center ownership plus a platform owner. openshell-spike amends #4263 D11.
- [ ] 0.2 Codex shape refute: round 1 was ADAPT (13 findings, design revised). Rounds 2-3 must reach SHIP-TO-BUILD before B1; past round 3 it escalates to the lead.

## 1. B0 + B1: keyed lease, fences, generation, reconcile

- [ ] 1.1 B0 (separate small PR, deployed first): name the columns in `AgentTurnJournal` inserts, so an added column cannot break a revert.
- [ ] 1.2 Keyed lease store behind cp-scheduler's seam: flock-proven death, UNKNOWN blocks, liveness retention, the proof hash, and the restore tool with its offline high-water manifest (D1/D2).
- [ ] 1.3 `owner_fence` per key, `fenced` vs `advance_fence`, migrations only under the host lock, and the `OWNER_STORES` registry with its inventory test (D3).
- [ ] 1.4 `agent_turns.owner_generation`; reconcile per key at `< G`, after acquisition; the status projection at `== G`; standby-start and restore-order tests.

## 2. B2: whole-execution admission

- [ ] 2.1 Per-store `admission_open` on the fence row; `exec_claims` with liveness-keyed open/closed; continuations through `parent_exec_id`; op-id attach/conflict; a release only after a re-verified all-closed idle test (B2-1..B2-3, D6a).
- [ ] 2.2 Read-then-acknowledge steering and carryover (D9), and the explicit learned-cursor range (D8). Add the invariant tests, including tonight's mid-turn loss.

## 3. C1: frontend/owner split

- [ ] 3.1 Process split, the local socket (peer creds plus a per-key-generation HMAC), the full Identity envelope with owner-side tier and access resolution, and owner-side capability minting (D6). Add the module classifier test.
- [ ] 3.2 Pending journal with states, op ids, the abandonment facts, verified projection, and the deletion exclusion (D7).

## 4. C2: handover

- [ ] 4.1 `deploy-prod`: per-key idle moves, the frontend-only path (#4272), the operator force path, and the metrics (D4/D10).
- [ ] 4.2 Proof: a scripted deploy loop with a request-level error probe (0 failed, 0 duplicate effects, 0 interrupted), the force path's honest notice, then the founder's long-turn live proof. Sync the specs and archive.
