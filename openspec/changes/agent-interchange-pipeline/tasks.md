## 0. Review and admission

- [x] 0.1 Independently review the current-main proposal, design, capability delta, and task plan across correctness, architecture, security, performance, and scope; fold every blocking finding before implementation. Reviewed through exact head `e7b965c1` after resolving portable-lineage, idempotency, transaction, adapter-proof, secret-commitment, load, inventory-coverage, and wire-schema findings; strict validation passed and the reviewer returned `Ready to implement: Yes`.

## 1. Test-first domain contract

- [x] 1.1 Add red cross-installation tests proving a multi-parent child exported into an empty commons retains exact canonical content/fingerprint and immutable parent/component fingerprint declarations without manufacturing verified credit; also prove a child can blend at least three public definitions authored by other actors. Red on 2026-07-31 with missing fingerprints and rewritten origins; green on Windows/Python 3.14 with `19 passed` in `tests/test_custom_agents.py` and changed-file Ruff clean.
- [ ] 1.2 Add red adversarial tests proving raw foreign input and unkeyed raw hashes are never stored or logged, low-entropy credentials cannot be guessed from evidence, private source commitments expire after 24 hours, core-enumerated JSON inventory cannot omit/duplicate a path, opaque inventory stays unverified/non-lossless, every byte/count/depth/path/detail bound fails closed, unknown safe content is namespaced, and adapter output cannot bypass canonical validation.
- [x] 1.3 Add red receipt, idempotency, and concurrency tests proving exact source/adapter/output/report binding, distinct adapter-version provenance, one logical stage per identical retry, conflict on changed inputs, and atomic failure with no partial stage/definition/lineage. Red with the missing module on 2026-07-31; green on Windows/Python 3.14 with six focused receipt/idempotency/concurrency tests and changed-file Ruff clean.

## 2. Staging and interchange core

- [ ] 2.1 Implement additive SQLite stage/receipt storage plus purpose-keyed private source commitments, 24-hour expiry, bounded canonical/report/receipt validators, actor-private reads, and sanitized-content receipts; make tasks 1.2-1.3 green without persisting raw sources or unkeyed raw hashes.
- [ ] 2.2 Implement the exact bounded `agent-interchange-adapter/v1` request/response/receipt schemas, including named algorithm/digest fields, status-dependent exactly-one output rules, encoded/decoded/whole-envelope limits, trusted JSON Pointer inventory enumeration, the canonical native adapter, and the closed non-executable declarative JSON mapping runner/fixture; require exact inventory coverage, preserve safe namespaced extensions, mark unverifiable opaque formats non-exhaustive, and return `requires_runtime` for every adapter outside the grammar until Engine OS admission exists.
- [x] 2.3 Refactor immutable definition publication onto a caller-supplied SQLite transaction, preserve portable fingerprint lineage separately from local verified projections, and commit stage status, definition, lineage, and receipt linkage atomically; make task 1.1 green without changing existing publish/remix/bind results. Verified 2026-07-31 on Windows/Python 3.14: injected publish failure rolled back all definition/stage changes, retry published once, and the 24 domain/interchange tests passed.

## 3. Public surface and safety proof

- [ ] 3.1 Add only the new bounded `stage_import`, `get_import_stage`, `publish_stage`, and `convert_export` operations to existing graph agent targets; reuse existing publish/remix/bind/get-agent contracts and prove private authorization, OAuth mutation gating, terminal errors, payload descriptions, and the exact seven-handle manifest.
- [ ] 3.2 Run focused tests, Ruff, secret/log scans, canonical-handle drift checks, and a deployment-shaped §14 proof: 200 concurrent actors across eight processes, 1,000 mixed requests in five minutes, maximum 256-KiB/64-component payloads, p95 <2s, p99 <3s, throughput ≥3.33/s, zero unhandled busy errors/partial writes/duplicates/leaks, and <1% unexpected errors; record dated environment, commands, revision, topology, distributions, timing, conflicts, and results.

## 4. Release and foldback

- [ ] 4.1 Independently review the implementation and evidence, deploy through the normal pipeline, run the public canary, and complete one rendered connector conversation using the declarative foreign-manifest proof adapter: import → inspect report → blend other users' agents → publish → bind privately → foreign export.
- [ ] 4.2 Check production for clean post-fix organic use; if absent, leave a dated monitoring row, then sync `agent-interchange` into canonical specs and archive this change only after `universe-custom-agents` has landed and its dependency truth is canonical.
