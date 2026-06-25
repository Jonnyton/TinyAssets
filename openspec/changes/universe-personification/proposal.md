## Why

Host directive 2026-06-24. Every interaction with a universe — on every surface (MCP chatbot, Twitter, web, email, game) — is the universe's **personification** acting: a named *person* (a mind) the founder is shaping, not a neutral tool surface. The ratified spec seeds this (§3 *"Tiny = mind #0 … dogfooding how anyone **personifies their own intelligence**"*; §9 voice engine; §7 soul/org-chart; §1 "summon a mind") but never states it as an interaction-layer invariant, nor pins the embody/first-person default, the OAuth→persona binding, visitor governance, or surface modulation. This change makes the personification the explicit, universal interaction layer.

## What Changes

- **Invariant:** all universe interaction, on every surface, is conducted AS the universe's personification. **The mind IS the personification** (soul + brain + voice composed into one person) — NOT a new organ or primitive; the platform adds no "persona" primitive, it states the invariant.
- **Embody, first person (host-resolved 2026-06-24):** a chatbot bound to a universe by the founder's OAuth **embodies** the persona and speaks in FIRST PERSON ("I'm Tiny; I'm working on X"), never relays ("Tiny says…"). The `control_station` prompt + MCP `instructions` + in-voice `assemble(lens)→view` delivery carry the persona's voice. Embodiment is scoped to the Workflow surface; it SHALL NOT override the chatbot's general-assistant identity elsewhere.
- **OAuth → persona binding:** a user's OAuth determines which universe(s) they own and therefore which personification their chatbot embodies. One personification per universe (its named mind).
- **Visitors interact WITH the persona:** non-owners interact with a universe's persona as external parties (still first-person from the persona's side), governed by the soul's org-chart (what it may say/decide, to whom) + the universe's privacy tier (identity tiers §11.1).
- **One identity, surface- + interlocutor-aware:** a single consistent "I" across all surfaces; tone, disclosure, and exercised authority modulate by who is asking and the surface — WHO is speaking never changes, only HOW.
- **Persona behavior is a forkable `[composable]` default; substrate enforces only the floor** (OAuth identity binding + org-chart authority + privacy tier). No platform-baked persona script.
- **Tiny (self-as-platform recursion):** the platform universe — the one running the user-buildable loop that maintains the platform — is personified as **Tiny**, whose self-model is "I am the platform, and everything the founder builds through it." The deepest dogfood in the system.

## Capabilities

### New Capabilities
- `universe-personification`: The universal interaction layer — every universe interaction, on every surface, is the universe's named personification (= its mind: soul+brain+voice); the embody/first-person default under OAuth binding; visitor interaction governed by org-chart + privacy floor; one surface-aware identity; persona behavior composable with the substrate enforcing only the floor.

### Modified Capabilities
<!-- No existing openspec capability covers personification/voice. The separate `brain-canonical-store` change/PR supplies the in-voice view CONTENT this layer delivers; no requirement of it changes here. -->

## Impact

- **Connector behavioral surface:** the `control_station` MCP prompt (`workflow/universe_server.py` `@mcp.prompt` registration, ~:270) + the MCP `instructions` field + tool descriptions — must instruct first-person embodiment of the bound universe's persona.
- **Ratified spec:** `docs/specs/2026-06-10-tiny-first-principles-spec.md` §9 (voice → embody/first-person invariant), §3 (personification = the mind, invariant), §7 (visitor governance floor). Amendment tasks listed; **NOT applied in this draft**.
- **Brain:** `brain-canonical-store` (PR #1369) supplies the assembled-view content; this layer governs its in-voice delivery. No code overlap.
- **Identity/auth:** OAuth → universe binding (PR-165 actor-identity substrate; §7 founder recognition).
- **Gates:** host-directed design change (NOT external-research-derived, so the research-review rule does not strictly apply). Cross-provider review recommended before it gates connector-behavior build; connector embody behavior stays behind the normal verification gates.
