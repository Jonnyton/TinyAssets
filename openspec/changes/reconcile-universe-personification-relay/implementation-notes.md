# Section 6 implementation notes — dispositions, inventory, and definitions

> Premise-verified against `origin/main` on 2026-07-24. Companion to `tasks.md`
> §6 and `design.md`. This change stays **active/unbuilt** by design (D2): the
> survivors are aspirations and MUST NOT be synced into `openspec/specs/` until
> code + tests make them as-built truth. This file records what each Section-6
> task actually needs, why most are blocked, and the definitions/inventory that
> can be produced now without a host decision.

## Section 6 disposition rollup (11 tasks)

Section 6 has two kinds of task: **definition/reconciliation gates** (6.1–6.3, which produce a
recorded contract and can advance now) and **implementation tasks** (6.4–6.11, which need code +
tests). The distinction is load-bearing: an unbuilt *implementation* dependency does not block the
*definition* that gates it (design.md:173-175). Cross-family review (Codex, 2026-07-24, ADAPT)
corrected an earlier draft that over-blocked 6.1/6.2 and over-claimed 6.8.

| Task | Kind | Disposition | Blocker / evidence |
|---|---|---|---|
| 6.1 define anti-collision write boundary | definition | **DISCHARGED** | Host 2026-07-25 selected explicit canonical `write_page scope=commons|universe`; commons stays authenticated-writable; universe redirects to `converse`; no prose classifier; governed founder learning remains exempt (design D5). |
| 6.2 reconcile tier binding w/ `universe-visibility` | definition | **DISCHARGED — contract recorded** | Spec-level reconciliation (§"6.2 reconciliation contract" below). `universe-visibility` defines unauthenticated-reader semantics *at spec level* (its delta spec: existence/metadata/content as three separately-granted capabilities, per-universe + per-page, fail-closed); the tier↔visibility contract is agreed against that. Implementation (6.6) stays blocked on that change's machinery. |
| 6.3 define connector tool-selection metric | definition | **ADVANCED — filing pending** | Definition shape below. `live-mcp-connector-surface` has no tool-selection-accuracy requirement (spec grep). Turning it into a requirement is a separate change (out of this Files boundary + would be an aspiration in as-built truth). |
| 6.4 whole-mind personification on speaking surfaces | impl | **PARTIALLY LANDED** | `converse` first-person surface + direct-control neutrality proven (evidence below). Outbound speaking surfaces do not exist yet, so the contract cannot be fully discharged. |
| 6.5 authorization-before-voice generalization | impl | **BLOCKED — after 6.2** | General pre-assembly interlocutor filtering needs a non-founder path; none exists. The narrow floor (founder-only, fail-closed `converse`) is already landed + tested. |
| 6.6 authenticated interlocutor tier binding | impl | **BLOCKED — after 6.2 impl** | No `identity_tier`/T0/T1/T2 machinery in `tinyassets/*.py` (grep returns only a stale comment in `cloud_worker.py`); needs `universe-visibility` machinery, which is 0/10. |
| 6.7 implement scoped anti-collision boundary | impl | **IMPLEMENTED IN THIS SLICE** | Canonical `write_page` validates `scope=commons|universe`, fails closed on contradictions/unknowns, preserves omission and auth behavior, and leaves governed learning unchanged; covered by focused routing/public-surface tests. |
| 6.8 forkable first-party persona custody | impl | **CORE LANDED — custody residual unbuilt (NOT checked)** | Identity-source core proven: `tests/test_persona.py::test_resolve_persona_identity_never_comes_from_soul` + `persona.py:94-125` + as-built spec requirement "Persona identity is sourced from the learned self-model, never the operational soul". The *forkable custody* mechanism (founder tuning of the self-model voice) is not separately proven, so the task stays unchecked. |
| 6.9 one identity across speaking surfaces | impl | **BLOCKED — after 6.2/6.6** | Cross-surface/interlocutor modulation needs the multi-surface + tier paths that do not exist. The single-surface identity-not-replaced invariant is the same landed core as 6.8. |
| 6.10 Tiny as platform personification | impl | **BLOCKED — unbuilt/design-gated** | No `Tiny`/platform-universe personification code exists; this is a substantial feature that intersects platform-universe architecture and needs its own design gate. |
| 6.11 sync-specs + archive | impl | **BLOCKED — MUST NOT RUN** | Gated on 6.3–6.10. Running it now writes unbuilt aspirations into `openspec/specs/` — the exact failure this change exists to prevent. |

**Current correction (2026-07-29):** the task ledger is authoritative over the stale rows below:
6.3, 6.6, and 6.8 are landed; 6.9's interlocutor half is landed; and this slice completes
6.1/6.7. Tasks 6.4, 6.5, 6.9-cross-surface, 6.10, and 6.11 remain blocked on surfaces/design
gates this slice does not open.

Historical rollup before those landings: **1 discharged (6.2), 2 advanced-definition (6.1 host-gated residual, 6.3 filing pending),
1 partial (6.4), 1 core-landed-not-checked (6.8), 6 blocked** on the open host decision
(#1583 → 6.7), the unbuilt `universe-visibility` *machinery* (→ 6.5/6.6/6.9), unbuilt
platform-universe personification (→ 6.10), or the above gates (→ 6.11). Forcing the blocked
implementation tasks would rebuild the wrong shape and reintroduce the
`stale-backlog-rows-misdirect` failure mode this change was created to close.

## 6.1 — anti-collision write-boundary endpoint inventory

**Superseded by the 2026-07-25 host decision and design D5.** The implemented predicate is the
exact canonical `write_page` target enum (`scope=commons|universe`), never prose shape.
`scope=commons` keeps authenticated shared-commons writes available and rejects a simultaneous
`universe_id`; `scope=universe` returns the existing `relay_to_universe` envelope naming
`converse`; unknown values fail closed; omission preserves compatibility. Current main has one
advertised remote endpoint (`/mcp`); the retired directory and hidden legacy-wiki surfaces named
in the historical inventory below are not implementation targets. The in-process governed
learning path remains exempt.

The delta requirement ("The anti-collision boundary is stated honestly …") mandates that any
write restriction "SHALL name its exact endpoint, its predicate, and its redirect destination
before it is implemented." Below is the enumerated write surface so the host decision has a
concrete target. The **predicate** (what counts as profile-shaped / person-dossier content) and
whether to enforce at all remain the host's call (#1583).

**Enforceable write endpoints (TinyAssets-side):**

- `tinyassets/universe_server.py::write_page` (canonical `/mcp`, `anonymous_write_challenge=True`):
  - **Issue filings** (`kind=bug|patch_request|feature|design`) → always land on the shared
    **commons** (`_wiki_impl(action="file_bug", …)`, ~L846). Coordination content, not persona.
  - **Page write/patch with a universe target** → returns a `relay_to_universe` directive
    (~L864-880); private canon is written by the universe's own intelligence via `converse`,
    never by the chatbot relay. Already collision-safe by construction.
  - **Page write/patch with NO universe target** → shared **commons** write (~L869-878).
    *This is the anti-collision surface.* Today there is no person-dossier predicate here; a
    profile-shaped write to the commons is not refused/redirected.
- `tinyassets/directory_server.py::write_page` (L437) — the directory-server write path;
  same commons-vs-relay shape, must be covered by any predicate so the boundary is not
  bypassable via the other server. (Per #1583 Finding 2, the platform is "not gapped" because
  private canon relays, but the commons predicate would need to apply to both servers.)
- `tinyassets/universe_server.py::write_graph` (`anonymous_write_challenge=True`) — targets
  `goal|request|branch|universe`; the `persona` target is already **retired**
  (`tests/test_persona.py::test_write_graph_persona_target_is_retired`), so it cannot fabricate
  persona identity. Direct-control, collision-safe.

**Governed-learning exemption (MUST NOT be restricted):** the universe intelligence's own
learning path deliberately and correctly persists founder facts to `founder.md`
(`universe_intelligence.py` `_GROUNDING_FILES = ("identity.md", "founder.md", "origin.md",
"body.md")`, and the `_LEARNING_SYSTEM` extractor's `"founder.md": "<markdown: who my founder
is>"`). Any commons predicate MUST exempt this path — an unscoped "reject profile-shaped writes"
rule would break governed founder learning, the defect Codex finding 2 caught.

**Redirect destination (proposed, host to confirm):** a refused commons person-dossier write
should name `converse` (relay to the target universe's own governed learning path) as the
correct destination, rather than failing silently — matching the third delta scenario.

**Host decision needed (#1583):** (a) enforce a commons person-dossier predicate at all? (b) if
so, the exact predicate; (c) the redirect UX. Until resolved, 6.1/6.7 stay blocked.

## 6.2 — tier-binding ↔ visibility reconciliation contract (recorded)

The delta requirement "Interlocutor identity binds to a tier before the universe answers" must
agree with the `universe-visibility` change on what an unauthenticated reader may see. Both are
spec-level today (tier binding is unbuilt here; visibility is 0/10). The reconciliation is
therefore agreed at the spec/principle level and re-checked before 6.6 implements.

**Two orthogonal axes, both required, neither substitutes for the other:**

- **Tier binding (this change)** answers *who is the persona talking to*: `T0` = no TinyAssets
  OAuth to the universe (anonymous); `T1` = a durable host/OAuth subject; `T2` = a verified
  founder. Resolved from authenticated request state, never from message content.
- **Visibility (`universe-visibility`)** answers *what may this reader read*: existence
  discovery, metadata read, and content read as three **separately-granted** capabilities,
  evaluated **per universe and per page**, **fail-closed** when a universe's level is undeclared,
  and reported observably to a permitted reader.

**Agreed anonymous-reader definition:** `T0` (this change) ≡ the "unauthenticated reader" of
`universe-visibility`. They denote the same principal — the caller with no OAuth to the target
universe.

**Agreed authority/disclosure contract:**

1. A conversation turn's disclosure to the interlocutor is the **intersection** of (a) what the
   interlocutor's tier authorizes and (b) what the target universe/page's declared visibility
   level permits that reader. A `T0`/anonymous interlocutor's persona reply and its assembled
   context MUST NOT reveal content the universe's visibility level withholds from an
   unauthenticated reader (existence, metadata, or content, per that level). This feeds the
   "Authorization precedes voice" requirement: the exclusion happens during assembly, not by a
   prompt instruction to withhold.
2. **Fail-closed agreement:** if the target universe has no declared visibility level,
   `universe-visibility` refuses the read; correspondingly, a `T0` conversation turn against an
   undeclared universe is refused rather than served — the same fail-closed posture the two
   capabilities share.
3. **Separation of source:** tier comes only from authenticated request state; visibility comes
   only from the universe/page declaration. Neither is inferred from the other, and neither is
   taken from message content.
4. **Founder path unchanged:** `T2`/founder retains founder-tier disclosure on their own
   universe; visibility levels bound *anonymous/other-reader* disclosure, not the founder's own
   access to their own universe.

**Residual for 6.6 (implementation, blocked):** the actual tier-resolution + per-page visibility
enforcement machinery does not exist (`universe-visibility` is 0/10; no `identity_tier` in code).
This contract is the agreed target; if the `universe-visibility` delta materially changes its
level definitions before 6.6 lands, re-verify this section against it.

## 6.3 — connector tool-selection accuracy metric (definition shape)

Residual of retired task 2.9 (Codex review 2026-07-22 finding 4). There is no embodiment prompt
left to regress; the surviving risk is **connector instruction density vs tool-selection
accuracy** — as the server `instructions` + `control_station` prompt grow, does the host chatbot
still pick the right handle? This belongs to `live-mcp-connector-surface` (owns the prompt
catalog + the canonical seven-handle set), not to persona forkability, and cannot become a
requirement until baseline/metric/threshold exist. Drafted shape:

- **Subject under test:** the connecting chatbot's handle choice given the shipped server
  `instructions` + `control_station` prompt over the canonical handles (`read_graph`,
  `write_graph`, `run_graph`, `read_page`, `write_page`, `converse`, optional `get_status`).
- **Baseline:** handle-selection accuracy on a fixed, labelled prompt→expected-handle set
  measured against the **current** instruction density (pre-any-new-personification-text). The
  labelled set does not exist yet and must be authored by the connector-surface owner.
- **Metric:** top-1 correct-handle rate on that fixed set (and, secondarily, the
  `converse`-first-on-opening rate the `first-contact` flow depends on).
- **Permitted regression:** the maximum allowed drop in top-1 accuracy when personification text
  is added to the sanctioned channels. Recommended default **0 pp** (no regression) until the
  connector owner sets a tolerance; a proposed change that regresses beyond it fails the gate.

**Filing route:** this definition is authored here (in-boundary). Turning it into a *requirement*
against `live-mcp-connector-surface` is a separate OpenSpec change with the labelled dataset +
harness; it is NOT synced into `openspec/specs/live-mcp-connector-surface/` now, because the
metric is not yet as-built.

## 6.4 — evidence that the converse speaking surface + direct-control neutrality are landed

- **First-person whole-mind speaking surface:** `universe_intelligence._build_persona_system_prompt`
  assembles a first-person system prompt grounded in the universe's OKF bundle; proven by
  `tests/test_universe_intelligence.py::test_system_prompt_is_first_person_and_grounded` and
  `::test_unnamed_newborn_prompt_is_honest`.
- **Direct-control tools stay neutral / never fabricate voice:** the `write_graph` persona
  target is retired (`tests/test_persona.py::test_write_graph_persona_target_is_retired`); the
  connector relays + renders and never composes the universe's voice
  (`tests/test_relay_ux_prompts.py`, and `test_persona.py` asserts "data, never instructions" /
  "never wrap the reply as your own quotation").
- **Not yet dischargeable:** outbound speaking surfaces (e.g. autonomous outbound posts) do not
  exist, so the requirement's "outbound surfaces" clause has nothing to satisfy. 6.4 stays
  partial until an outbound speaking surface ships.
