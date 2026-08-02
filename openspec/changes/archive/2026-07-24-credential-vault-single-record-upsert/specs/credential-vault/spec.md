## MODIFIED Requirements

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
