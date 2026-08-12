# Credential Vault

> As-built baseline (2026-07-19, change `spec-out-existing-platform`): describes landed behavior on `main` at baseline time, known limitations included. Future behavior changes arrive as OpenSpec change deltas against this capability.

## Purpose

Per-universe typed credential store (as-built: flat JSON guarded by best-effort file permissions) with daemon-side resolvers and a provider auth env overlay so a universe runs on its founder's assigned engine, not the host's.
## Requirements
### Requirement: Per-Universe Typed Credential Store

The system SHALL persist credentials in a per-universe vault file named `.credential-vault.json` inside the universe directory, written as a JSON object with `schema_version` 1 and a `credentials` list. Every credential record SHALL declare a `credential_type` that is one of `social`, `llm_subscription`, `llm_api_key`, or `vcs`; a record with any other type SHALL be rejected at write time. A Codex `llm_subscription` record that provides `auth_json_b64` SHALL contain a non-empty, strictly decodable base64 value whose decoded bytes are valid JSON; malformed values SHALL be rejected before the stored vault is replaced. The write helper (`tinyassets.credential_vault.write_credential_vault`) SHALL return a non-secret summary containing only the vault path, credential count, credential types, service names, collapsed-record count, and descriptors for any VCS purpose slots removed by a narrowing upsert, and SHALL never include secret material in that summary.

#### Scenario: Typed credentials round-trip and the summary carries no secret

- **WHEN** a caller writes a vault containing a `vcs`/github record with a token, a `social` record with a token, and an `llm_subscription` record
- **THEN** the returned summary reports `credential_count` 3 and the sorted credential types, and no secret token string appears anywhere in the summary
- **AND** loading the vault back returns the stored records including their secret values

#### Scenario: Unknown credential type is rejected

- **WHEN** a caller attempts to write a record whose `credential_type` is not one of the four allowed types
- **THEN** the write raises a `ValueError` identifying the unknown credential type and the vault is not populated with the invalid record

#### Scenario: Malformed Codex auth bundle is rejected before vault replacement

- **WHEN** a caller writes a Codex `llm_subscription` record whose `auth_json_b64` is not a non-empty strict-base64 encoding of valid JSON
- **THEN** the write raises `ValueError` before replacing the existing credential vault

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

The system SHALL materialize per-universe subscription auth homes for the CLI-subprocess writers from `llm_subscription` records. For Codex it SHALL resolve or create a `CODEX_HOME`, writing an `auth.json` from a non-empty, strictly decoded, valid-JSON vault-provided `auth_json_b64` bundle when absent or when its decoded bytes differ from the materialized file, and writing a minimal `config.toml` when absent, defaulting to a `.credentials/codex` artifact directory when no durable path is configured. A malformed bundle SHALL raise `ValueError` before any existing `auth.json` is replaced. For Claude it SHALL resolve or create a `CLAUDE_CONFIG_DIR`, defaulting to a `.credentials/claude` artifact directory. Availability probes (`codex_subscription_auth_available`, `claude_subscription_auth_available`) SHALL report whether the vault can provide the corresponding auth route.

#### Scenario: Codex auth bundle materializes from the vault

- **WHEN** the vault holds an `llm_subscription` record for `codex` with an `auth_json_b64` payload and no durable home is pre-configured
- **THEN** materialization writes `auth.json` and a `config.toml` under the `.credentials/codex` directory and `codex_subscription_auth_available` returns true

#### Scenario: Codex auth rotation updates a preserved materialization home

- **WHEN** a partial Codex subscription upsert changes `auth_json_b64` while preserving a configured home whose `auth.json` contains different bytes
- **THEN** the next vault-backed Codex materialization atomically replaces `auth.json` with the decoded incoming blob instead of retaining the stale file

#### Scenario: Malformed Codex auth bundle preserves materialized auth

- **WHEN** vault-backed Codex materialization encounters an `auth_json_b64` value that cannot be strictly decoded to non-empty valid JSON
- **THEN** it raises `ValueError` before replacing an existing `auth.json`

#### Scenario: Claude config directory resolves from a configured path

- **WHEN** the vault holds an `llm_subscription` record for `claude` with a configured `claude_config_dir`
- **THEN** the resolver returns that directory, `claude_subscription_auth_available` returns true, and the claude-code provider overrides include `CLAUDE_CONFIG_DIR` set to that path

### Requirement: Per-Universe Provider Auth Env Overlay Without Cross-Universe Leakage

For a host-local call with no explicit or environment-resolved universe, the system SHALL preserve the ordinary host subprocess environment and SHALL NOT invoke a universe vault helper. For a universe-scoped CLI call, `subprocess_env_for_provider` SHALL accept only the exact canonical provider names `claude-code` and `codex`, SHALL classify any non-empty explicit `universe_dir` or `TINYASSETS_UNIVERSE` binding as universe scope before credential work, and SHALL construct the child environment from an empty dictionary rather than a copied host environment. An explicit universe SHALL override an environment-bound universe.

For a host-local call the system SHALL continue to apply the subscription-only API-key policy: when API-key providers are not explicitly enabled, `subprocess_env_without_api_keys` MUST remove `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `GEMINI_API_KEY`, `GROQ_API_KEY`, and `XAI_API_KEY`.

The universe child MAY inherit only required execution basics: `PATH`; Windows process bootstrap variables `SYSTEMROOT`, `WINDIR`, `COMSPEC`, `PATHEXT`, and `SYSTEMDRIVE`; locale, timezone, and terminal variables `LANG`, `LANGUAGE`, `LC_ALL`, `LC_COLLATE`, `LC_CTYPE`, `LC_MESSAGES`, `LC_MONETARY`, `LC_NUMERIC`, `LC_TIME`, `LC_ADDRESS`, `LC_IDENTIFICATION`, `LC_MEASUREMENT`, `LC_NAME`, `LC_PAPER`, `LC_TELEPHONE`, `TZ`, `TERM`, `COLORTERM`, `NO_COLOR`, `PYTHONUTF8`, and `PYTHONIOENCODING`; and CA bundle variables `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS`, and `CODEX_CA_CERTIFICATE` only when their values identify absolute existing regular files. Environment names SHALL be matched case-insensitively on Windows and emitted with canonical names. Ambient proxy variables, `SSL_CERT_DIR`, `NODE_OPTIONS`, known provider/cloud credentials, cloud-route activation, any other `LC_*` name, and unknown future variables SHALL NOT enter the universe child. The child SHALL force `AWS_EC2_METADATA_DISABLED=true`.

The builder SHALL normalize a relative universe binding to an absolute canonical universe root. Before any public vault resolver or helper reads the selected source, it SHALL inspect `<universe>/.credential-vault.json` without following its final component. A missing source SHALL mean an empty vault. A present source SHALL be a physically contained, non-symlink regular file with exactly one hard link; a symlink, junction/reparse link, hardlinked or multi-link file, non-file, or physically outside source SHALL refuse provider launch before runtime or credential artifacts are created.

Before any provider-child directory creation or credential-helper side effect, the builder SHALL resolve every planned runtime target, the selected provider's existing/configured auth path returned by the public read-only vault resolver, and the selected provider's default `.credentials/<service>` materialization target. It SHALL refuse provider launch if any target physically resolves outside the canonical universe root, including through an existing symlink, junction, or reparse component.

After the complete preflight succeeds, the builder SHALL create private universe-owned home, profile, XDG, temporary, and runtime-only empty-auth roots beneath `<universe>/.runtime/provider-child/<provider>/`, with best-effort `0700` modes, and SHALL set `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME`, `XDG_RUNTIME_DIR`, `TMPDIR`, `TMP`, and `TEMP` to absolute paths under those roots. It SHALL derive `HOMEDRIVE` and `HOMEPATH` only for a normal Windows drive path. Before credential overlay, it SHALL pin default `CLAUDE_CONFIG_DIR` and `CODEX_HOME` beneath the provider child's distinct `auth-empty` runtime root and SHALL NOT create `.credentials/*` for a universe with no credential record.

The selected universe's credential helper MAY overlay only `CODEX_HOME` and `OPENAI_API_KEY` for `codex`, or `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_OAUTH_TOKEN`, and `ANTHROPIC_API_KEY` for `claude-code`. After the helper returns, the builder SHALL revalidate the complete overlay and SHALL refuse an auth-home path that physically resolves outside the canonical universe root. An unknown key, non-string value, malformed vault, outside-universe path, or unexpected helper failure SHALL refuse provider launch with a sanitized credential-resolution error that exposes neither secret values nor underlying exception text. A bring-your-own `llm_api_key` deposit SHALL be accepted only for a service that maps to a supported provider environment variable, and an unsupported service SHALL be rejected at deposit time.

This process-environment requirement does not claim network sandboxing or universal managed-identity isolation. It prevents ambient cloud-route activation and disables AWS EC2 metadata lookup for the child; other metadata-service and egress controls remain separate boundaries.

#### Scenario: Env overlay resolves the universe from the environment binding

- **WHEN** `TINYASSETS_UNIVERSE` binds a subprocess to a universe whose vault configures a Claude config directory
- **THEN** the child environment is first isolated to that universe and then gains the vault-selected `CLAUDE_CONFIG_DIR`

#### Scenario: Explicit universe directory wins over process binding

- **WHEN** the process environment points at universe A but a provider call explicitly supplies universe B
- **THEN** environment isolation and credential overlay use universe B and do not use universe A's vault

#### Scenario: Ambient direct and cloud authority cannot enter a universe child

- **GIVEN** the host carries direct Claude auth, Bedrock or Vertex activation, cloud keys, profiles, credential files, roles, or container credential endpoints
- **WHEN** a universe-scoped provider child is assembled
- **THEN** none of those ambient variables enters the child
- **AND** `AWS_EC2_METADATA_DISABLED` is exactly `true`

#### Scenario: Unknown future credential variables are default denied

- **GIVEN** the host carries a provider credential variable the current runtime does not recognize
- **WHEN** a universe-scoped provider child is assembled
- **THEN** that variable is absent because it was never explicitly admitted

#### Scenario: Safe runtime basics survive without ambient routing authority

- **GIVEN** the host carries required path, locale, terminal, timezone, a valid absolute CA bundle file, proxy variables, and arbitrary runtime injection variables
- **WHEN** a universe-scoped provider child is assembled
- **THEN** only the explicit safe runtime variables and valid CA bundle file enter the child
- **AND** proxy variables, `NODE_OPTIONS`, `SSL_CERT_DIR`, relative CA paths, directories, and missing CA files are absent
- **AND** an unrecognized name such as `LC_FUTURE_PROVIDER_MASTER_TOKEN` is absent

#### Scenario: Home profile and temporary discovery are universe owned

- **GIVEN** the host points home, profile, AppData, XDG, and temporary variables at host paths
- **WHEN** a universe-scoped provider child is assembled
- **THEN** every child discovery root points beneath that universe's private provider-child runtime root
- **AND** both default CLI auth homes point beneath that provider child's runtime-only `auth-empty` root
- **AND** no `.credentials/*` artifact is created and Claude subscription availability remains false

#### Scenario: Physical runtime path escape is rejected before writes

- **GIVEN** an existing symlink, junction, or reparse component sends a planned runtime root outside the canonical universe
- **WHEN** a universe-scoped provider child is assembled
- **THEN** provider launch is refused before any provider-child directory is created through that component

#### Scenario: Configured or default credential path escape is rejected before materialization

- **GIVEN** either the selected provider's configured auth path or default materialization target physically resolves outside the canonical universe
- **WHEN** a universe-scoped provider child is assembled
- **THEN** provider launch is refused before the credential helper creates or materializes anything at that outside path

#### Scenario: Linked vault source is rejected before credential work

- **GIVEN** `<universe>/.credential-vault.json` is a symlink, junction/reparse link, hardlink, or other multi-link source for credential data outside the universe's private vault file
- **WHEN** a universe-scoped provider child is assembled
- **THEN** provider launch is refused with a sanitized credential-resolution error before any public vault resolver reads that source
- **AND** no provider-child runtime or credential artifact is created

#### Scenario: Outside helper overlay path is rejected

- **WHEN** a provider helper returns a recognized auth-home key whose path physically resolves outside the canonical universe
- **THEN** provider launch is refused with a sanitized credential-resolution error

#### Scenario: Partial selected-universe overlay cannot retain alternate host authority

- **GIVEN** the host carries Claude and Codex authority
- **WHEN** the selected universe vault supplies only one recognized Claude or Codex overlay
- **THEN** that recognized universe-owned value survives
- **AND** no unrelated host authority enters through the empty-base environment

#### Scenario: Arbitrary helper output is rejected

- **WHEN** a universe credential helper returns any environment key not recognized for the selected provider
- **THEN** provider launch is refused with a sanitized credential-resolution error
- **AND** the arbitrary key and its value are not returned in a child environment or error

#### Scenario: Credential-resolution failure is fail-closed

- **WHEN** a universe-scoped vault import or resolver raises a malformed-data or unexpected error
- **THEN** provider launch is refused with an explicit sanitized credential-resolution error
- **AND** no environment containing inherited host authority is returned

#### Scenario: Host-local provider call keeps host authority

- **WHEN** a provider subprocess call has no explicit or environment-resolved universe
- **THEN** the environment builder returns the ordinary host environment under its normal API-key opt-in policy
- **AND** it does not invoke a universe vault helper

#### Scenario: Host-local API-key variables remain opt-in

- **GIVEN** the host carries `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `GEMINI_API_KEY`, `GROQ_API_KEY`, and `XAI_API_KEY`
- **WHEN** a host-local subprocess environment is built without explicit API-key-provider opt-in
- **THEN** all six variables are absent while host subscription authority remains available

#### Scenario: Noncanonical universe provider is rejected before credential work

- **WHEN** a universe-scoped caller requests `future-cli`, `gemini`, `CODEX`, or any provider name other than exact `claude-code` or `codex`
- **THEN** provider launch is refused before a vault helper is invoked

#### Scenario: Missing credential uses empty runtime auth

- **WHEN** a canonical universe provider has no credential record
- **THEN** environment construction succeeds with a universe-owned empty runtime auth home
- **AND** authentication failure occurs later at provider-call time without any maintainer authority

#### Scenario: Unsupported bring-your-own service is rejected at deposit

- **WHEN** a founder attempts to deposit an `llm_api_key` for a service that does not map to a supported provider environment variable
- **THEN** the deposit is rejected with an error naming the supported services and no unusable key is written to the vault

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

The system SHALL treat a validated one-record payload written to an existing vault as a logical-slot upsert and SHALL treat an empty or two-or-more-record payload as an exact ordered replacement. Every successful write SHALL pass through the fixed sibling path `.credential-vault.json.tmp` and replace `.credential-vault.json` directly from that path. Its non-secret summary SHALL report the number of redundant matching records collapsed and descriptors for any VCS purpose slots removed by a narrowing upsert. This boundary SHALL NOT claim cross-process locking, a unique temporary filename, compare-and-swap, or version conflict detection.

#### Scenario: Single record upserts into an existing vault

- **WHEN** a valid one-record payload is written while `.credential-vault.json` exists and is valid
- **THEN** the system reads the stored records, replaces all records matching the incoming logical slot with one result at the first matching position, preserves unmatched records in order, and appends the incoming record when no slot matches

#### Scenario: Logical slots follow resolver selectors

- **WHEN** the system matches a record for a one-record upsert
- **THEN** `llm_api_key` uses credential type plus the environment-variable slot selected by normalized effective-service aliases, `llm_subscription` and `social` use credential type plus normalized effective service, and `vcs` uses credential type plus normalized effective service plus exact destination plus an overlapping normalized purpose set

#### Scenario: VCS purpose selectors overlap

- **WHEN** an existing VCS record and an incoming VCS record have the same service and destination and their selectors share at least one purpose, including a stored `purposes` list that contains the incoming singular `purpose`
- **THEN** the records match one logical slot, the incoming whole record replaces all overlapping matches, and a first stored token cannot shadow the deposited rotation

#### Scenario: VCS narrowing reports removed purpose slots

- **WHEN** a one-record VCS upsert replaces an overlapping record whose normalized purpose set contains selectors absent from the incoming record
- **THEN** the write summary identifies the removed purposes with credential type, normalized service, exact destination, and sorted purpose names without including any secret value

#### Scenario: Subscription partial writes preserve sibling fields

- **WHEN** one `llm_subscription` record is upserted into one or more matching subscription records
- **THEN** stored fields are combined with first-record precedence, stored members of any Claude or Codex resolver-equivalent alias family named by the incoming record are removed, incoming fields are applied, unrelated sibling fields survive, and all matching records collapse to the combined record

#### Scenario: Single upsert cleans duplicate resolver slots

- **WHEN** exact bulk replacement has stored multiple matching BYO-key or Claude-subscription records whose first record shadows later records
- **THEN** their existing first-record resolution semantics remain in effect until a one-record upsert for that logical slot collapses every match to one record and reports the number of redundant records removed

#### Scenario: Bulk write replaces the vault exactly

- **WHEN** a valid payload contains two or more credential records
- **THEN** the stored list is replaced by that payload in order, including any duplicate logical slots, without merging it with prior records

#### Scenario: Empty write clears the vault

- **WHEN** a valid payload contains zero credential records
- **THEN** the stored list is replaced with an empty list

#### Scenario: Malformed existing vault blocks single-record upsert

- **WHEN** a one-record payload targets an existing vault whose JSON or credential records are malformed
- **THEN** the write raises `ValueError` before replacing the malformed vault

#### Scenario: Successful write replaces the vault through the fixed sibling

- **WHEN** a valid credential payload is written without an overlapping writer or filesystem error
- **THEN** `.credential-vault.json.tmp` is written and directly replaces `.credential-vault.json`

#### Scenario: Concurrent writers have no serialization guarantee

- **WHEN** two processes write the same universe vault concurrently, including overlapping one-record read-modify-write upserts
- **THEN** the boundary provides no lock, unique temporary path, compare-and-swap check, lost-update prevention, or deterministic winner guarantee

### Requirement: Assigned serving credential is the sole universe execution authority
For a universe-scoped workflow execution, the vault SHALL expose credential material only through the exact current serving assignment selected for that universe. The daemon SHALL resolve the serving agent row, assignment, provider-work binding, custody reference, and binding budgets inside one transaction while holding shared provider-assignment admission for the complete run; it SHALL snapshot that assigned credential for the run and clean the snapshot afterward, including when authority construction or the provider body fails. A concurrent disable, revision change, rebind, or custody rotation SHALL wait for the active run or cause the next resolution to hold. A missing, malformed, stale, revoked, exhausted, or unavailable assignment SHALL produce the typed hold `no_requester_owned_executor` without attaching the underlying credential exception chain; the vault/provider boundary SHALL NOT copy ambient host credential variables, search for another credential record, or fall back to another provider.

#### Scenario: Exact assigned credential is snapshotted
- **WHEN** a workflow's current serving assignment and vault custody reference agree
- **THEN** the daemon receives a launch-scoped snapshot for only that assigned credential
- **AND** the snapshot is removed after the run

#### Scenario: Assignment mutation cannot race an active snapshot
- **WHEN** a provider assignment writer attempts to disable, revise, rebind, or rotate the credential while a run holds assigned credential authority
- **THEN** the mutation waits for the run's shared admission fence
- **AND** no stale serving identity can be launched after the mutation commits

#### Scenario: Missing assigned credential cannot inherit host auth
- **WHEN** the host process has valid provider auth but the task universe has no usable assigned credential
- **THEN** execution holds with `no_requester_owned_executor`
- **AND** no host auth home, token, API key, endpoint, or provider route enters the child

#### Scenario: Another vault credential is not an implicit fallback
- **WHEN** the assigned credential is unavailable and the same vault contains another provider credential
- **THEN** the other credential remains unused unless the user explicitly rebinds the workflow
