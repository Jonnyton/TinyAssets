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

For every provider call carrying an explicit universe directory, the system SHALL construct the subprocess environment by removing all ambient provider API-key variables and host subscription selectors, including `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`, and `CODEX_HOME`, before applying only credentials resolved from that universe's vault. A universe-scoped cloud provider with no resolvable vault credential SHALL NOT be invoked. Calls with no universe context SHALL preserve host daemon and local-development authentication behavior. A bring-your-own `llm_api_key` deposit SHALL be accepted only for a service that maps to a supported provider env var, and an unsupported service SHALL be rejected at deposit time.

#### Scenario: Env overlay resolves the universe from the environment binding

- **WHEN** a subprocess environment binds `TINYASSETS_UNIVERSE` to a universe whose vault configures a Claude config directory, and the claude-code auth overlay is applied
- **THEN** the environment gains `CLAUDE_CONFIG_DIR` set to the configured directory

#### Scenario: Unsupported bring-your-own service is rejected at deposit

- **WHEN** a founder attempts to deposit an `llm_api_key` for a service that does not map to any supported provider env var
- **THEN** the deposit is rejected with an error naming the supported services and no unusable key is written to the vault

#### Scenario: Vaultless universe cannot inherit host subscription auth

- **GIVEN** the daemon environment contains valid Claude and Codex host subscription variables
- **AND** a universe has no credential vault
- **WHEN** that universe routes a writer call
- **THEN** neither cloud provider is invoked using the host subscription
- **AND** routing fails with provider exhaustion unless an explicitly eligible credentialless local provider serves it

#### Scenario: Founder BYO key replaces rather than composes with host auth

- **GIVEN** a universe vault contains a founder-provided API key for its selected writer
- **WHEN** the provider subprocess environment is built
- **THEN** it contains the founder key and an isolated provider home
- **AND** contains no host token, host config directory, or host provider home

#### Scenario: BYO key is exclusive with a vault subscription

- **GIVEN** a universe vault contains both an API key and subscription auth for the selected provider
- **WHEN** the provider subprocess environment is built
- **THEN** it receives the API key and an isolated provider home
- **AND** it does not receive the vault subscription token or home, so the payer class is deterministic

#### Scenario: Host development call remains compatible

- **GIVEN** a provider call with no universe context
- **WHEN** its subprocess environment is built
- **THEN** the existing host daemon/developer authentication behavior is preserved
