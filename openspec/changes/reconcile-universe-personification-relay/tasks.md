## 1. Verify the contradiction (done in this change)

- [x] 1.1 `git fetch --prune`; classify against `origin/main` at `2c1f63cb`, not the stale local checkout
- [x] 1.2 Confirm source 1 — host directive: `STATUS.md` `[filed:2026-07-02] RESHAPE`, "Do NOT build more chatbot-embodiment"
- [x] 1.3 Confirm source 2 — `docs/design-notes/2026-07-02-universe-intelligence-relay-architecture.md` §3 (why embodiment was live-falsified)
- [x] 1.4 Confirm source 3 — shipped code: `tinyassets/universe_server.py:208` ("You do NOT speak as the universe … RELAY … RENDER")
- [x] 1.5 Confirm the landed as-built capability `openspec/specs/universe-personification-and-relay/spec.md` codifies relay
- [x] 1.6 Find the **fourth** stale source: ratified `docs/specs/2026-06-10-tiny-first-principles-spec.md:128` still says "never relays" despite task 1.1 claiming amendments unapplied

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
- [x] 4.2 Record the 2.9 residual (connector instruction density vs tool-selection accuracy) as a scenario rather than an embodiment test
- [x] 4.3 Cross-reference `universe-visibility` (anonymous-reader semantics) and `brain-okf-canonical-store` (assembled-view content) instead of duplicating them

## 5. Gates

- [x] 5.1 Opposite-provider review dispatched to Codex (background `scripts/codex_review.py`)
- [ ] 5.2 Record the Codex verdict (approve / adapt / reject) in `design.md` §"Cross-provider review" and fold any adaptations
- [ ] 5.3 **Host decision** — amend ratified `docs/specs/2026-06-10-tiny-first-principles-spec.md:128` to the relay model, or let it stand as historical ratification? (`design.md` §"Host decision required")
- [ ] 5.4 Draft PR opened; **do NOT merge** — a spec reversal is host-visible

## 6. Fold-back (after host approval — NOT in this draft)

- [ ] 6.1 `sync-specs` the four ADDED requirements into `openspec/specs/universe-personification-and-relay/spec.md`
- [ ] 6.2 Open a follow-up change to BUILD the surviving requirements (this change ships spec only, no code)
- [ ] 6.3 Archive this change
