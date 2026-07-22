## Context

`universe-personification` and the shipped platform disagree about who speaks. The change says
the **chatbot embodies** the universe in first person and never relays; production says the
chatbot is a **thin relay** that renders the universe intelligence's own first-person reply.
Production is right — the embodiment model was live-falsified on 2026-07-02 and the host
directed the reversal the same day.

This design does not re-litigate that reversal. It reconciles the spec system with it: decide
what each of the 11 unchecked tasks means now, retire what is dead, and keep what survives
somewhere durable.

All classifications below were re-verified against `origin/main` at `19bf2534` on 2026-07-22
after the ratified relay correction landed in PR #1578.

## Goals / Non-Goals

**Goals:**
- Classify every unchecked task with a reason traceable to code or spec on `origin/main`.
- Make the reversed tasks unbuildable-by-accident, not merely commented on.
- Preserve surviving intent as requirements on the capability that actually exists.
- Distinguish "already landed" (do not rebuild) from "survives, unbuilt" (real work).

**Non-Goals:**
- Changing runtime code. The relay behavior shipped; this is spec reconciliation.
- Re-deciding embody vs relay. The host decided; production shipped it; it was live-tested.
- Re-amending the ratified narrative spec; PR #1578 already resolved that prerequisite.
- Building the surviving requirements in this reconciliation PR. They remain as deltas in
  this active change until later implementation and tests make them as-built truth.

## Decisions

**D1 — Retire by archive, not delete.** The change's design thinking (authorization-precedes-
voice, the anti-collision contract, tier binding) is real and partly still correct. Archiving to
`openspec/changes/archive/2026-07-22-universe-personification/` preserves all four artifacts —
their original content intact, with a `SUPERSEDED` banner prepended and `tasks.md` annotated
per-task (not "verbatim": the classification is written into the file, which is the point) —
while removing it from `openspec list`, the surface an agent actually reads for claimable work.
Deleting would destroy the reasoning; leaving it active would keep the misdirection live.
*Alternative:* rewrite it in place as a relay-shaped change — rejected: it would rewrite the
history of a merged PR (#1372) and misrepresent what was reviewed and approved.

**D2 — Survivors become deltas against the capability that exists — and STAY in the change until
built.** The surviving items are requirements about the *landed* relay surface, so they are
authored as ADDED requirements on `universe-personification-and-relay`. But they are **not
synced into `openspec/specs/`**: that directory is as-built truth (`openspec/config.yaml`:
*"do not spec aspirations"*; AGENTS.md § Spec-driven development), and every survivor is
explicitly unbuilt. Syncing them would put aspirations into the file that other agents read as
a description of what the platform *does* — reintroducing, in the opposite direction, exactly
the spec-vs-reality gap this change exists to close.
Therefore: **this change stays active** and is the implementation change for the survivors; the
sync happens only when code and tests exist. *(Codex review 2026-07-22 finding 1 — the first
draft had a `sync-specs` task and would have committed this error.)*
*Alternative:* archive this change on merge and sync immediately — rejected for the above.

**D3 — Task 4.1 is marked MUST-NOT-RUN, explicitly and in the file.** A generic "superseded"
banner is not enough for a task whose execution would write the reversed model into
`openspec/specs/`. It gets its own inline warning naming the damage.

The same hazard applies to the retirement itself: `openspec archive` is documented as
"Archive a completed change **and update main specs**" (verified via `openspec archive --help`,
CLI 1.4.1), so running it on this change would have synced the reversed embodiment deltas into
`openspec/specs/universe-personification/` — task 4.1 by another route. `--skip-specs` exists
and would have been safe; this change used the `git mv` procedure the `openspec` skill
documents, which avoids the flag-dependency entirely. Recorded so the next agent retiring a
reversed change does not reach for the default command.

**D4 — "Already landed" claims are code-cited, not asserted.** Per the 2026-07-21
`stale-backlog-rows-misdirect` lesson, a premise stated without verification is the failure mode
being fixed. Every "already landed" row below names the file and the behavior.

## Task-by-task reconciliation

11 unchecked tasks. Verified against `origin/main`.

| Task | Classification | Reason (verified on `origin/main`) |
|---|---|---|
| **2.1** `control_station` prompt: compact first-person embodiment | **REVERSED** | `universe_server.py:209` now instructs the exact opposite — "You do NOT speak as the universe … you are the connector, not the universe." Building this re-instructs chatbot embodiment. |
| **2.2** MCP `instructions` + tool descriptions: persona voice at connect **+** anti-collision guard | **SPLIT — REVERSED + ALREADY LANDED** | Persona-voice-at-connect half is REVERSED (same instructions block now says relay/render). Anti-collision half ALREADY LANDED: `universe_server.py:216` ships "Don't memorize persona views." |
| **2.3** In-voice `assemble(lens) → view` delivery | **REVERSED (mechanism) — intent relocated** | Chatbot-side in-voice view delivery is gone with embodiment. The grounded-assembly intent landed *inside* `converse`: `universe_intelligence.py` assembles a first-person persona system prompt from the universe's own OKF bundle. Lens/assembly work continues in the active `brain-okf-canonical-store` change. |
| **2.4** Authorization-before-voice | **SURVIVES — partially landed** | Still exactly right under relay, and arguably load-bearing. Landed: the `converse` handle is founder-only + fail-closed (as-built spec, "The MCP converse handle is founder-only and fail-closed"). Unbuilt: general pre-assembly filtering by interlocutor — no visitor path exists yet to filter for. |
| **2.5** Visitor actor binding + T0/T1/T2 tier gating | **SURVIVES — unbuilt** | No `identity_tier` / T0-T1-T2 machinery in `tinyassets/*.py`. As-built spec defers public "talk to a stranger's universe" to a later, separately-gated slice. Under relay, the binding attaches to the `converse` caller rather than to a chatbot embodiment session. Adjacent to the active `universe-visibility` change — see Dependencies. |
| **2.6** Anti-collision write path: reject profile-shaped / persona-dossier writes | **SURVIVES — NARROWED/ADAPTED, unbuilt** | The unscoped rule contradicts governed founder learning. The successor limits any future rejection to a defined external/commons endpoint, predicate, and redirect while exempting the universe's own learning path. |
| **2.7** Honest fallback / degraded mode | **ALREADY LANDED** | `universe_intelligence.py:428` raises on a missing universe; `:164` "you are newly born and still learning" for an unnamed universe; `:208` never-infer/never-invent/never-carry-over rules. Three as-built scenarios cover it. |
| **2.8** Persona as a forkable `[composable]` default | **SURVIVES — ADAPTED** | Custody moved first-party. Forking changes universe-side learned self-model/voice content; the operational soul governs the floor but never supplies persona identity, and no script is handed to the chatbot. |
| **2.9** Tool-selection regression tests: embodiment does not degrade accuracy | **REVERSED as written — residual preserved** | There is no embodiment prompt left to regress. The underlying risk survives in changed form (connector instruction density vs tool-selection accuracy), but no threshold-less scenario belongs in this delta; task 6.3 requires a separately defined baseline, metric, and permitted regression against `live-mcp-connector-surface`. |
| **4.1** `sync-specs` → `openspec/specs/universe-personification/spec.md` | **REVERSED — MUST NOT RUN** | Executing this would write the embodiment model into `openspec/specs/`, where it would read as current spec truth beside the as-built relay capability. The most dangerous row in the file. |
| **4.3** Archive after merge | **SURVIVES — actionable now** | PR #1372 merged 2026-06-25. This change performs the archive (with classification attached). |

### Requirement-by-requirement reconciliation

The retired delta contains nine behavioral requirements in addition to its task ledger. Every
one is classified here so archiving cannot silently discard intent:

| Retired requirement | Classification | Disposition |
|---|---|---|
| Every universe interaction is the named projection of the whole mind | **SURVIVES — ADAPTED** | Carried into the successor for conversational/outbound speaking surfaces; the old ban on neutral tool-only surfaces is narrowed because PR #1578 explicitly preserves direct-control action tools. |
| Authorization precedes voice | **SURVIVES — partially landed** | Carried into the successor; founder-only `converse` is the current narrow floor, general pre-assembly filtering remains unbuilt. |
| The founder's chatbot embodies the persona | **REVERSED** | Retired. The universe intelligence speaks; the chatbot relays and never impersonates it. |
| Persona views never enter host chatbot memory | **SPLIT — advisory landed / enforcement ADAPTED and unbuilt** | Host-memory guidance is advisory; any enforceable rejection is limited to a separately defined external/commons write boundary and exempts governed founder learning. |
| OAuth binds the user, embodied persona, and identity tier | **SURVIVES — ADAPTED and unbuilt** | Ownership/founder gating remains; embodiment-session language is removed and tier binding attaches to the authenticated `converse` caller. |
| Visitors interact with the persona behind the pre-rendering floor | **SURVIVES — unbuilt** | Carried across the authorization and interlocutor-tier successor requirements; disclosure semantics must reconcile with `universe-visibility` before implementation. |
| One identity, modulated by interlocutor and surface | **SURVIVES — unbuilt** | Carried into the successor with identity sourced only from the learned self-model; soul governs but never supplies identity. |
| Honest fallback — no invented persona state | **ALREADY LANDED** | Preserved in the canonical as-built relay spec and current runtime; do not rebuild. |
| Tiny is the platform universe's personification | **SURVIVES — unbuilt** | Carried into the successor as a governed self-as-platform requirement with no special authority bypass. |

**Rollup (11 tasks):** **4 reversed** (2.1, 2.3, 2.9, 4.1) · **1 split** — reversed + already
landed (2.2) · **5 survive** (2.4, 2.5, 2.6, 2.8, and 4.3 which is discharged by this change) ·
**1 already landed** (2.7). *(Corrected per Codex review 2026-07-22 finding 5 — an earlier
rollup said "4 survive · 2 already landed", double-counting 4.3.)*

At retirement time, tasks **1.1–1.3** were checked `[x]` and annotated "NOT applied in this
draft", while the ratified paragraph still carried the full embody / "never relays" invariant.
That disagreement made it a fourth stale source. PR #1578 / `f605bb99` subsequently corrected
the paragraph to the relay model before this reconciliation was allowed to land.

## Dependencies

- **`universe-visibility`** (active, 0/10) defines per-universe/per-page visibility levels for
  unauthenticated readers. Task 2.5's interlocutor tier binding is adjacent but distinct:
  visibility governs *what a reader may read*, tier binding governs *who the persona is
  talking to*. They must agree on the anonymous-reader definition. Recorded as a cross-ref,
  not duplicated here.
- **`brain-okf-canonical-store`** (active, 9/16) owns the assembled-view content that 2.3's
  intent relocated into. No requirement of it changes here.
- **`live-mcp-connector-surface`** owns connector vocabulary and tool-selection evidence.
  Task 6.3 must define its baseline, metric, and permitted regression there before any
  connector-density claim becomes a requirement.

## Risks / Trade-offs

- **Archiving hides the reasoning from `openspec list`** — mitigated: survivors are promoted to
  the active successor delta spec, so nothing actionable lives only in the archive.
- **Seven surviving requirements remain unimplemented** — intentional and explicit. They remain
  only in this active change; canonical `openspec/specs/` stays as-built truth until code and
  tests land.

## Cross-provider review

Opposite-provider gate dispatched to Codex 2026-07-22 (`scripts/codex_review.py`, background
offload) covering: (a) is any classification wrong against `origin/main`, (b) is surviving
intent lost by archiving, (c) is archive-plus-new-change the right OpenSpec move.

> ### Verdict: **ADAPT** (Codex, 2026-07-22) — all 5 findings folded.

Codex independently confirmed the relay behavior in code, ran 55 focused tests (passed), and
validated all 29 OpenSpec items (strict, passed). It **upheld the 11-task classification** — no
row was wrong — and instead found defects in the *reconciliation's own design*:

| # | Severity | Finding | Fold |
|---|---|---|---|
| 1 | Critical | Syncing the explicitly-unbuilt survivors into `openspec/specs/` violates as-built-truth (`config.yaml` "do not spec aspirations"). | **D2 rewritten**; `sync-specs` task removed; this change stays active as the implementation change. Verified in `openspec/config.yaml:36` + AGENTS.md. |
| 2 | Critical | The anti-collision requirement conflated host-memory ingestion (not enforceable) with TinyAssets writes, and contradicted landed behavior that deliberately persists founder facts to `founder.md`. | Requirement **rewritten** to state the advisory boundary honestly, exempt the governed learning path, and demand endpoint/predicate/redirect be named before implementation. Verified at `universe_intelligence.py:39,219`. |
| 3 | Required | The host question's "let it stand as historical ratification" option would leave normative-looking text alive. | Question **reframed** to two active options (amend / mark superseded); "do neither" explicitly ruled out. |
| 4 | Required | Tool-selection regression scenario was misplaced under persona forkability with no threshold. | **Removed from the spec**; carried as task 6.3 against `live-mcp-connector-surface` with baseline/metric/threshold required. |
| 5 | Nit | Rollup miscounted (4 survive / 2 landed vs actual 5 / 1); "preserves every artifact verbatim" was inaccurate. | Rollup **corrected**; D1 wording fixed. |

Findings 1 and 2 were re-verified against the repo before folding rather than accepted on
report. Both were real: the first draft of this change would have written aspirational
requirements into as-built truth, and would have specced a rule contradicting shipped code.

## Host decision resolved

PR #1578 landed at `f605bb99` on 2026-07-22 and amended the ratified paragraph to the relay
model. Its review also made the anti-collision boundary truthful: host-memory guidance is
advisory, while any future profile/dossier rejection must be narrowly defined on an
external/commons endpoint and must exempt governed founder learning. This closes the only
host-visible prerequisite without syncing any unbuilt delta into canonical as-built specs.

## Migration Plan

Spec-only; no runtime change, so no rollback is required. This PR banners, classifies, and
archives the reversed change, then leaves this successor change active. Definition and
cross-capability tasks 6.1–6.3 gate independently landable implementation tasks 6.4–6.10; only
then may task 6.11 sync the seven ADDED requirements into
`openspec/specs/universe-personification-and-relay/spec.md` and archive this change.
