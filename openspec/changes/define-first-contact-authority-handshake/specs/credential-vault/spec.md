## ADDED Requirements

### Requirement: Requester credentials enter through authenticated out-of-band enrollment
The credential custodian SHALL accept provider secrets only through a same-origin HTTPS enrollment flow that re-authenticates the exact requester issuer/subject, re-authorizes current tenant/universe/delegation access, binds the credential owner, uses exact redirects and CSRF state, and uses authorization code plus PKCE for vendor OAuth. Public MCP/chat payloads, `set_engine`, graph/page text, logs, traces, market records, and setup challenges SHALL NOT accept or carry raw provider credentials or upstream bearer tokens. A valid inbound MCP access token authenticates TinyAssets only and SHALL NOT be stored, exchanged, or forwarded as a provider credential.

#### Scenario: public raw-key deposit is rejected
- **WHEN** a caller supplies a provider API key or subscription token through MCP/chat JSON or `set_engine`
- **THEN** the request is rejected without persisting or echoing the secret and returns only a non-secret out-of-band setup descriptor

#### Scenario: revoked tenant access blocks enrollment completion
- **WHEN** a requester loses current tenant, universe, or delegation access after a setup challenge is issued
- **THEN** enrollment completion is rejected without attaching a credential to that tenant or universe

### Requirement: Credential custody is encrypted and secret vending is ephemeral
The credential custodian SHALL encrypt every stored secret with managed key custody and SHALL treat plaintext and base64 as ineligible at-rest representations. Each strict-schema credential reference SHALL bind its type (`social`, `llm_subscription`, `llm_api_key`, or `vcs`), service, owner principal, version/revocation epoch, and allowed destination, purpose, route, and phase constraints; unknown types, malformed records, custody failures, and constraint mismatches SHALL fail closed. A trusted broker SHALL vend a secret only as a purpose-, route-, phase-, job-, owner-, and expiry-scoped ephemeral lease to the authorized adapter, and SHALL destroy the lease material after use. Public summaries and resolvers SHALL expose only opaque credential references and redacted metadata; raw secret values SHALL NOT enter request authority, graph state, provider results, receipts, logs, or traces.

#### Scenario: plaintext or base64 store is ineligible
- **WHEN** a storage backend can persist a credential only as recoverable plaintext or base64 with filesystem permissions
- **THEN** enrollment fails closed and no executable credential reference is created

#### Scenario: adapter receives one scoped ephemeral lease
- **WHEN** an authorized provider phase needs a stored requester credential
- **THEN** the broker vends only the secret lease scoped to that owner, purpose, route, phase, job, and expiry
- **AND** lease material is destroyed after the phase and is absent from the result and receipt

#### Scenario: malformed or mismatched credential reference fails closed
- **WHEN** a credential record has an unknown type, malformed encrypted payload, wrong owner, revoked version, or destination/purpose/route/phase mismatch
- **THEN** no lease is vended and the error cannot fall through to an ambient credential

### Requirement: Provider adapters materialize credentials ephemerally from a default-deny base
For requester-authorized execution, provider adapters SHALL start from a minimal allowlisted environment with empty home, profile, config, cloud, and subscription-auth roots. They SHALL overlay only the scoped ephemeral lease approved for the exact invocation and SHALL remove/destroy any temporary file, directory, environment value, or broker handle after use. They SHALL NOT inherit the host environment, reuse a durable Codex/Claude auth home, materialize base64 auth bundles into persistent universe files, or accept a direct BYOC deposit through a public request. Import, custody, resolution, overlay, and cleanup errors SHALL fail closed.

#### Scenario: CLI writer uses an ephemeral isolated auth home
- **WHEN** an authorized CLI provider requires file-based authentication for one phase
- **THEN** the broker materializes only a temporary invocation-scoped auth home from the approved lease under an empty isolated root
- **AND** the root is destroyed after use and no host or universe-persistent auth home is read

#### Scenario: overlay error cannot preserve ambient host credentials
- **WHEN** credential import, resolution, overlay, or cleanup raises any error for an explicit request authority
- **THEN** provider dispatch is rejected and no inherited host credential, auth home, profile, socket, or hardware route remains eligible

## REMOVED Requirements

### Requirement: As-Built Storage Protection Is Filesystem Permissions Only

**Reason:** Recoverable plaintext/base64 guarded only by best-effort file permissions cannot satisfy the request-authority secret boundary, multi-tenant isolation, or regulated custody requirements.

**Migration:** Before public requester-owned execution is enabled, migrate credentials into encrypted managed custody, verify every migrated owner/reference, revoke and remove recoverable legacy files and materialized auth artifacts, and keep provider-backed execution held for any credential that cannot be migrated safely. Rollback disables requester-owned execution; it never restores plaintext/base64 custody.

### Requirement: Per-Universe Typed Credential Store

**Reason:** A secret-bearing `.credential-vault.json` round trip exposes recoverable values and conflates tenant metadata with secret custody. The replacement keeps typed redacted references in tenant state and encrypted secret values in managed custody.

**Migration:** Convert every supported record into an owner-bound encrypted custody entry plus opaque typed reference, verify count/type/service/destination/purpose parity, revoke records that cannot be attributed safely, then remove the secret-bearing JSON file. Rollback holds affected execution rather than restoring recoverable files.

### Requirement: Fail-Loud Load Semantics

**Reason:** The legacy loader contract is tied to the removed secret-bearing JSON file. The replacement fails closed at strict reference, encrypted payload, ownership, revocation, constraint, vending, and adapter boundaries.

**Migration:** Migration tooling SHALL still reject malformed legacy files and SHALL NOT silently skip any record; after verified conversion, runtime uses the new custody/reference failure semantics and no longer loads the legacy file.

### Requirement: Daemon-Side GitHub Token Resolution By Exact Destination And Purpose

**Reason:** Returning a raw long-lived token to a daemon-side caller is replaced by owner-, destination-, purpose-, route-, phase-, job-, and expiry-scoped ephemeral vending.

**Migration:** Convert GitHub records to encrypted custody with exact destination/purpose constraints, update effectors to consume brokered leases, verify mismatches vend nothing, then revoke direct raw-token resolver access.

### Requirement: Subscription-Home Materialization For CLI Writers

**Reason:** Persistent Codex/Claude auth homes and base64 bundle materialization conflict with encrypted custody, per-invocation least privilege, cleanup, and cross-tenant isolation.

**Migration:** Replace persistent auth-home resolution with temporary invocation-scoped isolated roots materialized from approved ephemeral leases; verify provider startup and cleanup, then delete/revoke legacy universe auth artifacts. Rollback holds the provider route.

### Requirement: Per-Universe Provider Auth Env Overlay Without Cross-Universe Leakage

**Reason:** Copying the ambient host environment and deleting known names is fail-open and cannot prove that only requester-authorized resources reached the provider.

**Migration:** After draft PR #1606 and the fail-closed overlay lane reconcile, replace ambient inheritance with a minimal allowlisted base plus the exact scoped lease. Mutation-test every provider surface and every error path, then remove direct deposits and legacy overlay fallbacks. Rollback disables explicit requester execution rather than restoring host inheritance.
