# Universe Personification and Relay

> As-built baseline (2026-07-19, change `spec-out-existing-platform`): describes landed behavior on `main` at baseline time, known limitations included. Future behavior changes arrive as OpenSpec change deltas against this capability.

## Purpose

A universe embodied as a first-party personified intelligence that speaks first-person and is the sole writer of its own brain; the connecting chatbot is a thin relay. Contact runs through a sandboxed `converse` turn on the universe's assigned engine.
## Requirements

The built-in persona/prompt/learning requirements describe the default
conversation implementation. An explicitly selected governed consumer instead
uses the canonical consumer requirements below and does not also run that
built-in writer/learning pipeline.

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
The `converse` operation (`tinyassets.universe_intelligence.converse`) SHALL resolve the universe's own directory and assigned engine (`UniverseContext`), assemble a first-person persona system prompt grounded in the universe's OKF grounding files, and run exactly one LLM turn as the universe with `role="writer"` so the universe's preferred writer and vault key take effect. The turn SHALL be in-process and scoped to the universe by construction, and SHALL NOT pass through the MCP transport auth gate (that gate authorizes untrusted external callers; the intelligence is first-party for its own universe). An assigned engine that cannot enforce the sandbox SHALL refuse the turn rather than run it unconfined: the Codex provider raises a `ProviderError` for any `sandbox_workspace` turn (its `--sandbox read-only` still reads the whole filesystem and it honors no tool policy), so as-built, `claude-code` is the only engine that can serve `converse`, and a Codex-assigned universe fails closed with an error directing reassignment. As-built limitation: this turn is turn-scoped for M1; the persistent 24/7 loop is a later slice.

#### Scenario: converse runs on the assigned engine as the persona
- **WHEN** `converse` is called for an existing universe with a founder message
- **THEN** it runs one `role="writer"` turn on that universe's assigned engine
- **AND** the system prompt speaks in the first person, grounded in the universe's own bundle

#### Scenario: an unnamed newborn stays honest
- **WHEN** `converse` runs for a universe with no learned name
- **THEN** the assembled first-person prompt has the universe acknowledge it is newly born and still learning, rather than inventing a name

#### Scenario: quoted grounding is declared current so recall costs no round-trip
- **WHEN** at least one grounding file is inlined into the assembled prompt
- **THEN** the grounding section states that each quoted heading is that file's current and complete contents for this turn, so the turn answers from the prompt instead of spending another model round-trip fetching the same text
- **AND** the statement forbids no tool and preserves reading a file before editing it
- **WHEN** no grounding file was inlined, or the tier filter permitted only a subset
- **THEN** no such statement is made about contents that are absent, and it never names a withheld file

#### Scenario: a missing universe fails loudly
- **WHEN** `converse` is called for a universe directory that does not exist
- **THEN** it raises rather than fabricating a reply

#### Scenario: a sandbox-incapable assigned engine fails closed
- **WHEN** `converse` runs for a universe whose assigned engine is Codex
- **THEN** the provider raises a `ProviderError` refusing to run the founder-facing turn unconfined
- **AND** the error directs assigning a sandbox-capable engine (`claude-code`) instead of silently running without the sandbox

### Requirement: The engine turn is confined by a fail-closed sandbox
Every universe-intelligence engine turn SHALL run with `sandbox_workspace=True` (cwd pinned to the universe's own directory) and a tool policy that requests `WebFetch` as the sole allowed tool and fail-closed denies every other currently-enumerated tool by name — including `Bash`, `Monitor` (which runs shell commands), filesystem tools, scheduling/messaging tools, and all MCP server tools via the `mcp__*` wildcard. This is a policy-level constraint honored by the `claude-code` CLI, not a true allow-only sandbox: the CLI has no allow-only-X mode, so an unenumerated future tool would stay usable until added to the denylist. The universe's own soul and canon SHALL reach the engine via context injection into the system prompt, NOT via a filesystem read tool, and brain writes SHALL go through the separate governed learning path rather than the engine's tools. As-built limitation: the denylist is rot-prone as the CLI adds tools, and true filesystem/OS-level confinement (bwrap/container) is deferred — the sandbox is deny-enumerated policy, not OS enforcement.

#### Scenario: the sandbox config locks the engine down
- **WHEN** the engine `ModelConfig` for a universe turn is built
- **THEN** it pins the workspace to the universe's directory, requests `WebFetch` as the sole allowed tool, and denies the enumerated shell, filesystem, messaging, scheduling, and `mcp__*` tools

#### Scenario: both engine turns are sandboxed
- **WHEN** `converse` runs its reply turn and its learning-extraction turn
- **THEN** both turns use the fail-closed sandboxed config

### Requirement: Learning is a separate tolerant model-extracted step with field-specific filtering, and reply delivery survives failures
After the reply turn, `converse` SHALL run a separate provider call whose prompt
asks for durable facts explicitly stated in the founder's latest message.
Parsing SHALL tolerate fenced JSON or an embedded top-level object and return
an empty proposal when no dict can be recovered. `commit_learning` SHALL
string-coerce `name`, treat non-dict `soul` as empty, accept only governed soul
filenames with non-empty string bodies, apply the generic-boilerplate regex only
to `soul["identity.md"]`, and filter canon list items individually for non-empty
title/content. It SHALL NOT compare accepted non-generic name, soul, or canon
facts with the founder message, so unsupported extractor output can pass. A
`SoulEditError` while reading governed files SHALL become an empty governed set
without logging at that catch; rejected soul edits and failed canon items SHALL
be logged. Any other extraction/commit exception reaching `converse` SHALL be
logged, and no learning failure SHALL prevent reply delivery.

#### Scenario: tolerant parsing and field-specific filtering
- **WHEN** extraction returns fenced or embedded JSON with mixed valid and invalid fields
- **THEN** the top-level dict is recovered when possible
- **AND** name, governed non-empty soul bodies, and non-empty canon items are handled by their field-specific coercion and filters rather than one strict schema validator

#### Scenario: accepted extractor output is not source-entailment checked
- **WHEN** field-specific filters accept a non-generic name, soul body, or canon item
- **THEN** commit does not compare that fact with the founder's latest message before persistence

#### Scenario: generic identity boilerplate is filtered only from identity.md
- **WHEN** a proposal contains only an `identity.md` body matched by the generic-boilerplate regex and no accepted name or canon item
- **THEN** commit makes no soul edit
- **AND** the regex is not applied to the separate name or canon fields

#### Scenario: governed-file read failure is silently narrowed
- **WHEN** `read_governed_files` raises `SoulEditError`
- **THEN** commit uses an empty governed-file set without logging at that catch
- **AND** continues processing any accepted name or canon fields

#### Scenario: persistence failure preserves the reply
- **WHEN** extraction or commit raises beyond the field-specific handled failures
- **THEN** `converse` logs the error and the founder still receives the reply

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

### Requirement: Voice is a rendering of the canonical universe turn, not a second author
The voice surface SHALL relay each committed founder utterance through the existing `converse` operation and SHALL treat the exact returned text as the universe's canonical reply; Realtime SHALL NOT independently answer as, rename, or add facts for the universe.

#### Scenario: Voice relay returns a universe reply
- **WHEN** `converse` returns successfully for a spoken founder turn
- **THEN** the app renders that exact text in the canonical conversation history
- **AND** any speech output is treated only as an audio rendering of that reply

#### Scenario: Speech renderer differs from canonical text
- **WHEN** the speech renderer's output transcript differs materially from the canonical `converse` reply
- **THEN** the canonical stored and displayed reply remains unchanged
- **AND** the client records content-free mismatch evidence and does not replace history with the renderer output

### Requirement: A selected governed consumer uses one canonical conversation path
The canonical turn path SHALL retain its authenticated principal, home,
interlocutor policy, receiver-scoped conversation history, current model
preferences and execution receipts when an explicitly installed governed
consumer handles the turn. The default persona/writer path SHALL remain the
default when no handler is selected; a selected handler SHALL NOT also run that
default writer or its cognitive/learning pipeline behind the user's back.

#### Scenario: A custom graph handles an ordinary app or connector message
- **WHEN** a founder sends a message with a valid selected Branch-backed handler
- **THEN** the trusted shell admits that immutable handler under the receiver's current execution authority
- **AND** it renders one terminal canonical reply selected by the adapter's declared output contract
- **AND** history and current input method remain associated with the same receiver conversation

#### Scenario: A user changes model for the current turn
- **WHEN** the user chooses an authorized model or ordered fallback policy for that turn
- **THEN** writer calls in the selected handler respect that current choice and ordinary eligibility checks
- **AND** the app reports the actual executing provider/model, not the creator's suggested default

#### Scenario: A slow or cancelled custom turn has not completed
- **WHEN** the underlying run is pending, running, cancelled, interrupted or uncertain
- **THEN** the shell exposes that run's actual progress/outcome through existing turn/run evidence
- **AND** it neither fabricates a terminal reply nor launches a replacement writer automatically
- **AND** cancellation uses the existing governed run control rather than deleting private state

#### Scenario: A turn response is lost or an installation changes during execution
- **WHEN** an admitted custom turn already has a run identity and a client reconnects, or the installation revision subsequently changes
- **THEN** observation resolves that existing attempt and selection revision
- **AND** automatic transport recovery does not admit a duplicate graph or append a second canonical reply
- **AND** an explicit new user send remains a distinct request, not falsely advertised as exactly-once replay

#### Scenario: V1 excludes recursive canonical-writer entry
- **WHEN** a selected component depends on nested executable references or requires the canonical converse handle as an engine/code-node tool
- **THEN** v1 refuses unsupported nested references and the governed tool surface does not expose converse
- **AND** the platform does not claim general recursive-harness ancestry support

### Requirement: Canonical custom requests reserve one existing run
Custom-consumer turns SHALL require the versioned keyed request object and SHALL
atomically bind owner/universe/session-scoped stable caller intent and captured
installation/context to one existing runs-database run. They SHALL reuse the
common run-owned start/dispatch mechanism, not add a conversation execution queue,
launch claim or provider authority. Status SHALL remain owner-scoped and truthful.
New v1 requests SHALL stamp canonical_consumer/version 1/empty options under the
same transaction; initial, same-key and unstarted restart nomination SHALL use
the same static origin dispatcher. Unknown/uninstalled origin or durable started
evidence SHALL remain held rather than authorize uncertain replay.

#### Scenario: Transport reconnect follows changed history and saved defaults
- **WHEN** the same scoped key and original caller request return after history or saved model defaults changed
- **THEN** the original admission and run are returned using their captured server context
- **AND** current history/defaults are not recomputed into replay conflict detection
- **AND** explicitly changed message, model choice or installation intent conflicts without execution

#### Scenario: Custom request protocol is absent or races with installation
- **WHEN** a selected custom handler receives no keyed request object, or a new keyed request names a stale installation revision
- **THEN** it refuses before either writer executes and reports the protocol or selection prerequisite
- **AND** it does not silently fall back to unkeyed default chat
- **AND** unkeyed default chat remains unchanged when no custom handler is selected

#### Scenario: A repeated request follows handler disable
- **WHEN** an existing admitted key is observed after its installation is disabled
- **THEN** current owner/home authorization precedes lookup and the original run remains observable
- **AND** the request neither changes its selected definition nor starts another run

### Requirement: Terminal history is a mandatory idempotent projection
A custom turn's immutable terminal envelope SHALL be frozen from its admitted run
and projected as one founder/reply or founder/platform-notice pair. A durable
per-admission projection record SHALL be committed atomically with that pair in
the existing conversation database. Reconciliation SHALL never rerun effects.

#### Scenario: Owner observes unknown or ambiguous admitted execution
- **WHEN** the owner reads a nonterminal custom turn with an unknown, legacy or invalid origin, or a queued run carrying either durable start-marker component
- **THEN** the common metadata-only admission classifier exposes held state, phase, `automatic_replay=false` and whether actions may have occurred without changing persisted run status
- **AND** unavailable origin reports `origin_unavailable` and queued started work reports `recovery_required`, not proven healthy waiting work
- **AND** terminal history projection retains its existing guarded repair; observation never loads execution input bodies or dispatches effects

#### Scenario: Crash occurs between conversation commit and runs projection flag
- **WHEN** the terminal pair exists but the admission has not recorded its projection completion
- **THEN** repair finds the matching projection digest and original row numbers
- **AND** it repairs only the admission flag without adding a second pair or provider call

#### Scenario: Pair storage fails or the terminal result is uncertain
- **WHEN** projection cannot commit or the run lacks a validated terminal output
- **THEN** status reports held/pending and no successful canonical reply is fabricated
- **AND** trusted recovery and the same run identity remain available

#### Scenario: The terminal callback is lost before history projection
- **WHEN** the exact run completed but its callback did not project the canonical pair
- **THEN** ordinary owner-authorized turn status converges that same terminal projection idempotently
- **AND** no provider invocation, execution dispatch or second history pair occurs

#### Scenario: Detailed history expires
- **WHEN** ordinary retention removes old conversation text or terminal details
- **THEN** durable scoped admission/projection identity prevents replay or reappend
- **AND** an expired observation reports expired rather than rebuilding or rerunning the turn
