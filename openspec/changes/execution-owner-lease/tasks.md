## 0. Gate

- [ ] 0.1 Get a cross-family (Codex) refute of this proposal and design, covering D1/D3/D5/D6/D7 and Q1. Get the lead's and openshell-spike's decision on Q1 (single owner or per-universe ownership) before B1.

## 1. Slice B1: lease, generation, fence, reconcile (one PR)

- [ ] 1.1 Build the lease store behind cp-scheduler's `OwnerLease` seam: acquisition proven by flock death, the restore-safe generation, the proof hash and `verify_lease_proof`. The current single process acquires it at boot.
- [ ] 1.2 Add `agent_turns.owner_generation` (migration plus backfill to 1). Reconcile is gated on the lease and runs at `< G`, and the status projection uses `== G`. Delete BootTurns' created-at disjunct. Add the standby-start and restore-order tests.
- [ ] 1.3 Inventory every owner database, add `owner_fence` and the `fenced()` writer, and turn the inventory into a test: every writer is fenced or listed with a reason.

## 2. Slice B2: barrier and admission (one PR)

- [ ] 2.1 Add the activation barrier: advance the fences, ack each effect executor (in-process broker stream cancellation at an older G, plus a `boxhostd` stub), reconcile, then open. Inventory the effect paths (Q3).
- [ ] 2.2 Make admission and the journal row one fenced transaction, closed by a fenced write. Test that no request is admitted without a row.
- [ ] 2.3 Make steering and carryover read-then-acknowledge after durable persistence (D9). Add the invariant test that covers the live 2026-10-02 mid-turn loss.

## 3. Slice C1: frontend/owner split (one PR)

- [ ] 3.1 Split the frontend and owner processes, with the local socket (peer creds plus a per-generation HMAC) and owner-side capability minting from the asserted identity (D6). Split the modules and add the classifier test.
- [ ] 3.2 Add the frontend pending-request journal (persist first), the live-request queue with its bound, and the owner's notice-back drain (D7). Account deletion sweeps by owner.

## 4. Slice C2: handover deploy path (one PR)

- [ ] 4.1 Give `deploy-prod` a frontend-only path (deploy-incident's #4272 switch) and an owner-handover path (D8). Phase 1's wait becomes the owner drain. Publish the metrics.
- [ ] 4.2 Prove it: a scripted deploy loop with a request-level error probe shows 0 failed requests, no duplicate effects and no live turn settled. Measure interrupted turns per handover. Then the founder's long-turn live proof.
- [ ] 4.3 Sync the `execution-owner` and `uptime-and-alarms` specs, then archive.
