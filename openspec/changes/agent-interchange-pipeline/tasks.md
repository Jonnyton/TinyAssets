## 0. Review and admission

- [ ] 0.1 Independently review the current-main proposal, design, capability delta, and task plan across correctness, architecture, security, performance, and scope; fold every blocking finding before implementation.

## 1. Test-first domain contract

- [ ] 1.1 Add red tests proving exact canonical export-import-export fingerprints, preservation of unfamiliar bounded components, exclusion of every private/runtime field, and a verified child blend from at least three public definitions authored by other actors.
- [ ] 1.2 Add red adversarial tests proving raw foreign input is never durably stored or logged, credential/authority values are omitted, unknown safe content is namespaced, reports classify every item, false lossless claims fail, and adapter output cannot bypass canonical validation.
- [ ] 1.3 Add red receipt, idempotency, and concurrency tests proving exact source/adapter/output/report binding, distinct adapter-version provenance, one logical stage per identical retry, conflict on changed inputs, and atomic failure with no partial stage/definition/lineage.

## 2. Staging and interchange core

- [ ] 2.1 Implement additive SQLite stage/receipt storage plus bounded canonical validators, exhaustive report validation, digest verification, actor-private reads, and sanitized retention behavior; make tasks 1.2-1.3 green without persisting raw sources.
- [ ] 2.2 Implement the canonical native adapter and `agent-interchange-adapter/v1` protocol boundary, including safe namespaced extensions and explicit `requires_runtime` refusal when executable Engine OS admission is unavailable; make native round-trip and hostile-adapter tests green.
- [ ] 2.3 Implement explicit stage → publish and cross-user multi-parent remix orchestration by delegating only to the existing immutable `publish_definition` transaction; make task 1.1 green and preserve informational-only unresolved external origins.

## 3. Public surface and safety proof

- [ ] 3.1 Add bounded `read_graph`/`write_graph` agent operations for stage, inspect, publish, remix, bind, canonical export, and foreign export; prove private authorization, OAuth mutation gating, payload descriptions, and the exact seven-handle manifest.
- [ ] 3.2 Run focused tests, Ruff, secret/log scans, canonical-handle drift checks, and §14 parallel import/remix/load proof; record dated environment, commands, revision, timing, throughput, error rate, duplicate counts, and results.

## 4. Release and foldback

- [ ] 4.1 Independently review the implementation and evidence, deploy through the normal pipeline, run the public canary, and complete one rendered connector conversation: import → inspect report → blend other users' agents → publish → bind privately → export.
- [ ] 4.2 Check production for clean post-fix organic use; if absent, leave a dated monitoring row, then sync `agent-interchange` into canonical specs and archive this change only after `universe-custom-agents` has landed and its dependency truth is canonical.
