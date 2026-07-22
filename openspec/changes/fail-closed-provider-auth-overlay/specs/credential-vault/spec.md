## MODIFIED Requirements

### Requirement: Per-Universe Provider Auth Env Overlay Without Cross-Universe Leakage
The system SHALL construct a CLI writer subprocess environment from the host environment, the subscription-only API-key policy, and at most one resolved universe's vault. When API-key providers are not explicitly enabled, `subprocess_env_without_api_keys` MUST remove `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `GEMINI_API_KEY`, `GROQ_API_KEY`, and `XAI_API_KEY` before vault auth is applied. A call MUST be treated as universe-scoped when it supplies `universe_dir` or the copied environment contains a non-empty `TINYASSETS_UNIVERSE`; before importing, resolving, or applying any vault helper, the environment builder SHALL remove inherited `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`, and `CODEX_HOME`. `apply_provider_auth_env` / `provider_auth_env_overrides` SHALL then add only credentials supplied by the explicitly selected universe, or otherwise the universe bound by `TINYASSETS_UNIVERSE`: for the `codex` writer it MAY inject `CODEX_HOME` and `OPENAI_API_KEY`; for the `claude-code` writer it MAY inject `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_OAUTH_TOKEN`, and `ANTHROPIC_API_KEY`. A malformed-vault `ValueError` SHALL propagate, and any other import, application, or resolution error for a universe-scoped call MUST raise `ProviderUnavailableError` without exposing environment or vault secret values. A host-local call with no explicit or environment-bound universe SHALL retain host subscription variables and its existing best-effort helper behavior. A bring-your-own `llm_api_key` deposit SHALL be accepted only for a service that maps to a supported provider env var, and an unsupported service SHALL be rejected at deposit time so a key that could never reach a provider is not silently stored.

#### Scenario: Env overlay resolves the universe from the environment binding
- **WHEN** a subprocess environment binds `TINYASSETS_UNIVERSE` to a universe whose vault configures a Claude config directory, and the claude-code auth overlay is applied
- **THEN** inherited host subscription variables are removed first and the environment gains `CLAUDE_CONFIG_DIR` set to the universe's configured directory

#### Scenario: Explicit universe directory wins over process binding
- **WHEN** the process environment points at universe A but a provider call supplies universe B's directory explicitly
- **THEN** inherited host subscription variables are removed and the auth overlay resolves credentials from universe B rather than universe A

#### Scenario: Universe without credential does not inherit host subscription
- **WHEN** a universe-scoped provider subprocess begins with host `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`, or `CODEX_HOME` values and the selected universe's vault supplies none of those variables
- **THEN** all inherited host-subscription variables are absent from the final environment so the universe call fails authentication instead of billing the host

#### Scenario: Partial overlay cannot retain unrelated host credentials
- **WHEN** a universe vault supplies only one host-subscription variable, such as its own `CLAUDE_CONFIG_DIR`, while the copied host environment also contains an OAuth token and Codex home
- **THEN** the universe-supplied value remains and every host-subscription variable omitted by the vault remains absent

#### Scenario: Unexpected scoped overlay error fails closed and loud
- **WHEN** importing, applying, or resolving vault helpers raises an exception other than `ValueError` for an explicit or environment-bound universe call
- **THEN** no inherited host-subscription value is available to the provider and the environment builder raises `ProviderUnavailableError` without secret material in its message

#### Scenario: Malformed vault fails loudly
- **WHEN** vault application or resolution raises `ValueError` for malformed credential data
- **THEN** the environment builder propagates that error instead of returning an environment

#### Scenario: Host-local provider call keeps host subscription
- **WHEN** a provider subprocess call has no explicit `universe_dir` and no non-empty `TINYASSETS_UNIVERSE` binding
- **THEN** the environment builder retains the host's subscription variables and an unexpected optional vault-helper failure does not create a cross-universe secret path

#### Scenario: API keys are stripped under the default policy
- **WHEN** API-key providers are not explicitly enabled and a provider subprocess environment inherits any configured API-key variable from the host
- **THEN** those API-key variables are removed before the universe vault overlay, after which only a supported value supplied by that universe can re-enter the environment

#### Scenario: Unsupported bring-your-own service is rejected at deposit
- **WHEN** a founder attempts to deposit an `llm_api_key` for a service that does not map to any supported provider env var
- **THEN** the deposit is rejected with an error naming the supported services and no unusable key is written to the vault
