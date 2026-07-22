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
- [x] 5.2 Codex verdict **ADAPT** recorded in `design.md` §"Cross-provider review"; all 5 findings folded (classification upheld — the findings were against this change's own design)
- [x] 5.3 Re-verify Codex findings 1 + 2 against the repo before folding, rather than accepting on report
- [ ] 5.4 **Host decision** — amend ratified `docs/specs/2026-06-10-tiny-first-principles-spec.md:128` to the relay model, **or** mark it explicitly superseded with a pointer? (`design.md` §"Host decision required"; doing neither is not an option)
- [x] 5.5 Draft PR opened — #1515; **do NOT merge** — a spec reversal is host-visible

## 6. Implementation (this change stays ACTIVE until these land)

> Codex finding 1: the survivors are unbuilt, and `openspec/specs/` is as-built truth
> (`openspec/config.yaml`: "do not spec aspirations"). There is deliberately **no `sync-specs`
> task here** — the sync happens only after the code and tests below exist.

- [ ] 6.1 Build the surviving requirements (authorization-before-voice generalization; interlocutor tier binding; scoped commons-side anti-collision write path; forkable persona under first-party custody), each with tests
- [ ] 6.2 Define the anti-collision write restriction concretely before implementing it — exact endpoint, predicate, redirect destination — and confirm it does not restrict the governed founder-learning path (`founder.md`)
- [ ] 6.3 Define baseline, metric, and permitted regression for connector tool-selection accuracy, and file it against `live-mcp-connector-surface` (residual of retired task 2.9)
- [ ] 6.4 Reconcile interlocutor tier binding with the `universe-visibility` change's anonymous-reader semantics
- [ ] 6.5 Only then: `sync-specs` into `openspec/specs/universe-personification-and-relay/spec.md`, then archive this change
