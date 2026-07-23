## ADDED Requirements

### Requirement: Credential alias selection and first-record secret extraction are exact
The system SHALL map an `llm_api_key` record's effective service, defined as non-empty `service` falling back to non-empty `provider`, to an environment variable as follows: `anthropic`, `claude`, and `claude-code` map to `ANTHROPIC_API_KEY`; `openai` and `codex` map to `OPENAI_API_KEY`; `gemini` and `google` map to `GEMINI_API_KEY`; `groq` maps to `GROQ_API_KEY`; and `xai` and `grok` map to `XAI_API_KEY`. A BYO-key lookup SHALL scan only `llm_api_key` records whose effective service maps to the requested environment variable and SHALL return the first matching record's first non-empty `api_key`, `key`, or `token`, otherwise its decoded `token_b64` or `secret_b64`; if that first matching record has no supported secret, resolution SHALL return empty without scanning later matching records. Claude OAuth resolution SHALL inspect only the first `llm_subscription` record whose effective service is exactly `claude`, returning that record's first non-empty `oauth_token` or `claude_code_oauth_token`, otherwise its decoded `token_b64` or `secret_b64`, and returning empty without scanning later matching records when the first record has no secret. For either resolver, a selected non-empty base64 field that cannot be decoded as base64 and UTF-8 SHALL raise `ValueError` rather than returning empty or scanning a later record.

#### Scenario: Exact BYO aliases select their environment variable
- **WHEN** an `llm_api_key` record uses one of the ten supported effective-service aliases
- **THEN** it is eligible only for the environment variable named by the exact alias table

#### Scenario: Provider supplies the effective service when service is absent
- **WHEN** an `llm_api_key` record omits or empties `service` and names a supported alias in `provider`
- **THEN** BYO-key lookup uses that `provider` value as the effective service

#### Scenario: First Claude subscription yields a direct or base64 secret
- **WHEN** the first effective-service `claude` subscription contains a direct OAuth field or a decodable `token_b64` or `secret_b64`
- **THEN** Claude OAuth resolution returns that record's first available secret in the specified order

#### Scenario: Empty first Claude subscription shadows later records
- **WHEN** the first effective-service `claude` subscription has no supported secret and a later matching subscription does
- **THEN** Claude OAuth resolution returns empty without inspecting the later record

#### Scenario: Malformed selected base64 fails loudly
- **WHEN** a selected BYO-key or first matching Claude subscription record has no supported direct secret and its selected `token_b64` or `secret_b64` cannot be decoded as base64 and UTF-8
- **THEN** resolution raises `ValueError` without returning empty or scanning a later record

#### Scenario: Unknown effective service does not resolve
- **WHEN** an `llm_api_key` record's effective service is absent or not in the exact alias table
- **THEN** that record does not satisfy any provider environment lookup

### Requirement: Credential vault replacement is process-local and unversioned
The system SHALL write each validated vault payload through the fixed sibling path `.credential-vault.json.tmp` and replace `.credential-vault.json` directly from that path. This boundary SHALL NOT claim cross-process locking, a unique temporary filename, compare-and-swap, or version conflict detection; overlapping writers can race over the same temporary and target paths.

#### Scenario: Successful write replaces the vault through the fixed sibling
- **WHEN** a valid credential list is written without an overlapping writer or filesystem error
- **THEN** `.credential-vault.json.tmp` is written and directly replaces `.credential-vault.json`

#### Scenario: Concurrent writers have no serialization guarantee
- **WHEN** two processes write the same universe vault concurrently
- **THEN** the current boundary provides no lock, unique temporary path, compare-and-swap check, or deterministic winner guarantee
