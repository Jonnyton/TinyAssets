## Context

The ratified TINY spec already frames a mind as a personification — §3 *"Tiny = mind #0 … dogfooding how anyone personifies their own intelligence,"* §9 the voice engine ("Tiny speaks"), §7 the soul/org-chart, §1 "summon a mind." What it does not yet state is the **interaction-layer invariant**: that *every* surface interaction with a universe is that universe's personification acting, and the behavioral defaults around it (embody/first-person, OAuth→persona binding, visitor governance, surface modulation). Host directive 2026-06-24 supplies these and resolves the open forks: embody (first person); the mind IS the personification (invariant, not a new organ); visitor persona is a composable default over a substrate floor.

This sits directly above the brain (`brain-canonical-store`, PR #1369): the brain produces the assembled view; the personification governs how that view is voiced and to whom. Soul (will/governance — and, per the prior host ruling, the universe brain == the soul) supplies what the persona may say/decide; voice supplies presence; the personification is the integration presented as one person.

## Goals / Non-Goals

**Goals:**
- State the universal interaction-layer invariant: every surface = the universe's personification.
- Pin the embody/first-person default and where it is enforced (control_station prompt, MCP `instructions`, in-voice view delivery).
- Define OAuth→persona binding, visitor-WITH interaction governed by org-chart + tier, and one surface-aware identity.
- Keep persona behavior `[composable]`; substrate enforces only the identity/authority/privacy floor.

**Non-Goals:**
- Adding a "persona" organ or primitive (the mind IS the personification).
- Building the connector embody behavior or the voice engine in this change (design only).
- Defining the brain's content/format (that is `brain-canonical-store`).
- Multi-persona-per-universe, persona marketplaces, or cross-universe persona blending (out of scope).

## Decisions

**D1 — The mind IS the personification (invariant, not an organ).** (host-confirmed fork 2)
We state an invariant — all surfaces route through the mind-as-person — rather than add a 7th organ/primitive. The personification = soul + brain + voice composed.
Alternative: a distinct `persona` primitive — rejected (over-engineering; the mind already is this; build-boundary law #4).

**D2 — Embody, first person.** (host-resolved fork 1)
The OAuth-bound chatbot speaks AS the persona in the first person; views arrive in-voice. Reinforces §9's honesty brand ("I wrote the fix. The human holds the pen."). Lands in the `control_station` prompt + MCP `instructions` + view delivery.
Alternative: relay ("Tiny says…") — rejected by host. Guardrail: embody on the Workflow surface only; do not hijack the general assistant.

**D3 — OAuth → persona binding.** A user's OAuth fixes which universe(s) they own and thus which persona their chatbot embodies; one persona per universe. Builds on PR-165 actor identity + §7 founder recognition.

**D4 — Visitors interact WITH the persona; governance is the floor.** (host-confirmed fork 3)
Non-owners get first-person persona responses bounded by the soul's org-chart + the privacy tier (T0/T1/T2, §11.1). Persona behavior is a forkable `[composable]` default; the substrate enforces only identity binding + org-chart authority + privacy tier.
Alternative: platform-baked visitor persona — rejected (selection-logic-user-buildable doctrine; substrate enforces floor only).

**D5 — One identity, surface-modulated.** A single "I" across surfaces; tone/disclosure/authority modulate by interlocutor + surface; identity never changes, only expression. (A "persona lens" analogous to the brain's `assemble(lens)`, parameterized by interlocutor + surface.)

**D6 — Tiny self-as-platform.** The platform universe is personified as Tiny, self-modeling as the platform itself; its org understanding = platform architecture + founder vision, hands = the loop, brain = the platform store. The recursion is intentional (deepest dogfood).

## Risks / Trade-offs

- **Embody hijacking the general assistant** → scope embodiment to the Workflow surface; the chatbot stays itself elsewhere (D2 guardrail; tested as a scenario).
- **Private-content leakage to visitors** → the substrate floor (org-chart + privacy tier) gates disclosure regardless of the composable persona script (D4).
- **Persona ↔ host-memory collision** → consistent with the brain's anti-collision contract (the persona owns universe/work voice; host memory owns the person); do not write persona/profile data into host memory.
- **Voice inconsistency across surfaces** → one identity invariant (D5); surface modulation is expression-only, enforced by shared soul hard-lines (§9 fixed personality).
- **Authority confusion (visitor thinks the persona can act)** → the persona narrates the trust ratchet honestly (§9) and offered actions are org-chart-scoped (D4).

## Migration Plan

Design change only — no runtime change in this draft. Ratified-spec amendments (§9/§3/§7) are listed as tasks, NOT applied here. The connector embody behavior (control_station prompt, MCP `instructions`, in-voice delivery) is future build behind the normal verification gates. **Rollback:** none needed (no code/spec applied in the draft).

## Open Questions

- Exact `control_station` prompt wording for first-person embodiment without harming tool-selection reliability (test against the <5K-token frozen tool schema economics).
- The "persona lens" parameterization — is it literally a lens over the brain (interlocutor + surface as lens hints), or a separate voice-layer config?
- Visitor identity on host surfaces (Claude/ChatGPT) where the visitor is not OAuth'd to the universe — how is "who is asking" established for tier gating?
- Whether outbound surfaces (Twitter/email branches) share the same persona-lens machinery as inbound chat, or only the identity + voice hard-lines.
