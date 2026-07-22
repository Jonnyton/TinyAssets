## MODIFIED Requirements

### Requirement: Per-Universe Provider Auth Env Overlay Without Cross-Universe Leakage

The system SHALL overlay per-universe provider auth onto a CLI-subprocess writer's environment (`apply_provider_auth_env` / `provider_auth_env_overrides`) so a universe runs on its founder's assigned engine rather than the host's. For the `codex` writer it MAY inject `CODEX_HOME` and `OPENAI_API_KEY`; for the `claude-code` writer it MAY inject `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_OAUTH_TOKEN`, and `ANTHROPIC_API_KEY`. An explicit-universe environment SHALL remove every process-global API-key and subscription-auth variable regardless of host API-key opt-in before applying only that universe's overlay. CLI auth materialization SHALL reacquire the same assignment lock and require fresh `engine_assignment_state="ready"` plus candidate membership before reading the vault and returning an immutable child environment; the lock SHALL be released before CLI/network execution. Any vault load, import, or credential-materialization error SHALL fail before subprocess launch and SHALL NOT return inherited auth. A bring-your-own `llm_api_key` deposit through `set_engine` SHALL be accepted only for a service with an executable per-universe provider route: `anthropic` to `claude-code` or `openai` to `codex`. `set_engine` SHALL initialize `preferred_writer` and the singleton ceiling to that provider; a contradictory explicit writer or unroutable service/alias SHALL be rejected before mutation. All `set_engine` sources SHALL serialize on the same per-universe cross-process `.engine-assignment.lock` from snapshot through commit or rollback. Before secret mutation, config SHALL store `engine_assignment_state="pending"` with `allowed_providers=[]`; only a complete commit stores `engine_assignment_state="ready"`. Successful assignment SHALL replace prior engine API-key records while preserving unrelated vault records. Ordinary failure SHALL restore the exact prior vault and config; rollback failure SHALL leave the pending empty-ceiling quarantine in place and report both failures.

#### Scenario: Env overlay resolves the universe from the environment binding

- **WHEN** a subprocess environment binds `TINYASSETS_UNIVERSE` to a universe whose vault configures a Claude config directory, and the claude-code auth overlay is applied
- **THEN** the environment gains `CLAUDE_CONFIG_DIR` set to the configured directory
- **AND** no unrelated host API key, auth home, or subscription token remains

#### Scenario: Unsupported bring-your-own service is rejected at deposit

- **WHEN** a founder attempts `set_engine` with an `llm_api_key` service or alias that has no executable per-universe provider route
- **THEN** the deposit is rejected with an error naming `anthropic` and `openai` and no unusable key is written to the vault

#### Scenario: Mismatched service and writer are rejected without mutation

- **WHEN** a founder submits an Anthropic key with explicit `preferred_writer="codex"` or an OpenAI key with explicit `preferred_writer="claude-code"`
- **THEN** `set_engine` returns an error identifying the matching provider
- **AND** neither the credential vault nor universe config is created or changed

#### Scenario: Successful BYO deposit binds credential and route

- **WHEN** a supported service/provider pair is accepted through `set_engine`
- **THEN** the vault stores the key only under that service
- **AND** the config stores that provider as both preferred and exclusively allowed
- **AND** the response and ledger contain no key material

#### Scenario: Successful BYO deposit preserves unrelated credentials

- **WHEN** a vault containing social, VCS, subscription, and prior engine API-key records receives a successful BYO engine assignment
- **THEN** the prior engine API-key set is replaced by only the selected service key
- **AND** every unrelated social, VCS, and subscription record remains semantically unchanged

#### Scenario: Host API-key opt-in does not authorize an explicit universe

- **WHEN** host API-key opt-in and ambient provider keys/auth homes are present but an explicit universe has no matching vault credential
- **THEN** its subprocess environment contains none of the ambient provider auth values
- **AND** the provider fails before consuming host or platform quota

#### Scenario: Vault failure never returns inherited auth

- **WHEN** vault load, import, or credential materialization raises an I/O or unexpected error for an explicit universe
- **THEN** environment construction raises before subprocess launch
- **AND** no inherited API key, OAuth token, config directory, or auth home is returned

#### Scenario: Auth materialization cannot cross a reassignment quarantine

- **WHEN** routing admits a CLI provider, then reassignment stores `pending` and mutates the vault before child auth is materialized
- **THEN** auth materialization reacquires the assignment lock, revalidates fresh state and provider membership, and returns no partial/new environment while pending
- **AND** no subprocess launches until a complete ready assignment or exact rollback is observed

#### Scenario: Config failure restores the previous vault and ceiling

- **WHEN** a BYO assignment writes the new vault record but its atomic config update fails
- **THEN** the exact prior vault content/existence and prior config remain in place
- **AND** the failed assignment cannot leave a new credential reachable through an unrestricted or stale ceiling

#### Scenario: Rollback failure quarantines later routing

- **WHEN** assignment fails after secret mutation and exact vault or config restoration also fails
- **THEN** the action reports both the assignment and rollback failure and never reports success
- **AND** the durable pending state retains `allowed_providers=[]`
- **AND** subsequent normal, policy, and judge routes invoke zero providers until an explicit repair completes

#### Scenario: Concurrent assignments cannot mix or stale-rollback state

- **WHEN** two same-universe assignments overlap and one succeeds while the other fails
- **THEN** the cross-process assignment lock serializes their snapshot-to-rollback/commit sections
- **AND** final vault key, preferred provider, singleton ceiling, and `engine_assignment_state="ready"` belong to one complete successful transaction
- **AND** the failed transaction cannot restore over or mix with the later winner
