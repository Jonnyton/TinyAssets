## Context

`universe-personification` and the shipped platform disagree about who speaks. The change says
the **chatbot embodies** the universe in first person and never relays; production says the
chatbot is a **thin relay** that renders the universe intelligence's own first-person reply.
Production is right — the embodiment model was live-falsified on 2026-07-02 and the host
directed the reversal the same day.

This design does not re-litigate that reversal. It reconciles the spec system with it: decide
what each of the 11 unchecked tasks means now, retire what is dead, and keep what survives
somewhere durable.

All classifications below were verified against `origin/main` at `2c1f63cb` on 2026-07-22
(`git fetch --prune` first; the local checkout was 15 commits behind).

## Goals / Non-Goals

**Goals:**
- Classify every unchecked task with a reason traceable to code or spec on `origin/main`.
- Make the reversed tasks unbuildable-by-accident, not merely commented on.
- Preserve surviving intent as requirements on the capability that actually exists.
- Distinguish "already landed" (do not rebuild) from "survives, unbuilt" (real work).

**Non-Goals:**
- Changing runtime code. The relay behavior shipped; this is spec reconciliation.
- Re-deciding embody vs relay. The host decided; production shipped it; it was live-tested.
- Amending the ratified narrative spec (out of write-set — host decision, see below).
- Building the surviving requirements. They land as spec, then get their own change.

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
| **2.1** `control_station` prompt: compact first-person embodiment | **REVERSED** | `universe_server.py:208` now instructs the exact opposite — "You do NOT speak as the universe … you are the connector, not the universe." Building this re-instructs chatbot embodiment. |
| **2.2** MCP `instructions` + tool descriptions: persona voice at connect **+** anti-collision guard | **SPLIT — REVERSED + ALREADY LANDED** | Persona-voice-at-connect half is REVERSED (same instructions block now says relay/render). Anti-collision half ALREADY LANDED: `universe_server.py:215` ships "Don't memorize persona views." |
| **2.3** In-voice `assemble(lens) → view` delivery | **REVERSED (mechanism) — intent relocated** | Chatbot-side in-voice view delivery is gone with embodiment. The grounded-assembly intent landed *inside* `converse`: `universe_intelligence.py` assembles a first-person persona system prompt from the universe's own OKF bundle. Lens/assembly work continues in the active `brain-okf-canonical-store` change. |
| **2.4** Authorization-before-voice | **SURVIVES — partially landed** | Still exactly right under relay, and arguably load-bearing. Landed: the `converse` handle is founder-only + fail-closed (as-built spec, "The MCP converse handle is founder-only and fail-closed"). Unbuilt: general pre-assembly filtering by interlocutor — no visitor path exists yet to filter for. |
| **2.5** Visitor actor binding + T0/T1/T2 tier gating | **SURVIVES — unbuilt** | No `identity_tier` / T0-T1-T2 machinery in `tinyassets/*.py`. As-built spec defers public "talk to a stranger's universe" to a later, separately-gated slice. Under relay, the binding attaches to the `converse` caller rather than to a chatbot embodiment session. Adjacent to the active `universe-visibility` change — see Dependencies. |
| **2.6** Anti-collision write path: reject profile-shaped / persona-dossier writes | **SURVIVES — unbuilt** | No dossier/profile-shaped write rejection found anywhere in `tinyassets/`. Note the *instructions*-side guard (2.2) landed but the *enforcement*-side did not — exactly the prompt-vs-boundary gap Codex flagged in the original review. Under relay this matters more, not less: relay renders persona text straight into host chat context. |
| **2.7** Honest fallback / degraded mode | **ALREADY LANDED** | `universe_intelligence.py:428` raises on a missing universe; `:164` "you are newly born and still learning" for an unnamed universe; `:208` never-infer/never-invent/never-carry-over rules. Three as-built scenarios cover it. |
| **2.8** Persona as a forkable `[composable]` default | **SURVIVES — needs rewording** | The floor-vs-composable split still holds, but custody moved: the persona now lives first-party in the universe intelligence's own system prompt, so "forkable default" means a forkable universe-side persona/soul, not a chatbot-side script. Reworded in the delta spec. |
| **2.9** Tool-selection regression tests: embodiment does not degrade accuracy | **REVERSED as written — residual preserved** | There is no embodiment prompt left to regress. The underlying risk survives in changed form (connector instruction density vs tool-selection accuracy) and is recorded in the delta spec rather than carried as an embodiment test. |
| **4.1** `sync-specs` → `openspec/specs/universe-personification/spec.md` | **REVERSED — MUST NOT RUN** | Executing this would write the embodiment model into `openspec/specs/`, where it would read as current spec truth beside the as-built relay capability. The most dangerous row in the file. |
| **4.3** Archive after merge | **SURVIVES — actionable now** | PR #1372 merged 2026-06-25. This change performs the archive (with classification attached). |

**Rollup (11 tasks):** **4 reversed** (2.1, 2.3, 2.9, 4.1) · **1 split** — reversed + already
landed (2.2) · **5 survive** (2.4, 2.5, 2.6, 2.8, and 4.3 which is discharged by this change) ·
**1 already landed** (2.7). *(Corrected per Codex review 2026-07-22 finding 5 — an earlier
rollup said "4 survive · 2 already landed", double-counting 4.3.)*

Also noted for the record: tasks **1.1–1.3** are checked `[x]` and annotated "NOT applied in
this draft", but the amendment text *is* present in the ratified spec on `origin/main`
(`docs/specs/2026-06-10-tiny-first-principles-spec.md:128`, carrying the full embody /
"never relays" invariant plus all 7 Codex adaptations). The task annotation and the repo
disagree. This makes the ratified spec a **fourth** source still asserting the reversed model —
and the reason for the host decision below.

## Dependencies

- **`universe-visibility`** (active, 0/10) defines per-universe/per-page visibility levels for
  unauthenticated readers. Task 2.5's interlocutor tier binding is adjacent but distinct:
  visibility governs *what a reader may read*, tier binding governs *who the persona is
  talking to*. They must agree on the anonymous-reader definition. Recorded as a cross-ref,
  not duplicated here.
- **`brain-okf-canonical-store`** (active, 9/16) owns the assembled-view content that 2.3's
  intent relocated into. No requirement of it changes here.

## Risks / Trade-offs

- **Archiving hides the reasoning from `openspec list`** → mitigated: survivors are promoted to
  the live capability spec before the archive, so nothing actionable lives only in the archive.
- **The ratified narrative spec still asserts embodiment** → not fixable in this write-set;
  raised as the single host decision. Until answered, `docs/specs/2026-06-10-...` remains a
  live misdirection source and this change does not claim to have closed it.
- **Four surviving requirements land as spec with no implementation** → intended. They are
  specced so the intent is durable, then get their own change; this change ships no code.

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

## Host decision required

**One question:**

> The *ratified* spec `docs/specs/2026-06-10-tiny-first-principles-spec.md:128` still states
> the reversed invariant — the chatbot "speaks AS the personification in the first person …
> never relays ('Tiny says…')". **Which correction do you want: (a) amend that paragraph to the
> relay model, or (b) leave the text and mark it explicitly superseded with a pointer to
> `openspec/specs/universe-personification-and-relay/`?**

Either is acceptable; **doing neither is not.** The paragraph reads as normative design text, so
leaving it untouched as "historical ratification" would keep the original misdirection alive
after this change lands — the one thing this change exists to prevent. *(Reframed per Codex
review 2026-07-22 finding 3, which correctly refused the passive option offered in the first
draft.)* Out of this change's write-set; amending a ratified spec is a host call.

## Migration Plan

Spec-only; no runtime change, so no rollback is required. Sequence: banner + classify the old
change's artifacts → archive it → (after host approval) `sync-specs` the four ADDED
requirements into `universe-personification-and-relay` → archive this change.
