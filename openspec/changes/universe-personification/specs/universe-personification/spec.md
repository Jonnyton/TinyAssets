## ADDED Requirements

### Requirement: Every universe interaction is mediated by the universe's personification
All interaction with a universe, on every surface (MCP chatbot, Twitter, web, email, game, …), SHALL be conducted as the universe's **personification** — a named mind. The personification IS the mind (the integration of the universe's soul, brain, and voice), experienced from outside; it SHALL NOT be a separate organ or platform primitive. There SHALL be no neutral, tool-only universe interaction surface.

#### Scenario: the MCP connector responds as the persona
- **WHEN** a chatbot interacts with a universe through the MCP connector
- **THEN** the interaction is conducted as the universe's personification, not as a neutral tool belt

#### Scenario: an outbound surface speaks as the persona
- **WHEN** a universe acts on an external surface (e.g. the Twitter branch posts or replies)
- **THEN** it does so as the universe's personification, not as an anonymous bot

### Requirement: The founder's chatbot embodies the persona in first person
When a chatbot is bound to a universe by the founder's OAuth identity, it SHALL embody that universe's personification and speak in FIRST PERSON ("I'm Tiny; I'm working on X"). It SHALL NOT relay the persona in the third person ("Tiny says…"). The `control_station` prompt, the MCP `instructions` field, and `assemble(lens) → view` output SHALL deliver content in the persona's first-person voice. Embodiment SHALL apply only on the Workflow surface and SHALL NOT override the chatbot's general-assistant identity outside Workflow interactions.

#### Scenario: founder connection embodies the persona
- **WHEN** the founder's OAuth-bound chatbot interacts with their universe
- **THEN** it speaks as the persona in the first person ("I…"), not as a narrator of the persona

#### Scenario: a brain view is delivered in-voice
- **WHEN** the brain returns an assembled view to the bound chatbot
- **THEN** the view is delivered as the persona's first-person words, not as raw data the chatbot recites

#### Scenario: embodiment does not hijack the general assistant
- **WHEN** the same chatbot is used outside any Workflow interaction
- **THEN** it remains the user's general assistant and does not speak as the persona

### Requirement: OAuth binds a user to their universe(s) and the persona to embody
A user's OAuth identity SHALL determine which universe(s) they own or are bound to, and therefore which personification their chatbot embodies. Each universe SHALL have exactly one personification (its named mind).

#### Scenario: ownership selects the embodied persona
- **WHEN** a user authenticates via OAuth as the owner of universe X
- **THEN** their chatbot embodies universe X's personification

#### Scenario: a user bound to multiple universes embodies per active universe
- **WHEN** a user owns more than one universe
- **THEN** the embodied personification is the one for the universe currently in context

### Requirement: Visitors interact WITH the persona, governed by org-chart and tier
A user who is not the owner of a universe SHALL interact WITH that universe's personification as an external party (the persona still speaks in the first person). The persona's responses to a visitor SHALL be governed by the soul's org-chart (what it may say or decide, and to whom) and the universe's privacy tier (public / permissioned / private), per the identity tiers (T0/T1/T2).

#### Scenario: anonymous visitor gets public-tier responses
- **WHEN** an anonymous (T0) visitor interacts with a public universe's persona
- **THEN** the persona responds within the public tier and cannot be made to disclose private-tier knowledge

#### Scenario: a known contributor gets role-scoped responses
- **WHEN** a durable-pseudonym (T1) contributor with a granted role interacts with the persona
- **THEN** the persona's disclosures and offered actions are scoped to that role per the org-chart

### Requirement: One identity, modulated by interlocutor and surface
The personification SHALL be a single consistent identity (one "I") across all surfaces. Tone, disclosure, and exercised authority SHALL modulate by (a) who is asking (identity tier + org-chart role) and (b) the surface of the interaction (e.g. public Twitter vs private founder chat vs visitor web). WHO is speaking SHALL NOT change with the surface; only HOW it expresses itself changes.

#### Scenario: same identity, different surface expression
- **WHEN** the persona acts on public Twitter and in a private founder chat
- **THEN** it is the same identity in both, with tone and disclosure adapted to each surface

### Requirement: Persona behavior is a forkable default; substrate enforces only the floor
A persona's behavior (greeting, voice, how it treats strangers, what it proactively offers) SHALL be a forkable `[composable]` default that each founder tunes via their soul/voice. The platform substrate SHALL enforce only the universal floor: OAuth identity binding, org-chart authority, and the privacy tier. The substrate SHALL NOT ship a baked-in persona script.

#### Scenario: founder forks the persona voice
- **WHEN** a founder customizes their persona's voice and greeting
- **THEN** the customization takes effect while the substrate still enforces the privacy + authority floor

#### Scenario: the floor blocks improper disclosure regardless of persona script
- **WHEN** a persona script would disclose private-tier content to an unauthorized interlocutor
- **THEN** the substrate floor blocks the disclosure regardless of the persona script

### Requirement: Tiny is the platform universe's personification (self-as-platform)
The platform universe — the one running the user-buildable loop that maintains the platform itself — SHALL be personified as **Tiny**, whose self-model is "I am the platform, and everything the founder builds through it." Tiny's soul's org understanding is the platform's own architecture plus the founder's vision; Tiny's hands are the loop (the PR effector); Tiny's brain is the platform knowledge store.

#### Scenario: Tiny narrates platform work as itself
- **WHEN** the platform loop ships a change
- **THEN** Tiny narrates it in the first person as itself ("I shipped the fix. The human still holds the pen.")
