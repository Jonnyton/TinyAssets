## MODIFIED Requirements

### Requirement: Per-Universe Provider Auth Env Overlay Without Cross-Universe Leakage
The system SHALL construct a CLI writer subprocess environment from the host environment, the subscription-only API-key policy, and at most one resolved universe's vault. When API-key providers are not explicitly enabled, `subprocess_env_without_api_keys` MUST remove `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `GEMINI_API_KEY`, `GROQ_API_KEY`, and `XAI_API_KEY` before vault auth is applied. `apply_provider_auth_env` / `provider_auth_env_overrides` SHALL then overlay the explicitly supplied `universe_dir`, or otherwise the universe resolved from `TINYASSETS_UNIVERSE`: for the `codex` writer it MAY inject `CODEX_HOME` and `OPENAI_API_KEY`; for the `claude-code` writer it MAY inject `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_OAUTH_TOKEN`, and `ANTHROPIC_API_KEY`. If a universe is resolved and applying its vault changes none of the inherited host-subscription variables `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`, and `CODEX_HOME`, the environment builder MUST remove all three so the ordinary missing-credential path fails authentication rather than consuming the host's subscription. It SHALL preserve host subscription variables for a host-local call with no resolved universe. As-built limitations: this removal is all-or-nothing, so changing any one host-subscription variable preserves every unchanged inherited host value; and any non-`ValueError` raised while importing, applying, or resolving vault helpers is swallowed and returns the environment in its current state, which can also retain inherited host subscription values for an explicitly resolved universe. A malformed-vault `ValueError` SHALL propagate. A bring-your-own `llm_api_key` deposit SHALL be accepted only for a service that maps to a supported provider env var, and an unsupported service SHALL be rejected at deposit time so a key that could never reach a provider is not silently stored.

#### Scenario: Env overlay resolves the universe from the environment binding
- **WHEN** a subprocess environment binds `TINYASSETS_UNIVERSE` to a universe whose vault configures a Claude config directory, and the claude-code auth overlay is applied
- **THEN** the environment gains `CLAUDE_CONFIG_DIR` set to the configured directory

#### Scenario: Explicit universe directory wins over process binding
- **WHEN** the process environment points at universe A but a provider call supplies universe B's directory explicitly
- **THEN** the auth overlay resolves credentials from universe B and does not use universe A's vault

#### Scenario: Universe without credential does not inherit host subscription
- **WHEN** a universe-scoped provider subprocess begins with host `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`, or `CODEX_HOME` values and the resolved universe's vault supplies none of those variables
- **THEN** all inherited host-subscription variables are absent from the final environment so the universe call fails closed instead of billing the host

#### Scenario: Host-local provider call keeps host subscription
- **WHEN** a provider subprocess call has no explicit or environment-resolved universe
- **THEN** the environment builder retains the host's subscription variables for that host-local daemon or development flow

#### Scenario: Vault-supplied subscription replacement survives
- **WHEN** a resolved universe's vault replaces at least one host-subscription variable with that universe's own value
- **THEN** the replacement remains in the final environment and the all-or-nothing missing-credential guard does not run
- **AND** any other inherited host-subscription variables remain unchanged, so a partial overlay can still expose host credentials

#### Scenario: Unexpected overlay error preserves the current environment
- **WHEN** importing, applying, or resolving the vault helpers raises an exception other than `ValueError` after a universe-scoped environment has inherited host subscription variables
- **THEN** the environment builder swallows the error and returns the environment in its current state without guaranteeing removal of those host variables

#### Scenario: Malformed vault fails loudly
- **WHEN** vault application or resolution raises `ValueError` for malformed credential data
- **THEN** the environment builder propagates that error instead of returning an environment

#### Scenario: API keys are stripped under the default policy
- **WHEN** API-key providers are not explicitly enabled and a provider subprocess environment inherits any configured API-key variable from the host
- **THEN** those API-key variables are removed before the universe vault overlay, after which only a supported value supplied by that universe can re-enter the environment

#### Scenario: Unsupported bring-your-own service is rejected at deposit
- **WHEN** a founder attempts to deposit an `llm_api_key` for a service that does not map to any supported provider env var
- **THEN** the deposit is rejected with an error naming the supported services and no unusable key is written to the vault
