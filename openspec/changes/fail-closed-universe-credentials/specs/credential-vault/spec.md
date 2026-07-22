# Credential Vault Delta

## MODIFIED Requirements

### Requirement: Per-Universe Provider Auth Env Overlay Without Cross-Universe Leakage

For every provider call carrying an explicit universe directory, the system SHALL construct the subprocess environment by removing all ambient provider API-key variables and host subscription selectors, including `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`, and `CODEX_HOME`, before applying only credentials resolved from that universe's vault. A universe-scoped cloud provider with no resolvable vault credential SHALL NOT be invoked. Calls with no universe context SHALL preserve host daemon and local-development authentication behavior.

#### Scenario: Vaultless universe cannot inherit host subscription auth

- **GIVEN** the daemon environment contains valid Claude and Codex host subscription variables
- **AND** a universe has no credential vault
- **WHEN** that universe routes a writer call
- **THEN** neither cloud provider is invoked using the host subscription
- **AND** routing fails with provider exhaustion unless an explicitly eligible credentialless local provider serves it.

#### Scenario: Founder BYO key replaces rather than composes with host auth

- **GIVEN** a universe vault contains a founder-provided API key for its selected writer
- **WHEN** the provider subprocess environment is built
- **THEN** it contains the founder key and an isolated provider home
- **AND** contains no host token, host config directory, or host provider home.

#### Scenario: Host development call remains compatible

- **GIVEN** a provider call with no universe context
- **WHEN** its subprocess environment is built
- **THEN** the existing host daemon/developer authentication behavior is preserved.
