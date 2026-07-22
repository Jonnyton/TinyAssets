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

> **Landedness re-verified 2026-07-22** (`design.md` §"Section 6 landedness re-verification").
> Every implementation task below is **partially satisfied or unbuilt — verify the citation
> before building**. None is complete. Rollup: 2 definitions discharged · 1 split · 3 partial
> (6.4, 6.5, 6.8) · 4 unbuilt (6.6, 6.7, 6.9, 6.10) · 1 gated (6.11).

- [x] 6.1 Define the anti-collision write restriction concretely before implementation — exact external/commons endpoint, predicate, redirect destination — and confirm it does not restrict the governed founder-learning path (`founder.md`)
      → `design.md` §"Task 6.1". **Endpoint:** the `write_page` issue-filing branch
      (`universe_server.py:816-833`) — NOT the commons at large. The plain-page commons write
      (`:882-902`) is **unreachable in production**: authenticated callers always redirect to
      `relay_to_universe` (`_request_universe` never returns empty, `api/helpers.py:89-116,144`)
      and anonymous mutating writes are refused by `write_gate_rejection` (`middleware.py:443-464`).
      **Predicate:** structural — a declared non-self `subject_person` field, NOT a content
      classifier. **Redirect:** the shipped `status="relay_to_universe"` shape (`:876-881`).
      **`founder.md` exemption confirmed by construction** — it is written only by
      `commit_learning` (`universe_intelligence.py:334`), which `write_page` never calls.
- [x] 6.2 Reconcile interlocutor tier binding with the `universe-visibility` change's anonymous-reader semantics and record the agreed authority/disclosure contract
      → `design.md` §"Task 6.2", contracts **A1–A5**: one anonymous predicate from
      `is_authenticated_request()` (T0 ≡ universe-visibility's "unauthenticated reader");
      visibility is the **ceiling**, tier is the **selector**; T1 defaults to the T0 surface;
      disclosure is stated by the connector, never by the voice; fail-closed composes.
- [x] 6.3a Define the metric, population, prompt set, protocol, and permitted regression for connector tool-selection accuracy, filed against `live-mcp-connector-surface` (residual of retired task 2.9)
      → `design.md` §"Task 6.3". First-tool-call accuracy over `CANONICAL_HANDLES`
      (`scripts/mcp_public_canary.py:70-79`), ≥5 user-phrased prompts per handle, measured through
      the rendered chatbot per `ui-test`; regression rule = −5pp aggregate AND no handle at zero.
- [ ] 6.3b Measure and record the tool-selection accuracy **baseline** via a live `ui-test` run — not derivable from the repo, and deliberately left unstated rather than fabricated. Gates 6.11.
- [ ] 6.4 Implement the whole-mind personification contract on speaking surfaces, including proof that direct-control tools remain neutral and never fabricate universe voice
      → **PARTIALLY LANDED.** Relay contract `universe_server.py:208-216`; first-person assembly
      `universe_intelligence.py:123-160`; direct-control neutrality `:876-881`; proof
      `tests/test_persona.py:286,344,369,392`. **Remaining:** only one speaking surface exists
      (`converse`, sole caller `universe_server.py:977`; zero `outbound` hits), so the
      multi-surface half of the requirement is untestable until a second surface ships.
- [ ] 6.5 After 6.2: implement authorization-before-voice generalization with tests proving unauthorized content never enters persona assembly
      → **PARTIALLY LANDED (narrowest floor).** The founder-only fail-closed gate
      (`universe_server.py:956-975`) already satisfies the third scenario. **Remaining:**
      `_build_persona_system_prompt(universe_dir)` (`universe_intelligence.py:123`) takes **no
      interlocutor parameter** and is structurally incapable of filtering; scenarios 1–2 have no
      subject until a non-founder path exists.
- [ ] 6.6 After 6.2: implement authenticated interlocutor tier binding with cross-principal and `universe-visibility` disclosure tests
      → **UNBUILT, and BLOCKED — not merely gated.** No `identity_tier`/T0/T1/T2 machinery exists
      (every `*_tier` symbol in `tinyassets/` is a different axis). Per contract A2 this is
      **blocked on `universe-visibility` tasks 1.1–1.3** (that change is 0/10) — the "what
      visibility grants tier T" term is undefined until they land.
- [ ] 6.7 After 6.1: implement the scoped external/commons anti-collision boundary with predicate, redirect, governed-learning exemption, and adversarial tests
      → **UNBUILT, and much smaller than it reads** now that 6.1 has scoped it: one endpoint
      (the issue-filing branch), one structural predicate, an already-shipped redirect shape, and
      an exemption that holds by construction. Assert the exemption with a live
      `commit_learning` test anyway — an unexercised carve-out silently disappears.
- [ ] 6.8 Implement forkable first-party persona custody with tests proving identity comes from learned self-model content while soul remains governance input and never supplies or replaces persona identity
      → **SUBSTANTIALLY PARTIAL.** Identity-from-self-model and soul-never-supplies-identity are
      landed and proven (`persona.py:119-122`; `tests/test_persona.py:101,198`), as is first-party
      custody (`universe_intelligence.py:123-131`; `tests/test_persona.py:326`). **Remaining: the
      fork itself** — zero `fork` hits in `persona.py`, `universe_self_model.py`,
      `universe_bundle.py`. No fork operation, no fork test.
- [ ] 6.9 Implement one learned identity across speaking surfaces with tests for surface/interlocutor modulation without identity replacement
      → **UNBUILT AS STATED, and currently VACUOUS.** Two of its three surfaces do not exist (no
      visitor path — see 6.5; no outbound surface — see 6.4). A test written today would pass
      without exercising the invariant. **Depends on 6.4 and 6.6**, an ordering the original list
      did not express.
- [ ] 6.10 Implement Tiny as the platform universe's governed personification with tests proving self-as-platform grants no authority bypass
      → **UNBUILT.** The only `Tiny` occurrence in `tinyassets/*.py` is a comment
      (`universe_soul.py:28`); every other hit is a test fixture string. No platform universe is
      named or bound.
- [ ] 6.11 Only after 6.4–6.10 and the task 6.3b connector evidence gate: `sync-specs` into `openspec/specs/universe-personification-and-relay/spec.md`, then archive this change
      → Still MUST NOT RUN. Re-affirmed: `openspec archive` silently syncs specs (D3), so
      reaching for the default command here would write unbuilt requirements into as-built truth.
