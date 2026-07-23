## 1. Establish the active change as the behavioral target owner

- [x] 1.1 Record the conflicting SQLite-canonical and markdown-canonical legacy statements as provenance
- [x] 1.2 Record the 2026-06-24 host directive in the proposal and design
- [x] 1.3 Keep the OpenSpec delta as the sole in-flight behavioral target owner
- [x] 1.4 Remove any requirement to amend legacy `docs/specs/` files as authority
- [x] 1.5 Carry source-of-truth, redaction, build-boundary, and backup behavior in the delta/design
- [x] 1.6 Cite the OKF source and `okf_version "0.1"` as provenance for the target

## 2. Companion + coordination alignment

- [ ] 2.1 With host approval, fold the accepted store/redaction/build-boundary/backup architecture into PLAN before implementation or spec sync
- [ ] 2.2 Keep STATUS dependencies explicit so no Brain implementation treats the legacy narrative or research companion as authority

## 3. Cross-provider review gate (MUST precede any build-gating)

- [x] 3.1 Codex review pass obtained — verdict **ADAPT** (`docs/audits/2026-06-24-brain-okf-canonical-codex-review.md`); 6 required adaptations
- [x] 3.2 Folded all 6 adaptations into the spec delta + design + proposal; legacy documents remain non-authoritative provenance:
  - [x] 3.2.1 Commit protocol replaces "write-through resolves Gap #4" (spec Req 2; design D2; proposal)
  - [x] 3.2.2 `log.md` (human history) split from the transactional journal/outbox (spec "Reserved files" Req; design D2)
  - [x] 3.2.3 OKF compatibility shim — wiki not conformant as-is (spec "compatibility shim" Req; design D5; proposal slice-1)
  - [x] 3.2.4 Build-boundary: conformance validation = `[substrate]`; upstream-watch steward = `[composable]` (spec requirement; design D4)
  - [x] 3.2.5 Redaction: block operational index FIRST; secrets tombstone omits content-hash (spec requirement)
  - [x] 3.2.6 Reword inconsistency → cross-artifact mismatch; SHOULD-not-MUST key preservation; broken-link wording (proposal Why; design Context; spec Req 3)

## 4. OpenSpec fold-back

- [ ] 4.1 `sync-specs`: merge the `brain-canonical-store` delta into `openspec/specs/brain-canonical-store/spec.md` (after host merge key)
- [x] 4.2 PR #1369 merged 2026-06-25; the change remains unarchived because PLAN foldback and canonical sync are still gated
- [ ] 4.3 Archive the change after merge

## 5. Future build (gated — NOT in this change; behind the Codex 6 pre-build gates)

- [ ] 5.1 OKF compatibility shim (wikilink→Markdown projection; root-`index.md`→`okf_version`-only; `log.md` normalization; `drafts/` bundle-vs-staging rule)
- [ ] 5.2 Write commit protocol (idempotency key; pending→durable states; atomic temp+rename; outbox ordering; crash recovery; rebuild reconciliation)
- [ ] 5.3 Conformance validation `[substrate]` + `okf_version` pin + composable upstream-watch steward
