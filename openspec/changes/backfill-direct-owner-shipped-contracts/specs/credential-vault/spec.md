## ADDED Requirements

### Requirement: Provider credentials project into exact CLI environments
The system SHALL map a universe vault's `llm_api_key` service aliases to provider environment variables as follows: `anthropic`, `claude`, and `claude-code` map to `ANTHROPIC_API_KEY`; `openai` and `codex` map to `OPENAI_API_KEY`; `gemini` and `google` map to `GEMINI_API_KEY`; `groq` maps to `GROQ_API_KEY`; and `xai` and `grok` map to `XAI_API_KEY`. The `claude-code` subprocess projection SHALL include only a resolved `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_OAUTH_TOKEN`, and/or `ANTHROPIC_API_KEY`; the `codex` projection SHALL include only a resolved `CODEX_HOME` and/or `OPENAI_API_KEY`; every other provider name SHALL receive no vault-auth overrides. A Claude subscription record SHALL resolve the first `oauth_token` or `claude_code_oauth_token` secret it contains. A BYO key SHALL be selected only from an `llm_api_key` record whose service maps to the requested environment variable.

#### Scenario: Claude OAuth token is projected to the Claude CLI
- **WHEN** the selected universe has a Claude subscription record containing `oauth_token`
- **THEN** the `claude-code` projection includes that value as `CLAUDE_CODE_OAUTH_TOKEN`
- **AND** the `codex` projection does not receive it

#### Scenario: Claude BYO key reaches only the Claude CLI route
- **WHEN** the selected universe has an `llm_api_key` record whose service is `anthropic`, `claude`, or `claude-code`
- **THEN** the `claude-code` projection includes the secret as `ANTHROPIC_API_KEY`
- **AND** the `codex` projection does not receive that key

#### Scenario: OpenAI BYO key reaches only the Codex CLI route
- **WHEN** the selected universe has an `llm_api_key` record whose service is `openai` or `codex`
- **THEN** the `codex` projection includes the secret as `OPENAI_API_KEY`
- **AND** the `claude-code` projection does not receive that key

#### Scenario: Non-CLI provider has no vault projection
- **WHEN** provider auth overrides are requested for a provider name other than `codex` or `claude-code`
- **THEN** the projection is empty even if the vault contains a service alias for an in-process provider

### Requirement: Credential vault replacement is process-local and unversioned
The system SHALL write the validated vault payload to the fixed sibling path `.credential-vault.json.tmp`, apply mode `0600` on a best-effort basis, replace `.credential-vault.json` with that temporary file, and apply mode `0600` to the replacement on a best-effort basis. The payload SHALL contain `schema_version: 1` and the normalized credential list, while the returned summary SHALL omit secret values. This boundary SHALL NOT claim cross-process locking, a unique temporary filename, compare-and-swap, or version conflict detection; overlapping writers can race over the same temporary and target paths.

#### Scenario: Successful write replaces the vault and returns a secret-free summary
- **WHEN** a valid credential list is written without an overlapping writer or filesystem error
- **THEN** the target contains the versioned normalized JSON payload
- **AND** the returned summary reports path, count, credential types, and services without returning credential secrets

#### Scenario: Concurrent writers have no serialization guarantee
- **WHEN** two processes write the same universe vault concurrently
- **THEN** the current boundary provides no lock, unique temporary path, compare-and-swap check, or deterministic winner guarantee

