## ADDED Requirements

### Requirement: Universe-scoped provider subprocesses never inherit host subscription authority

`subprocess_env_for_provider` SHALL determine whether a call is universe-scoped before applying provider authentication. For a universe-scoped call, the child environment SHALL remove inherited `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`, and `CODEX_HOME` before applying only that universe's credential-vault overlay. A missing credential, a partial vault overlay, or any credential-resolution failure SHALL NOT restore or preserve host subscription authority. Credential-resolution failures SHALL fail explicitly. A host-local call for which no universe resolves MAY preserve the host's own subscription variables.

This requirement governs credential authority only. Provider-chain allowlisting and provider/credential-source receipts remain separate requirements.

#### Scenario: Uncredentialed universe cannot spend host subscription

- **GIVEN** the host process carries all three host subscription variables
- **WHEN** a universe with no provider credential prepares a provider subprocess
- **THEN** none of the three variables is present in the child environment
- **AND** the provider fails authentication rather than using host authority

#### Scenario: Partial universe overlay cannot retain alternate host authority

- **GIVEN** the host process carries a Claude OAuth token and shared Claude and Codex homes
- **WHEN** the universe vault supplies only its own `CLAUDE_CONFIG_DIR`
- **THEN** the universe directory is present
- **AND** the inherited host OAuth token and Codex home are absent

#### Scenario: Credential-resolution failure is fail-closed

- **WHEN** a universe-scoped vault import or resolver raises an unexpected error
- **THEN** provider launch is refused with an explicit credential-resolution error
- **AND** no environment containing inherited host subscription authority is returned

#### Scenario: Host-local execution retains host authority

- **WHEN** no explicit or environment-bound universe resolves
- **THEN** the host-local subprocess retains the host subscription variables
