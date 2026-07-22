# Credential Vault

> As-built baseline (2026-07-19, change `spec-out-existing-platform`): describes landed behavior on `main` at baseline time, known limitations included. Future behavior changes arrive as OpenSpec change deltas against this capability.

## Purpose

Per-universe typed credential store (as-built: flat JSON guarded by best-effort file permissions) with daemon-side resolvers and a provider auth env overlay so a universe runs on its founder's assigned engine, not the host's.

## Requirements

### Requirement: Per-Universe Typed Credential Store

The system SHALL persist credentials in a per-universe vault file named `.credential-vault.json` inside the universe directory, written as a JSON object with `schema_version` 1 and a `credentials` list. Every credential record SHALL declare a `credential_type` that is one of `social`, `llm_subscription`, `llm_api_key`, or `vcs`; a record with any other type SHALL be rejected at write time. The write helper (`tinyassets.credential_vault.write_credential_vault`) SHALL return a non-secret summary containing only the vault path, credential count, credential types, and service names, and SHALL never include secret material in that summary.

#### Scenario: Typed credentials round-trip and the summary carries no secret

- **WHEN** a caller writes a vault containing a `vcs`/github record with a token, a `social` record with a token, and an `llm_subscription` record
- **THEN** the returned summary reports `credential_count` 3 and the sorted credential types, and no secret token string appears anywhere in the summary
- **AND** loading the vault back returns the stored records including their secret values

#### Scenario: Unknown credential type is rejected

- **WHEN** a caller attempts to write a record whose `credential_type` is not one of the four allowed types
- **THEN** the write raises a `ValueError` identifying the unknown credential type and the vault is not populated with the invalid record

### Requirement: Fail-Loud Load Semantics

The system SHALL treat a missing vault file as an empty credential set so an absent vault never blocks a daemon. A vault that exists but is not valid JSON, or that contains a non-object credential record or a record missing a `credential_type`, SHALL raise a `ValueError` rather than being silently skipped, so a daemon can never silently grant or lose authority because of a malformed secret file.

#### Scenario: Missing vault loads as empty

- **WHEN** `load_credential_vault` is called for a universe directory that has no `.credential-vault.json`
- **THEN** it returns an empty list without raising

#### Scenario: Malformed vault raises

- **WHEN** a vault file exists but is not valid JSON
- **THEN** `load_credential_vault` raises a `ValueError` describing the parse failure instead of returning partial or empty data

### Requirement: As-Built Storage Protection Is Filesystem Permissions Only

The vault file and any materialized credential artifacts (for example a Codex `auth.json` or a Claude config directory) SHALL be persisted as unencrypted content on disk, and the only at-rest protection SHALL be a best-effort POSIX file mode — `0o600` for the vault file and secret files, `0o700` for the `.credentials` artifact directory. As-built limitation: there is no encryption at rest, no cipher, and no key management; base64 fields such as `token_b64` / `secret_b64` are an encoding convention, not encryption, and best-effort `chmod` is inert on operating systems that do not honor POSIX modes. A layered cipher/store design exists only as an approved future design and is not present in the code on `main`.

#### Scenario: Secret is stored in cleartext under a restricted file mode

- **WHEN** a credential with a plaintext or base64-encoded secret is written to the vault
- **THEN** the on-disk `.credential-vault.json` contains that secret as recoverable cleartext (directly or base64-decodable) with no ciphertext layer
- **AND** the write sets the file mode to `0o600` on operating systems that honor POSIX permissions, while the content itself remains unencrypted regardless of the mode

### Requirement: Daemon-Side GitHub Token Resolution By Exact Destination And Purpose

The system SHALL provide a daemon-side resolver (`resolve_github_token`) that returns a GitHub token only from a `vcs` record whose service is `github` and whose `destination` and `purpose` exactly match the request; any mismatch SHALL yield an empty string. Resolved secret values SHALL be returned only to daemon-side effectors and providers that need them and SHALL NOT be written into public universe state.

#### Scenario: Exact destination and purpose select the correct token

- **WHEN** the vault holds two github `vcs` records for the same destination with `purpose` `read` and `write`, and a caller resolves that destination with `purpose` `write`
- **THEN** the resolver returns the write-purpose token, and resolving with `purpose` `read` returns the read-purpose token

#### Scenario: Mismatched destination yields no token

- **WHEN** a caller resolves a destination that does not exactly match any stored `vcs` record
- **THEN** the resolver returns an empty string rather than a token for a similar destination

### Requirement: Subscription-Home Materialization For CLI Writers

The system SHALL materialize per-universe subscription auth homes for the CLI-subprocess writers from `llm_subscription` records. For Codex it SHALL resolve or create a `CODEX_HOME`, writing an `auth.json` from a vault-provided `auth_json_b64` bundle and a minimal `config.toml` when absent, defaulting to a `.credentials/codex` artifact directory when no durable path is configured. For Claude it SHALL resolve or create a `CLAUDE_CONFIG_DIR`, defaulting to a `.credentials/claude` artifact directory. Availability probes (`codex_subscription_auth_available`, `claude_subscription_auth_available`) SHALL report whether the vault can provide the corresponding auth route.

#### Scenario: Codex auth bundle materializes from the vault

- **WHEN** the vault holds an `llm_subscription` record for `codex` with an `auth_json_b64` payload and no durable home is pre-configured
- **THEN** materialization writes `auth.json` and a `config.toml` under the `.credentials/codex` directory and `codex_subscription_auth_available` returns true

#### Scenario: Claude config directory resolves from a configured path

- **WHEN** the vault holds an `llm_subscription` record for `claude` with a configured `claude_config_dir`
- **THEN** the resolver returns that directory, `claude_subscription_auth_available` returns true, and the claude-code provider overrides include `CLAUDE_CONFIG_DIR` set to that path

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
