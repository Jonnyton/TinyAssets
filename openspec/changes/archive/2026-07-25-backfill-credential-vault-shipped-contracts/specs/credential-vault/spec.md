## ADDED Requirements

### Requirement: Credential alias selection and first-record secret extraction are exact
The system SHALL derive a credential record's effective service by taking non-empty `service` before non-empty `provider`, then trimming and lowercasing its string form. For `llm_api_key` records, `anthropic`, `claude`, and `claude-code` map to `ANTHROPIC_API_KEY`; `openai` and `codex` map to `OPENAI_API_KEY`; `gemini` and `google` map to `GEMINI_API_KEY`; `groq` maps to `GROQ_API_KEY`; and `xai` and `grok` map to `XAI_API_KEY`. A BYO-key lookup SHALL scan records in stored order and return from the first `llm_api_key` record whose normalized effective service maps to the requested environment variable. From that record it SHALL return the first non-empty string `api_key`, `key`, or `token`, otherwise the decoded string from a truthy `token_b64` before `secret_b64`; if the selected value is not a non-empty string or decodes empty, resolution SHALL return empty without scanning later matching records. Claude OAuth resolution SHALL likewise inspect only the first `llm_subscription` record whose normalized effective service is `claude`, returning its first non-empty string `oauth_token` or `claude_code_oauth_token`, otherwise its selected base64 field, and returning empty without scanning later matching records. Base64 resolution SHALL use the runtime's permissive standard decoder followed by UTF-8 decoding and whitespace trimming: ignored non-alphabet characters are not independently rejected, while an actual base64 or UTF-8 decoding exception SHALL be surfaced as `ValueError`.

#### Scenario: Normalized BYO aliases select their environment variable
- **WHEN** an `llm_api_key` record uses one of the ten supported effective-service aliases with any letter case or surrounding whitespace
- **THEN** it is eligible only for the environment variable named by the exact alias table

#### Scenario: Provider supplies the effective service when service is absent
- **WHEN** an `llm_api_key` record omits or empties `service` and names a supported alias in `provider`
- **THEN** BYO-key lookup uses that `provider` value as the effective service

#### Scenario: Empty first BYO match shadows later records
- **WHEN** the first `llm_api_key` record mapped to the requested environment variable has no supported string secret and a later mapped record does
- **THEN** BYO-key resolution returns empty without inspecting the later record

#### Scenario: First Claude subscription yields a direct or base64 secret
- **WHEN** the first effective-service `claude` subscription contains a direct OAuth field or a decodable `token_b64` or `secret_b64`
- **THEN** Claude OAuth resolution returns that record's first available secret in the specified order

#### Scenario: Empty first Claude subscription shadows later records
- **WHEN** the first effective-service `claude` subscription has no supported secret and a later matching subscription does
- **THEN** Claude OAuth resolution returns empty without inspecting the later record

#### Scenario: Selected base64 decoding exceptions fail loudly
- **WHEN** a selected BYO-key or first matching Claude subscription record has no supported direct secret and standard base64 or UTF-8 decoding of its selected `token_b64` or `secret_b64` raises
- **THEN** resolution raises `ValueError` without returning empty or scanning a later record

#### Scenario: Unknown effective service does not resolve
- **WHEN** an `llm_api_key` record's normalized effective service is absent or not in the exact alias table
- **THEN** that record does not satisfy any provider environment lookup

### Requirement: Credential vault replacement is process-local and unversioned
The system SHALL write each validated vault payload through the fixed sibling path `.credential-vault.json.tmp` and replace `.credential-vault.json` directly from that path. This boundary SHALL NOT claim cross-process locking, a unique temporary filename, compare-and-swap, or version conflict detection; overlapping writers can race over the same temporary and target paths.

#### Scenario: Successful write replaces the vault through the fixed sibling
- **WHEN** a valid credential list is written without an overlapping writer or filesystem error
- **THEN** `.credential-vault.json.tmp` is written and directly replaces `.credential-vault.json`

#### Scenario: Concurrent writers have no serialization guarantee
- **WHEN** two processes write the same universe vault concurrently
- **THEN** the current boundary provides no lock, unique temporary path, compare-and-swap check, or deterministic winner guarantee
