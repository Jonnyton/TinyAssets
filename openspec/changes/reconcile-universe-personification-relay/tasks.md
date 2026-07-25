## 1. Verify the contradiction (done in this change)

- [x] 1.1 `git fetch --prune`; classify against `origin/main`, then re-verify at `7a118dca` after PR #1578
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

- [x] 4.1 Seven ADDED requirements on `universe-personification-and-relay`, covering every surviving retired requirement (whole-mind speaking surfaces; authorization-before-voice; interlocutor tier binding; narrowed anti-collision boundary; forkable first-party persona; one learned identity across surfaces; Tiny as governed platform personification)
- [x] 4.2 Remove the threshold-less 2.9 scenario from this delta; carry connector instruction-density vs tool-selection accuracy as definition task 6.3 against `live-mcp-connector-surface`
- [x] 4.3 Cross-reference `universe-visibility` (anonymous-reader semantics) and `brain-okf-canonical-store` (assembled-view content) instead of duplicating them

## 5. Gates

- [x] 5.1 Opposite-provider review dispatched to Codex (background `scripts/codex_review.py`)
- [x] 5.2 Codex verdict **ADAPT** recorded in `design.md` §"Cross-provider review"; all 5 findings folded (classification upheld — the findings were against this change's own design)
- [x] 5.3 Re-verify Codex findings 1 + 2 against the repo before folding, rather than accepting on report
- [x] 5.4 **Host decision resolved** — PR #1578 / `f605bb99` amended the ratified paragraph to the relay model (`design.md` §"Host decision resolved")
- [x] 5.5 Draft PR opened — #1515; auto-merge disabled while the prerequisite and current-base repairs were incomplete
- [x] 5.6 Re-run current-base gates at `7a118dca`: strict all-spec validation 29/29, archive annotations 11/11, successor requirements/scenarios 7/17, focused tests 75 passed + 1 skipped, diff checks clean, independent final review APPROVE

## 6. Implementation (this change stays ACTIVE until these land)

> Codex finding 1: the survivors are unbuilt, and `openspec/specs/` is as-built truth
> (`openspec/config.yaml`: "do not spec aspirations"). There is deliberately **no
> pre-implementation `sync-specs`** — task 6.11 becomes eligible only after the code and tests
> below exist.
>
> **Section-6 disposition premise-verified against `origin/main` 2026-07-24; cross-family
> review Codex ADAPT 2026-07-24. Per-task rollup, endpoint inventory, the 6.2 reconciliation
> contract, and the 6.3 metric definition live in `implementation-notes.md`.** 6.1–6.3 are
> *definition* gates (advanceable now); 6.4–6.11 are *implementation* tasks that need code +
> tests. An unbuilt implementation dependency does not block the definition that gates it.

- [ ] 6.1 Define the anti-collision write restriction concretely before implementation — exact external/commons endpoint, predicate, redirect destination — and confirm it does not restrict the governed founder-learning path (`founder.md`) — **ADVANCED (host-gated residual):** endpoint (both `write_page` servers' commons path), redirect (`converse`), and founder-learning exemption named in `implementation-notes.md` §6.1; the *whether-to-enforce + exact person-dossier predicate* is the residual host decision (open PR #1583, audit-only "DO NOT MERGE without host review", recommends a `host-decision`). Do NOT implement (that is 6.7) until it resolves.
- [x] 6.2 Reconcile interlocutor tier binding with the `universe-visibility` change's anonymous-reader semantics and record the agreed authority/disclosure contract — **DISCHARGED:** spec-level tier↔visibility contract recorded in `implementation-notes.md` §6.2 (T0 ≡ unauthenticated reader; disclosure = tier ∩ visibility; fail-closed on undeclared; source-separation). Implementation is 6.6, still blocked on `universe-visibility` machinery.
- [ ] 6.3 Define baseline, metric, and permitted regression for connector tool-selection accuracy, and file it against `live-mcp-connector-surface` (residual of retired task 2.9) — **ADVANCED (definition drafted, filing pending):** baseline/metric/permitted-regression shape in `implementation-notes.md` §6.3. Turning it into a requirement is a separate change against `live-mcp-connector-surface` (needs the labelled prompt→handle dataset + harness; not synced into as-built specs now).
- [ ] 6.4 Implement the whole-mind personification contract on speaking surfaces, including proof that direct-control tools remain neutral and never fabricate universe voice — **PARTIALLY LANDED:** `converse` first-person surface proven (`test_universe_intelligence.py::test_system_prompt_is_first_person_and_grounded`); direct-control neutrality proven (`test_persona.py::test_write_graph_persona_target_is_retired`, `test_relay_ux_prompts.py`). Outbound speaking surfaces do not exist yet — the requirement's "outbound surfaces" clause has nothing to discharge until one ships.
- [ ] 6.5 After 6.2: implement authorization-before-voice generalization with tests proving unauthorized content never enters persona assembly — **BLOCKED (no non-founder path):** general pre-assembly interlocutor filtering has nothing to filter for until a non-founder conversation path exists; the founder-only fail-closed `converse` floor is already landed + tested.
- [ ] 6.6 After 6.2: implement authenticated interlocutor tier binding with cross-principal and `universe-visibility` disclosure tests — **BLOCKED (unbuilt dependency):** no `identity_tier`/T0/T1/T2 machinery in `tinyassets/*.py`; needs `universe-visibility` enforcement machinery (0/10). Contract agreed (6.2); implementation gated.
- [ ] 6.7 After 6.1: implement the scoped external/commons anti-collision boundary with predicate, redirect, governed-learning exemption, and adversarial tests — **BLOCKED (host decision):** gated on the #1583 enforce/predicate decision (6.1 residual).
- [ ] 6.8 Implement forkable first-party persona custody with tests proving identity comes from learned self-model content while soul remains governance input and never supplies or replaces persona identity — **CORE LANDED, custody residual unbuilt (NOT checked):** identity-source core proven (`test_persona.py::test_resolve_persona_identity_never_comes_from_soul`, `persona.py:94-125`, as-built spec "Persona identity is sourced from the learned self-model, never the operational soul"). The *forkable custody* mechanism (founder tuning of the self-model voice) is not separately built/proven.
- [ ] 6.9 Implement one learned identity across speaking surfaces with tests for surface/interlocutor modulation without identity replacement — **BLOCKED (after 6.2 impl / 6.6):** cross-surface + interlocutor-modulation needs the multi-surface + tier paths that do not exist. Single-surface identity-not-replaced is the same landed core as 6.8.
- [ ] 6.10 Implement Tiny as the platform universe's governed personification with tests proving self-as-platform grants no authority bypass — **BLOCKED (unbuilt/design-gated):** no `Tiny`/platform-universe personification code exists; a substantial feature intersecting platform-universe architecture that needs its own design gate.
- [ ] 6.11 Only after 6.4–6.10 and the task 6.3 connector evidence gate: `sync-specs` into `openspec/specs/universe-personification-and-relay/spec.md`, then archive this change — **BLOCKED — MUST NOT RUN:** gated on 6.4–6.10 + 6.3; running it now writes unbuilt aspirations into `openspec/specs/`, the exact failure this change exists to prevent.
