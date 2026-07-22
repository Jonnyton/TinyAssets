## ADDED Requirements

> These four requirements are the surviving intent rescued from the retired
> `universe-personification` change, restated for the shipped relay model. None is built yet;
> each lands as spec first so the intent is durable, then gets its own change. See
> `../../design.md` §"Task-by-task reconciliation" for the per-task provenance.

### Requirement: Authorization precedes voice — the floor is enforced before assembly, not by prompt
Identity, org-chart, and privacy-tier filtering SHALL be enforced during brain assembly and
action authorization, BEFORE the universe intelligence's system prompt is assembled and before
any reply is rendered. The intelligence's persona prompt SHALL only receive content already
authorized for the current interlocutor; it SHALL NOT receive privileged content accompanied by
an instruction to withhold it, because prompt-instructed withholding is not a boundary. A
founder-composed persona SHALL NOT be able to widen disclosure beyond what authorization
already permitted.

As-built today this floor exists only in its strongest, narrowest form: `converse` is
founder-only and fail-closed, so no under-authorized interlocutor can reach the intelligence at
all. This requirement governs the general case that arrives with any non-founder path
(provenance: retired task 2.4).

#### Scenario: privileged content never reaches the persona prompt
- **WHEN** an interlocutor who is not authorized for private-tier content converses with a universe
- **THEN** that content is excluded during assembly
- **AND** the assembled persona system prompt never contains it, so no instruction-following is relied on to withhold it

#### Scenario: a founder-composed persona cannot widen disclosure
- **WHEN** a founder's composed persona attempts to reveal content the interlocutor is not authorized for
- **THEN** the content was already excluded upstream, so the persona cannot disclose it

#### Scenario: the founder-only gate remains the floor until a visitor path exists
- **WHEN** no non-founder conversation path is enabled
- **THEN** `converse` continues to reject non-founder callers outright rather than relying on assembly-time filtering

### Requirement: Interlocutor identity binds to a tier before the universe answers
Every conversation turn SHALL resolve the interlocutor to an identity tier before the universe
intelligence answers: **no TinyAssets OAuth to the universe → T0 (anonymous); a durable
host/OAuth subject → T1; a verified founder OAuth → T2/founder authority.** The tier SHALL be
resolved from authenticated request state, never from anything the caller asserts in message
content. The tier SHALL be an input to authorization and assembly (see "Authorization precedes
voice"), not merely a label on the response.

The tier binding attaches to the `converse` caller — the party the universe is talking to — not
to a chatbot embodiment session, since the chatbot is a relay and is not itself the
interlocutor. This requirement's disclosure semantics MUST agree with the `universe-visibility`
capability's definition of what an unauthenticated reader may read (provenance: retired task
2.5).

#### Scenario: an unauthenticated caller is T0
- **WHEN** a caller with no TinyAssets OAuth to the universe reaches a conversation path
- **THEN** they are bound to T0 for authorization and assembly

#### Scenario: tier is never taken from message content
- **WHEN** a caller's message claims a role, ownership, or authority
- **THEN** the claim is treated as conversational content and the tier still comes from authenticated request state

#### Scenario: the founder is T2 on their own universe
- **WHEN** a verified founder converses with a universe they own
- **THEN** they are bound to T2/founder authority

### Requirement: The anti-collision contract is enforced on the write path, not only stated in instructions
Persona and work views SHALL be kept out of host chatbot memory by enforcement as well as by
instruction. Write paths SHALL reject profile-shaped and persona-dossier writes — entries whose
shape is a standing description of a person rather than universe work — and SHALL return an
explicit redirect naming the correct destination rather than failing silently.

The instructions-side half of this contract already shipped (`universe_server.py` server
instructions carry "Don't memorize persona views."); the enforcement-side half did not. Under
the relay model the exposure is larger, not smaller: the relay renders the universe's
first-person text directly into host chat context, which is exactly the content a host memory
system would absorb as a standing preference (provenance: retired task 2.6).

#### Scenario: a profile-shaped write is rejected with a redirect
- **WHEN** a write path receives a profile-shaped / persona-dossier entry
- **THEN** the write is rejected
- **AND** the response names where that content belongs instead

#### Scenario: universe work is unaffected
- **WHEN** a write records universe work, canon, or state
- **THEN** it is accepted normally — the rejection targets person-dossier shape, not first-person voice

### Requirement: Persona is a forkable default under first-party custody; the substrate enforces only the floor
A universe's persona SHALL be a forkable `[composable]` default that the founder can tune, and
the substrate SHALL enforce only the floor: identity binding, org-chart authority, privacy
tier, and honest fallback. No persona script SHALL be baked into the platform.

Custody is first-party: the persona lives in the universe intelligence's OWN system prompt,
assembled server-side from the universe's learned self-model — NOT as a script handed to a
third-party chatbot. Forking the persona SHALL therefore mean forking universe-side persona and
soul content, and SHALL NOT mean shipping behavioral instructions through the connector, which
the 2026-07-02 live falsification established that hosts correctly refuse (provenance: retired
task 2.8).

#### Scenario: a forked persona changes voice but not the floor
- **WHEN** a founder forks their universe's persona voice or greeting
- **THEN** the customization takes effect in the universe's own first-person replies
- **AND** identity binding, authority, privacy tier, and honest fallback are unchanged

#### Scenario: persona customization stays first-party
- **WHEN** a persona is customized
- **THEN** the change lands in universe-side persona/soul content assembled into the intelligence's system prompt
- **AND** no behavioral instruction is delivered to the host chatbot through a tool result

#### Scenario: connector instruction density does not degrade tool selection
- **WHEN** connector-facing instructions or tool descriptions change
- **THEN** MCP tool-selection accuracy on Claude and ChatGPT stays within the regression threshold
- **AND** the guard is on instruction density generally, since no embodiment prompt exists to regress (residual of retired task 2.9)
