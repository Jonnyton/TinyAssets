## 1. Amend the ratified narrative spec (`docs/specs/2026-06-10-tiny-first-principles-spec.md`)

- [x] 1.1 Replace the §5 store bullet (L65) with the OKF-canonical + rebuildable-operational-index text (per proposal "What Changes" + design D1/D2)
- [x] 1.2 Update the §5(h) line: "the OKF bundle stays canonical; SQLite/FTS/vectors are the rebuildable index" (HTML element-IDs unchanged)
- [x] 1.3 Reorder the §11.2 redaction propagation pipeline to delete from the canonical bundle first, then rebuild the index
- [x] 1.4 Update the §13 build-boundary audit wording: bundle store + index = `[substrate]`; OKF-conformance / auto-sync steward = `[composable]`
- [x] 1.5 Update the §14 migration/backup note: the nightly snapshot IS the canonical bundle (retires the 2026-06-09 "backup never finished" gap)
- [x] 1.6 Add an OKF reference (SPEC.md URL + `okf_version "0.1"`) to §5 / the provenance line

## 2. Companion + coordination alignment

- [ ] 2.1 Add a precedent note to `docs/specs/2026-06-10-brain-v2-research-implications.md` — OpenClaw's markdown-source-of-truth + rebuildable-index IS the adopted model; canonicality is now bundle-first (no requirement change)
- [ ] 2.2 STATUS.md: add a brain-canonical coordination row/note so the `defantasy` and `tiny-spec` sessions (and the next brain-builder) build toward OKF-canonical, not SQLite-canonical

## 3. Cross-provider review gate (MUST precede any build-gating)

- [x] 3.1 Codex review pass obtained — verdict **ADAPT** (`docs/audits/2026-06-24-brain-okf-canonical-codex-review.md`); 6 required adaptations
- [x] 3.2 Folded all 6 adaptations into the spec delta + design + proposal + ratified spec:
  - [x] 3.2.1 Commit protocol replaces "write-through resolves Gap #4" (spec Req 2; design D2; proposal)
  - [x] 3.2.2 `log.md` (human history) split from the transactional journal/outbox (spec "Reserved files" Req; design D2)
  - [x] 3.2.3 OKF compatibility shim — wiki not conformant as-is (spec "compatibility shim" Req; design D5; proposal slice-1)
  - [x] 3.2.4 Build-boundary: conformance validation = `[substrate]`; upstream-watch steward = `[composable]` (spec Req; design D4; §13)
  - [x] 3.2.5 Redaction: block operational index FIRST; secrets tombstone omits content-hash (spec Req; §11.2)
  - [x] 3.2.6 Reword inconsistency → cross-artifact mismatch; SHOULD-not-MUST key preservation; broken-link wording (proposal Why; design Context; spec Req 3)

## 4. OpenSpec fold-back

- [ ] 4.1 `sync-specs`: merge the `brain-canonical-store` delta into `openspec/specs/brain-canonical-store/spec.md` (after host merge key)
- [x] 4.2 Draft PR opened — #1369 (merge to `main` still host-key gated; production-impacting)
- [ ] 4.3 Archive the change after merge

## 5. Future build (gated — NOT in this change; behind the Codex 6 pre-build gates)

- [ ] 5.1 OKF compatibility shim (wikilink→Markdown projection; root-`index.md`→`okf_version`-only; `log.md` normalization; `drafts/` bundle-vs-staging rule)
- [ ] 5.2 Write commit protocol (idempotency key; pending→durable states; atomic temp+rename; outbox ordering; crash recovery; rebuild reconciliation)
- [ ] 5.3 Conformance validation `[substrate]` + `okf_version` pin + composable upstream-watch steward
