## ADDED Requirements

### Requirement: Requester-supplied provider API keys remain on the requester-controlled executor
Requester-supplied provider API keys SHALL be accepted only by an
authenticated requester-controlled executor and SHALL be stored only in its
native OS secret store under a random versioned provider-secret reference.
The implementation SHALL consume PR #1736's existing `NativeCredentialStore`
backend allowlist and fail-closed policy rather than define a parallel native
store abstraction. Approved backends SHALL be Windows Credential Manager,
macOS Keychain, and Linux Secret Service/libsecret when available. An unsupported platform,
headless session without its native backend, locked backend, or backend error
SHALL fail closed with the existing typed `setup_required` hold and without a
plaintext file, environment, argv, host-home, server, maintainer/founder, or
alternate-store fallback.

This requirement applies to bring-your-own `llm_api_key` custody only.
Existing `llm_subscription`, `vcs`, and `social` credential behavior and
storage limitations remain owned by their canonical capabilities. Provider
secret references SHALL use a random namespace disjoint from #1736's stable
account-token references.

#### Scenario: unsupported raw API-key field is rejected at ingress
- **WHEN** a chatbot or control-plane request supplies an unsupported `api_key`, `key`, `token_b64`, `secret_b64`, or equivalent `llm_api_key` value
- **THEN** ingress returns the existing typed setup-required hold before config, vault, assignment, ledger, or provider mutation
- **AND** TinyAssets does not echo the value and every inventoried TinyAssets-owned gateway/access log, MCP middleware/request capture, response, ledger, trace, exception, and crash sink omits or redacts the supplied canary
- **AND** acceptance does not claim that TinyAssets can redact bytes already sent to a client-owned upstream chatbot transcript

#### Scenario: native store outage has no fallback
- **WHEN** requester-local enrollment cannot use the platform's approved native OS secret backend
- **THEN** enrollment fails closed with the approved backend and local-remediation guidance
- **AND** no secret is written to a file, environment variable, process argument, control-plane record, host home, or alternate host store

#### Scenario: approved native backend is platform exact
- **WHEN** enrollment runs on Windows, macOS, or Linux
- **THEN** it uses respectively Windows Credential Manager, macOS Keychain, or available Secret Service/libsecret
- **AND** any unsupported or unavailable case remains held without fallback

#### Scenario: provider and account reference namespaces are disjoint
- **WHEN** a provider API key is enrolled on a host that also holds an account refresh token
- **THEN** the provider secret receives a random versioned provider-secret reference
- **AND** it never overwrites, reuses, or derives #1736's account-token reference

### Requirement: The control plane stores only an opaque bound credential reference
The control plane SHALL store the authoritative opaque non-secret
`credential_binding_ref` only as the custody-side reference field of the
selected provider's entry in
`constrain-set-engine-provider-authority`'s versioned
`provider_authority_bindings` map. The
reference SHALL be random, non-derivable, and bound to exact credential-owner
principal, universe, canonical provider, stable `host_principal_id`, scope,
provider-assignment generation, issue time, and expiry. It SHALL NOT freeze an
issue-time `host_principal_generation`, contain or derive secret material, or be a
bearer grant, and SHALL NOT resolve for another principal, universe, provider,
host principal, revoked/expired host principal, stale host-principal
proof generation, stale provider-assignment generation, expired host attestation, or
tombstoned reference.

Every sensitive consumer SHALL present fresh host proof whose generation
equals the current active `host_principal_generation` read from trusted
control-plane state. Same-ID in-place device-key rotation SHALL fence old
proofs/sessions but SHALL NOT orphan or require re-enrollment of the provider
binding; fresh proof at the new generation MAY continue using it. Revocation,
expiry, and lost-key recovery SHALL fence the old binding because the old
principal is terminal and recovery creates a new `host_principal_id`. A valid
host-principal renewal that preserves ID and generation MAY continue using the
binding after current proof and extended expiry are rechecked.

The unversioned `.credential-vault.json` MAY retain non-authoritative,
non-secret display metadata, but a provider launch SHALL NOT trust it as
binding or generation state.

#### Scenario: wrong principal or host cannot resolve
- **WHEN** a binding created for principal A and host H1 is presented by principal B or host H2
- **THEN** resolution fails closed before provider launch
- **AND** no other keyring entry, vault alias, host home, environment, or maintainer credential is searched

#### Scenario: wrong scope cannot resolve
- **WHEN** a binding is presented for an action or provider capability outside its exact bound scope
- **THEN** resolution returns setup-required hold with zero provider and backend calls
- **AND** no broader universe grant, ACL admin role, empty capability ceiling, or opaque reference upgrades that scope

#### Scenario: stale consumer or tombstoned reference cannot reactivate
- **WHEN** the presented host proof generation or provider-assignment generation is stale, its host principal is revoked/expired, its host attestation expired, or its identifier is tombstoned
- **THEN** new launches return the existing setup-required hold with zero provider calls
- **AND** reusing the identifier cannot reactivate the retired binding

#### Scenario: host-principal renewal preserves a current binding
- **WHEN** an active host principal renews without changing `host_principal_id` or generation
- **THEN** fresh proof plus the current extended expiry may continue using the existing provider binding
- **AND** renewal neither bypasses provider-assignment generation checks nor reactivates a revoked or expired principal

### Requirement: Local binding enrollment is a crash-safe two-store commit-token protocol
Every enrollment, rotation, retirement, and compare-delete operation SHALL
first acquire exclusive `ProviderAssignmentAdmission` for the canonical
universe and validate expected assignment generation plus the affected
provider-binding digest. Enrollment, secret use, binding creation/rotation,
and cutover SHALL independently read trusted host-principal state and require
the exact principal to remain active and the presented host proof generation
to equal the current trusted `host_principal_generation` immediately before
starting or committing protected work. Revoked, expired, lost-key-recovered,
or stale-generation host consumers SHALL fail closed; same-ID in-place
rotation resumes only with fresh current-generation proof.

Terminal-principal retirement/compare-delete MAY instead use same-subject
step-up recovery or a separately authorized internal exact-tuple cleanup
consumer under exclusive `ProviderAssignmentAdmission`. Before mutation, that
consumer SHALL read trusted host-principal state and prove that the exact bound
principal is terminal because it is revoked, expired, or superseded by
same-subject lost-key recovery. Active, unknown, mismatched-subject, or
unprovably terminal state SHALL refuse cleanup. The admitted path SHALL be
tombstone/delete-only and SHALL NOT dereference, transfer, rebind, or launch
with the secret. Only then MAY the applicable operation acquire
the narrower local
pending-index/keyring locks. Reverse acquisition and untracked reentrancy
SHALL fail loud. No local pending-index/keyring lock SHALL remain held across
a control-plane CAS or any operation that could reacquire assignment
admission.

The selected host SHALL create a random `native_secret_ref`, enrollment id, and
one-use commit token in an atomically updated, secret-free bounded local
pending index before writing the exact native secret and entering state
`pending`. The control plane SHALL use exclusive
`ProviderAssignmentAdmission` to compare-and-swap a binding carrying that
enrollment id and commit-token digest into the expected assignment generation.
The host SHALL read and
verify that exact committed binding and record a local acknowledgement before
advancing the mapping to `committed`. The two stores SHALL NOT be described as
sharing one CAS or transaction.

A bounded local reconciler MAY tombstone a timed-out pending native reference
only after an authenticated control-plane read finds no matching enrollment id
and token digest. It SHALL then re-read the control plane. If a late binding
appeared after local tombstone, reconciliation SHALL hold provider launch and
compare-clear only that exact binding by enrollment id, token digest, and
assignment generation. It SHALL NOT restore the deleted local secret,
reactivate the tombstoned identifier, or treat either side as usable; a fresh
enrollment is required.

Native OS secret stores SHALL be treated as exact-reference set/get/delete
stores, not portable enumeration sources. The local pending index SHALL be the
only enumeration source for reconciliation. A native reference absent from
that index is unreachable rather than discoverable through a backend scan.

The host identity used by this protocol SHALL be a stable server-attested host
principal bound to the verified account principal by
`bind-host-principal-to-account`. A caller-supplied owner field, a per-session
host-pool row, or an unattested client-generated identifier SHALL NOT satisfy
that binding.

#### Scenario: local write succeeds before control-plane commit fails
- **WHEN** native storage succeeds but the expected assignment-generation CAS fails
- **THEN** the local reference remains pending and cannot satisfy provider launch
- **AND** bounded reconciliation tombstones it only after proving no authoritative binding exists

#### Scenario: reverse lock order fails loud
- **WHEN** code holding a pending-index or native-keyring lock attempts to acquire `ProviderAssignmentAdmission`
- **THEN** acquisition fails before waiting or mutation
- **AND** no enrollment, rotation, retirement, compare-delete, or launch state changes

#### Scenario: local acknowledgement is required for use
- **WHEN** the control-plane assignment carries the expected enrollment id and token digest but the host has not recorded its local acknowledgement
- **THEN** the binding remains unusable and provider launch is held
- **AND** neither control-plane presence nor local secret presence alone is treated as committed

#### Scenario: reconciliation enumerates only the secret-free pending index
- **WHEN** reconciliation searches for timed-out or split-brain local enrollments
- **THEN** it enumerates only the bounded secret-free local pending index
- **AND** it does not scan, list, or infer entries from the native OS secret backend

#### Scenario: self-asserted or per-session host identity is refused
- **WHEN** enrollment presents a caller-supplied account owner, an insert-always host-pool row, or an unattested client-generated host identifier
- **THEN** binding fails before native-secret or assignment mutation
- **AND** only an authenticated stable server-attested host principal may enter the commit-token protocol

#### Scenario: late binding after local tombstone is compare-cleared
- **WHEN** a delayed control-plane binding appears after the local pending reference was tombstoned
- **THEN** reconciliation holds launch and compare-clears only the exact late binding by enrollment id, token digest, and assignment generation
- **AND** the deleted local secret is not restored and a fresh enrollment is required

### Requirement: Provider API-key dereference occurs only at the authorized local launch boundary
A provider API key SHALL be dereferenced exactly once by the selected
requester-controlled executor after `ProviderExecutor.start()` validates
provider destination, persisted credential-owner principal, universe,
stable `host_principal_id`, presented host proof against current active
`host_principal_generation`, scope,
provider-assignment generation, binding digest, expiry, and tombstone state
from trusted control-plane state and crosses shared
`ProviderAssignmentAdmission` and the
`ProviderInvocation -> ProviderLaunchHandle` barrier. The secret MAY enter
provider-child memory or an ephemeral child environment only for that
requester-owned CLI/local/in-process launch and SHALL NOT enter process
arguments, persisted child configuration, logs, traces, or control-plane
state. No separate adapter SHALL independently validate or dereference the
tuple outside `ProviderExecutor.start()`.

`runner/v1`'s `credential_grant_ref` MAY carry the already-validated opaque
reference only after this composition. `SandboxRunner` does not possess the
full tuple and SHALL NOT treat the field as validation or authority. The
current D0 path is fake-only/production-denied and SHALL NOT be required or
accepted as ordinary requester-provider authority. Accepted-market remote
execution SHALL remain held until its owner accepts a production B2 authority
composition, and SHALL NOT receive a requester-local secret merely because the
runner carries a locator.

#### Scenario: validated launch resolves one coherent generation
- **WHEN** `ProviderExecutor.start()` crosses shared `ProviderAssignmentAdmission` and the provider-authority launch barrier with a current exact binding for a CLI/local/in-process transport
- **THEN** the selected local executor resolves exactly that generation once and launches only the canonical selected provider

#### Scenario: accepted-market execution does not borrow requester-local authority
- **WHEN** an accepted-market remote invocation has an opaque binding or fake-only D0 record but no owner-accepted production B2 authority
- **THEN** provider and backend dispatch remain held
- **AND** the requester-local native secret is not transferred or dereferenced

#### Scenario: resumed work uses persisted authority principal
- **WHEN** background, resumed, retried, or scheduled work reaches provider launch without a live requester session
- **THEN** binding validation uses the credential-owner principal frozen in verified request and assignment authority
- **AND** it does not substitute the daemon identity, ambient HTTP subject, current workspace member, changed ACL member, founder, or maintainer

#### Scenario: rotation fences new launches
- **WHEN** rotation or revocation advances the binding generation while launches are concurrent
- **THEN** shared `ProviderAssignmentAdmission` admits no new requester-owned launch with the retired generation
- **AND** the old native reference is deleted only after captured-generation launches drain or are explicitly cancelled

#### Scenario: host-principal rotation fences old proofs without orphaning the binding
- **WHEN** in-place device-key rotation advances `host_principal_generation` for the same active `host_principal_id` while a launch or custody cutover is pending
- **THEN** `ProviderExecutor.start()` and every protected commit recheck trusted host-principal state and provider-assignment state independently
- **AND** a prior-generation proof cannot dereference, launch, or commit, while fresh proof at the new generation for the same active `host_principal_id` may continue using the binding without re-enrollment

#### Scenario: lost-key recovery requires a new binding
- **WHEN** lost-key recovery revokes the old principal and creates a new `host_principal_id`
- **THEN** the old binding remains permanently fenced and its native reference enters the safe rotation/tombstone path
- **AND** same-subject step-up recovery or an authorized internal exact-tuple consumer may tombstone/delete the old binding without dereference, while the new principal must complete fresh provider enrollment rather than inheriting or re-binding the old reference

### Requirement: Remote HTTP secret resolution belongs only to the outbound boundary
For requester-owned remote HTTP, `ProviderExecutor.start()` SHALL validate the
complete assignment and binding tuple under shared
`ProviderAssignmentAdmission`, then obtain only the non-serializable,
per-universe grant-bound credential-blind proxy handle owned by
`outbound-boundary-layer`. Provider/executor code SHALL send only a redacted
request through that handle. The outbound proxy alone SHALL resolve the
credential reference and perform network I/O. For requester-owned
`llm_api_key`, that proxy and the native secret store SHALL run on the same
attested requester-controlled host, and the proxy SHALL resolve through this
capability's native reference rather than through a legacy
`credential-vault` `llm_api_key` record. The `outbound-boundary-layer` owner
has accepted this narrow custody-source adaptation through its task 0.5 and
credential-blind execution-admission requirement; retained
`llm_subscription`, `vcs`, and `social` custody remains unchanged. This narrow
acceptance does not complete the provider-call lifecycle gate in task 1.4b:
runtime remains held until the outbound owner classifies provider model calls
under its action-cap and confirmation contract and defines or explicitly
carves out request-lineage idempotency, journal-before-fire, reconciliation,
terminal receipts, and batch holds without creating a second outbound
authority or receipt system.
Neither the executor nor an HTTP provider SHALL dereference native material
into provider-child memory, environment, arguments, config, logs, traces,
receipts, or server state.

A missing, expired, revoked, ambiguous, wrong-principal, or wrong-universe
outbound grant/proxy SHALL hold before provider, credential, or network
access. This custody capability SHALL NOT create a second outbound ledger,
grant, proxy, secret path, or ambient fallback.

This `llm_api_key` requirement SHALL NOT apply to the keyless
`ollama-local` supplement, which has no `credential_binding_ref`; the planned
`activate-requester-host-engines` owner SHALL select that transport solely
from its attested requester endpoint and executor-host identity.

#### Scenario: authorized remote HTTP uses only the outbound proxy
- **WHEN** requester-owned remote HTTP passes assignment, binding, and outbound-grant validation
- **THEN** `ProviderExecutor.start()` binds the redacted request to the outbound owner's non-serializable proxy handle on the same attested requester-controlled host as native custody
- **AND** only that proxy resolves the provider-custody native reference and performs network I/O; it never resolves a legacy vault `llm_api_key`

#### Scenario: invalid outbound authority holds before secret or network access
- **WHEN** the outbound grant or proxy is missing, expired, revoked, ambiguous, wrong-principal, or wrong-universe
- **THEN** remote HTTP remains held before provider, credential, or network access
- **AND** no local dereference, ambient credential, alternate proxy, or maintainer route is attempted

### Requirement: Engine OS credential requirements are opaque and credential-blind

For Engine OS execution admission, this capability SHALL resolve the trusted
logical requirement's opaque `credential_requirement_ref` and digest, while
the outbound owner resolves its independent `egress_requirement_ref` and
digest. The exact resolved objects, digests, workload, profile, binding, grant,
and proxy authority SHALL agree through an owner-published compatible pairing
before credential or network access. A caller, graph, provider, backend, or
adapter SHALL NOT supply the resolved object, replace its digest, or treat a
`credential_binding_ref`, generic grant, proxy handle, or matching name as the
credential requirement or as compatibility proof.

`source_exec/runner_source_exec` SHALL resolve to no credential available to
the workload. `inference_only/provider_cli` SHALL expose no raw key, token,
auth file, `native_secret_ref`, `credential_binding_ref`, or other recoverable
credential material to model-controlled work. CLI/local/in-process resolution
SHALL remain inside the authorized executor launch boundary. Requester-owned
remote HTTP SHALL remain inside the outbound owner's non-serializable proxy on
the same attested requester-controlled host as native custody and SHALL never
resolve a legacy vault `llm_api_key` record.

No profile SHALL be admitted when either owner binding or its exact compatible
pairing is absent, stale, mismatched, malformed, unknown, or unpublished. This
requirement does not define a complete credential taxonomy or compatibility
matrix, does not change retained subscription/VCS/social custody, and does not
resolve the provider-call lifecycle questions that remain open in task 1.4b.

#### Scenario: source execution resolves no credential

- **WHEN** `source_exec/runner_source_exec` reaches execution admission
- **THEN** its exact credential requirement resolves to no credential available to the workload
- **AND** no vault record, native reference, grant, proxy, environment, or caller field widens it

#### Scenario: provider inference requires an exact credential-blind pairing

- **WHEN** `inference_only/provider_cli` reaches execution admission
- **THEN** its credential reference and digest and the outbound owner's egress reference and digest match an owner-published compatible pairing
- **AND** model-controlled work receives no recoverable credential material

#### Scenario: opaque references do not imply compatibility

- **WHEN** the credential and egress bindings are each well-formed but their exact compatible pairing is absent or unpublished
- **THEN** admission remains held before credential resolution or network access
- **AND** matching names, grants, proxy handles, or opaque references do not infer compatibility

### Requirement: Shared-universe administration does not confer credential use
A shared universe SHALL NOT own or copy provider API-key material, and a
universe ACL `admin` grant SHALL NOT confer authority to attach, resolve,
rotate, delete, replace, or use a credential binding owned by another
principal. Every binding mutation other than the terminal-principal
tombstone/delete-only cleanup path defined above, and every binding use, SHALL
require an exact current credential-owner
principal/host/provider/universe/scope/generation match in addition to
universe and fulfillment-class authority; otherwise the universe SHALL remain
held. The sole mismatch exception is the tombstone/delete-only
terminal-principal cleanup path defined above, after trusted state proves the
exact bound principal terminal and same-subject step-up or internal exact-tuple
cleanup authority. It grants no credential use or cross-principal
administration.

#### Scenario: active principal cannot be deleted through terminal cleanup
- **WHEN** same-subject step-up or an internal cleanup consumer targets a binding whose exact host principal remains active, is unknown, or cannot be proven terminal
- **THEN** tombstone/delete cleanup is refused before binding, native-store, or assignment mutation
- **AND** the cleanup authority cannot dereference, transfer, rebind, or launch with the secret

#### Scenario: second admin cannot attach or use founder binding
- **WHEN** a second principal holding `admin` submits or encounters a binding owned by the founder
- **THEN** configuration refuses to attach it and execution cannot resolve, replace, rotate, delete, or launch with it
- **AND** administration alone yields no credential-use authority

#### Scenario: shared universe without an exact binding remains held
- **WHEN** a shared universe has no current binding for the persisted credential-owner principal and selected host
- **THEN** provider execution returns setup-required hold with zero provider calls
- **AND** no member, founder, maintainer, or alternate-host credential is substituted

### Requirement: Legacy llm_api_key retirement is replacement-first, monotonic, and concurrency-safe
Each legacy `llm_api_key` slot SHALL use an immutable migration id, expected
record digest, credential slot, and assignment generation. A shipped-alias
slot SHALL contain the environment-variable slot and stored occurrence derived
from exactly `anthropic`, `claude`, `claude-code`, `openai`, `codex`, `gemini`,
`google`, `groq`, `xai`, or `grok`; an absent or unsupported service SHALL enter
terminal `held_ambiguous`. The saga SHALL implement exactly these states:

`discovered`, `held`, `notified`, `replacement_pending`,
`replacement_verified`, `rotation_required`, `revoked_upstream`,
`cutover_committed`, `artifacts_deleted`, `record_deleted`, `closed`,
`closed_without_replacement`, and `held_ambiguous`.

The only ordinary successful path SHALL be:

`discovered -> held -> notified -> replacement_pending ->
replacement_verified -> rotation_required -> revoked_upstream ->
cutover_committed -> artifacts_deleted -> record_deleted -> closed`.

At terminal state, provider-assignment vocabulary SHALL remain owned by
`constrain-set-engine-provider-authority`:

- `closed` SHALL publish `engine_source=requester_local` through its atomic
  post-custody writer and SHALL be `ready` only when the current binding plus
  all live-role coverage are complete; otherwise it remains `held + []`;
- `closed_without_replacement` SHALL retain `engine_source=byo_api_key` with
  `engine_assignment_state=failed` and `allowed_providers=[]`; and
- `held_ambiguous` SHALL likewise retain `engine_source=byo_api_key` with
  `failed + []`, while preserving the unclassifiable source record.

Unresolvable ownership at `discovered` SHALL transition only to terminal
`held_ambiguous`, with no deletion. Any nonterminal state MAY carry a
`failed_held(last_committed_state, sanitized_failure_class)` overlay without
advancing or leaving that committed state; retry SHALL attempt only that
state's next legal edge. An owner who explicitly declines replacement MAY use only
`discovered -> held -> notified -> rotation_required -> revoked_upstream ->
artifacts_deleted -> record_deleted -> closed_without_replacement`; its
assignment SHALL remain held/setup-required. Every other transition SHALL be
refused.

The saga SHALL never decode, export, automatically migrate, or use the legacy
secret and SHALL hold provider launch until terminal `closed` has a current
replacement assignment. Every transition SHALL hold the exclusive writer from
`ProviderAssignmentAdmission`, owned by
`constrain-set-engine-provider-authority`, be monotonic and idempotent, and
fence requester-owned launch through that change's shared-reader
`ProviderInvocation -> ProviderLaunchHandle` barrier.
`replacement_verified` SHALL require exact local provider authentication
without reading legacy bytes. `cutover_committed` SHALL be a compare-and-swap
of the provider assignment binding and generation after upstream rotation/revocation
attestation. A mismatch SHALL remain held and re-inventory; rollback SHALL
enroll a fresh local generation or remain held and SHALL never restore raw
vault material. Accepted-market execution remains separately governed by its
owner-accepted production B2 authority.

#### Scenario: inventory exposes metadata only
- **WHEN** migration inventories a legacy `llm_api_key` record containing direct or base64-recoverable fields
- **THEN** the serialized inventory contains only universe, slot, normalized service, present field names, byte length, record digest, and generation
- **AND** no decoded or encoded secret value appears

#### Scenario: replacement verification and upstream revocation precede cutover
- **WHEN** an owner begins retirement of a live legacy `llm_api_key`
- **THEN** provider launch remains held until a pending local replacement authenticates exactly and positive provider or explicitly labeled owner revocation attestation is recorded
- **AND** provider assignment cutover occurs only afterward by expected-generation compare-and-swap under exclusive `ProviderAssignmentAdmission`

#### Scenario: explicit no-replacement retirement remains held
- **WHEN** the authorized owner declines a replacement and positively attests upstream revocation
- **THEN** exact cleanup may end in `closed_without_replacement`
- **AND** the assignment remains `engine_source=byo_api_key`, `engine_assignment_state=failed`, and `allowed_providers=[]` and cannot launch with legacy, founder, maintainer, or alternate authority

#### Scenario: concurrent record or assignment change aborts destructive work
- **WHEN** the stored record digest or assignment generation changes after inventory
- **THEN** cutover and compare-and-delete perform no destructive action and re-inventory under the current generation
- **AND** an unrelated or newly rotated credential survives

#### Scenario: exact artifact ownership gates deletion
- **WHEN** a materialized artifact has a changed digest, more than one reference, a different owner, slot, or generation, a mixed-purpose provider home, or ambiguous provenance
- **THEN** deletion is refused and the saga remains held
- **AND** no recursive provider-home deletion or source-record deletion occurs

#### Scenario: exact artifacts precede source record deletion
- **WHEN** every inventoried artifact has the expected canonical path, digest, owner, slot, generation, and exactly one reference
- **THEN** those exact artifacts are compare-deleted before the unchanged source record
- **AND** the final source deletion verifies the inventoried digest under exclusive `ProviderAssignmentAdmission`

#### Scenario: crash and retry converge without resurrection
- **WHEN** the process crashes after any legal saga transition and retries with the universe/slot/generation-scoped idempotency key
- **THEN** it resumes from the last monotonic state or returns the prior terminal result
- **AND** it never rereads, exports, restores, or launches with the legacy secret

#### Scenario: ambiguous owner remains terminally held
- **WHEN** a legacy record cannot be attributed to an authorized owner
- **THEN** migration enters `held_ambiguous` with no export or deletion
- **AND** provider launch remains refused as `engine_source=byo_api_key`, `engine_assignment_state=failed`, and `allowed_providers=[]`, with no alternate credential fallback

#### Scenario: illegal transitions are refused
- **WHEN** a caller attempts any transition outside the exact state graph, including deletion before revocation or cutover before replacement verification
- **THEN** no state, assignment, artifact, or record mutation occurs
- **AND** the saga remains at its last committed held state

#### Scenario: global reset cannot bypass retirement
- **WHEN** `openspec/changes/test-identity-and-reset/` global reset encounters any legacy `llm_api_key`
- **THEN** it performs zero mutation and remains blocked until every legacy key's owner-notified replacement/revocation/cutover/artifact/source saga reaches safe terminal deletion
- **AND** it cannot clear the vault, assignment, artifact, or native reference directly
- **AND** malformed, unclassifiable, or ambiguously preservable vault state blocks reset before mutation

#### Scenario: multi-process custody race has one usable binding
- **WHEN** concurrent pending enrollment, commit-token publication, local acknowledgement, local tombstone, late control-plane binding, split-brain compare-clear, rotation, dereference, revocation, deletion, retry, stale-host expiry, and provider-authority launch barriers target one universe/provider/host
- **THEN** exactly one current binding and generation is usable or all paths remain held
- **AND** assignment-before-custody lock order holds, reverse acquisition and untracked reentrancy fail loud, and no torn secret read, post-fence launch, lost rotation, deadlock, duplicate authority, orphaned active native reference, or tombstone resurrection occurs
