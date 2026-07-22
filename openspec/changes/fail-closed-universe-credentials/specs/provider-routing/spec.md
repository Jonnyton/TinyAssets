# Provider Routing Delta

## MODIFIED Requirements

### Requirement: Per-universe engine preference and privacy allowlist

Every successful `set_engine` action that selects a concrete provider SHALL persist `allowed_providers` containing only that provider in addition to `preferred_writer`. A BYO key/provider mismatch SHALL be rejected. Universe-scoped routing SHALL filter out every cloud provider whose credential is not resolvable from the universe vault, including per-node policy attempt orders, and SHALL fail closed rather than fall back to ambient host credentials.

#### Scenario: Selected founder engine cannot fall through to host credentials

- **GIVEN** a founder sets a Claude engine with their Anthropic key
- **WHEN** Claude fails
- **THEN** the router does not attempt Codex or any other provider outside `allowed_providers=["claude-code"]`.

#### Scenario: BYO key cannot select an incompatible provider

- **GIVEN** an Anthropic key and `preferred_writer="codex"`
- **WHEN** `set_engine` validates the assignment
- **THEN** it rejects the mismatch and does not modify the vault or config.

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
