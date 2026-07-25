## MODIFIED Requirements

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
