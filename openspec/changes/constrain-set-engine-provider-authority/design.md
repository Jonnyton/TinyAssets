## Context

`UniverseConfig.allowed_providers` and the router's filtering primitive already
exist. The missing boundary is assignment: `set_engine` writes
`preferred_writer` but leaves `allowed_providers=None`, which means unrestricted
fallback. A user's Anthropic key can therefore select Claude first while still
allowing Codex, API providers, or a local engine afterward.

Draft PR #1606 (`constrain-founder-provider-routing`) contains substantial
offline work for the BYO founder-key case: assignment locking, deny-all
quarantine, runtime ceiling refresh, credential isolation, migration tooling,
and a deployment fence. It is draft, dirty against main, blocked on live
migration, and independently rated ADAPT because unrelated graph paths and
ambient credential inheritance still exceed its proof. PR #1484 overlaps
canonical and packaged `api/universe.py`; PR #1623 and its prerequisite stack
overlap the canonical provider-routing spec. The active provider-auth overlay
also owns runtime and test surfaces touched by #1606. This lane is therefore
the declared narrow successor, but runtime changes do not begin until those
lanes release or partition their ownership.

Provider destination and credential source are separate authorities:

- The destination ceiling answers which provider identities may receive work.
- Credential isolation answers which account, key, OAuth store, home
  directory, or requester-owned resource that provider may use.

This change owns the first boundary. It may reuse independently reviewed pieces
of #1606, but it does not claim the second boundary complete.

## Goals / Non-Goals

**Goals:**

- Make every new engine assignment fail closed at the provider-destination
  boundary.
- Publish one coherent source, preference, credential reference, and ceiling
  under concurrent assignment and routing.
- Keep stale contexts, retry logic, pins, policies, health checks, and role
  fallbacks from widening authority.
- Define held states for engine sources that record intent but do not yet bind
  executable compute.
- Preserve the useful, reviewed R2-1a work from #1606 through the declared
  retained-work split.

**Non-Goals:**

- Proving that a selected CLI cannot inherit host credentials; the
  fail-closed auth-overlay successor owns that proof.
- Activating self-hosted endpoints or host daemons, or routing accepted-market
  work through the ordinary provider router.
- Designing market matching, pricing, settlement, or provider receipts.
- Adding a second router or moving R2-1a into `universe-creation`.
- Keeping a runtime compatibility shim for unrestricted assignments.
- Proving call-local credential kind/authority evidence; provider receipts owns
  that evidence after the credential and destination boundaries land.

## Decisions

### 1. Treat `allowed_providers` as a replacement-only authority ceiling

The state meanings are exact:

| Value | Meaning |
|---|---|
| `None` | pre-cutover legacy encoding only; invalid after migration |
| `[]` | explicit deny-all for unassigned, held, pending, or failed state |
| non-empty list | the only canonical provider identities eligible to run |

Assignment always replaces the prior ceiling; it never unions old and new
providers. Preference, policy, pin, registration, health, quota, and retry may
only reorder or narrow this set.

Every new universe begins with `engine_assignment_state="unassigned"` and
`allowed_providers=[]`. Assignment state is one of `unassigned`, `pending`,
`ready`, `held`, or `failed`. `ready` requires a non-empty canonical ceiling;
all other states require `[]`. `None` is accepted only by the offline cutover
reader and never by the post-cutover runtime.

Alternative considered: treat `preferred_writer` as authority. Rejected because
its canonical behavior intentionally preserves fallback.

### 2. Use a strict service-to-route resolver for BYO assignments

The public BYO service values are exactly:

| Input service | Vault service | Provider ceiling | Preferred writer |
|---|---|---|---|
| `anthropic` | `anthropic` | `["claude-code"]` | `claude-code` |
| `openai` | `openai` | `["codex"]` | `codex` |

An omitted writer is derived. An explicit writer must match the row exactly.
Aliases, unknown services, unknown writers, and mismatches fail before any
mutation. The resolver is separate from the environment-variable lookup map;
the latter contains services for which per-universe executable routing is not
implemented.

Alternative considered: accept `claude`, `claude-code`, and `codex` as service
aliases. Rejected because the project replaces ambiguous boundary shapes
instead of maintaining compatibility aliases.

### 3. Hold non-executable source assignments at deny-all

`self_hosted_endpoint`, `market_rented`, and `host_daemon` currently persist
intent but do not bind an executable provider grant. Each assignment therefore
publishes `allowed_providers=[]`. Endpoint, market, daemon, provider, or writer
fields remain non-authorizing hints.

A later source-specific activation operation may validate a self-hosted
endpoint or daemon binding and replace `[]` with its reviewed provider set. It
must not reinterpret the hint as authority implicitly. `market_rented` is
different: accepted-market execution remains `[]` in the ordinary provider
router and runs only through the paid-market/distributed-execution owner's
signed remote-executor path.

Alternative considered: allowlist the supplied provider immediately. Rejected
because registration or preference is not proof that compute was bound or
authorized.

### 4. Make assignment a durable quarantined transaction

One per-universe cross-process writer lock spans:

1. Validate all public input without mutation.
2. Create a durable, secret-free transaction journal and publish
   `engine_assignment_state="pending"` with `allowed_providers=[]`.
3. Update source state and, for BYO, only the targeted universe vault record,
   preserving unrelated bytes and records.
4. Write a `commit_ready` journal record containing only transaction identity
   and non-secret state digests.
5. Publish the complete final config atomically as `ready` plus a singleton
   ceiling, or `held` plus `[]`, including the matching transaction identity.
   This atomic replacement is the assignment commit/linearization point.
6. Remove the matching journal durably as post-commit cleanup.

Any failure after quarantine publishes or recovers
`engine_assignment_state="failed"` with `allowed_providers=[]`; it never
restores `None` or a prior wider set. The journal records only identifiers,
stage, and secret-free failure class. A later assignment or recovery resumes
or replaces the failed transaction under the same lock and must not trust
partial source/vault state without journal validation. Admission accepts a
ready/held config with a leftover journal only when transaction identity and
non-secret digests match a `commit_ready` record; any other active or
uncommitted journal fails held. A crash after final-config publication is thus
safe cleanup, while a crash before publication cannot execute. Two assignments
serialize, and every ready final vault plus config describes one complete
assignment.

The implementation should extract or cherry-pick the smallest independently
reviewed lock and transaction pieces from #1606 after reconciling them against
current main. It must not copy the draft wholesale.

Alternative considered: config-only atomic write. Rejected because config and
vault are separate resources and can otherwise describe different assignments.

### 5. Intersect fresh assignment and immutable request authority

Every universe-originated call carries a typed provider-destination call scope
whose universe variant contains the already-authorized universe directory and
a reference/view derived from the accepted immutable request authority contract.
If PR #1617's `RequestExecutionAuthority` is retained after the #1660 review,
this change MUST consume it rather than define a second request-eligibility
type. Persisted `allowed_providers` remains separate. Effective provider
authority is:

`fresh assignment ceiling INTERSECT request_allowed_providers INTERSECT narrower policy`

Neither set may replace or widen the other. An omitted universe authority scope
fails closed. Only an enumerated non-request-reachable host operation may
supply a
`HostLocalProviderCapability`: a process-internal, non-serializable,
identity-validated token minted only by trusted daemon bootstrap after local
operator configuration. It is mutually exclusive with universe authority and
MUST NOT appear in MCP/API schemas, JSON, environment-derived request fields,
node state, universe config, any user-controlled constructor, or any
user/request/universe lineage. A boolean, string, enum value, caller-created
lookalike, or genuine token substituted for universe work is invalid. Approved
host-local operations are inventoried and negative-tested.

This change does not define, construct, resolve, persist, or widen requester
authority, an execution grant, a market agreement, delegation, credential-vault
truth, or a receipt. Its provider layer consumes only the immutable
already-resolved eligible-provider view/reference. It cannot rediscover grants,
credentials, offers, budgets, or ambient host resources. Omitted scope is never
host-local: `None`, booleans, enums, strings, caller-created lookalikes,
ambient `TINYASSETS_UNIVERSE`, or a legacy global fallback authorize nothing.
The landed #1692 `OperatorRequestAdmissionVerdict`, its priority grant, and its
queued v1 `BranchTask` are admission and ordering artifacts only. Neither
those landed artifacts nor any current or future admission receipt or
scheduling claim can populate the typed request eligible-provider set or
authorize provider access, credentials, compute, market purchase, execution
lease, settlement, or spending.

The accepted #1660 opposite-provider verdict must first settle requester
authority semantics in the current `universe-creation` owner and disposition
PR #1617. Only then may a declared subordinate
`provider-authority-propagation` prerequisite own the provider-layer transport
gap: the universe-versus-host-local carrier union, host-token boundary, and
exhaustive non-enforcing threading. It MUST reference the accepted requester
authority, MUST NOT resolve requester/market authority itself, and MUST NOT
create a second router, receipt, vault, market, or credential-isolation
contract. The inventory includes graph run/resume/version/policy/judge plus
RAPTOR, reflexion, agentic retrieval, and every other `call_provider` use.

Immediately before each attempt, routing acquires a shared, nonblocking
per-universe reader admission, validates fresh assignment and journal state,
computes the intersection, and asks the landed auth-overlay boundary to resolve
an immutable `ResolvedProviderAuthority` containing the admitted provider,
exact credential/auth provenance and material reference. The router then mints
an immutable, non-serializable
`ProviderInvocation` containing prompt/system/model inputs, universe identity,
the resolved authority, and an identity-validated router launch token. Secret
material is never journaled or logged.

The one-phase `BaseProvider.complete(...)` interface is replaced, without a
compatibility shim, by:

1. `await BaseProvider.start(invocation) -> ProviderLaunchHandle`, called while
   the shared reader is held; and
2. `await ProviderLaunchHandle.result() -> ProviderResponse`, called after the
   reader is released.

`start()` returns only after the authority handoff is irreversible:

- CLI/local subprocess providers have spawned the child with fully materialized
  env, stdin, cwd, and endpoint inputs.
- HTTP/in-process providers have copied fully materialized endpoint, headers,
  body, and client inputs into a transport-owned scheduled request.

Launch uses a monotonic `launch_timeout_seconds` separate from model completion
timeout: default 5 seconds, configurable from 1 through 30 seconds. `start()` is
cancellation-safe. Before creating any child/request it installs a cleanup
guard and fsyncs a secret-free `provider_launch_pending` record with a unique
launch id. The child process group or transport idempotency key carries that
id. Successful start plus handle registration atomically advances the record
to `provider_launch_active`; terminal transport outcome is recorded durably
before removal. Deadline, exception, or caller cancellation aborts the request
or kills/reaps the process. The cleanup guard proves terminal cleanup before
the reader unlocks. When cleanup succeeds, a waiting assignment writer may
proceed. If terminal cleanup cannot be proven within the same bounded cleanup
deadline, routing releases the reader only after installing a durable
per-universe `provider_launch_cleanup_failed` fence; subsequent routing and
assignment fail loud until operator recovery, rather than mutating authority
around a possibly live launch.

After `start()` returns, neither provider nor handle may read provider authority
from universe files, vault, process env, auth homes, or config.
Direct/bypass invocation without the router-minted launch token fails
held. The router registers every returned handle before unlock and owns it in a
structured `try/finally`; un-awaited handles are not exposed to callers.
`result()` and `close()` share one atomic terminal state machine. Exactly one
transition owns transport completion or reaping across success, ordinary
provider error, model timeout, caller cancellation, explicit close, and
concurrent `result()`/`close()` calls; all other callers await and receive the
cached terminal outcome. The reader is held through authority resolution and
`start()`, then released; network completion may continue through the handle.
Shared readers coexist. An attempt launched before a writer publishes
`pending` may finish with its captured authority, while attempts reaching
admission during or after quarantine fail held with zero provider access. The
exclusive assignment writer waits for authority materialization and launch,
not for network completion, and ordinary async execution never blocks on
filesystem locks.

Startup and assignment reconcile every leftover pending/active launch before
routing or authority mutation. They locate and abort/reap a tagged child,
query transport idempotency evidence where available, and finalize the durable
transport outcome once. If terminal state cannot be proven, the cleanup-failed
fence remains and routing plus assignment fail loud. Crash injection covers
pre-creation, post-creation before registration, post-registration before
unlock, and post-completion before finalization.

The rule covers ordinary role chains, policy attempts and fallback, judge
ensembles, sync wrappers, hard pins, and every retry. A stale context may not
widen a newer ceiling. Missing, unreadable, invalid, or lock-contended
authority state fails held before credential, auth-health, quota, or provider
access.

Alternative considered: refresh once at the start of a router call or overwrite
the assignment ceiling with request eligibility. Rejected because assignment
may begin between retries, and either authority set alone can be wider than the
other.

### 6. Keep role behavior honest under a singleton ceiling

`["claude-code"]` produces no judge, extract, or embed candidate where Claude is
absent from those role chains. `["codex"]` permits Codex only where that role
chain contains it. An empty authority intersection raises a typed
`ProviderAuthorityHeldError` for single-role, policy, and ensemble calls; the
provider bridge MUST NOT convert it into fallback prose. The ordinary
judge-ensemble `[]` result remains reserved for a non-empty authority set with
no healthy registered judge. No role invokes or reports a provider outside the
intersection.

Successful BYO `set_engine` returns `status="engine_set"` and
`assignment_state="ready"`. Valid non-executable source intent returns
`status="setup_required"` and `assignment_state="held"`. A post-quarantine
failure returns a secret-free `status="assignment_failed"` with
`assignment_state="failed"`; validation failures retain the prior state
byte-for-byte.

### 7. Split #1606 into this declared successor

#1606 will not merge wholesale. This successor selectively retains its reviewed
assignment lock, transaction, inventory, migration, and deployment-fence work
after current-main reconciliation. Generic ambient-auth stripping belongs to
the provider-auth overlay. The request-bundle intersection wording is retained
here and folded back to `universe-creation`; its duplicate R2-1a implementation
is removed there. #1606 closes without merge only after the retained commits
and remaining credential, graph-authority, and universe-creation owners are
recorded durably.

## Risks / Trade-offs

- **[Held sources appear less functional]** -> Return explicit
  `setup_required`/held state and implement source-specific activation rather
  than silently borrowing platform compute.
- **[Existing unrestricted assignments remain dangerous]** -> Use a reviewed,
  platform-wide deny-all cutover derived from #1606 before new writers are
  exposed.
- **[Fresh reads add latency]** -> Read only the small non-secret ceiling under
  a nonblocking snapshot/reader mechanism; verify under the §14 concurrency
  load gate.
- **[A singleton ceiling is mistaken for credential isolation]** -> Keep claims,
  tests, receipts, and user copy explicitly scoped to provider destination
  until the auth-overlay lane proves credential provenance.
- **[PR #1606 contains valuable but over-coupled work]** -> Preserve reviewed
  commits selectively and independently re-review the reconciled diff.
- **[Market intent is mistaken for provider authority]** -> Keep
  `market_rented` at `allowed_providers=[]`; accepted-market work uses only the
  paid-market/distributed-execution signed remote-executor path and never the
  ordinary provider router.
- **[Old contexts or malformed config bypass authority]** -> Revalidate at each
  attempt and fail closed before auth, quota, health, or provider access.
- **[Assignment changes between admission and auth resolution]** -> Hold the
  shared reader through immutable auth capture and provider launch; allow
  only network completion outside the lock.
- **[Host-local bypass becomes forgeable or a confused deputy]** -> Use only
  the identity-validated, non-serializable bootstrap token bound to enumerated
  non-request-reachable operations; inventory callers and prove every public
  representation and every universe/user/request use is rejected.

## Migration Plan

1. Record the #1606 retained-work split: exact assignment, migration, and
   deployment-fence commits move to this successor; auth stripping, graph
   propagation, and other owners are named; duplicate universe-creation edits
   are removed; #1606 is marked to close without merge after preservation.
2. Rebase after #1484 releases canonical and packaged `api/universe.py`; after
   #1623's prerequisite stack lands or #1623 is rebased/retargeted and releases
   the canonical provider-routing spec; and after the provider-auth overlay
   lands or partitions exact ownership.
3. Obtain the required opposite-provider verdict on #1660, fold accepted
   requester-authority semantics into the current `universe-creation` owner,
   and explicitly disposition #1617. Then land a subordinate
   `provider-authority-propagation` prerequisite that references the accepted
   requester authority and owns only the typed universe/host-local carrier,
   identity-validated bootstrap token, and exhaustive non-enforcing threading.
   It must inventory graph/run/resume/version/policy/judge, RAPTOR, reflexion,
   agentic retrieval, and all remaining `call_provider` uses.
4. Implement new-universe, assignment lifecycle, shared-reader/exclusive-writer
   semantics, and deterministic fake-only tests.
5. Adapt #1606's secret-free inventory into a reviewed platform-wide decision
   manifest. Unassigned universes become `unassigned + []`; proven canonical
   or unambiguous legacy-alias Anthropic/OpenAI assignments become matching
   `ready` singletons; non-executable intent becomes `held + []`; ambiguous,
   incomplete, or partially failed assignments become `failed + []`;
   unreadable records stop the migration.
6. Quiesce legacy writers, apply the conversion with the new immutable image,
   prove zero post-cutover `None` values, zero unclassified universes,
   idempotence, and journal recovery, then run a daemon-only loopback canary.
7. Roll forward only. Do not automatically restart a pre-ceiling writer or
   restore `None` after the fence.
8. Run strict OpenSpec validation, focused suites, mirror parity, §14
   concurrency/load proof, rendered chatbot acceptance, and post-fix
   real-user observation before declaring the public surface proven.

## Open Questions

- Which exact #1606 commits survive independent review after current-main
  reconciliation? The ownership decision is settled; the hashes remain to be
  selected.
- Will source-specific activation extend `set_engine` or use separate endpoint
  and daemon binding primitives? The authority transition must be explicit
  either way. Accepted-market execution is excluded and remains on its signed
  remote-executor path.
