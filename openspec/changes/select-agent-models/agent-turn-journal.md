# Durable HTTP agent progress: storage review boundary

September10,2026. Proposed implementation within tasks2.3/2.4; no runtime table,
dispatch or resume authority is implemented yet. This is the progress journal
required by the existing model-selection design, not a new workflow system.

## Verified seam and purpose

At feature d58c3010, ordinary universe_server.converse reaches served-request
provider assignment and served_provider_budget_reservations. Custom agent roots
and provider_invocation_reservations are a separate execution path; do not invent
a custom invocation to journal an ordinary conversation. The shared store's
connection uses storage.db_path, SQLite WAL and explicit BEGIN IMMEDIATE.

ProviderRequestCapability is live, nonserializable message authority. A transport
request id, saved policy or journal row cannot revive it. Recovered progress must
go through new, genuine owner-authorized execution and fresh assignment/grant
checks. The journal supplies no provider/tool authority, capability, credential,
endpoint, header or arbitrary URL. The existing engine_tool_client owns transport
and fresh route validation; the current admission path owns every inference.

conversation_store is best-effort final text memory, not effect ownership. Do not
put tool intents there. The new journal is the immutable turn-input/round/result
source for HTTP continuation, rather than a second mutable conversation buffer.

## Proposed data shape

Use a private storage/agent_turn_journal.py and immutable domain records, in the
same db_path database through SQLiteProviderWorkAuthorityStore.connection. Schema
creation happens before a caller transaction; each mutating operation requires
an active transaction and never commits implicitly. A thin store wrapper opens
BEGIN IMMEDIATE/commit and exposes these operations for the future executor.
No changes to existing authority event chains or settled-budget schemas.

Three versioned tables, all explicitly owner_user_id/universe_id scoped:

- agent_turns: server-generated opaque turn_id; immutable initial prompt/system
  snapshot preserving exact text; captured policy generation (nullable legacy);
  creation time; monotonic generation; frontier state and current round ordinal.
  This is not a client-selected idempotency key. Owner/universe is trusted caller
  namespace, not proof of authentication. Every read/write requires both values;
  a turn id alone cannot select another owner's data.
- agent_turn_rounds: turn_id plus positive round ordinal; source_ref/model id;
  exact advertised tool-schema snapshot; verified served reservation id plus
  binding generation/digest copied as provenance; request digest; state and exact
  decoded AgentReply snapshot. Usage fields are nullable actual observations.
  Reservation provenance is not authority or evidence of current entitlement.
- agent_turn_tools: turn_id/round ordinal/call ordinal primary identity; exact
  provider call id/name/argument string; state; canonical MCP result JSON and
  fixed outcome diagnosis. Provider call ids are unique within a response batch,
  not a global durable id across rounds. A future codec integration will address
  currently rejected cross-round reused ids using real fixtures; no invention
  or rewriting of returned wire ids in this storage slice.

Root and round/tool foreign keys use owner/universe and their composite parent
identity. No FK to budget rows: normal settled-budget pruning must not erase
tool-effect evidence. The provenance snapshot remains after those rows age out.
No credentials, capability nonces, bearer, route secrets or auth-home paths are
stored. Payloads are private owner data; errors/log/repr never contain them.

All snapshots use strict JSON with duplicate/nonfinite rejection and explicit
schema version; reads validate typed fields and exact duplicated identity/state
columns. Corruption is held, never treated as a missing turn. Use existing codec
records for validated text/tool replies rather than a parallel provider parser.
Stored tool results retain canonical MCP content/structuredContent/isError,
including standard image/audio/resource blocks; exclude transport metadata and
unrecognized envelope extras. A known non-text result must remain preserved
even though the current text codec cannot feed it to a model. Mark that turn
unsupported rather than discarding the result or pretending the effect is unknown.

## Proposed transition contract

One generation-CAS frontier per turn prevents two workers advancing it together.
Every operation carries expected_generation. A mismatch returns a fixed conflict
without mutation. Equivalent finalization is idempotent only for byte-identical
identity/payload; conflicting duplicate results refuse, never overwrite.

1. Create root at generation1, ready for inference, from trusted exact input and
   owner namespace. No provider or tool launch occurs. Actual caller integration
   must create it only after genuine conversation authority is checked.
2. Begin round records the exact candidate/tool inventory and admitted reservation
   provenance, and advances ready -> inference_started before network dispatch.
   Only one active round can exist. Future executor must use fresh admission for
   this one inference; this operation does not reserve, spend or refresh authority.
3. Finish inference preserves one complete validated reply and actual nullable
   usage; atomic whole-batch insertion creates planned tool rows in returned
   order. Completed text advances to completed; tool requests to tools_pending;
   refusal/truncated/filter/unknown to a named held state, never completed.
   An inference transport failure can be recorded separately as held; storage
   does not decide whether capacity permits retry or another model.
4. Before each tools/call, atomically move the next planned row to started and
   commit. Earlier calls must have completed results; no skip or reorder. Only
   the winning CAS can dispatch. Caller must stop if that commit fails.
5. After a real MCP result, store it exactly and move started -> completed.
   isError is a known returned tool result, not permission to replay. When the
   whole batch has completed results, frontier becomes ready for next inference.
   Non-text projection holds with its known result intact.
6. Post-dispatch exception/cancellation/invalid result becomes unknown and holds
   the turn. If the process dies between intent and result, started is already
   ambiguous on recovery: never turn it back to planned, including after a timer.
   A missing durable result after a successful effect is still unsafe to replay.
   Pre-dispatch rejection may record not_sent, but only from explicit transport
   evidence; absence of a result is never that evidence. No implicit retries.

Persisted inference_started, started/unknown tool, or corrupted state cannot
automatically resume. A terminal result record may be recovered only as data,
not as authorization. Pure loading is read-only and never claims work or retries.
The later executor must revalidate owner/home/deletion/assignment/grants before
resuming any planned action, and a stale worker's later result must fail its CAS.
Never reuse a cancelled live capability or refill a spent invocation carrier.

No transparent exactly-once claim across remote effects: commit-before-send
can leave a harmless but indeterminate intent when a process dies before send.
Failing closed there is required; do not add a lease that silently replays it.

## Retention, deletion and rollout

The new tables own private owner data, not published or settlement history.
Retain unresolved progress without automatic pruning. Initial implementation has
no independent cleanup timer or silent payload truncation; completed history
retention can later reuse explicit owner data-retention policy. Account/universe
deletion must remove roots and all rounds/tools, including former-home rows;
add owner-key entries to account_deletion's existing exception map as needed.
Test deletion against real dependency ordering/foreign keys, not just a map.

Additive create-if-absent schema with version validation; no old rows rewritten.
Rollback to the older runtime leaves journal tables inert, not replayable. Do not
activate the HTTP agent or picker in this storage-only commit. Cost-constrained
agent request transport, finite trusted launch plan, per-inference accounting,
cross-model transcript conversion and resumed-owner execution are the next
integration, not something a journal alone proves. No public MCP/API changes.

## Required review and tests

Review exact table/transaction seam and record ownership before code, especially
whether three tables are necessary or a smaller equivalent preserves identity,
generation-CAS, whole-batch insertion and known-result retention without new
authority. Resolve post-dispatch cancellation and recovery states explicitly.
No source of rank, model choice, cost authorization or background-self ownership
changes. Bound runtime by existing resource/authority policy, not a new arbitrary
workflow-size limit hidden in storage.

Prove real SQLite concurrent start/finalize races, rollback-on-fault before send,
duplicate exact/conflicting results, no partial batch insert, scope isolation,
malformed/corrupt records, crash after committed intent, known isError and
unsupported-content result retention, reused wire id in another round, budget
pruning independence and real account deletion. Use synthetic data and actual
Linux as well as Windows. No live workflow, provider or permission edits.
