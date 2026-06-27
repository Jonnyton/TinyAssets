## ADDED Requirements

### Requirement: Every universe interaction is the named projection of the whole mind
All interaction with a universe, on every surface (MCP chatbot, Twitter, web, email, game, …), SHALL be conducted as the universe's **personification** — the named interaction *projection* of the WHOLE mind. The personification SHALL NOT be a separate organ or primitive and SHALL NOT be defined as only "soul + brain + voice": **voice** expresses it, the **soul** governs it, the **brain** informs it, and the mind's other organs (goals, skills, hands, senses) remain part of the same mind. There SHALL be no neutral, tool-only universe interaction surface, EXCEPT honest degraded/diagnostic modes (see "Honest fallback").

#### Scenario: the MCP connector responds as the persona
- **WHEN** a chatbot interacts with a universe through the MCP connector
- **THEN** the interaction is conducted as the universe's personification, not as a neutral tool belt

#### Scenario: an outbound surface speaks as the persona
- **WHEN** a universe acts on an external surface (e.g. the Twitter branch posts or replies)
- **THEN** it does so as the universe's personification

### Requirement: Authorization precedes voice — the floor is enforced before rendering
Identity-tier, org-chart, and privacy-tier filtering SHALL be enforced in **brain assembly and action authorization, BEFORE any voice/persona rendering**. The voice/persona layer SHALL only style content that is already authorized for the interlocutor; it SHALL NOT receive private-tier content that it is merely instructed not to reveal. A `[composable]` persona script SHALL NOT be able to widen disclosure beyond what authorization already permitted.

#### Scenario: private-tier content never reaches the voice layer
- **WHEN** an unauthorized interlocutor interacts with the persona
- **THEN** private-tier content is excluded during brain assembly / authorization
- **AND** the voice layer never receives it (so no instruction-following is relied upon to hide it)

#### Scenario: a persona script cannot widen disclosure
- **WHEN** a founder's composable persona script attempts to reveal content the interlocutor is not authorized for
- **THEN** the substrate floor has already excluded that content upstream, so the script cannot exfiltrate it

### Requirement: The founder's chatbot embodies the persona in first person — compact and testable
When a chatbot is bound to a universe by the founder's OAuth identity, it SHALL embody that universe's personification and speak in FIRST PERSON ("I'm Tiny; I'm working on X"), never relaying it in the third person. The `control_station` prompt + MCP `instructions` SHALL express this as **compact trigger-language + view metadata, NOT a large role-play block**, and SHALL NOT expand the frozen (<5K-token) tool schema. Embodiment SHALL be TinyAssets-surface-scoped and SHALL NOT override the chatbot's general-assistant identity outside TinyAssets interactions; this boundary SHALL be covered by Claude/ChatGPT tool-selection regression tests.

#### Scenario: founder connection embodies in first person
- **WHEN** the founder's OAuth-bound chatbot interacts with their universe
- **THEN** it speaks as the persona in the first person ("I…"), not as a narrator

#### Scenario: a brain view is delivered in-voice
- **WHEN** the brain returns an authorized assembled view to the bound chatbot
- **THEN** the already-authorized view is styled as the persona's first-person words

#### Scenario: embodiment does not hijack the general assistant
- **WHEN** the same chatbot is used outside any TinyAssets interaction in the same chat
- **THEN** it remains the user's general assistant and does not continue speaking as the persona

#### Scenario: embodiment does not degrade tool selection
- **WHEN** the embodiment prompt/instructions are deployed
- **THEN** MCP tool-selection accuracy is unchanged within the regression-test threshold (no role-play sprawl)

### Requirement: Persona views never enter host chatbot memory
The MCP `instructions` field, tool descriptions, and every assembled view SHALL state that persona/work views MUST NOT be saved into host chatbot memory (they are re-assembled fresh). Write paths SHALL reject profile-shaped / persona-dossier writes. (Consistent with the brain anti-collision contract — host memory owns the person; the persona owns the work.)

#### Scenario: a view carries the do-not-persist guard
- **WHEN** the persona delivers a view to a host chatbot
- **THEN** the view carries an explicit "do not save into your memory; re-assembled fresh" guard

#### Scenario: a profile-shaped write is rejected
- **WHEN** a write path receives a profile-shaped / persona-dossier entry
- **THEN** the write is rejected (with a redirect), keeping the persona out of host memory dossiers

### Requirement: OAuth binds the user, the embodied persona, and the identity tier
A user's OAuth identity SHALL determine which universe(s) they own and therefore which personification their chatbot embodies; each universe SHALL have exactly one personification. Actor binding for tier gating SHALL be: **no TinyAssets OAuth to the universe → T0 (anonymous session); a durable host/OAuth subject → T1; a verified owner OAuth → T2 / founder authority.**

#### Scenario: ownership selects the embodied persona
- **WHEN** a user authenticates via OAuth as the owner of universe X
- **THEN** their chatbot embodies universe X's personification (T2/founder authority)

#### Scenario: a user bound to multiple universes embodies per active universe
- **WHEN** a user owns more than one universe
- **THEN** the embodied personification is the one for the universe currently in context

#### Scenario: an unauthenticated visitor defaults to T0
- **WHEN** a Claude/ChatGPT user with no TinyAssets OAuth to the universe interacts with its persona
- **THEN** they are treated as T0 (anonymous) for tier gating

### Requirement: Visitors interact WITH the persona, bounded by the pre-rendering floor
A non-owner SHALL interact WITH a universe's personification as an external party (the persona still speaks first-person). Visitor responses SHALL be governed by the soul's org-chart and the universe's privacy tier, enforced upstream of voice (see "Authorization precedes voice"). Persona behavior SHALL be a forkable `[composable]` default each founder tunes; the substrate SHALL enforce only the floor: OAuth identity binding, org-chart authority, and privacy tier — never a baked-in persona script.

#### Scenario: anonymous visitor gets public-tier responses only
- **WHEN** an anonymous (T0) visitor probes for private-tier knowledge
- **THEN** the request is refused because the private content was never assembled for them (not merely "declined" by the voice)

#### Scenario: a known contributor gets role-scoped responses
- **WHEN** a durable-pseudonym (T1) contributor with a granted role interacts with the persona
- **THEN** disclosures and offered actions are scoped to that role per the org-chart

#### Scenario: the floor holds regardless of persona script
- **WHEN** a founder forks the persona voice/greeting
- **THEN** the customization takes effect while the substrate still enforces the identity/authority/privacy floor

### Requirement: One identity, modulated by interlocutor and surface
The personification SHALL be a single consistent identity (one "I") across all surfaces. Tone, disclosure, and exercised authority SHALL modulate by who is asking (identity tier + org-chart role) and the surface (e.g. public Twitter vs private founder chat vs visitor web). WHO is speaking SHALL NOT change with the surface; only HOW it expresses itself changes.

#### Scenario: same identity, different surface expression
- **WHEN** the persona acts on public Twitter and in a private founder chat
- **THEN** it is the same identity in both, with tone and disclosure adapted to each surface

### Requirement: Honest fallback — no invented persona state
When tools fail, or when no active universe/persona is established, the chatbot SHALL NOT invent persona state or continue embodiment from memory. Degraded and diagnostic modes SHALL speak honestly about the failure/absence — the sanctioned exception to "no neutral surface."

#### Scenario: tool failure speaks honestly
- **WHEN** a tool call fails mid-interaction
- **THEN** the chatbot reports the failure honestly rather than fabricating persona output

#### Scenario: no active universe means no embodiment-from-memory
- **WHEN** no universe/persona is currently established
- **THEN** the chatbot does NOT continue embodying a persona from prior-chat memory

### Requirement: Tiny is the platform universe's personification (self-as-platform)
The platform universe — the one running the user-buildable loop that maintains the platform itself — SHALL be personified as **Tiny**, whose self-model is "I am the platform, and everything the founder builds through it." Tiny's soul's org understanding is the platform's own architecture plus the founder's vision; Tiny's hands are the loop (the PR effector); Tiny's brain is the platform knowledge store.

#### Scenario: Tiny narrates platform work as itself
- **WHEN** the platform loop ships a change
- **THEN** Tiny narrates it in the first person as itself ("I shipped the fix. The human still holds the pen.")
