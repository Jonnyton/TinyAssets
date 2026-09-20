## ADDED Requirements

### Requirement: Consumer selection is receiver-private and explicit
The platform SHALL select an executable agent consumer only from an explicit,
revision-guarded installation owned and last updated by the current receiver,
bound to one exact public definition/component and supported adapter contract.
Discovery, import, preview, public publication and layout-only application SHALL
NOT activate a turn handler or grant provider/effect authority.

#### Scenario: Another creator's composition is selected
- **WHEN** owner B explicitly installs a supported component published by A
- **THEN** selection is stored only in B's existing private binding
- **AND** A's bindings, credentials, grants and private resources are not copied
- **AND** the serving provider binding and saved model preferences are unchanged

#### Scenario: A collaborator changes the selected installation
- **WHEN** current owner/home, latest updater, exact component pin or unique installation cannot be verified
- **THEN** the consumer is held before execution without guessing an installation
- **AND** current selection and refusal remain visible; installation mutations still require current receiver ownership, eligibility and revision checks

### Requirement: Public content is consumed only through governed adapters
The platform SHALL preserve unknown native components without executing them,
and SHALL validate each explicitly selected component against the exact installed
adapter contract. The v1 adapter SHALL invoke an immutable published
Branch through existing graph execution rather than evaluate imported source in
the daemon or authenticated application origin.

#### Scenario: Definition includes unsupported renderer content
- **WHEN** a composition contains a supported turn component and an unsupported executable UI component
- **THEN** compatibility reports the unsupported UI explicitly
- **AND** the UI source remains portable and inert rather than silently executed or discarded

#### Scenario: Branch contract cannot be resolved exactly
- **WHEN** the snapshot, executable closure, adapter version, input mapping or declared reply output is missing or incompatible
- **THEN** the relevant selection, admission or terminal projection boundary refuses or holds without execution or reply fabrication
- **AND** it does not substitute mutable latest code or fabricate an equivalent result

#### Scenario: First adapter contains nested execution references
- **WHEN** a selected graph declares invoke-by-definition, invoke-by-version or another unresolved executable dependency
- **THEN** v1 refuses activation/admission with the unsupported requirement
- **AND** separately authorized ordinary tool effects are not misrepresented as frozen executable dependencies

#### Scenario: Public source is read or remixed for installation
- **WHEN** the receiver selects a published source version
- **THEN** metadata-only version lookup and current receiver readability checks precede snapshot loading
- **AND** active status, exact hash and current provenance checks precede execution
- **AND** existing foreign-code rules require ordinary receiver-authorized remix without copying creator grants or losing public lineage

### Requirement: Consumed graphs use current receiver authority
Every consumed graph SHALL derive principal, home, run admission and provider
authority from the current authenticated receiver through existing trusted
helpers. Provider/model choices, fallback, spend, confinement, resource access
and external effects SHALL retain their ordinary current checks. A public
definition's requirements or references SHALL NOT become a grant.

#### Scenario: Creator requests an unavailable or paid model
- **WHEN** a public component names a source or model outside B's current authorized selection
- **THEN** the ordinary unavailable/approval outcome applies without borrowing A's access or enabling paid fallback
- **AND** model display reports only actual execution or honest unresolved status

#### Scenario: Access is revoked after installation
- **WHEN** provider, resource or effect authority is revoked before its next use
- **THEN** that use refuses under the existing authority boundary
- **AND** a stored installation approval does not override the revocation

#### Scenario: The served agent attempts to install itself
- **WHEN** an engine-tool request attempts a consumer-selection binding mutation
- **THEN** the existing engine agent-binding mutation refusal remains enforced
- **AND** founder principal identity alone is not treated as a human installation action

#### Scenario: Node defaults conflict with the user's chosen model
- **WHEN** graph preferences contradict an explicit current-turn primary or try to add fallback/spend authority
- **THEN** admission refuses the conflict without reusing a converse capability
- **AND** an absent node fallback restriction does not discard the user's authorized ordered fallback policy

### Requirement: Installation preserves private universe continuity
Installing, mixing, disabling or rolling back consumers SHALL preserve the
receiver's private conversation, memory, files, model preferences, connections,
pending requests and unrelated configuration. Reusable public exports SHALL
exclude that private state and retain native component lineage.

#### Scenario: Owner B mixes components from two public creators
- **WHEN** B publishes a native remix and selects its compatible consumers
- **THEN** public lineage names the source components and the sources remain immutable
- **AND** B's operational data and authority remain in B's existing stores

### Requirement: Trusted recovery never replays uncertain work
The platform SHALL expose current selection and explicit disable/rollback
outside custom content, using current receiver authority and revision checks.
Recovery SHALL affect subsequent turn admission without replaying an admitted
turn, restoring revoked grants or undoing completed effects. The previous-selection
control SHALL retain only the prior selection from the current app visit; an
older immutable design may be explicitly inspected and selected again. It SHALL
NOT imply a durable rollback timeline or undo completed effects.

#### Scenario: Handler fails after an effect
- **WHEN** the selected handler fails or its terminal outcome is uncertain
- **THEN** the app reports the actual run state and keeps recovery available
- **AND** it does not automatically invoke the default writer or resend the whole request

#### Scenario: Disable races with another installation update
- **WHEN** the expected private binding revision is stale
- **THEN** recovery reports conflict and reloads the current selection before a new explicit update
- **AND** it does not overwrite the newer state

### Requirement: Capability claims match real consumption
The platform SHALL distinguish preserved definitions, supported consumers,
activated installations and completed execution. This first adapter SHALL NOT
claim arbitrary executable UI, native-device event routing, foreign-harness
loading or whole-setup migration merely because their components round-trip.

#### Scenario: A design requires a renderer the platform does not have
- **WHEN** the receiver inspects that design
- **THEN** the UI identifies the missing governed renderer requirement
- **AND** ordinary layout and turn-consumer support are reported separately
