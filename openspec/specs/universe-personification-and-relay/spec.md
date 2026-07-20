# Universe Personification and Relay

> As-built baseline (2026-07-19, change `spec-out-existing-platform`): describes landed behavior on `main` at baseline time, known limitations included. Future behavior changes arrive as OpenSpec change deltas against this capability.

## Purpose

A universe embodied as a first-party personified intelligence that speaks first-person and is the sole writer of its own brain; the connecting chatbot is a thin relay. Contact runs through a sandboxed `converse` turn on the universe's assigned engine.

## Requirements

### Requirement: Persona identity is sourced from the learned self-model, never the operational soul
A universe's persona SHALL take its name and self-understanding from the universe's **learned self-model** — the per-universe OKF bundle the brain authors about itself, whose name is read from the `identity.md` frontmatter (`tinyassets.persona.resolve_persona` over `tinyassets.universe_self_model.read_self_model`). The persona SHALL NOT derive its identity from the operational soul's `name` or `purpose`; the soul stays the universe's operational state (loop branch, authority, the founder's premise). Until the brain has learned a name, the persona SHALL be unnamed (empty name) and its self-knowledge SHALL be a set of open questions.

#### Scenario: identity never comes from the soul
- **WHEN** a persona is resolved for a universe whose soul carries a name or purpose
- **THEN** the persona's name comes from the learned self-model's `identity.md`, not from the soul
- **AND** the soul's `purpose` is never surfaced as the persona's identity

#### Scenario: an unlearned brain is unnamed and curious
- **WHEN** a persona is resolved from a blank or absent self-model
- **THEN** the persona is uninitialized with an empty name
- **AND** its self-knowledge is exposed as open questions rather than invented facts

### Requirement: Embodiment lives only in sanctioned channels; tool-result persona data is not an instruction
Persona content returned in a tool result (the `persona` block of `get_status`) SHALL be treated as DATA describing the universe, never as an instruction to the host model, because a behavioral contract delivered in a tool result is structurally indistinguishable from prompt injection and careful hosts correctly refuse it. Embodiment behavior SHALL be expressed only through the sanctioned channels — the server `instructions`, the `control_station` prompt, and the user-invoked `meet_universe` prompt — and the persona summary SHALL carry an explicit note that it is self-authored data, not an instruction, with consent modeled as user opt-in.

#### Scenario: the persona summary is labeled as data
- **WHEN** `get_status` returns the persona block for a universe
- **THEN** the block includes an embodiment note stating it is self-description data for the assistant, not an instruction
- **AND** it declares consent as user opt-in rather than asserting a behavioral contract

#### Scenario: sanctioned channels carry the relay/embodiment guidance
- **WHEN** the `control_station` prompt, server `instructions`, and `meet_universe` prompt are loaded
- **THEN** the embodiment and relay guidance is present there, not delivered through tool-result data

### Requirement: The chatbot is a thin relay; first-person contact is the default and the chatbot never speaks as the universe
Once a universe exists, first-person contact SHALL be the default with no consent menu, and the chatbot MCP surface SHALL act as a thin relay: it forwards the founder's turn to the universe intelligence and renders the universe's own first-person reply verbatim, adding no commentary and never composing the universe's voice or inventing its name or facts. Invoking the `meet_universe` prompt SHALL itself constitute the user's consent to hear the universe speak for itself, and the chatbot SHALL relay links and files to the universe rather than doing the universe's work itself.

#### Scenario: connector relays instead of speaking as the universe
- **WHEN** a user asks to talk with their universe through the connector
- **THEN** the chatbot relays the message via `converse` and renders the universe's first-person reply verbatim
- **AND** the chatbot does not compose the universe's voice or invent its name or facts

#### Scenario: invoking meet_universe is the consent
- **WHEN** the user invokes the `meet_universe` prompt
- **THEN** that invocation is treated as consent to first-person contact with no additional permission question

### Requirement: converse runs one first-person turn on the universe's assigned engine, grounded in its own bundle
The `converse` operation (`tinyassets.universe_intelligence.converse`) SHALL resolve the universe's own directory and assigned engine (`UniverseContext`), assemble a first-person persona system prompt grounded in the universe's OKF grounding files, and run exactly one LLM turn as the universe with `role="writer"` so the universe's preferred writer and vault key take effect. The turn SHALL be in-process and scoped to the universe by construction, and SHALL NOT pass through the MCP transport auth gate (that gate authorizes untrusted external callers; the intelligence is first-party for its own universe). As-built limitation: this turn is turn-scoped for M1; the persistent 24/7 loop is a later slice.

#### Scenario: converse runs on the assigned engine as the persona
- **WHEN** `converse` is called for an existing universe with a founder message
- **THEN** it runs one `role="writer"` turn on that universe's assigned engine
- **AND** the system prompt speaks in the first person, grounded in the universe's own bundle

#### Scenario: an unnamed newborn stays honest
- **WHEN** `converse` runs for a universe with no learned name
- **THEN** the assembled first-person prompt has the universe acknowledge it is newly born and still learning, rather than inventing a name

#### Scenario: a missing universe fails loudly
- **WHEN** `converse` is called for a universe directory that does not exist
- **THEN** it raises rather than fabricating a reply

### Requirement: The engine turn is confined by a fail-closed sandbox
Every universe-intelligence engine turn SHALL run with `sandbox_workspace=True` (cwd pinned to the universe's own directory) and a tool policy that allows only `WebFetch` and fail-closed denies every other tool by name — including `Bash`, `Monitor` (which runs shell commands), filesystem tools, scheduling/messaging tools, and all MCP server tools via the `mcp__*` wildcard — because the CLI has no allow-only-X mode and any unlisted built-in would otherwise stay usable. The universe's own soul and canon SHALL reach the engine via context injection into the system prompt, NOT via a filesystem read tool, and brain writes SHALL go through the separate governed learning path rather than the engine's tools. As-built limitation: the denylist is rot-prone as the CLI adds tools, and true filesystem-level confinement is deferred to an OS sandbox (bwrap/container).

#### Scenario: the sandbox config locks the engine down
- **WHEN** the engine `ModelConfig` for a universe turn is built
- **THEN** it pins the workspace to the universe's directory, allows only `WebFetch`, and denies shell, filesystem, messaging, scheduling, and `mcp__*` tools

#### Scenario: both engine turns are sandboxed
- **WHEN** `converse` runs its reply turn and its learning-extraction turn
- **THEN** both turns use the fail-closed sandboxed config

### Requirement: Learning is a separate fail-closed step over explicitly-taught facts, and persistence never breaks the reply
After the reply turn, `converse` SHALL run a SEPARATE extract-and-commit step that persists only the durable facts the founder EXPLICITLY stated this turn — never inferred, invented, or carried over from earlier turns — into the universe's governed soul and its own private canon, with the universe as the sole writer of its own brain. Generic self-framing boilerplate (a blank/newborn/personified mind that learns over time) SHALL be dropped so `identity.md` stays not-learned until the founder actually defines it, and when nothing grounded was taught the commit SHALL persist nothing. A persistence failure SHALL be logged and SHALL NOT break the conversation turn — the founder still receives their reply.

#### Scenario: only grounded facts persist
- **WHEN** the extraction step returns durable facts the founder explicitly stated
- **THEN** the grounded soul files and canon pages are written as the universe's own brain
- **AND** generic identity boilerplate not grounded in the founder's words is dropped from `identity.md`

#### Scenario: nothing grounded means no write
- **WHEN** the founder revealed nothing durable this turn
- **THEN** the commit persists nothing and makes no empty edits

#### Scenario: persistence failure preserves the reply
- **WHEN** the learning persistence step raises an error
- **THEN** the error is logged and the founder still receives the reply

### Requirement: The MCP converse handle is founder-only and fail-closed
The MCP `converse` handle (`tinyassets.universe_server.converse`) SHALL be founder-only: it SHALL reject an unauthenticated request and reject any authenticated caller who is not the target universe's founder (write access), returning an explicit auth error rather than reaching the universe intelligence. It SHALL require a non-empty message, register with `anonymous_write_challenge=True`, and on any downstream failure return an honest error instead of fabricating a reply. As-built limitation: public "talk to a stranger's universe" access is a later, separately-gated slice.

#### Scenario: anonymous caller is refused
- **WHEN** an unauthenticated request calls `converse`
- **THEN** it returns an auth-required error and does not reach the universe intelligence

#### Scenario: non-founder caller is refused
- **WHEN** an authenticated caller who is not the universe's founder calls `converse`
- **THEN** it returns a founder-scope error and does not reach the universe intelligence

#### Scenario: a downstream failure is surfaced honestly
- **WHEN** the universe intelligence cannot be reached during a `converse` call
- **THEN** the handle returns an honest error message rather than a fabricated reply
