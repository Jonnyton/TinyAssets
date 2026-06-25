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

- [ ] 3.1 Request a Codex review pass on this amendment (OKF-as-foundation is research-derived → opposite-provider review per AGENTS.md); record the verdict artifact path in this change
- [ ] 3.2 Fold any Codex adaptations back into the narrative spec + the `brain-canonical-store` delta

## 4. OpenSpec fold-back

- [ ] 4.1 `sync-specs`: merge the `brain-canonical-store` delta into `openspec/specs/brain-canonical-store/spec.md`
- [ ] 4.2 Open a PR to `main` linking this change so the live sessions see the new canonicality (merge gated on the §3 review + host key — merging to main is production-impacting)
- [ ] 4.3 Archive the change after merge
