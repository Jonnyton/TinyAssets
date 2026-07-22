> # ⛔ STOP — §2 IS WRITTEN AGAINST A REVERSED INVARIANT. DO NOT BUILD IT AS WRITTEN.
>
> This change was authored when the chatbot was meant to **embody** the universe.
> The **2026-07-02 host reshape reversed that**: the universe intelligence is the
> single personified agent and sole action-taker, and the chatbot MCP demotes to
> onboarding + **relay**. The live contract is now *"you are the connector, not the
> universe"* — the chatbot renders the universe's own first-person reply verbatim
> and never composes its voice.
>
> That reshape is not a proposal; it is deployed and live-verified (`converse`,
> prod, 2026-07-22). Building §2.1–§2.3 as written would re-introduce chatbot
> embodiment and regress it.
>
> **Specifically reversed — do NOT implement from this text:**
> - `2.1` "compact first-person embodiment" in `control_station` — the chatbot does
>   not embody; `converse` does.
> - `2.2` "persona voice at connect" in MCP `instructions` — first contact relays
>   through `converse`; the connector does not speak as the universe.
> - `2.3` "In-voice `assemble(lens) → view`" — there is no chatbot voice to assemble
>   into.
>
> **Still valid, and worth building:** `2.4` authorization-before-voice. Authz
> filtering in brain assembly is orthogonal to *which* component speaks, and the
> relay shape needs it just as much.
>
> Per the reversal rule, this change is **not done until it is retired or rewritten
> against the relay shape**. Leaving it validating-but-wrong is how a reversed
> invariant gets rebuilt by the next lane that greps for unchecked boxes. Reconcile
> the spec before building anything in §2. See
> `docs/design-notes/2026-07-02-universe-intelligence-relay-architecture.md` and
> `docs/design-notes/2026-07-22-first-contact-birth-moves-to-converse.md`.

## 1. Ratified-spec amendments (`docs/specs/2026-06-10-tiny-first-principles-spec.md`) — NOT applied in this draft

- [x] 1.1 §9 (voice): embody / first-person invariant, **compact trigger-language** (no role-play sprawl), TinyAssets-surface-scoped guardrail + anti-collision + honest fallback + authorization-precedes-voice
- [x] 1.2 §3 (mind anatomy): personification = the **named interaction projection of the WHOLE mind** (voice expresses, soul governs, brain informs; goals/skills/hands/senses remain) — invariant, not an organ
- [x] 1.3 §7 (soul & org-chart): visitor-governance floor enforced in **brain assembly + authorization BEFORE voice**; persona behavior = `[composable]` default; T0/T1/T2 visitor binding

## 2. Connector behavioral surface (future build — behind verification gates + the Codex adaptations)

- [ ] 2.1 `control_station` prompt: compact first-person embodiment (trigger-language + view metadata; NO large role-play block; no tool-schema sprawl)
- [ ] 2.2 MCP `instructions` + tool descriptions: persona voice at connect + anti-collision "do not save into host memory" guard
- [ ] 2.3 In-voice `assemble(lens) → view` delivery of ALREADY-AUTHORIZED content (depends on `brain-canonical-store` #1369)
- [ ] 2.4 **Authorization-before-voice:** enforce identity / org-chart / privacy-tier filtering in brain assembly + action authz; voice never receives unauthorized content
- [ ] 2.5 Visitor actor binding + tier gating (no TinyAssets OAuth → T0; durable subject → T1; owner OAuth → T2)
- [ ] 2.6 Anti-collision write-path: reject profile-shaped / persona-dossier writes
- [ ] 2.7 Honest fallback / degraded mode: no invented persona state; no embodiment-from-memory when no active universe/persona
- [ ] 2.8 Persona behavior as a forkable `[composable]` default; substrate enforces only identity/authority/privacy floor
- [ ] 2.9 Tool-selection regression tests (Claude + ChatGPT) proving embodiment does not degrade accuracy

## 3. Cross-provider review

- [x] 3.1 Codex review obtained — verdict **ADAPT** (`docs/audits/2026-06-25-universe-personification-codex-review.md`); 7 required adaptations
- [x] 3.2 Folded all 7 adaptations into proposal + design + spec delta:
  - [x] 3.2.1 Invariant = projection of the WHOLE mind (not soul+brain+voice only)
  - [x] 3.2.2 Anti-collision requirement (instructions/views + reject profile-shaped writes)
  - [x] 3.2.3 Authorization precedes voice (floor enforced in assembly, not by prompt)
  - [x] 3.2.4 Visitor actor binding (T0/T1/T2 default)
  - [x] 3.2.5 Compact / testable embodiment (no role-play sprawl; regression tests)
  - [x] 3.2.6 Honest fallback (no invented persona state)
  - [x] 3.2.7 Added scenarios (multi-universe; private-content probing; host-memory collision; outside-TinyAssets non-hijack)

## 4. OpenSpec fold-back

- [ ] 4.1 `sync-specs` → `openspec/specs/universe-personification/spec.md` (after approval)
- [x] 4.2 Draft PR opened — #1372
- [ ] 4.3 Archive after merge
