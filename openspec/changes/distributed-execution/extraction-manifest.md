# Current-main extraction manifest

Freshness: 2026-08-02, branch base `origin/main@ce35784f`, with D0 present as
merged PR #1701 (`aa328495718b5ebee34aa7adaa92882b7db74288`). This manifest
records provenance for already-landed D0 behavior. It does not import a stale
branch, activate a production route, or complete V1.

## Acceptance contract

This recovery slice closes tasks 2.1-2.5, 2.8, and 2.9 only when all of the
following remain true:

1. each selected stale source has an exact commit anchor and a named
   current-main replacement;
2. PR #1491 daemon-key binding stays deferred until its S3 consumers exist;
3. PR #1478's CI gate stays deferred until it is recreated from current paths;
4. PR #1572 contributes no runtime, schema, test, or compatibility behavior;
5. D0 changes none of PR #1697's descriptor/runtime files and the current
   descriptor, heartbeat, lifecycle, and contested-registration tests pass.

## Completed extraction provenance

| Task | Reviewed stale source | Current-main replacement in #1701 | Excluded lineage |
|---|---|---|---|
| 2.1 | #1472: capsule vectors and mutations from `f6f6814e687f10135e394c67cff0c0b6f5322cdd`, `1fb921dd7b186e6b76368b8ebeee9c66da75ed7f`, `0d19e515683b56c8875cd607681975f23f6ee29c`, and result/blob cases from `cf4fa726b24d6412dbe1f6905d6dec072fc71c98` | `tinyassets/execution_authority/records.py`, `tests/test_execution_authority_records.py`, and `tests/test_distributed_execution_d0.py`; exact-domain vectors, unknown-field/type/bounds rejection, cross-domain reuse, and candidate/terminal binding are exercised | S0 worker/deploy removal, daemon transport/auth rollout, runtime/config, workflows, and all other files from the 104-file PR |
| 2.2 | #1477's change-only range begins at `eb4ab6f024d1079d58d559a24d6f0735139d1e5e`; the reviewed M1 foundation is `16ab2f67128b56b20b18e3722d20c1f12755a826` plus `f82179b33dbc1b2568abc925129c1b33332b7b38` | `tinyassets/execution_authority/verified.py`, `records.py`, and the fake-only spine in `tests/support/execution_authority.py`; #1701 deliberately rebuilt these against current main | `run_graph` integration (`d838fb1577d910fc9c52ad4267099e27a82d78ef`), transport, provider, production-root, inherited patch-loop, credential-vault, and unrelated commits |
| 2.3 | #1479 immutable-domain implementation `9be3e6a3a46fa8cffeeee91b5919d82d76b130aa` | fixed domain contracts in `records.py`; `test_unknown_domain_version_or_field_fails_closed`, exact owner/daemon/job/capsule/lease comparisons in the D0 sink, and no caller `unbound_fields` seam | stacked lease-store/runtime files and plugin merge-conflict repair commits |
| 2.4 | #1481 evidence-ledger implementation `cc3a9a7b7065e6295e62f0a89f1f0a4708ff7ef7` | `tinyassets/execution_authority/evidence_store.py`; generation restore, replacement/UPSERT, verify-first replay, identical-fact collapse, and conflicting-fact corruption tests in `tests/test_execution_evidence_store.py` | stacked runtime lease-store lineage and generated mirror-only commits |
| 2.5 | #1487 blob/lock implementation `38936d608db5a45bd33715ec9cf6ab02afcfef90` plus proof tests `73a823eac846d12b450799b25c5c8e9cfcd4cc8a` and `a4374eb7913e96af67fee939893b4ae606827257` | `tinyassets/execution_authority/blob_proof.py` and evidence-store coordination; fresh-byte proof, physical aliases, operation-local reload, lock order, interleavings, and exact table validation in `tests/test_execution_blob_proof.py` and `tests/test_execution_evidence_store.py` | stacked `runtime/blob_refs.py`, `runtime/lease_store.py`, inherited branch merges, and mirror-only commits |

All replacements landed in #1701's engineering commit
`c2226e93421f6fa8cc5ce697a362be290efc132a`, squash-merged as
`aa328495718b5ebee34aa7adaa92882b7db74288`. No stale PR was merged, rebased,
cherry-picked, or used as the branch base.

## Deliberately deferred sources

- **2.6 / #1491:** the reviewed behavior is key/thumbprint recomputation at
  daemon-key consumption sites and non-vacuous per-fence mutation coverage.
  The 386-file PR head is
  `cee48beb4fc37e7785b16ef1bdde1d8364a838a9`; its S3 carriers and consumers
  are not part of D0, so none of it is extracted here.
- **2.7 / #1478:** the reviewed source is
  `4e50face4e20002c9ba2cbbfa66a803457071f3d`, but current main has no
  `.github/workflows/authority-invariants.yml`. Local CPython 3.11 evidence
  from #1701 does not substitute for the required blocking current-path CI
  gate, so this task remains open. The suspicious-read scan remains advisory.

## Explicit #1572 exclusion

PR #1572 remains open and design-gated at head
`42e7dca79e8e07ca7a71ceaf2663cba93d34dbb4`. Its branch-version M2 design,
`tinyassets/runtime/signed_records.py`, full-hash version-ID behavior, legacy-ID
break, branch-version tests, schema expectations, and compatibility behavior
are absent from #1701. Current main has no
`tinyassets/runtime/signed_records.py`; D0 uses the purpose-separated
`tinyassets/execution_authority/` package instead. This closes 2.8 without
accepting or superseding #1572.

## #1697 preservation proof

PR #1697's exact reviewed head is
`2d3a774f05379a2718ab7749646732080d179ee9`. The #1701 squash diff changes
none of `tinyassets/{cloud_worker,daemon_registry,daemon_server}.py` or their
descriptor/runtime tests. On 2026-08-02, Windows, CPython 3.11+, the command

```text
python -m pytest -q tests/test_cloud_worker.py tests/test_daemon_registry.py tests/test_supervisor_liveness.py
```

passed `136 passed in 7.04s`. The suite covers release-derived
`queue_protocol_version=2` descriptors, build/config SHA, boot/worker/runtime
identity, universe binding, exact 90-second liveness, descriptor persistence
and clearing, pause/retire lifecycle preservation, two-worker contested
adoption, and eight-way same-worker registration. This closes 2.9 without
promoting any descriptor or scheduling fact into B2 authority.

## Reproduction checks

```text
git diff --name-only aa328495^1 aa328495 -- tinyassets/cloud_worker.py tinyassets/daemon_registry.py tinyassets/daemon_server.py tests/test_cloud_worker.py tests/test_daemon_registry.py tests/test_supervisor_liveness.py
# expected: no output

Test-Path tinyassets/runtime/signed_records.py
# expected: False
```
