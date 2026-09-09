## ADDED Requirements

### Requirement: Connection-scoped model choices
The app SHALL expose model choices from the universe owner's authorized connections with freshness and capability information, without a compiled model-release list.

#### Scenario: A newly released model appears
- **WHEN** refreshed connection discovery returns a new model
- **THEN** the owner can see and select it without a platform release, subject to current authority and supported capabilities

#### Scenario: Discovery fails
- **WHEN** discovery cannot refresh
- **THEN** cached choices are labelled stale and the app does not claim current availability

### Requirement: Current choice and durable preference are distinct
The app SHALL allow switching the interactive agent, saving a default and ordering accepted fallbacks independently of connection identity and actual execution receipts.

#### Scenario: Concurrent universe choices
- **WHEN** two owners choose different models on the same provider family
- **THEN** each next authorized inference uses its own choice without process-global preference leakage

#### Scenario: No accepted fallback
- **WHEN** the owner saves a model with an empty fallback sequence
- **THEN** exhaustion leaves that selection unchanged and does not substitute another source

### Requirement: Actual execution is visible and actionable
The typed-chat interface SHALL show a clickable active provider/model control, distinguish preference from actual execution, and remain usable without a working LLM.

#### Scenario: A router answers with another model
- **WHEN** a response reports a model different from the requested alias
- **THEN** the answering-model display uses the reported model without rewriting the saved default

#### Scenario: Model metadata is unavailable
- **WHEN** a response does not report a usable model identifier
- **THEN** the answer remains usable and the display marks the actual model unknown instead of presenting the requested alias as verified
