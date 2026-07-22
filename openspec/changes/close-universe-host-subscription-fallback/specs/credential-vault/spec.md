## ADDED Requirements

### Requirement: Universe-scoped CLI provider subprocesses never inherit host provider authority

`subprocess_env_for_provider` SHALL classify any non-empty explicit `universe_dir` or environment binding as universe scope before applying provider authentication, without requiring the bound path or vault helper to succeed first. For a universe-scoped CLI call, the child environment SHALL remove inherited OAuth/API-provider variables, SHALL replace inherited or default-discovered CLI auth homes with that universe's `.credentials/claude` and `.credentials/codex` paths, and only then SHALL apply that universe's credential-vault overlay. This isolation SHALL apply even when host API-key providers are opted in. A missing credential, a partial vault overlay, a missing/malformed universe path, or any credential-resolution failure SHALL NOT restore or preserve maintainer provider authority in the CLI child. Credential-resolution failures SHALL fail explicitly with a sanitized error. A host-local call with no explicit or environment binding SHALL preserve provider variables according to the host's normal API-key opt-in policy and SHALL NOT require a vault helper.

This requirement governs credential authority only. Provider-chain allowlisting and provider/credential-source receipts remain separate requirements.

#### Scenario: Uncredentialed universe cannot spend host subscription

- **GIVEN** the host process carries all three host subscription variables
- **WHEN** a universe with no provider credential prepares a provider subprocess
- **THEN** inherited tokens and API-provider variables are absent
- **AND** `CLAUDE_CONFIG_DIR` and `CODEX_HOME` point to that universe's `.credentials` roots rather than maintainer auth homes
- **AND** the provider fails authentication rather than using host authority

#### Scenario: Partial universe overlay cannot retain alternate host authority

- **GIVEN** the host process carries a Claude OAuth token and shared Claude and Codex homes
- **WHEN** the universe vault supplies only its own `CLAUDE_CONFIG_DIR`
- **THEN** the universe-owned Claude directory is present
- **AND** the inherited host OAuth token is absent
- **AND** `CODEX_HOME` points to the universe's Codex `.credentials` root rather than the host home

#### Scenario: Host API-key opt-in does not leak into a universe CLI child

- **GIVEN** the host has opted into API-key providers and carries process-global provider keys or endpoints
- **WHEN** a universe with no matching vault credential prepares a provider subprocess
- **THEN** none of the process-global API-provider variables is present in the CLI child environment
- **AND** the CLI cannot use maintainer API quota through inherited environment authority

#### Scenario: Default CLI homes cannot recover maintainer subscription authority

- **GIVEN** the host has valid-looking auth only under `HOME/.claude` and `HOME/.codex`
- **WHEN** an uncredentialed universe prepares a provider subprocess without explicit auth-home variables
- **THEN** the child pins `CLAUDE_CONFIG_DIR` and `CODEX_HOME` to that universe's `.credentials` roots
- **AND** neither CLI can discover the maintainer's default-home auth

#### Scenario: Credential-resolution failure is fail-closed

- **WHEN** a universe-scoped vault import or resolver raises an unexpected error
- **THEN** provider launch is refused with an explicit credential-resolution error
- **AND** no environment containing inherited host subscription authority is returned
- **AND** the error does not include underlying credential values or helper exception text

#### Scenario: Host-local execution retains host authority without vault helpers

- **WHEN** no explicit or environment-bound universe is present and vault helpers are unavailable
- **THEN** the host-local subprocess retains host provider variables according to the host's normal API-key opt-in policy
- **AND** environment assembly succeeds without invoking a vault helper
