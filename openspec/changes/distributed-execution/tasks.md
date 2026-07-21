# Tasks — distributed execution

Live delivery ledger. Landed items keep their PR so the audit trail survives;
this file is kept current on git so any AI sees the true state, not a stale plan.

## 1. Authority foundation (M1) — LANDED

- [x] 1.1 Shared `RecordVerifier` / `Verified[T]` signed-record primitive (#1477)
- [x] 1.2 Sound field binding, cross-instance blob lock, migration validation, honest custody (#1477)
- [x] 1.3 Per-domain immutable field contracts; `unbound_fields` removed; durable lease-owner binding (B05/B06, #1479)

## 2. Lease store + evidence ledger — LANDED

- [x] 2.1 Durable monotonic generation floor; restored superseded generation fails closed (B01, #1481)
- [x] 2.2 Block `INSERT OR REPLACE`/`REPLACE`/UPSERT on attestations and `lease_events` (B02/B03, #1481)
- [x] 2.3 Verify-first attestation replay (B04, #1481)

## 3. B2 spine — LANDED

- [x] 3.1 A persisted run becomes a job and reaches signed terminal acceptance (#1477)
- [x] 3.2 Real `run_graph` user path creates the job; composition root wires the authority stack (#1477)
- [x] 3.3 Authenticated claim/result/complete over the transport; daemon-side signed client (#1477)

## 4. Blob authority (M2 substrate) — ⚠ IN REPAIR

- [~] 4.1 One lock order, physical root identity, no stale index, full attestation table contract (B07–B10, #1487)
  - **BLOCKER (2026-07-21):** committed #1487 is RED on a clean checkout — 3 tests
    (`test_record_candidate_marks_result_blobs_referenced`,
    `test_mark_referenced_rejects_raw_blob_reference`,
    `test_stale_instance_cannot_resurrect_collected_binding`) expect a
    "verified blob proof" implementation that was never committed. The completing
    code exists only as uncommitted WIP in the build worktree (the M2 tightening
    lane). Must land the implementation or align the tests before #1487 merges.
- [ ] 4.2 M2 content-addressing tightening: every accepted content hash recomputed
  from bytes, never read from a mutable row (in flight)

## 5. Identity / device-key authority (M1 on S3) — PARTIAL

- [x] 5.1 Daemon-impersonation fix: thumbprint recomputed from key at all five
  stored-key consumption sites; per-fence revocation probes (#1491)
- [ ] 5.2 Bind device-key resolution + enrollment-approval to a platform-signed
  enrollment record (unwired substrate; live rollout host-gated — B24)

## 6. GitHub effect (S10.5 / M2+M3) — ⚠ NEEDS REBASE

- [ ] 6.1 Exactly-once reviewable PR effect, legacy route retired (#1493)
  - **BLOCKER:** branched off `fix2` before the B05/B06 domain-contract model; its
    new signed fields (`universe_id`, `base_commit`, `base_tree`) are not
    classified into the per-domain partition. Rebase onto the contract model and
    classify the fields before merge.
- [ ] 6.2 M3 redesign: merge worker is NOT authoritative → the projection-as-cache
  justification is invalid; only GitHub's protected SHA-bound transaction may
  produce `merged`

## 7. Confinement (S0/S6–S9) — SEAM ONLY

- [x] 7.1 Per-job sandbox runner seam; fail-closed, unavailable by default; live
  engine untouched (#1485)
- [ ] 7.2 Platform-specific backend (container/WSL2/bwrap) + actual removal of
  secret co-residency (host-gated)

## 8. CI authority gates — LANDED / EXTENDING

- [x] 8.1 py311 floor + security-suite + advisory authority scan, self-enforcing (#1478)
- [ ] 8.2 Wire the full forge/mutation-probe file set into the blocking job + a
  guard test that fails when a new probe file is not wired (in flight)

## 9. Pre-deploy integration — IN PROGRESS

- [~] 9.1 Integration branch merging the mergeable stack; full suite + canary.
  Surfaced the #1487 committed-red blocker (4.1) and the #1493 rebase need (6.1).
- [ ] 9.2 Dual-family pre-deploy gate across the integrated whole
- [ ] 9.3 Merge + deploy (host-gated: main merge + prod deploy)

## 10. Live acceptance — NOT STARTED

- [ ] 10.1 First B2 live test: a real daemon claims and completes a real job
  through the live surface, verified via rendered chatbot `ui-test`
