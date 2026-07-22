## 1. Verify the contradiction (done in this change)

- [x] 1.1 `git fetch --prune`; classify against `origin/main`, then re-verify at `f605bb99` after PR #1578
- [x] 1.2 Confirm source 1 — ratified correction: PR #1578 / `f605bb99` replaces chatbot embodiment with the relay model
- [x] 1.3 Confirm source 2 — `docs/design-notes/2026-07-02-universe-intelligence-relay-architecture.md` §3 (why embodiment was live-falsified)
- [x] 1.4 Confirm source 3 — shipped code: `tinyassets/universe_server.py:209` ("You do NOT speak as the universe … RELAY … RENDER")
- [x] 1.5 Confirm the landed as-built capability `openspec/specs/universe-personification-and-relay/spec.md` codifies relay
- [x] 1.6 Find the **fourth** stale source, then verify PR #1578 / `f605bb99` corrected it before this reconciliation lands

## 2. Classify the 11 unchecked tasks (done — `design.md` §"Task-by-task reconciliation")

- [x] 2.1 Classify each task reversed / survives / already landed / unclear, one-line reason each
- [x] 2.2 Verify every "already landed" claim against `origin/main` code with a file citation (2.2-instructions, 2.7-honest-fallback, 2.3-grounded-assembly)
- [x] 2.3 Verify every "survives, unbuilt" claim by confirming absence in `tinyassets/` (no `identity_tier`; no dossier-write rejection)
- [x] 2.4 Flag task 4.1 (`sync-specs`) as MUST-NOT-RUN with the specific damage named

## 3. Retire the reversed change without deleting it

- [x] 3.1 `SUPERSEDED` banner on `universe-personification/proposal.md`, `design.md`, and the delta spec
- [x] 3.2 Rewrite `universe-personification/tasks.md` with per-task classification inline, so the file itself answers "should I build this?"
- [x] 3.3 Archive to `openspec/changes/archive/2026-07-22-universe-personification/` (removes it from `openspec list`; preserves every artifact)

## 4. Carry surviving intent forward

- [x] 4.1 Four ADDED requirements on `universe-personification-and-relay` (authorization-before-voice; interlocutor tier binding; anti-collision write path; forkable persona under first-party custody)
- [x] 4.2 Remove the threshold-less 2.9 scenario from this delta; carry connector instruction-density vs tool-selection accuracy as definition task 6.3 against `live-mcp-connector-surface`
- [x] 4.3 Cross-reference `universe-visibility` (anonymous-reader semantics) and `brain-okf-canonical-store` (assembled-view content) instead of duplicating them

## 5. Gates

- [x] 5.1 Opposite-provider review dispatched to Codex (background `scripts/codex_review.py`)
- [x] 5.2 Codex verdict **ADAPT** recorded in `design.md` §"Cross-provider review"; all 5 findings folded (classification upheld — the findings were against this change's own design)
- [x] 5.3 Re-verify Codex findings 1 + 2 against the repo before folding, rather than accepting on report
- [x] 5.4 **Host decision resolved** — PR #1578 / `f605bb99` amended the ratified paragraph to the relay model (`design.md` §"Host decision resolved")
- [x] 5.5 Draft PR opened — #1515; auto-merge disabled while the prerequisite and current-base repairs were incomplete
- [ ] 5.6 Re-run strict all-spec validation, task-annotation checks, diff checks, and independent final review on current `origin/main`

## 6. Implementation (this change stays ACTIVE until these land)

> Codex finding 1: the survivors are unbuilt, and `openspec/specs/` is as-built truth
> (`openspec/config.yaml`: "do not spec aspirations"). There is deliberately **no `sync-specs`
> task here** — the sync happens only after the code and tests below exist.

- [ ] 6.1 Define the anti-collision write restriction concretely before implementation — exact external/commons endpoint, predicate, redirect destination — and confirm it does not restrict the governed founder-learning path (`founder.md`)
- [ ] 6.2 Reconcile interlocutor tier binding with the `universe-visibility` change's anonymous-reader semantics and record the agreed authority/disclosure contract
- [ ] 6.3 Define baseline, metric, and permitted regression for connector tool-selection accuracy, and file it against `live-mcp-connector-surface` (residual of retired task 2.9)
- [ ] 6.4 Only after 6.1–6.3: build the surviving requirements (authorization-before-voice generalization; interlocutor tier binding; scoped commons-side anti-collision write path; forkable persona under first-party custody), each with tests
- [ ] 6.5 Only then: `sync-specs` into `openspec/specs/universe-personification-and-relay/spec.md`, then archive this change
