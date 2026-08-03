## 1. Contract Admission

- [ ] 1.1 Strict-validate this proposal/design/spec/task set, obtain an independent exact-head architecture and security review, and fold every blocking finding before production-code implementation. Acceptance: the review explicitly covers custody placement, authenticated context, cross-scope disclosure, idempotency/races, export, deletion residue, and the dark integration boundary. Verification: `openspec validate establish-private-conversation-custody --strict`, `openspec validate --all --strict`, and `python scripts/openspec_flow.py check-change establish-private-conversation-custody --provider codex-gpt5-desktop` all exit zero at the reviewed head.

## 2. Typed Custody Contract

- [ ] 2.1 Test-first, add `tinyassets/conversation_custody.py` domain records and validation for the fixed-universe custody context, immutable thread/message/receipt shapes, canonical bounded JSON payloads, request digests, and deterministic private export. Acceptance: unsupported modes, cross-universe contexts, malformed identifiers/timestamps/replies, non-JSON/nested/oversized payloads, and noncanonical reconstructions fail closed while arbitrary bounded payload members round-trip. Verification: focused tests in `tests/test_conversation_custody.py` demonstrate RED before implementation and then pass.

## 3. Private-Universe Persistence

- [ ] 3.1 Test-first, add `tinyassets/storage/conversation_custody.py` with per-universe SQLite placement, immutable/idempotent thread creation, exact-scope reads, transactional append-only messages, same-thread reply checks, and concurrent contiguous ordinals. Acceptance: identical retries return the exact record, changed retries conflict, wrong owner/universe/binding writes nothing, distinct concurrent appends are stored once with contiguous ordinals, and accepted thread/message records have no update path. Verification: focused persistence and cross-process race tests pass with WAL and foreign keys enabled.
- [ ] 3.2 Test-first, add deterministic exact-thread export plus atomic owner-requested/retention-expiry deletion and content-free idempotent receipts. Acceptance: premature retention deletion and wrong-scope deletion are atomic no-ops; successful deletion removes all thread/message content and private-derived digests/refs while an exact receipt replay survives; tampered canonical/index/digest/ordinal state raises an integrity error without partial output. Verification: focused export/deletion/corruption tests pass and a direct SQLite residue assertion finds no deleted private payload, digest, interlocutor, source-event, or reply value.

## 4. Packaging and Dark Boundary

- [ ] 4.1 Mirror both canonical modules into the packaged universe-server runtime and prove no public MCP handle, app/provider import, network call, binding mutation, definition/lineage mutation, credential field, or production construction path was added. Acceptance: canonical/package files are byte-identical and the existing exact-seven public-handle assertion is unchanged. Verification: `python scripts/check_packaged_runtime_parity.py`, focused custom-agent/runtime regressions, and repository searches for forbidden integration paths pass.

## 5. Verification and Foldback

- [ ] 5.1 Run the focused suite plus relevant custom-agent, runtime-manifest, storage, security, race, Ruff, mirror, strict OpenSpec, and bounded-flow gates; obtain independent exact-head code/security review and fold every blocking finding. Acceptance: fresh command output is green, the reviewer approves the exact head, and review evidence names any same-provider fallback if opposite-provider review is unavailable.
- [ ] 5.2 Sync `conversation-custody` into `openspec/specs/`, archive this completed change, publish/merge the single PR, retire the STATUS/worktree claim in the landing lane, and hand the fixed-universe context/store interfaces to `connect-custom-agent-app-conversations` without activating app ingress or production storage. Verification: merged current main contains the synced spec and modules, no active change or STATUS claim remains, and the successor handoff records all remaining authority prerequisites.
