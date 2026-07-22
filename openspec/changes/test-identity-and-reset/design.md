## Context

The production identity is an authorization-server-issued subject resolved request-locally by the
OAuth middleware. `founder_home` binds that subject to its first-contact home. ACL rows grant access;
they are mutable and therefore are not deletion ownership. The current `tinyassets.reset.reset` is a
confirm-gated global teardown and the canonical lifecycle spec correctly forbids public per-universe
deletion.

Automated tests already simulate many subjects, but fake providers and direct calls cannot prove that
two real connectors received distinct principals and ordinary grants. The missing acceptance primitive
is therefore a safe way for host operators to recycle dedicated test accounts plus a token-safe way for
each caller to observe its own resolved request identity.

## Goals / Non-Goals

**Goals:**

- Recycle an allowlisted external test principal to first-contact state without changing another
  principal's state.
- Keep reset authority exclusively in an authenticated host/operator shell and make destructive scope
  reviewable before apply.
- Make the filesystem/database operation deterministic under concurrency, interruption, and schema
  growth.
- Prove at least two real external identities through ordinary rendered connector flows.
- Report self-only request identity evidence without retaining or exposing bearer material.

**Non-Goals:**

- No MCP/API/user-facing delete or account-reset surface.
- No general per-universe delete, GDPR erasure, retention policy, or customer support impersonation.
- No fake bearer, caller-selected subject, direct `ContextVar` injection, shared test secret, or
  privileged auth shortcut.
- No cross-user visibility acceptance in this change; that belongs to universe visibility and identity
  authorization.
- No provider-auth health/evidence changes; those belong to provider status / PR #1570.
- No use of platform/maintainer hardware, local model routes, quota, accounts, credentials, auth homes,
  Claude/OpenAI limits, or any other maintainer resource for a user's workload.

## Decisions

### 1. Test identities are real external identities; the roster carries no credentials

An operator-private, access-controlled roster maps a human-safe alias to an exact external subject ID.
It is never committed or logged. The roster never contains bearer tokens, refresh tokens, cookies,
API keys, provider auth homes, or fabricated grants.
Each identity is provisioned and authorized through ordinary WorkOS and connector flows. A missing
alias or a subject not on the allowlist fails closed; an allowlisted subject with no current state is an
idempotent no-op.

The public status response returns a deployment-scoped, non-reversible principal fingerprint, not the
raw subject. The operator can precompute the expected fingerprint from restricted roster state. Durable
logs, third-party chatbot transcripts, screenshots, and committed artifacts therefore never need the
raw stable subject.

Alternative rejected: an internal impersonation header or shared test bearer. It would prove a more
privileged path than users receive and would turn the test harness into an auth bypass.

### 2. Scoped reset is an operator maintenance command, not a product primitive

The implementation extends the local reset CLI with explicit `plan` and `apply` phases. It is not
imported or registered by the MCP/API servers. `plan` is read-only and returns a stable plan ID plus the
exact directories, bindings, grants, rows, and preservation/block reasons. `apply` requires that plan ID
and revalidates it after acquiring the affected-scope maintenance lease.

The only candidate home comes from the exact `founder_home` row for the allowlisted subject. An admin
ACL is access, not ownership, and can never add a universe to the deletion set. Apply rejects a home
also bound to another principal, a foreign grant on the candidate home, inconsistent path/index data,
or any other ambiguous ownership signal. Grants held by the reset subject on other universes may be
removed without changing those universes' content.

Alternative rejected: dynamically discovering "owned" universes from self-granted admin ACLs. ACLs are
mutable collaboration state and cannot authorize irreversible deletion.

### 3. Every store is classified explicitly; schema growth fails closed

The design uses a reviewed deletion graph, not "delete from every table containing `universe_id`."
Every table/file carrying the subject, candidate universe ID, or candidate path is classified as one of:

- resettable mutable home state;
- preserved commons/history/audit/market state;
- separately removable subject grant/binding state; or
- blocking/unclassified state.

For `P = allowlisted subject` and `H = its exact founder-home universe`, the reviewed baseline is:

| Store and key | Classification / action |
|---|---|
| `.tinyassets.db`: `founder_home(founder_sub=P)` | Reset the exact binding. Any other binding to `H` blocks. |
| `.tinyassets.db`: `universe_acl` | Reset `P`'s grants elsewhere; any actor other than `P` on `H` blocks. ACL/admin never establishes ownership. |
| `.tinyassets.db`: `universes`, `universe_rules`, `universe_notes`, `universe_work_targets`, `universe_hard_priorities`, `branches`, `branch_heads`, `universe_snapshots` | Reset exact `H`/branch rows. Any foreign creator/owner/reference blocks. |
| `.tinyassets.db`: `author_runtime_instances`, `user_requests`, `vote_windows`, `vote_ballots` | Pending/running/claimed/open work blocks until normal stop/cancel/close; then reset only reviewed mutable `H` rows. |
| `.tinyassets.db`: `action_records` | Preserve immutable audit rows, including references to `P` or `H`. |
| `.tinyassets.db`: `user_accounts`, `user_sessions`, `capability_grants` | Preserve account/auth state; never inspect, emit, hash, stage, or delete session credentials. |
| `.tinyassets.db`: `author_definitions`, `author_forks` | Preserve global daemon identity/lineage. |
| `.tinyassets.db`: `branch_definitions`, `goals`, `gate_claims`, `canonical_bindings`, `unreconciled_writes` | Preserve commons/audit; an unresolved write referencing `H` blocks until reconciled. |
| `.tinyassets.db`: escrow locks/budgets/balances, payout wallets, pending settlements/batches, transaction log, treasury/bounty/royalty/take-rate tables | Preserve all financial rows. Any locked/open/submitted/`in_doubt` obligation involving `P`, `H`, or its work blocks until normal settlement/refund/reconciliation. |
| Root `.runs.db` and sidecars: runs/events/cancels/judgments/lineage/receipts, node-edit audit, branch versions, contribution/gate/outcome/attribution/conformance records, schedules/subscriptions | Preserve the complete audit/history DB. Queued/running work or active schedules/subscriptions for `P`/`H` block until normally cancelled/paused. |
| `H/.runs.db` and sidecars | Preserve by tested canonical relocation, otherwise block. Silent deletion contradicts run-history preservation. |
| Root or `H/.langgraph_runs.db`, `H/checkpoints.db` and sidecars | Resumable/in-flight work blocks. Terminal home-local checkpoints may reset only as reviewed derived state; root/global stores are preserved. |
| Root `.auth.db` and sidecars | Preserve OAuth state. Reset restores home first-contact, not pre-authentication state; never inspect or log secret values. |
| `H/.credential-vault.json`, `H/.credentials/**`, materialized `auth.json` or provider homes | Block. Revoke/remove through credential lifecycle first; reset never stages, journals, copies, or deletes credentials. Host env/auth homes and preferences are always outside scope. |
| `H/.effector_consents.db` | Active consent blocks; revoke normally, then the home-local store may reset. |
| `H/.external_write_receipts.db` | Preserve idempotency/audit by canonical relocation, otherwise block; pending receipts always block. |
| Root or `H/.idempotency.db` | Preserve root. Home-local side-effect receipts require canonical relocation or block until safely expired. |
| Root `.node_eval.db`, `.project_memory.db`, `daemon_brain.db`, and root Lance/vector indexes | Preserve global evaluation/history/memory. Active references to `H` block; no embedded-text/JSON sweep. |
| Root/legacy `knowledge.db`, `story.db`, `checkpoints.db` and SQLite sidecars | Preserve as ambiguous global/legacy state. Any `P`/`H` reference or hot/resumable checkpoint blocks until migrated or closed normally. |
| Root append-only `ledger.json` | Preserve byte-for-byte; an in-flight or unreconciled entry involving `P`/`H` blocks. |
| Legacy root `.node_registry.json` | Preserve. Any live or ambiguous registration targeting `H` blocks until retired or migrated normally. |
| Scoped root `lance/` rows | Reset derived rows only with exact `universe_id=H`/`user_id=P`; missing/legacy/shared scope blocks. |
| `H/lance/`, `H/knowledge.db`, `H/story.db`, home-local memory/index stores | Reset as exclusive home content after writers stop; any foreign/shared row blocks. |
| Ordinary files under `H/` | Reset after quiescence. Pending branch tasks, live heartbeats, active auto-ship, or external-effect evidence block until normal lifecycle/archival completes. |
| `H/auto_ship_attempts.jsonl`, rollback/audit logs, `bid_execution_log.json` | Preserve through canonical archival or block; never silently delete append-only effect evidence. |
| `data_dir/founder_offers/<P>.json` | Block. Disable through the normal market lifecycle; reset never deletes or ignores an enabled offer. |
| Repository bids, bid outputs, settlements, and goal-pool files | Preserve shared repository state; open/claimed work involving `P`/`H` blocks until normal completion/cancellation. |
| Root `wiki/`, `wiki_trigger_attempts.db`, `output/`, `runs/`, release receipt, commons/catalog files | Preserve byte-for-byte; an active writer referencing `H` blocks. |
| Root `.active_universe` | Preserve for authenticated reset. If it names `H`, block until the local/tray lifecycle retargets it. |
| Legacy DB generations, SQLite hot journals/sidecars, and orphan reset staging | Block until migration or recovery completes. |
| Any symlink, junction, Windows reparse point, mount boundary, `.git` worktree, or path outside `data_dir/H` | Block. Planning and cleanup never follow links; source and staging must remain under the approved root on one filesystem. |

An unclassified matching row blocks apply. The home directory and resettable universe-scoped rows are
removed; the founder-home binding and the subject's ACL grants are removed. Other principals' homes,
universes, grants, daemon identities, commons, wiki, `.runs.db`, immutable audit/history, billing and
market records, and all maintainer/provider credentials are preserved. A candidate home containing a
credential artifact or unresolved receipt/consent is blocked rather than deleted. This classification
spans every database and filesystem store that carries the affected keys.

Alternative rejected: broad schema introspection. It silently expands deletion authority whenever a
future migration adds a `universe_id` column.

### 4. Apply is quiesced, plan-bound, and crash-recoverable without a backup product

Apply acquires a durable, process-shared, fenced lease covering the test principal and candidate home
before re-reading and hashing the plan. Every writer touching either key must refuse or wait while the
lease is held. The plan digest binds the roster revision, schema/inventory revision, principal
fingerprint, exact home-binding and grant row versions, resolved source/staging paths, and scope. A
completed plan replay returns its existing receipt and cannot touch a replacement home created later.

A content-free operation journal is durably flushed, including its parent directory metadata, before
mutation. Source and staging paths must resolve within the designated data root and may not be symlinks,
junctions, or reparse points. The home directory is staged by same-filesystem rename. Explicit database
deletes and a commit-witness row are then written in the same SQLite transaction. Recovery runs before
the server accepts traffic or any affected writer resumes: no commit witness means restore the staged
directory and unchanged/rolled-back rows; a witness means finish post-commit cleanup and preserve the
receipt. Fault points immediately before/after rename, immediately before/after commit, and during
cleanup must converge through those two states.

The implementation does not create a long-lived general restore archive or copy full user content under
`.resets`. Recovery material is least-privilege, limited to the in-flight operation, and removed after
commit or rollback. Operator audit records retain metadata and hashes, not user content or credentials.

Alternative rejected: `rmtree` followed by a SQLite transaction plus a best-effort restore command. A
process death between those systems can restore rows while files remain lost.

### 5. Identity evidence lives in the shared status implementation

The auth middleware retains only a request-local bearer-presence bit alongside the already resolved
identity; it never retains the bearer. A dedicated high-entropy deployment secret derives a
non-reversible, stable `principal_fingerprint` using versioned, domain-separated HMAC-SHA-256 (or an
equivalent reviewed PRF) over the subject. Plain hashing and raw-subject fallback are forbidden; the
identity evidence fails closed when its dedicated key is unavailable. The key is separate from
provider, maintainer, OAuth, and roster credentials and is never logged or exposed. The fingerprint
includes a version prefix; rotation intentionally changes the fingerprint under a new version, and the
operator precomputes the new expected value from restricted roster state before the old version retires.
The shared status implementation returns
`request_identity: {bearer_present, principal_fingerprint}` for authenticated, anonymous,
first-contact, and normal read paths. Both `get_status` and `read_graph target=status` use that
implementation so aliases cannot disagree. A present invalid bearer still fails at transport with
`401` and never reaches the tool.

The response is self-only: callers cannot supply or query another subject. It exposes no raw subject,
email, token, grant set, provider credential, ambient maintainer identity, or auth-home path.

Alternative rejected: adding a new identity MCP handle. The existing status read is composable and a
new handle would expand the public tool surface unnecessarily.

### 6. Acceptance inherits requester compute authority; it never borrows maintainer resources

This harness does not define provider routing. It consumes the canonical first-contact/requester
authority decision: model execution is eligible only when the request carries a complete requester-owned
BYOC bundle or an accepted-market compute/model grant. If neither exists, acceptance stops after proving
birth and the principal fingerprint and asserts a structured held/setup-required result with zero
provider invocation.

Platform or maintainer hardware, local Ollama/other local routes, quota, accounts, credentials, auth
homes, Claude/OpenAI limits, and ambient process configuration are never eligible for a user acceptance
run. A test cannot call success merely because birth/identity worked and a maintainer model answered.

Alternative rejected: letting the test borrow an ambient local model because it is credentialless. The
resource owner, not credential presence, determines authority.

## Risks / Trade-offs

- **[Legacy or corrupt ownership is ambiguous]** -> `plan` reports the inconsistency and `apply` fails
  closed; no ACL-based ownership inference is allowed.
- **[A writer races reset]** -> the affected-scope lease precedes plan revalidation and remains held
  through commit/recovery.
- **[Filesystem and SQLite cannot share one transaction]** -> same-volume staging plus a durable
  operation journal defines deterministic pre- and post-commit recovery.
- **[Schema growth silently widens deletion]** -> unclassified matching state blocks apply and a schema
  inventory test fails until the classification is reviewed.
- **[Stable external subjects are privacy-sensitive]** -> raw subjects remain in restricted
  request-local/operator state; the public surface and durable proof use aliases or deployment-scoped
  fingerprints.
- **[Dedicated test accounts accumulate shared state]** -> any foreign binding/grant or ambiguous home
  blocks reset rather than affecting collaborators.
- **[Fingerprint-key rotation changes test evidence]** -> version prefixes and operator-side
  precomputation make the change explicit; there is no raw-subject fallback.
- **[Birth succeeds without authorized compute]** -> acceptance expects structured held/setup-required
  state and proves no provider was invoked rather than consuming maintainer resources.

## Migration Plan

1. Freeze the complete cross-store inventory, fenced-writer protocol, journal/commit-witness state
   machine, and path rules; land executable red tests for ownership ambiguity, schema growth, path
   containment, concurrent writers, every interruption point, idempotence, and mutation widening.
2. Implement the roster, plan/apply journal, explicit deletion graph, and affected-scope barrier without
   exposing a server route; preserve the existing global reset contract.
3. Add request-local bearer-presence evidence and return it from the shared status implementation and
   both public aliases; rebuild the packaged runtime mirror.
4. Provision at least two ordinary external test identities and grants. Run local tests, public canary,
   and rendered chatbot acceptance through supported hosts, recording only fingerprinted identity
   evidence and proving requester/market compute authority or zero provider invocation.
5. Observe post-fix real-user/test-account use. Only then sync the delta specs and archive the change.

Rollback is code rollback plus deterministic completion of any journaled in-flight operation. There is
no migration that marks existing production users as test identities.

## Pre-implementation Gates

No principal/home maintenance lease exists today, so task 1.1 must select and review the smallest
durable fenced barrier. It must verify the inventory above against the current schema and freeze exact
keys, lifecycle states, dependency order, and reset/preserve/block actions before any code capable of
mutation is written. A discovered store is not implicitly resettable; it blocks until reviewed.
