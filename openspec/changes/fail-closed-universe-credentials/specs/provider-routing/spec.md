# Provider Routing Delta

## MODIFIED Requirements

### Requirement: Per-universe engine preference and privacy allowlist

Every successful `set_engine` action that selects a concrete, credential-bound provider SHALL persist `allowed_providers` containing only that provider in addition to `preferred_writer`. A BYO key/provider mismatch SHALL be rejected. Universe-scoped routing SHALL filter out every cloud provider whose credential is not resolvable from the universe vault across normal chains, policy attempt orders, judge ensembles, version runs, and resumed runs, and SHALL fail closed rather than fall back to ambient host credentials.

#### Scenario: Selected founder engine cannot fall through to host credentials

- **GIVEN** a founder sets a Claude engine with their Anthropic key
- **WHEN** Claude fails
- **THEN** the router does not attempt Codex or any other provider outside `allowed_providers=["claude-code"]`.

#### Scenario: BYO key cannot select an incompatible provider

- **GIVEN** an Anthropic key and `preferred_writer="codex"`
- **WHEN** `set_engine` validates the assignment
- **THEN** it rejects the mismatch and does not modify the vault or config.

#### Scenario: Unbound host daemon does not authorize platform credentials

- **GIVEN** a founder selects `engine_source="host_daemon"`
- **AND** no founder-hosted runtime credential has been bound yet
- **WHEN** `set_engine` persists the selection
- **THEN** it records the preferred provider with `allowed_providers=[]` and a pending binding status
- **AND** universe calls fail closed rather than use ambient platform credentials.

#### Scenario: Vaultless judge ensemble cannot spend host API keys

- **GIVEN** host API-key judge providers are enabled
- **AND** a universe has no resolvable judge credential
- **WHEN** the universe requests a judge ensemble
- **THEN** no host-key provider is invoked and the ensemble returns no results.

## ADDED Requirements

### Requirement: Public provider and credential-payer receipts

Every provider-served public `converse` or `run_graph` operation SHALL expose a non-secret receipt naming the serving provider and credential payer class/owner. `converse` SHALL label its reply and learning-extraction calls separately. Because `run_graph` is asynchronous and may make zero to many calls, enqueue SHALL report `provider_receipt_status="pending"`; the durable run snapshot SHALL expose one receipt per provider-served node after calls occur. Receipts SHALL NOT contain tokens, secret values, or credential file contents.

#### Scenario: Converse reports both paid calls

- **WHEN** a founder conversation produces a reply and runs learning extraction
- **THEN** the response contains two purpose-labelled receipts with provider, credential class, and owner.

#### Scenario: Async graph reports pending then durable per-node receipts

- **WHEN** `run_graph` enqueues a run
- **THEN** its immediate response reports pending receipt state without claiming an unserved provider
- **AND WHEN** `get_run` is called after provider-served nodes execute
- **THEN** it returns their durable provider/payer receipts.

#### Scenario: Terminal failure preserves prior paid-call receipts

- **GIVEN** one graph node completes a provider call and a later node fails or is cancelled
- **WHEN** `get_run` returns the terminal snapshot
- **THEN** it includes the completed node's provider/payer receipt rather than an empty complete receipt set.
