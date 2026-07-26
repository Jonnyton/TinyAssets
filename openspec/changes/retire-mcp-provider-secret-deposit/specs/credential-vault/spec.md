## RENAMED Requirements

- FROM: `Credential alias selection and first-record secret extraction are exact`
- TO: `Credential alias selection and first-record credential resolution are exact`

## MODIFIED Requirements

### Requirement: As-Built Storage Protection Is Filesystem Permissions Only

The vault file and any materialized credential artifacts SHALL remain
unencrypted content on disk. For example, a Codex `auth.json` or a Claude
config directory SHALL be persisted as unencrypted
content on disk, and the only at-rest protection SHALL be a best-effort POSIX
file mode — `0o600` for the vault file and secret files, `0o700` for the
`.credentials` artifact directory. As-built limitation: there is no encryption
at rest, no cipher, and no key management; base64 fields such as `token_b64` /
`secret_b64` are an encoding convention, not encryption, and best-effort
`chmod` is inert on operating systems that do not honor POSIX modes. A layered
cipher/store design exists only as an approved future design and is not present
in the code on `main`.

This truthful limitation continues to govern retained `llm_subscription`,
`vcs`, and `social` records and their materialized artifacts. New
`llm_api_key` writes are prohibited by this change; a legacy `llm_api_key`
remains recoverable cleartext until the locked replacement-first retirement
saga deletes it, and the system SHALL NOT mislabel that interim state as
encrypted or native-store protected.

#### Scenario: Retained secret is stored in cleartext under a restricted file mode

- **WHEN** a permitted `llm_subscription`, `vcs`, or `social` credential with a plaintext or base64-encoded secret is written to the vault
- **THEN** the on-disk `.credential-vault.json` contains that secret as recoverable cleartext (directly or base64-decodable) with no ciphertext layer
- **AND** the write sets the file mode to `0o600` on operating systems that honor POSIX permissions, while the content itself remains unencrypted regardless of the mode

#### Scenario: Legacy llm_api_key remains truthfully classified until deletion

- **WHEN** a legacy `llm_api_key` record has not yet reached digest-matched source deletion
- **THEN** it remains classified as recoverable cleartext protected only by the existing filesystem boundary
- **AND** no status, summary, or migration state claims it was encrypted or silently moved to native storage

### Requirement: Per-Universe Typed Credential Store

The system SHALL persist credentials in a per-universe vault file named
`.credential-vault.json` inside the universe directory, written as a JSON
object with `schema_version` 1 and a `credentials` list. Every new credential
record SHALL declare a `credential_type` that is one of `social`,
`llm_subscription`, or `vcs`; a new `llm_api_key` record SHALL be rejected
before the stored vault is replaced. A Codex `llm_subscription` record that
provides `auth_json_b64` SHALL contain a non-empty, strictly decodable base64
value whose decoded bytes are valid JSON; malformed values SHALL be rejected
before the stored vault is replaced. Existing `llm_subscription`, `vcs`, and
`social` field validation and resolution semantics remain unchanged. A legacy
`llm_api_key` record SHALL be readable only by the opaque dual-loader and
metadata-only retirement path; ordinary resolution SHALL return a sanitized
legacy-hold failure without exposing or decoding the record.

The write helper (`tinyassets.credential_vault.write_credential_vault`) SHALL
return a non-secret summary containing only the vault path, credential count,
credential types, service names, collapsed-record count, and descriptors for
any VCS purpose slots removed by a narrowing upsert, and SHALL never include
secret material in that summary.

#### Scenario: Typed credentials round-trip and the summary carries no secret

- **WHEN** a caller writes a vault containing permitted `vcs`, `social`, and `llm_subscription` records
- **THEN** the returned summary reports the credential count and sorted credential types, and no secret token string appears anywhere in the summary
- **AND** loading the vault back returns the permitted stored records

#### Scenario: Unknown or llm_api_key credential type is rejected

- **WHEN** a caller attempts to write an unknown credential type or a new `llm_api_key`
- **THEN** the write raises a sanitized `ValueError` before replacing the vault
- **AND** the existing vault remains byte-identical

#### Scenario: Malformed Codex auth bundle is rejected before vault replacement

- **WHEN** a caller writes a Codex `llm_subscription` record whose `auth_json_b64` is not a non-empty strict-base64 encoding of valid JSON
- **THEN** the write raises `ValueError` before replacing the existing credential vault

#### Scenario: Legacy llm_api_key record is retirement-only

- **WHEN** an existing vault contains a legacy `llm_api_key`
- **THEN** ordinary credential resolution fails with a sanitized held result
- **AND** only the locked metadata inventory/deletion path may inspect its field names, byte length, and record digest without decoding a value

### Requirement: Per-Universe Provider Auth Env Overlay Without Cross-Universe Leakage

The system SHALL preserve the complete shipped host-local and
universe-scoped environment-isolation contract. For a host-local call with no
explicit or environment-resolved universe, the system SHALL preserve the
ordinary host subprocess environment and SHALL NOT invoke a universe vault
helper. For a universe-scoped CLI call,
`subprocess_env_for_provider` SHALL accept only the exact canonical provider
names `claude-code` and `codex`, SHALL classify any non-empty explicit
`universe_dir` or `TINYASSETS_UNIVERSE` binding as universe scope before
credential work, and SHALL construct the child environment from an empty
dictionary rather than a copied host environment. An explicit universe SHALL
override an environment-bound universe.

For a host-local call the system SHALL continue to apply the subscription-only
API-key policy: when API-key providers are not explicitly enabled,
`subprocess_env_without_api_keys` MUST remove `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `GEMINI_API_KEY`,
`GROQ_API_KEY`, and `XAI_API_KEY`.

The universe child MAY inherit only required execution basics: `PATH`; Windows
process bootstrap variables `SYSTEMROOT`, `WINDIR`, `COMSPEC`, `PATHEXT`, and
`SYSTEMDRIVE`; locale, timezone, and terminal variables `LANG`, `LANGUAGE`,
`LC_ALL`, `LC_COLLATE`, `LC_CTYPE`, `LC_MESSAGES`, `LC_MONETARY`,
`LC_NUMERIC`, `LC_TIME`, `LC_ADDRESS`, `LC_IDENTIFICATION`,
`LC_MEASUREMENT`, `LC_NAME`, `LC_PAPER`, `LC_TELEPHONE`, `TZ`, `TERM`,
`COLORTERM`, `NO_COLOR`, `PYTHONUTF8`, and `PYTHONIOENCODING`; and CA bundle
variables `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`,
`NODE_EXTRA_CA_CERTS`, and `CODEX_CA_CERTIFICATE` only when their values
identify absolute existing regular files. Environment names SHALL be matched
case-insensitively on Windows and emitted with canonical names. Ambient proxy
variables, `SSL_CERT_DIR`, `NODE_OPTIONS`, known provider/cloud credentials,
cloud-route activation, any other `LC_*` name, and unknown future variables
SHALL NOT enter the universe child. The child SHALL force
`AWS_EC2_METADATA_DISABLED=true`.

The builder SHALL normalize a relative universe binding to an absolute
canonical universe root. Before any public vault resolver or helper reads the
selected source, it SHALL inspect `<universe>/.credential-vault.json` without
following its final component. A missing source SHALL mean an empty vault. A
present source SHALL be a physically contained, non-symlink regular file with
exactly one hard link; a symlink, junction/reparse link, hardlinked or
multi-link file, non-file, or physically outside source SHALL refuse provider
launch before runtime or credential artifacts are created.

Before any provider-child directory creation or credential-helper side effect,
the builder SHALL resolve every planned runtime target, the selected provider's
existing/configured auth path returned by the public read-only vault resolver,
and the selected provider's default `.credentials/<service>` materialization
target. It SHALL refuse provider launch if any target physically resolves
outside the canonical universe root, including through an existing symlink,
junction, or reparse component.

After the complete preflight succeeds, the builder SHALL create private
universe-owned home, profile, XDG, temporary, and runtime-only empty-auth roots
beneath `<universe>/.runtime/provider-child/<provider>/`, with best-effort
`0700` modes, and SHALL set `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`,
`XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME`,
`XDG_RUNTIME_DIR`, `TMPDIR`, `TMP`, and `TEMP` to absolute paths under those
roots. It SHALL derive `HOMEDRIVE` and `HOMEPATH` only for a normal Windows
drive path. Before credential overlay, it SHALL pin default
`CLAUDE_CONFIG_DIR` and `CODEX_HOME` beneath the provider child's distinct
runtime-only `auth-empty` root and SHALL NOT create `.credentials/*` for a
universe with no credential record.

The selected universe's credential helper MAY overlay only `CODEX_HOME` and
`OPENAI_API_KEY` for `codex`, or `CLAUDE_CONFIG_DIR`,
`CLAUDE_CODE_OAUTH_TOKEN`, and `ANTHROPIC_API_KEY` for `claude-code`. Existing
`llm_subscription` resolution and materialization remain unchanged by this
change. A legacy `llm_api_key` SHALL NOT be selected or decoded by that helper.
For a requester-local API-key binding, the provider-authority-owned typed
local-launch adapter SHALL validate the persisted credential-owner principal,
universe, provider, host, scope, assignment generation, expiry, and tombstone
state under shared `ProviderAssignmentAdmission` and cross the
`ProviderInvocation -> ProviderLaunchHandle` barrier, then resolve the native
secret exactly once into the permitted ephemeral API-key variable. The current
D0 path is fake-only/production-denied and is not ordinary requester-provider
authority. Accepted-market remote execution remains blocked on its
owner-accepted production B2 authority and SHALL NOT receive this local
secret. The control-plane vault helper SHALL receive no raw API key.

After the helper returns, the builder SHALL revalidate the complete overlay and
SHALL refuse an auth-home path that physically resolves outside the canonical
universe root. An unknown key, non-string value, malformed vault,
missing/empty/stale/wrong binding, outside-universe path, or unexpected helper
failure SHALL refuse provider launch with a sanitized credential-resolution or
setup-required error that exposes neither secret values nor underlying
exception text. A new bring-your-own `llm_api_key` deposit SHALL be rejected at
ingress before vault or assignment mutation, regardless of service.

This process-environment requirement does not claim network sandboxing or
universal managed-identity isolation. It prevents ambient cloud-route
activation and disables AWS EC2 metadata lookup for the child; other
metadata-service and egress controls remain separate boundaries.

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

- **GIVEN** the host carries a provider credential variable the runtime does not recognize
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
- **THEN** launch is refused before any provider-child directory is created through that component

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

- **WHEN** a universe-scoped vault import, resolver, binding validation, or native dereference raises a malformed-data or unexpected error
- **THEN** provider launch is refused with an explicit sanitized credential-resolution or setup-required error
- **AND** no environment containing inherited host authority is returned

#### Scenario: Host-local provider call keeps host authority

- **WHEN** a provider subprocess call has no explicit or environment-resolved universe
- **THEN** the environment builder returns the ordinary host environment under its normal API-key opt-in policy
- **AND** it does not invoke a universe credential helper

#### Scenario: Host-local API-key variables remain opt-in

- **GIVEN** the host carries `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `GEMINI_API_KEY`, `GROQ_API_KEY`, and `XAI_API_KEY`
- **WHEN** a host-local subprocess environment is built without explicit API-key-provider opt-in
- **THEN** all six variables are absent while host subscription authority remains available

#### Scenario: Noncanonical universe provider is rejected before credential work

- **WHEN** a universe-scoped caller requests `future-cli`, `gemini`, `CODEX`, or any provider name other than exact `claude-code` or `codex`
- **THEN** provider launch is refused before a vault, binding, or native-secret helper is invoked

#### Scenario: Missing credential uses empty runtime auth with the provider-authority launch exception

- **WHEN** a canonical universe provider has neither a credential record nor a current requester-local API-key binding
- **THEN** environment construction succeeds with a universe-owned empty runtime auth home
- **AND** the accepted provider-authority launch adapter returns setup-required hold before provider invocation, with no maintainer/founder fallback

#### Scenario: Bring-your-own llm_api_key deposit is rejected

- **WHEN** any caller attempts to deposit a raw or recoverable `llm_api_key` into the universe vault
- **THEN** the deposit is rejected before vault, config, assignment, or ledger mutation
- **AND** requester-local native enrollment guidance contains no secret field while separately owned subscription behavior remains unchanged

### Requirement: Credential alias selection and first-record credential resolution are exact

The system SHALL derive a credential record's effective service by taking
non-empty `service` before non-empty `provider`, then trimming and lowercasing
its string form. For retirement-only `llm_api_key` records, `anthropic`,
`claude`, and `claude-code` map to `ANTHROPIC_API_KEY`; `openai` and `codex`
map to `OPENAI_API_KEY`; `gemini` and `google` map to `GEMINI_API_KEY`; `groq`
maps to `GROQ_API_KEY`; and `xai` and `grok` map to `XAI_API_KEY`. New
`llm_api_key` records SHALL NOT be written, and the public resolver SHALL NOT
select, decode, or return a legacy `llm_api_key`.

Each shipped-alias legacy slot SHALL be identified by universe id, exact
environment-variable slot from that ten-alias table, zero-based stored
occurrence among `llm_api_key` records mapped to that slot, and inventoried
record digest. Two aliases that map to one environment variable remain
separate occurrences when both records exist; retirement SHALL NOT conflate,
normalize, reorder, or collapse them. A missing or unsupported effective
service has no safe provider slot and SHALL enter terminal `held_ambiguous`
without decode, deletion, or fallback.

Claude OAuth resolution SHALL likewise inspect only the first
`llm_subscription` record whose normalized effective service is `claude`,
returning its first non-empty string `oauth_token` or
`claude_code_oauth_token`, otherwise its selected base64 field, and returning
empty without scanning later matching records. Base64 resolution SHALL use the
runtime's permissive standard decoder followed by UTF-8 decoding and whitespace
trimming: ignored non-alphabet characters are not independently rejected,
while an actual base64 or UTF-8 decoding exception SHALL be surfaced as
`ValueError`.

For requester-local API-key use,
`constrain-set-engine-provider-authority` SHALL select one exact opaque binding
in its assignment transaction under `ProviderAssignmentAdmission`, and its
typed local-launch adapter SHALL fail held on an empty, stale, wrong-provider,
wrong-principal, wrong-host, wrong-generation, expired, or tombstoned binding
without scanning vault records, host homes, environment variables, or keyring
entries.

#### Scenario: Normalized BYO aliases identify only a retirement slot

- **WHEN** a legacy `llm_api_key` record uses one of `anthropic`, `claude`, `claude-code`, `openai`, `codex`, `gemini`, `google`, `groq`, `xai`, or `grok` with any letter case or surrounding whitespace
- **THEN** metadata inventory assigns only the environment-variable slot named by the exact ten-alias table plus its stored occurrence and record digest
- **AND** ordinary provider resolution never returns its secret

#### Scenario: Provider supplies the effective service when service is absent

- **WHEN** a legacy `llm_api_key` record omits or empties `service` and names a supported alias in `provider`
- **THEN** retirement inventory uses that `provider` value as the effective service without decoding the record

#### Scenario: Same-family aliases retain distinct stored occurrences

- **WHEN** multiple legacy `llm_api_key` records use aliases mapping to the same environment variable
- **THEN** each record receives a distinct stored-occurrence slot and digest
- **AND** retirement never collapses one alias record into another

#### Scenario: Current exact binding selects only local dereference

- **WHEN** the provider assignment binding is current and exactly matches persisted credential-owner principal, universe, provider, host, scope, and generation and crosses shared `ProviderAssignmentAdmission`
- **THEN** the local-launch adapter resolves only that opaque binding at native launch
- **AND** no `llm_api_key` secret is decoded or returned by the universe vault

#### Scenario: First Claude subscription yields a direct or base64 secret

- **WHEN** the first effective-service `claude` subscription contains a direct OAuth field or a decodable `token_b64` or `secret_b64`
- **THEN** Claude OAuth resolution returns that record's first available secret in the specified order

#### Scenario: Empty first Claude subscription shadows later records

- **WHEN** the first effective-service `claude` subscription has no supported secret and a later matching subscription does
- **THEN** Claude OAuth resolution returns empty without inspecting the later record

#### Scenario: Selected base64 decoding exceptions fail loudly

- **WHEN** the first matching Claude subscription record has no supported direct secret and standard base64 or UTF-8 decoding of its selected `token_b64` or `secret_b64` raises
- **THEN** resolution raises `ValueError` without returning empty or scanning a later record

#### Scenario: Legacy base64 fields are never decoded

- **WHEN** a legacy `llm_api_key` record contains `token_b64` or `secret_b64`
- **THEN** inventory records only the field name, byte length, and record digest
- **AND** neither valid nor malformed `llm_api_key` content is decoded

#### Scenario: Unknown effective service does not resolve

- **WHEN** a legacy `llm_api_key` record's normalized effective service is absent or not in the exact ten-alias table
- **THEN** it does not satisfy any provider retirement slot or environment lookup
- **AND** it enters terminal `held_ambiguous` without decode, deletion, or fallback

### Requirement: Credential vault replacement is process-local and unversioned

The system SHALL treat a validated one-record payload written to an existing
vault as a logical-slot upsert and SHALL treat an empty or two-or-more-record
payload as an exact ordered replacement. Every successful write SHALL pass
through the fixed sibling path `.credential-vault.json.tmp` and replace
`.credential-vault.json` directly from that path. Its non-secret summary SHALL
report the number of redundant matching records collapsed and descriptors for
any VCS purpose slots removed by a narrowing upsert. This boundary SHALL NOT
claim cross-process locking, a unique temporary filename, compare-and-swap, or
version conflict detection.

A vault containing legacy `llm_api_key` records SHALL use an opaque
byte-preserving dual loader under the exclusive writer from
`ProviderAssignmentAdmission`, owned by
`constrain-set-engine-provider-authority`. The legacy side SHALL
inventory each raw JSON object byte slice, stored order, exact ten-alias
retirement slot, and digest without normalizing or decoding any secret field.
The ordinary side SHALL parse and validate only retained `llm_subscription`,
`vcs`, and `social` records. Every one-record, bulk, or empty ordinary write
SHALL transform only that retained-record subsequence and SHALL splice every
legacy object byte slice back byte-for-byte in its prior relative order before
the fixed-sibling replacement. Bulk replacement and empty clear are exact only
for the retained-record subsequence until the retirement saga compare-deletes
the legacy records.

The dual loader SHALL reject before the fixed-sibling write if it cannot
unambiguously preserve every legacy byte slice, relative order, slot, or
digest. It SHALL NOT pass a legacy record through the ordinary normalizer,
collapse aliases, decode fields, silently drop a record, or rewrite a legacy
object. Retirement transitions and exact compare-delete SHALL use the same
exclusive `ProviderAssignmentAdmission` writer, expected record digest, and
assignment generation. Launch exclusion SHALL compose with its shared-reader
`ProviderInvocation -> ProviderLaunchHandle` barrier for requester-owned local
execution; accepted-market execution remains separately blocked on an
owner-accepted production B2 authority contract. The provider-authority
contract is merged in PR #1784; this change does not claim the B2 dependency
is accepted.

#### Scenario: Single record upserts into an existing vault

- **WHEN** a valid one-record payload is written while `.credential-vault.json` exists and is valid
- **THEN** the system reads the stored records, replaces all records matching the incoming logical slot with one result at the first matching position, preserves unmatched records in order, and appends the incoming record when no slot matches
- **AND** any opaque legacy `llm_api_key` byte slices remain unchanged and outside the ordinary matching set

#### Scenario: Logical slots follow resolver selectors

- **WHEN** the system matches a record for a one-record upsert
- **THEN** `llm_api_key` uses credential type plus the environment-variable slot selected by normalized effective-service aliases, `llm_subscription` and `social` use credential type plus normalized effective service, and `vcs` uses credential type plus normalized effective service plus exact destination plus an overlapping normalized purpose set
- **AND** the `llm_api_key` selector is used only for opaque retirement-slot identity because no ordinary `llm_api_key` write is accepted

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
- **AND** after this change the BYO-key half is historical-only: ordinary writes cannot target it and the dual loader preserves every legacy occurrence for retirement

#### Scenario: Bulk write replaces the vault exactly

- **WHEN** a valid payload contains two or more credential records
- **THEN** the stored list is replaced by that payload in order, including any duplicate logical slots, without merging it with prior records
- **AND** if opaque legacy `llm_api_key` slices exist, this exact replacement applies only to the retained-record subsequence and preserves every legacy slice byte-for-byte in prior relative order

#### Scenario: Empty write clears the vault

- **WHEN** a valid payload contains zero credential records
- **THEN** the stored list is replaced with an empty list
- **AND** if opaque legacy `llm_api_key` slices exist, only the retained-record subsequence becomes empty and every legacy slice remains byte-for-byte in prior relative order

#### Scenario: Malformed existing vault blocks single-record upsert

- **WHEN** a one-record payload targets an existing vault whose JSON or credential records are malformed
- **THEN** the write raises `ValueError` before replacing the malformed vault

#### Scenario: Successful write replaces the vault through the fixed sibling

- **WHEN** a valid credential payload is written without an overlapping writer or filesystem error
- **THEN** `.credential-vault.json.tmp` is written and directly replaces `.credential-vault.json`

#### Scenario: Concurrent writers have no serialization guarantee

- **WHEN** two processes write the same universe vault concurrently, including overlapping one-record read-modify-write upserts
- **THEN** the boundary provides no lock, unique temporary path, compare-and-swap check, lost-update prevention, or deterministic winner guarantee
- **AND** a vault containing legacy `llm_api_key` is the narrow exception because its dual-loader writes hold exclusive `ProviderAssignmentAdmission`

#### Scenario: Legacy llm_api_key survives every ordinary write shape

- **WHEN** the existing vault contains any legacy `llm_api_key` and a caller attempts a one-record upsert, two-or-more exact replacement, or empty clear
- **THEN** the retained `llm_subscription`, `vcs`, and `social` operation remains usable under exclusive `ProviderAssignmentAdmission`
- **AND** every legacy `llm_api_key` object byte slice and relative order survives exactly

#### Scenario: Ambiguous opaque preservation fails before replacement

- **WHEN** the dual loader cannot unambiguously identify or splice every legacy byte slice, slot, order, and digest
- **THEN** the write raises `ValueError` before the fixed sibling is written
- **AND** no retained or legacy record is normalized, decoded, dropped, reordered, or replaced

#### Scenario: Malformed or unclassifiable existing state blocks every write and reset

- **WHEN** an existing vault is malformed or contains a record the dual loader cannot classify as retained or an exact legacy `llm_api_key` slice
- **THEN** one-record, bulk, empty, recovery, and `test-identity-and-reset` global-reset paths raise `ValueError` before the fixed sibling or any artifact/assignment/native-store mutation
- **AND** no path clears or rewrites the vault as recovery

#### Scenario: Global reset cannot bypass legacy retirement

- **WHEN** `openspec/changes/test-identity-and-reset/` global reset encounters one or more exact legacy `llm_api_key` slices
- **THEN** the confirmed global reset performs zero mutation and remains blocked while any legacy slice exists
- **AND** reset may resume only after every legacy key's owner-notified replacement/revocation/cutover/artifact/source saga reaches safe terminal deletion

#### Scenario: Retirement transition is locked and compare-and-delete

- **WHEN** migration inventories or advances a legacy `llm_api_key` record
- **THEN** it holds exclusive `ProviderAssignmentAdmission`, owned by `constrain-set-engine-provider-authority`, and verifies the expected digest and generation
- **AND** a mismatch performs no deletion and re-inventories current state
