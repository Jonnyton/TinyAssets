> **Lane disposition (premise sweep 2026-07-24, `origin/main` @ `6dd2bdf0`) — this change cannot reach 16/16, and that is the correct state.**
> All seven remaining tasks were verified against the tree, not taken on faith. One (2.2) was live and is now done. Two (2.1, 4.1) are blocked on a **host decision** — the open STATUS row "Resolve target-spec PLAN conflicts — store, private data…"; 4.1 is additionally blocked because `openspec/specs/` is as-built truth and this capability is unbuilt. One (4.3) is downstream of 4.1 and is not a safe no-op (`openspec archive` performs the forbidden sync). Three (§5) are explicitly out of scope by their own heading and belong to a successor change. Do not "finish" this change by checking those off.
> **Cross-family gate:** Codex was asked to refute the blocking analysis and returned `confirmed` on both claims, recommending exactly this terminal state.

## 1. Establish the active change as the behavioral target owner

- [x] 1.1 Record the conflicting SQLite-canonical and markdown-canonical legacy statements as provenance
- [x] 1.2 Record the 2026-06-24 host directive in the proposal and design
- [x] 1.3 Keep the OpenSpec delta as the sole in-flight behavioral target owner
- [x] 1.4 Remove any requirement to amend legacy `docs/specs/` files as authority
- [x] 1.5 Carry source-of-truth, redaction, build-boundary, and backup behavior in the delta/design
- [x] 1.6 Cite the OKF source and `okf_version "0.1"` as provenance for the target

## 2. Companion + coordination alignment

- [ ] 2.1 With host approval, fold the accepted store/redaction/build-boundary/backup architecture into PLAN before implementation or spec sync
  > **⛔ BLOCKED — host-decision, not a builder task.** Premise re-verified 2026-07-24: `PLAN.md` still carries no brain/OKF store decision. Its only canonical-store statement (`PLAN.md:560`, "GitHub is an export sink… Canonical state lives in Postgres") is *platform* goal/branch/node state — a different scope, neither approving nor contradicting the OKF bundle decision. The approval this task waits on is the open STATUS row **"Resolve target-spec PLAN conflicts — store, private data, primitives, privacy guidance"** (`host-decision`), which `docs/audits/2026-07-22-legacy-spec-disposition.md:69` independently names as the lane owning this file's store residue. A builder MUST NOT write the decision into PLAN on the host's behalf (AGENTS.md: PLAN changes require user approval).
- [x] 2.2 Keep STATUS dependencies explicit so no Brain implementation treats the legacy narrative or research companion as authority
  > **Discharged in two halves (verified 2026-07-24).** *Legacy-is-not-authority:* landed independently — `docs/specs/INDEX.md` now disclaims current authority for the whole directory, and `docs/audits/2026-07-22-legacy-spec-disposition.md` classifies `2026-06-10-brain-v2-research-implications.md` as **HISTORY** ("`brain-okf-canonical-store` owns the unbuilt OKF migration", line 67) and `2026-06-10-tiny-first-principles-spec.md` as **CLAIMED**, split across canonical specs / active Brain changes / the PLAN host-decision lane (line 69). *Dependency-is-explicit:* the STATUS `host-decision` row now names the store decision's gated consumers (this change's 2.1 foldback and 4.1 sync) inline, so a provider reading STATUS sees the block without opening the change. Coalesced into the existing row rather than added as a new one — STATUS is at its 60-line hard ceiling and already over its byte ceiling (`python scripts/check_context_budget.py`), and AGENTS.md requires duplicate host asks be coalesced to one.

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
  > **⛔ BLOCKED — the merge key landed, two other gates did not.** The parenthetical gate is satisfied: PR #1369 **MERGED** 2026-06-25 (merge commit `95d63682`, verified an ancestor of `origin/main`), so "after host merge key" no longer blocks. Two independent blockers remain, either one sufficient:
  > 1. **Gate ordering inside this change.** Task 2.1, `design.md` D6, and `proposal.md` §Impact all require host-approved PLAN foldback *before* spec sync. 2.1 is host-blocked (above), so 4.1 cannot precede it.
  > 2. **`openspec/specs/` is as-built truth.** AGENTS.md §"Spec-driven development" defines `openspec/specs/<capability>/spec.md` as the as-built requirement truth, and no file under `openspec/specs/` declares itself target-state. `brain-canonical-store` is entirely unbuilt — there is no `tinyassets/brain/` package, no commit protocol, no bundle-canonical write path (`docs/audits/2026-07-22-openspec-full-coverage-audit.md:105` classifies this change as "future brain-store migration"). Syncing it would assert requirements the system does not satisfy.
  >
  > Cross-family gate 2026-07-24: Codex (read-only, `codex exec`) was asked to **refute** this blocking claim and returned **confirmed**, recommending the change be left with 4.1/4.3 unchecked and block reasons recorded.
- [x] 4.2 Draft PR opened — #1369 (merge to `main` still host-key gated; production-impacting)
  > Landed: merged 2026-06-25T07:27:22Z as `95d63682` (`gh pr view 1369`). The trailing "still host-key gated" clause is historical wording, now stale.
- [ ] 4.3 Archive the change after merge
  > **⛔ BLOCKED — downstream of 4.1, and archiving is not a safe no-op.** `openspec archive` syncs delta specs as a side effect, so archiving now would perform the 4.1 sync this change's own D6 forbids. Archiving is also wrong on its own terms while §5 is unowned: an archived change with unbuilt, unrelocated requirements is exactly the spec drift AGENTS.md warns about. Sequence: host store decision → 2.1 PLAN foldback → 4.1 sync → §5 relocated to a successor change → 4.3.

## 5. Future build (gated — NOT in this change; behind the Codex 6 pre-build gates)

> **§5 is out of scope for this change by its own heading and MUST NOT be built in this lane.** These three items are why this change can never reach 16/16: they are forward build work parked in a design-amendment change. They belong in a successor change created after the host store decision. Leaving them unchecked here is correct; checking them off without the build would be a false completion claim.
>
> Premise re-verified against the tree 2026-07-24 (`origin/main` @ `6dd2bdf0`) so a future builder does not rebuild shipped code:

- [ ] 5.1 OKF compatibility shim (wikilink→Markdown projection; root-`index.md`→`okf_version`-only; `log.md` normalization; `drafts/` bundle-vs-staging rule)
  > **PARTIALLY LANDED — in the opposite direction. Reuse, do not rebuild.** `tinyassets/wiki/okf_export.py` ships all four projection mechanics, as a one-way *export* of curated wiki pages into a fresh bundle: `_convert_wikilinks` (resolvable wikilinks → absolute bundle links; unresolved rendered as plain labels and reported), `_write_index` (root `index.md` frontmatter is `okf_version: "0.1"` and nothing else — `okf_export.py:199`), `_write_log` (dated `log.md`), and `_EXCLUDED_ROOTS = {"drafts", "raw", "daemon-wiki"}` (`okf_export.py:15`) — which is a *de facto* answer to the `drafts/` question left open in `design.md`: drafts are operational staging outside the bundle. This is already as-built spec truth in `openspec/specs/knowledge-retrieval-and-memory/spec.md:386,404`, whose own wording is careful that it is "not complete upstream OKF conformance or canonical-store authority".
  > **Still unbuilt:** the D5 *read-path* shim — consuming the existing wiki **in place** for slice-1 `assemble(lens)`. The exporter writes a separate bundle and refuses a target inside the source root (`okf_export.py:38`); it is not an in-place reader. `assemble(lens)` does not exist (`tinyassets/` has no `brain/` package; the only `assemble_*` functions are unrelated retrieval helpers). Task stays unchecked.
- [ ] 5.2 Write commit protocol (idempotency key; pending→durable states; atomic temp+rename; outbox ordering; crash recovery; rebuild reconciliation)
  > **Wholly unbuilt — no partial credit.** No bundle write path, outbox, or entry-state machine exists anywhere in `tinyassets/`. The shipped exporter is read-only by construction (`okf_export.py:1`; it "MUST NOT add an MCP action or mutate the source wiki" per the as-built spec), so nothing here is started.
- [ ] 5.3 Conformance validation `[substrate]` + `okf_version` pin + composable upstream-watch steward
  > **Split verdict.** *Partially landed:* the `okf_version` pin exists (`OKF_VERSION = "0.1"`, `okf_export.py:12`) and a structural conformance validator ships (`_conformance_report`, `okf_export.py:232` — validates reserved-file shapes and parseable concept frontmatter with non-empty `type`). But it is deliberately narrow: it validates only the *generated* bundle, and the as-built spec states its `conformant` flag "does not claim complete upstream OKF or canonical-store conformance". *Unbuilt:* substrate-wide conformance validation over a canonical bundle, and the composable upstream-watch steward — a repo-wide search finds no OKF steward in any module or workflow. Task stays unchecked.
