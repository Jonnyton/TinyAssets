# Tasks — distributed execution

Live delivery ledger. This file is kept current on git so any AI sees the true
state, not a stale plan.

> **Reconciled against `origin/main` 2026-07-22.** The previous revision marked
> sections 1, 2, 3, 5.1 and 8.1 as LANDED. They are **not on `main`** — every
> PR they cite (#1477, #1478, #1479, #1481, #1487, #1491, #1493) is still
> **OPEN**. Only #1485 (7.1) is merged.
>
> The work is not lost: it exists on those open PRs. The ledger's error was
> equating "the branch work is finished / the PR is up" with "landed". A `[x]`
> in this file means **the artifact is in the `origin/main` tree** — nothing
> else. If you need code from an unmerged item below, check the PR out; do not
> assume `main` has it.

## 1. Authority foundation (M1) — ON OPEN PRs, NOT ON MAIN

- [ ] 1.1 Shared `RecordVerifier` / `Verified[T]` signed-record primitive (#1477 — OPEN)
  - Verified absent on main 2026-07-22: no `RecordVerifier` / `Verified[` in any
    `*.py` in the `origin/main` tree.
- [ ] 1.2 Sound field binding, cross-instance blob lock, migration validation, honest custody (#1477 — OPEN)
- [ ] 1.3 Per-domain immutable field contracts; `unbound_fields` removed; durable lease-owner binding (B05/B06, #1479 — OPEN)
  - #1479 is stacked on #1477; neither is merged.

## 2. Lease store + evidence ledger — ON OPEN PRs, NOT ON MAIN

`#1481` is OPEN (stacked on #1479). Verified absent on main 2026-07-22: the
runtime `lease_store`, the authenticated execution transport, and the signed
terminal-attestation system are not in the tree.

Be precise about what "absent" means here — `main` *does* have lease- and
attestation-shaped code that is **not** this system and must not be mistaken for
it: `branch_tasks.claim_task` and the branch-task lease fields
(`worker_owner_id` / `lease_expires_at` / heartbeat, surfaced at
`tinyassets/api/status.py:545-581`), gate-event outcome attestations
(`tinyassets/api/extensions.py:591`), and effector runtime attestations
(`tinyassets/effectors/windows_desktop.py:148`). None of these carry signed
records, a generation floor, or an append-only evidence ledger.

- [ ] 2.1 Durable monotonic generation floor; restored superseded generation fails closed (B01, #1481 — OPEN)
- [ ] 2.2 Block `INSERT OR REPLACE`/`REPLACE`/UPSERT on attestations and `lease_events` (B02/B03, #1481 — OPEN)
- [ ] 2.3 Verify-first attestation replay (B04, #1481 — OPEN)

## 3. B2 spine — ON OPEN PR, NOT ON MAIN

`#1477` is OPEN. Verified absent on main 2026-07-22: no job claim/result/complete
transport in the tree.

- [ ] 3.1 A persisted run becomes a job and reaches signed terminal acceptance (#1477 — OPEN)
- [ ] 3.2 Real `run_graph` user path creates the job; composition root wires the authority stack (#1477 — OPEN)
- [ ] 3.3 Authenticated claim/result/complete over the transport; daemon-side signed client (#1477 — OPEN)

## 4. Blob authority (M2 substrate) — ⚠ IN REPAIR, NOT ON MAIN

- [ ] 4.1 One lock order, physical root identity, no stale index, full attestation table contract (B07–B10, #1487 — OPEN)
  - **Current (verified 2026-07-22 at #1487 head `f6bee436`):** the three focused
    regressions
    (`test_record_candidate_marks_result_blobs_referenced`,
    `test_mark_referenced_rejects_raw_blob_reference`,
    `test_stale_instance_cannot_resurrect_collected_binding`) pass 3/3 and the
    verified-proof implementation is committed. The task stays unchecked because
    the stacked PR remains open and none of it is on `main`.
- [ ] 4.2 M2 content-addressing tightening: every accepted content hash recomputed
  from bytes, never read from a mutable row (in flight)

## 5. Identity / device-key authority (M1 on S3) — NOT ON MAIN

- [ ] 5.1 Daemon-impersonation fix: thumbprint recomputed from key at all five
  stored-key consumption sites; per-fence revocation probes (#1491 — OPEN)
  - Verified absent on main 2026-07-22: the string `thumbprint` does not appear
    in any `*.py` in the `origin/main` tree. This is a security fix that reads as
    shipped but is not — treat the impersonation vector as **open on main**.
- [ ] 5.2 Bind device-key resolution + enrollment-approval to a platform-signed
  enrollment record (unwired substrate; live rollout host-gated — B24)

## 6. GitHub effect (S10.5 / M2+M3) — ⚠ NEEDS REBASE

- [ ] 6.1 Exactly-once reviewable PR effect, legacy route retired (#1493 — OPEN)
  - **BLOCKER:** branched off `fix2` before the B05/B06 domain-contract model; its
    new signed fields (`universe_id`, `base_commit`, `base_tree`) are not
    classified into the per-domain partition. Rebase onto the contract model and
    classify the fields before merge.
  - Note: `tinyassets/effectors/github_pr.py` exists on main, but that is the
    **legacy** route this task retires — its presence is not partial completion.
- [ ] 6.2 M3 redesign: merge worker is NOT authoritative → the projection-as-cache
  justification is invalid; only GitHub's protected SHA-bound transaction may
  produce `merged`

## 7. Confinement (S0/S6–S9) — SEAM ONLY

- [x] 7.1 Per-job sandbox runner seam; fail-closed, unavailable by default; live
  engine untouched (#1485, merged as `8c70b5f0`)
  - Verified on main 2026-07-22: `tinyassets/sandbox_runner.py`,
    `tinyassets/sandbox/__init__.py`, `tinyassets/sandbox/detect.py`, plus
    `tests/test_sandbox_runner.py` / `tests/test_sandbox_detect.py`.
- [ ] 7.2 Platform-specific backend (container/WSL2/bwrap) + actual removal of
  secret co-residency (host-gated)

## 8. CI authority gates — NOT ON MAIN

- [ ] 8.1 py311 floor + security-suite + advisory authority scan, self-enforcing (#1478 — OPEN)
  - Verified absent on main 2026-07-22: no workflow in `.github/workflows/`
    references a security-suite, authority scan, or forge probe. (`3.11` does
    appear in `build-bundle.yml` / `branch-janitor.yml`, but as ordinary
    `setup-python` pins — that is not the floor gate this task describes.)
- [ ] 8.2 Wire the full forge/mutation-probe file set into the blocking job + a
  guard test that fails when a new probe file is not wired (in flight)

## 9. Pre-deploy integration — IN PROGRESS

- [~] 9.1 Integration branch merging the mergeable stack; full suite + canary.
  The earlier #1487 committed-red blocker is resolved on its current open head;
  the #1493 rebase need (6.1) remains. Branch-only; nothing from this lane is on
  `main`.
- [ ] 9.2 Dual-family pre-deploy gate across the integrated whole
- [ ] 9.3 Merge + deploy (host-gated: main merge + prod deploy)

## 10. Live acceptance — NOT STARTED

- [ ] 10.1 First B2 live test: a real daemon claims and completes a real job
  through the live surface, verified via rendered chatbot `ui-test`
