# Provider-generic credential vault

**Status:** IMPLEMENTED (CORE, `feat/credential-vault`, draft PR #1469). Claude-family review = APPROVE with adaptations (`docs/audits/2026-07-16-...-claude-review.md`); hardened through seven Codex adversarial security-review rounds (`...-codex-review{,-2..7}.md`). Not yet wired into S2/S4/S5 callers (separate seams).
**Date / initial provider:** 2026-07-16 / Codex (design) + Claude (CORE implementation)
**Scope:** CORE build complete; replaces Phase-1 plaintext/base64 vault semantics; GitHub is the first adapter, not the abstraction

## Decision

TinyAssets uses one provider-generic `VaultBroker` with two custody backends: `platform_encrypted` for chatbot-only/24×7 use and `daemon_local` for users who run a daemon. A connection binding stores only custody metadata plus an opaque `SecretRef`; values never enter universe files, branch state, prompts, the commons, or MCP responses.

Platform storage uses per-record envelope encryption with libsodium XChaCha20-Poly1305 AEAD. A random 32-byte DEK encrypts each protected envelope; the active KEK wraps that DEK. Canonical scope/ref/version metadata is AEAD additional data on both layers, so ciphertext or wrapped-DEK swapping fails authentication. Secretbox is sound for independent messages but lacks AAD; XChaCha AEAD is the chosen primitive.

This is an irreducible platform primitive: OAuth callbacks, custody isolation, non-exportability, and fail-closed resolution cannot safely be composed by a chatbot. Provider connect/disconnect are actions under the existing coarse `universe`/`write.graph` surface, not new top-level MCP tools.

## Platform backend: Linux droplet / Docker

- Store ciphertext rows in `/data/private/credential-vault/v1/vault.db` (SQLite **rollback-journal `journal_mode=DELETE` + `synchronous=EXTRA`**, NOT WAL — the CORE build superseded the note's original "WAL now" after the SQLite WAL-reset concurrent-writer corruption finding, ≤3.51.2; NOT TRUNCATE — EXTRA's extra directory fsync is a DELETE-mode guarantee; the broker contract permits a future Postgres backend). `/data` backups contain ciphertext, wrapped DEKs, and non-secret metadata only. Power-loss durability across a full power-cut/VM-reset is a deploy-validation release gate; `os._exit` tests prove process-crash durability only.
- Generate KEK files as 32 random bytes. Keep them at `/etc/tinyassets/credential-vault/keys/<key_id>.bin`, owned by root, mode `0400`, outside `/data`; bind-mount the directory read-only only into the vault-broker container. Compose file-backed secrets are bind mounts, so the host file is the custody boundary.
- Provision/recover the KEK from a separate existing GitHub Actions secret during deploy/DR; never place it in `/etc/tinyassets/env`, Compose interpolation, image layers, `/data`, or the same backup object as the vault DB. Keep an offline recovery copy separate from data backups.
- The broker is the only process with DB+KEK access. A minimal PID 1 reads the root-only mount at boot, locks the KEK in memory best-effort, then irreversibly drops to the dedicated vault UID and removes capabilities before opening its socket. Daemon/workers present a short-lived, signed capability naming exact `ref + scope + purpose + run_id`; the broker returns plaintext only to the trusted adapter/worker call. Untrusted job sandboxes never mount the broker DB, KEK, socket credential, or whole auth homes.
- Defense: theft of `/data`, a volume snapshot, or its backup does not reveal values. It does **not** defend against droplet root, vault-broker RCE, or an attacker controlling code authorized to request that record. Root can read KEKs; an authorized process can ask the broker to decrypt. State this in operator docs and incident response.
- KEK rotation: deploy new `key_id` alongside old → mark it active → transactionally unwrap each DEK with old and rewrap under new (payload ciphertext unchanged) → verify every live row with the real broker → retain old KEK offline for backup-retention duration → unmount/delete old online key. Never rotate by rewriting plaintext payloads.

## Local backend: Windows daemon custody

- Use current-user DPAPI directly, `CRYPTPROTECT_UI_FORBIDDEN`, never `CRYPTPROTECT_LOCAL_MACHINE`; store a **per-version** DPAPI blob (`<ref>.v<version>.json`) under `%LOCALAPPDATA%\TinyAssets\credential-store\v1\`, outside repositories/universes, with a DACL set + verified (Windows security API) to the daemon user SID + SYSTEM only.
- **Crash-consistency (implemented):** the DPAPI blob file is SUBORDINATE; which version is LIVE is decided ONLY by an authoritative control-DB pointer (`vault_local_live` in `_control.db`, DELETE+EXTRA). A CAS/put writes the new versioned blob (inert), then the control-DB commit atomically advances the pointer; a commit failure leaves the OLD version live (never a half-written new one). Delete commits the control-DB state (clear pointer + irreversible tombstone) BEFORE removing blob files. `os.write` is looped to completion + size-verified; the durable replace uses `MOVEFILE_WRITE_THROUGH`.
- The protected envelope repeats ref, full scope, kind, version, timestamps, and raw bytes; verify all after decrypt. Rotation is put-new → atomically switch binding → delete-old. A daemon identity/machine change requires re-deposit.
- A universe declares local custody with `engine_source: host_daemon` and a `SecretBinding` whose store is `{custody:"daemon_local", daemon_id, store_id}`. Other external-account bindings use the same shape. Dispatch only to that daemon; offline/wrong daemon means typed unavailability, never platform or ambient fallback.
- Local OAuth uses provider device flow or a daemon-owned loopback callback when supported. If a provider supports neither without a platform exchange, local custody is unavailable for that adapter; offer platform custody rather than transiently persisting on the platform.
- Threat boundary: DPAPI plus the DACL protects offline copies and other Windows users, not malicious code already running as the daemon user; same-principal code can invoke DPAPI. Run the daemon under a dedicated least-privilege account where practical and treat that principal's compromise as vault compromise.

## Schemas

```text
SecretKind = github_app_private_key | github_app_user_token | github_pat |
             oauth2_generic | api_key | webhook_secret

SecretScope {
  founder_id: FounderId                 # reserved platform service principal allowed
  universe_id: UniverseId               # reserved platform universe allowed
  provider: str                         # github, x, anthropic, ...
  destination: str                      # repo/account/endpoint; exact-match policy key
  purpose: str                          # oauth_client, external_write, engine, webhook, ...
}

SecretRef = "secret:v1:" + random_256_bits  # opaque: no provider/path/account/custody

VaultStore {
  custody: platform_encrypted | daemon_local
  store_id: StoreId
  daemon_id: DaemonId?                    # required only for daemon_local
}

SecretBinding { ref, kind, scope, store: VaultStore }

SecretDescriptor {
  binding, version,
  created_at, updated_at, expires_at?, state: active|disabled|revocation_pending
}

EncryptedRow {
  descriptor, algorithm:"xchacha20poly1305-ietf", key_id,
  wrap_nonce, wrapped_dek, data_nonce, ciphertext
}

DpapiBlob { descriptor, blob_path, protection:"dpapi-current-user", blob_version }
```

`github_app_user_token` and `oauth2_generic` values are opaque provider-codec bundles (access token, refresh token, granted scopes, provider expiry fields). The broker does not understand token JSON. The GitHub App PEM is `github_app_private_key`; installation tokens are minted for restricted repos/permissions, held only in memory, and never records. Platform OAuth client secrets are `api_key` records scoped to `founder_id=platform:tinyassets`, `universe_id=platform`, destination `oauth_client`, purpose `oauth_token_exchange`; adapters may instead bind a user's own developer-app client credentials when provider billing/custody requires it.

## Broker protocol and failures

```python
class VaultBroker(Protocol):
    def put(self, store: VaultStore, scope: SecretScope, kind: SecretKind, value: SecretBytes,
            *, replace: SecretRef | None = None,
            expected_version: int | None = None, expires_at=None) -> SecretDescriptor: ...
    def get(self, binding: SecretBinding, expected: SecretScope) -> SecretLease: ...
    def delete(self, binding: SecretBinding, expected: SecretScope) -> None: ...
    # First-class refresh (implemented) — the ONLY sanctioned way to rotate a
    # one-use token; a plain put(replace) REFUSES rotating-token kinds.
    def begin_refresh(self, binding, expected, holder, at_version) -> RefreshTicket | None: ...
    def complete_refresh(self, binding, expected, ticket, value, *, expires_at=None) -> SecretDescriptor: ...
```

- `SecretBytes`/`SecretLease` cannot stringify, serialize, pickle, or reveal in `repr`; lease buffers are short-lived and zeroed best-effort. Only provider adapters may read bytes. `put`/`complete_refresh` reject empty and >1 MiB payloads at the boundary before any write.
- `put(replace=..., expected_version=...)` is atomic CAS (both must be supplied together). **Refresh consume-before-mint (implemented high-water capability protocol):** `begin_refresh` atomically authenticates the current record and, only if `at_version` equals the authenticated current version, mints a random UNFORGEABLE capability (stored hashed under a monotonic **high-water** claim, one row per ref) and returns a `RefreshTicket`; the caller alone may then call the provider. `complete_refresh` requires presenting the exact minted capability (constant-time hash compare) and CAS-advances. `put(replace)` REFUSES `github_app_user_token`/`oauth2_generic`, so bypass is structurally impossible. A version can only be claimed if strictly higher than the high-water, so a straggler/replay cannot re-redeem a consumed one-use token.
- Backend absence, missing/corrupt/ref-swapped records, scope mismatch, revoked/expired values, malformed refs/inputs, corrupt SQLite/row shapes, or failed attestation raise `CredentialUnavailable(code, ref)` with no provider body/value or backend path; corruption invalidates the cached attestation. A refresh that claimed the current version but crashed before completing raises `REAUTHORIZATION_REQUIRED` once past a wedge timeout (the honest answer — the provider may have rotated the one-use token; never a silent `None` wedge, never an unsafe retry). `""`, `None`, process env, shared auth homes, and global credentials are forbidden fallbacks.
- The binding's discriminated store selects exactly one backend; the backend re-derives/verifies ref, kind, scope, custody, and store identity from protected contents. Cross-store lookup is forbidden. **`delete` writes a durable, IRREVERSIBLE high-water tombstone (control-DB row, `deleted=1`, never removed) BEFORE removing the protected bytes**, so a restored/reappearing record after deletion (within the same snapshot) is refused (`NOT_FOUND`) and never re-claimable — closing the two-domain (sidecar-file vs control-DB) restore race. Absence is `NOT_FOUND`, not success. Provider revocation is a separate adapter step. **Local (DPAPI) delete never claims success while encrypted bytes remain:** every on-disk version is recorded as DURABLE pending-GC IN the same committed tombstone transaction, swept after commit, and swept again at the start of EVERY operation (the read path invokes GC); if a sidecar is still locked, `delete` surfaces a typed `DELETE_PENDING` (the credential is already unreadable, but the bytes are honestly reported as not-yet-removed and are cleaned by the next op) rather than reporting a full deletion.
- **Anti-rollback (implemented; the honest guarantee is "rollback forces reauthorization", NOT "bytes unrecoverable").** Claims, tombstones, and ciphertext share one SQLite recovery domain, so restoring an OLDER full snapshot (production backs up/restores the WHOLE `/data` volume as a unit) would silently reopen consumed refresh claims and deletion tombstones. A monotonic epoch is bumped on every mutation and compared against a high-water epoch kept in an **INDEPENDENT recovery domain OUTSIDE `/data`** — a tiny SQLite guard DB at `TINYASSETS_VAULT_ROLLBACK_GUARD` (recommended: a separate volume) or a home-dir default, deliberately NOT under `data_dir()` so a `/data` volume restore does not carry it. The guard is durable (`synchronous=EXTRA`), concurrency-safe (`BEGIN IMMEDIATE` + monotonic-`max` — never regresses the high-water under concurrent writers), and fail-closed (a guard read/write error raises, never silently returns zero). **EVERY mutation (`put`/`delete`/`complete_refresh`/`begin_refresh`) checks rollback FIRST**, not only reads — otherwise an unrelated `put` would catch the DB epoch up to the guard and re-expose a rolled-back credential (fail-open). After a full-volume / full-DB / full-directory restore the DB epoch is behind the guard, so every operation raises `REAUTHORIZATION_REQUIRED`; `backup-restore.sh` additionally calls `EpochGuard.bump_for_restore()` to force the signal explicitly. For rotating OAuth kinds the restored refresh token is already dead provider-side, so this is exactly correct.

**Durability / storage (implemented).** Both SQLite stores use rollback-journal `journal_mode=DELETE` + `synchronous=EXTRA` (NOT WAL — the WAL-reset concurrent-writer bug ≤3.51.2; NOT TRUNCATE — EXTRA's extra fsync only holds in DELETE mode). Local DPAPI writes use a full `os.write` loop + fsync + Windows `MOVEFILE_WRITE_THROUGH`.

**Honestly-unresolved limitations (deploy-validation release gates, not proven by `os._exit`):** (a) full power-cut / VM-reset durability of the rollback-journal + EXTRA guarantee is a documented deploy-validation test, not proven in-suite (`os._exit` proves process-crash only); (b) the separate vault-broker process / UID+capability-drop / socket boundary is production-infra integration; (c) the Windows local blob DACL is set + verified per-record by the library, but the narrowed-DACL deployment posture across service accounts is an installer concern.

## Chat OAuth connect / disconnect

1. `connect_external_account` authenticates the WorkOS founder, validates universe authority, selects custody, and asks the provider adapter for minimum scopes and a supported custody-specific flow. It creates a random, single-use 10-minute flow row and returns `https://tinyassets.io/connect/<ticket>`, requested scopes, and expiry—never a credential input field.
2. Platform custody: opening the ticket requires WorkOS login for the same founder. The server creates transaction-bound `state` and PKCE S256 verifier; store only the state digest plus encrypted verifier/ref. The exact tinyassets.io callback verifies provider/state/founder/TTL/single-use, exchanges server-side with the platform-scoped client secret, validates the response, and writes directly to `platform_encrypted`.
3. Daemon-local custody: after the same founder login, the page hands the signed flow to the bound online daemon. The daemon alone runs provider device authorization or an OS-browser/loopback PKCE callback and exchanges the code using a public client or locally vaulted developer-app secret; it writes directly to `daemon_local`, then reports only signed completion metadata. Authorization codes, client secrets, and tokens never traverse or persist on TinyAssets. If neither device nor loopback/local exchange is supported, the adapter rejects local custody and offers platform custody.
4. Platform completion atomically stores the secret, creates/updates the non-secret connection binding, records requested/actually granted scopes, consumes the flow, and emits completion. Local completion is two-phase: daemon commits the DPAPI blob first, then the platform atomically validates its signed receipt, records the binding/metadata, and consumes the flow; an unacknowledged blob is garbage-collected by the daemon. Chat polls status and confirms provider, account/destination, granted scopes, and expiry.
5. The custody owner schedules refresh with jitter before expiry and once on provider 401: platform scheduler for platform records, bound daemon for local records. It takes the store's exclusive ref lease, refreshes, CAS-replaces the bundle, and syncs non-secret expiry/state. Invalid grant becomes `reauthorization_required`; no fallback. GitHub user tokens default to 8 hours with 6-month refresh tokens; refresh invalidates the old pair, hence serialization.
6. GitHub automation treats the non-expiring App PEM as the crown jewel, rotates with overlapping keys, and uses it to mint repository/permission-restricted installation tokens in memory (1-hour lifetime). Owner-attributed actions use the founder's expiring GitHub App user token. PAT is an explicit, fine-grained, expiring fallback.
7. `disconnect_external_account` disables the platform binding immediately and clears caches, then routes revocation/delete to the custody owner. Success deletes protected bytes. Transient/offline failure leaves `revocation_pending` metadata (and encrypted/local bytes) for retry, but effectors cannot use it; force-delete warns when remote revocation is unconfirmed. Provider uninstall/revocation webhooks perform the same disable path.
8. X uses OAuth 2 authorization-code + PKCE and requests `offline.access` only for background work. Current X docs advertise prepaid pay-per-use, not a guaranteed free write tier: content creates are listed at $0.015/request and creates with a URL at $0.20. Hard-$0 therefore requires the user's own X developer project/client credentials and billing (or a console-attested zero-cost allowance); a platform-owned X app is disabled unless the host accepts spend. The UI must not promise free posting and must fail before writes when the user's project has no credit/allowance.

## Redaction enforcement

- Ingress: raw secrets accepted only by HTTPS callback/deposit or local broker UI; MCP schemas reject token/key/PEM fields.
- Types/storage: no secret-valued fields on public models; no value hashes, prefixes, last-four, or other correlatable fingerprints. Internal rows carry descriptors; every public projection is an explicit ref/kind/scope/timestamps allowlist.
- HTTP/provider clients: configure load balancer/reverse proxy/app server **before launch** to disable query-string and header capture on `/connect/*` and `/oauth/callback/*`; log only route templates and generated request IDs. Apply the same allowlist at tracing/log-forwarder/crash-report boundaries; never retain raw provider bodies, Authorization, cookies, codes, or callback URLs.
- Runtime: no values in argv, process-global/child env, node state, prompts, model context, receipts, external-write packets, metrics, `get_status`, exports, wiki, or commons. Adapters use SDK/HTTP broker leases; a CLI integration is unavailable unless it supports a non-observable pipe/handle input. Same-user process inspection and crash tooling are explicitly in threat scope.
- Output: logs, receipts, exceptions, list/status/export/MCP/wiki expose only error class plus ref, kind, scope (including granted provider permissions where relevant), and timestamps. They never expose custody internals, backend paths/IDs, versions, ciphertext, wrapped DEKs, OAuth flow rows, or platform-scoped records.
- Defense-in-depth tests seed canary tokens/PEMs and scan logs, DB projections, temp paths, subprocess env captures, receipts, MCP responses, exports, wiki, crash output, and Git history; regex redaction alone is never the guarantee.

## Truthful attestation

`TINYASSETS_BYO_VAULT_ENCRYPTED` remains an operator opt-in, not proof. At startup each configured `VaultStore` runs its real path: put random probe bytes under reserved probe scope → exact read → wrong-scope read must fail → delete → subsequent read must be `NOT_FOUND`. Inspect backend-specific persistence: platform rows require allowed AEAD, ciphertext/wrapped DEK, active `key_id`, and no plaintext; local rows require a DPAPI blob bound to the expected current-user principal, restricted DACL, and no plaintext.

Attestation is cached only for `(VaultStore, backend_instance, boot_id, tested_at)`. Every `get` also requires that store's current attestation and valid backend-specific protected evidence. Failure disables only that store and raises `CredentialUnavailable(BACKEND_UNAVAILABLE)`. Public `get_status` never enumerates stores/backends: an authorized binding projects only ref/kind/scope/tested_at, or the typed error class when unavailable. S5 becomes `byo_execution_enabled(binding)`—true only when operator opt-in, this-boot store probe, record validation, and provider auth-health all pass.

## Legacy migration

Do **not** promote current `.credential-vault.json` or `.credentials/` material into live refs: provenance, expiry, ownership, and scope are not trustworthy. Deployment stops legacy readers, detects files, creates metadata-only `needs_redeposit` bindings, encrypts each original file as a non-executable quarantine blob, fsyncs, then removes active plaintext/materializations. Users reconnect by OAuth or trusted local deposit; delete quarantine after 30 days/confirmation.

This cannot erase old SSD blocks or backups. Treat every legacy value as exposed: revoke/rotate at the provider, document backup exposure, and never let quarantine satisfy a credential lookup.

## Convergence seams and build order

1. Core: broker types/errors, encrypted SQLite backend, DPAPI backend, per-store probe, redaction/canary tests, and multiprocess concurrency/load proof.
2. S2: `target_repo` remains public binding data; the deferred credential **value** becomes a `SecretBinding`. Portable branch designs keep no binding values/refs and remain inert until the founder binds after remix.
3. S5: replace `credential_vault.py` record parsing/materialization and empty-string resolvers with broker refs; thread authoritative founder/universe/store context; `host_daemon` selects DPAPI custody; no ambient engine fallback; attestation becomes per-store/per-record.
4. S4/E4: GitHub adapter consumes `github_app_private_key`, `github_app_user_token`, or `github_pat`; mint installation tokens in memory; serialize 8h/6mo refresh; effectors receive leases, never values or whole vault files.
   - **S3 executor boundary (implemented primitive — wire to it, do NOT invent a parallel one):** an isolated worker resolves a tenant credential via an OPAQUE, job-scoped grant, never a raw forgeable `universe_id` or `ref`. The daemon calls `broker.mint_job_grant(binding, expected, run_id, ttl=...)` (recorded from the authoritative run record; authenticates the credential first; the `ttl` is validated finite/positive/bounded — `ttl=inf` is rejected so a grant can never be non-expiring) → an opaque `JobGrant` (opaque id + a private non-observable bearer capability; it deliberately exposes **no** `run_id`/`universe_id`, so a bearer has nothing to replay). **The grant is BROKER-AUTHORITATIVE:** the worker calls `broker.resolve_job_grant(grant)` with ONLY the opaque grant; the broker resolves against the grant's OWN authoritative run/universe (from the stored row, never caller-supplied identifiers). Authorization is the unforgeable capability + a non-expired TTL. S3 SHOULD pass `verify_context=<callback>` to bind resolution to the LIVE authenticated executor identity — the broker hands it the authoritative `JobContext` (run_id/universe_id/founder_id) and requires `True`, failing closed on any falsey/raising result. It fails CLOSED (typed `CredentialUnavailable`) for a non-grant object or malformed grant (`INVALID_ARGUMENT`, never a raw `AttributeError`), an unknown grant (`NOT_FOUND`), a bad capability (`LEASE_LOST`), a rejected executor context (`CROSS_STORE_FORBIDDEN`), or an expired grant (`EXPIRED`).
5. OAuth/API: add connect/list/status/disconnect actions under the existing universe API cluster, exact callbacks at tinyassets.io, refresh/revocation scheduler, webhook handling, then GitHub rendered-chatbot acceptance; X follows only after billing/policy UX is honest.
6. Release gates: crash-injected CAS/rotation, 100+ concurrent put/get/delete and single-refresh races across daemon/workers, stolen-volume-without-KEK test, wrong-store/scope swaps, restart/DR restore, secret canary scan, Claude+ChatGPT `ui-test`, then post-fix real-user evidence/watch.

Pickup: Claude must re-check primary sources and repo seams in `docs/audits/2026-07-16-provider-generic-credential-vault-claude-review.md` with verdict approve/adapt/defer/reject. Implementation lane: `feat/credential-vault`, `../wf-credential-vault`, draft PR until that verdict and S2/S4/S5 dependencies land; exact write boundary lives in `STATUS.md`.

## Exact PLAN.md replacement: Commons-first architecture

> **Rule:** Private data lives on host machines; public data lives in the platform commons. Three parts: (a) when a user builds a private branch / canon / universe, the data lives on a host; the platform/server **never stores** private work content. The sole narrow exception is authentication material: private credentials live only in the encrypted per-user credential vault, or in user-local custody when the user runs a daemon, and never in shared/commons artifacts. (b) Platform-stored work data is the open-source community commons—public-by-definition. (c) Community designs published to the commons become the tool surface for next users via discovery + similarity + remix; the platform doesn't build features, the community evolves them. Non-secret opaque references and scope metadata may live in control-plane bindings.
>
> **Why:** Security architecture, not security policy—the platform never has private work content. Identity and resource alignment keep the platform's work-data space an open-source commons and private-work storage costs on hosts. The commons + remix engine makes minimal-primitives + community-build viable at scale. The vault is a security boundary, not a general private-storage feature: it is non-browseable, non-remixable, excluded from search/export/wiki/receipts, and accessed only through typed least-privilege broker calls. Hybrid credential custody preserves 24/7 connections for browser-only users without weakening the work-content rule.
>
> **How to apply:** Before adding any platform feature, first ask whether users and chatbots can compose it from existing primitives + community remix; if yes, improve discovery/similarity/remix instead of shipping the feature. All platform-stored work data is public-by-definition—no `is_private` platform records; private branches have no platform rows and remain host-gated. Before storing any private data, ask whether it is authentication material strictly required to operate the user's external account or engine. If no, keep it on the host. If yes, use only the credential broker with explicit founder/universe/provider/destination/purpose scope, opaque refs, attestation, redaction, rotation, revocation, and fail-closed absence. Never place credential values in commons artifacts, prompts, logs, receipts, MCP responses, exports, wiki, environment fallbacks, or shared auth homes.

## Rejected alternatives

- KEK in environment: inspect/debug/log exposure and broad process inheritance; strictly worse than a file mount.
- Plain Compose/Docker secret as the whole solution: transport/mount convenience, not per-record isolation, rotation, scope binding, or protection from container/root compromise.
- SOPS-managed runtime key: sound configuration encryption, but unattended decryption still needs an age/KMS key; with that key on the same host it adds tooling, not a new boundary.
- age per record: sound file encryption, but weak fit for transactional metadata/AAD/CAS and leaves recipient-private-key custody unsolved.
- libsodium secretbox: authenticated encryption but no AAD for binding scope/ref/version; use XChaCha20-Poly1305 AEAD.
- Tiny host-level key service: hides raw KEK from containers but cannot protect against root or an authorized compromised daemon and adds an uptime component; reconsider only with a stronger process-identity/authorization boundary.
- Automatic plaintext-to-live migration: silently blesses stale or mis-scoped credentials; quarantine plus provider rotation/re-deposit is safer.

## Open risks

- Droplet/broker compromise exposes decryptable credentials; reduce blast radius with least privilege, short-lived provider tokens, sandbox separation, audit, and fast provider revocation.
- KEK loss makes records unrecoverable; keeping KEK with data backups defeats stolen-backup protection. DR must prove separate automated recovery without logging it.
- SQLite local-volume multi-container locking and refresh leases need load/crash proof before production; Postgres becomes the scale path, not a second contract.
- DPAPI binds custody to Windows identity/machine and does not isolate from code running as that identity; service-account change, reinstall, or host loss requires re-deposit unless profile recovery is deliberately supported.
- Provider OAuth, pricing, scopes, revocation, and token formats change. Each adapter owns discovery/current-source tests and fails closed on unknown response shapes.
- A trusted worker necessarily sees a credential it uses; the broker prevents bulk vault exposure, not capture of an actively leased credential. Short leases and job isolation remain mandatory.

## Primary sources (accessed 2026-07-16)

- Docker Compose secrets/file mounts and env exposure risk: https://docs.docker.com/compose/how-tos/use-secrets/ and https://docs.docker.com/reference/compose-file/services/
- Docker `ENV` values inspectable: https://docs.docker.com/reference/dockerfile/#env
- libsodium XChaCha20-Poly1305 AEAD/AAD guidance: https://doc.libsodium.org/secret-key_cryptography/aead/chacha20-poly1305 and https://doc.libsodium.org/secret-key_cryptography/encrypted-messages
- SOPS envelope/age key custody: https://github.com/getsops/sops#encrypting-using-age
- Windows current-user DPAPI semantics: https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata
- OAuth PKCE/state security BCP: https://datatracker.ietf.org/doc/html/rfc9700
- GitHub PKCE user flow: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app
- GitHub App PEM custody/rotation: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/managing-private-keys-for-github-apps
- GitHub installation token lifetime: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app
- GitHub 8h access / 6mo refresh and one-time refresh semantics: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/refreshing-user-access-tokens
- X OAuth 2 PKCE/offline access: https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code
- X current pay-per-use pricing: https://docs.x.com/x-api/getting-started/pricing
