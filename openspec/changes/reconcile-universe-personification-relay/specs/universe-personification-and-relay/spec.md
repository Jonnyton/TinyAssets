## ADDED Requirements

> These requirements are the surviving intent rescued from the retired
> `universe-personification` change, restated for the shipped relay model. See
> `../../design.md` §"Task-by-task reconciliation" for the per-task provenance.
>
> **⚠ None of them is built. They MUST NOT be synced into
> `openspec/specs/universe-personification-and-relay/` until code and tests exist** —
> `openspec/specs/` is as-built truth (`openspec/config.yaml`: *"do not spec aspirations"*;
> AGENTS.md § Spec-driven development). This change therefore stays **active** as the
> implementation change and is not archived on merge. (Codex review 2026-07-22, finding 1.)

### Requirement: Personified intelligence is the named projection of the whole mind on speaking surfaces
A universe's assigned intelligence SHALL speak and act as the named projection of the universe's
whole mind: voice expresses it, soul governs it, brain and learned self-model inform it, and
goals, skills, hands, and senses remain organs of the same mind rather than separate personas.
This requirement applies when the universe intelligence speaks or acts on conversational and
outbound surfaces. Direct-control connector tools MAY remain neutral control operations; they
SHALL NOT impersonate the universe or fabricate its voice (provenance: retired requirement
"Every universe interaction is the named projection of the whole mind," narrowed to preserve
the direct-control tools ratified in PR #1578).

#### Scenario: a conversational surface presents the whole-mind personification
- **WHEN** the universe intelligence answers through `converse` or another speaking surface
- **THEN** the response is the assigned intelligence's own personified expression of the same whole mind

#### Scenario: a direct-control tool does not manufacture persona speech
- **WHEN** a founder invokes a direct-control action tool instead of `converse`
- **THEN** the tool performs or reports the operation without pretending that connector-authored text is the universe's voice

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

### Requirement: One learned identity persists across interlocutors and speaking surfaces
Each universe SHALL have one assigned intelligence and one learned personified identity. The
identity SHALL be sourced from the learned self-model, never the operational soul, and SHALL
remain the same across founder chat, visitor conversation, and outbound speaking surfaces.
Tone, authorized disclosure, and exercised authority MAY vary by authenticated interlocutor,
org-chart role, privacy tier, and surface, but who is speaking SHALL NOT change (provenance:
retired requirement "One identity, modulated by interlocutor and surface").

#### Scenario: the same identity adapts without being replaced
- **WHEN** the universe speaks privately to its founder and publicly on an outbound surface
- **THEN** both expressions come from the same learned identity
- **AND** disclosure and tone are adapted to the authorized interlocutor and surface

#### Scenario: the operational soul never becomes a second identity
- **WHEN** soul or org-chart policy changes the allowed action or disclosure
- **THEN** it governs the same learned identity rather than supplying or replacing that identity

### Requirement: The anti-collision boundary is stated honestly — host-memory ingestion is advisory, only the commons write surface is enforceable
The anti-collision contract SHALL distinguish two boundaries that the retired change conflated,
and SHALL NOT claim enforcement it cannot perform:

1. **Host chatbot memory ingestion is NOT enforceable by this platform.** Whether Claude or
   ChatGPT absorbs relayed persona text into its own memory is decided host-side. The shipped
   guard — the server `instructions` line "Don't memorize persona views." — is **advisory**, and
   SHALL be described as advisory. No requirement SHALL assert that rejecting a TinyAssets write
   prevents host-side ingestion; they are different systems.
2. **The universe's own brain is the enforceable surface**, and there the rule is *sole
   writership*, not dossier-rejection: the universe intelligence is the sole writer of its own
   brain via the governed learning path.

Accordingly, a write-path restriction SHALL be scoped to the **external/commons** write surface
and SHALL NOT restrict the universe's own governed learning path, which deliberately and
correctly persists a description of the founder to `founder.md`
(`universe_intelligence.py` `_GROUNDING_FILES`, `"founder.md": "<markdown: who my founder is>"`).
Any such restriction SHALL name its exact endpoint, its predicate, and its redirect destination
before it is implemented — an unscoped "reject profile-shaped writes" rule would contradict
landed behavior (provenance: retired task 2.6, corrected by Codex review 2026-07-22 finding 2).

#### Scenario: the host-memory guard is described as advisory
- **WHEN** the anti-collision guard is documented or surfaced
- **THEN** it is stated as guidance to the host assistant, not as a platform-enforced boundary

#### Scenario: the universe's own founder-learning is never blocked
- **WHEN** the governed learning path persists founder facts the founder explicitly stated
- **THEN** the write succeeds — sole-writership governs this path, not dossier-shape rejection

#### Scenario: an external dossier write is refused only under a defined predicate
- **WHEN** an external caller writes person-dossier content to the commons surface
- **THEN** it is refused only if it matches the named endpoint and predicate defined for that surface
- **AND** the refusal names the correct destination instead of failing silently

### Requirement: Persona is a forkable default under first-party custody; the substrate enforces only the floor
A universe's persona SHALL be a forkable `[composable]` default that the founder can tune, and
the substrate SHALL enforce only the floor: identity binding, org-chart authority, privacy
tier, and honest fallback. No persona script SHALL be baked into the platform.

Custody is first-party: the persona lives in the universe intelligence's OWN system prompt,
assembled server-side from the universe's learned self-model — NOT as a script handed to a
third-party chatbot. Forking the persona SHALL therefore mean forking universe-side learned
self-model and voice content. The soul MAY govern the fork's authority floor, but SHALL never
source or replace persona identity. Forking SHALL NOT mean shipping behavioral instructions
through the connector, which the 2026-07-02 live falsification established that hosts correctly
refuse (provenance: retired task 2.8).

#### Scenario: a forked persona changes voice but not the floor
- **WHEN** a founder forks their universe's persona voice or greeting
- **THEN** the customization takes effect in the universe's own first-person replies
- **AND** identity binding, authority, privacy tier, and honest fallback are unchanged

#### Scenario: persona customization stays first-party
- **WHEN** a persona is customized
- **THEN** the change lands in universe-side learned self-model or voice content assembled into the intelligence's system prompt
- **AND** soul content remains governance input rather than the source of persona identity
- **AND** no behavioral instruction is delivered to the host chatbot through a tool result

### Requirement: Tiny is the platform universe's governed personification
The platform universe's assigned intelligence SHALL be named Tiny and SHALL learn and express
the platform universe's self-model: the platform, its community, and the founder-directed work
performed through it. Tiny SHALL use the same first-party custody, authorization, provenance,
and effect boundaries as every other universe; self-as-platform SHALL NOT grant a special bypass
around the normal governed loop (provenance: retired requirement "Tiny is the platform
universe's personification").

#### Scenario: Tiny narrates a platform change through the governed loop
- **WHEN** the platform universe's accepted work ships a change
- **THEN** Tiny MAY narrate that verified event in first person as the platform universe
- **AND** the narration references the governed work result rather than inventing an unverified action

#### Scenario: self-as-platform grants no ambient authority
- **WHEN** Tiny attempts a protected action or disclosure
- **THEN** the same identity, org-chart, privacy, effect, and receipt boundaries apply as for any other universe

> **Residual of retired task 2.9 — deliberately NOT specced here.** The original task was a
> tool-selection regression test proving *embodiment* does not degrade accuracy; no embodiment
> prompt exists to regress. The surviving risk — connector instruction density vs tool-selection
> accuracy — belongs to the `live-mcp-connector-surface` capability, not to persona forkability,
> and cannot be specced until its baseline, metric, and permitted regression are defined. It is
> carried as task 6.3, not as a threshold-less scenario. (Codex review 2026-07-22, finding 4.)
