# Canonical consumer turn contract — decision draft

2026-09-19. Incorporates lead disposition of Fable 29752; proposal only. No
implementation authorized. Existing canonical handles, runs database, private
conversation database, graph executor and provider admission remain the owners.

**Lead approval:** 2026-09-19, exact proposal `493bd98c` approved for bounded
implementation. Required deletion/retention fences apply to terminal freeze and
projection; no reconstruction of erased homes/history. Independent storage work
may proceed while the shared prepared-start primitive is built. Push/PR still
requires exact-head independent review. This approval supersedes the proposal-only
status above for the specified implementation, not wider harness/setup scope.

Primitive check: `check_primitive_exists.py action conversation_turn` plus direct
`rg` over canonical server/API show no existing target with this contract. The
helper is diagnostic only; existing turn/run/provider primitives are reused as
mapped in `turn-seam-evidence.md`, not inferred absent from the verb search.

## 1. External request and status

Add optional `consumer_request` to `converse`, an exact versioned object:

```json
{
  "version": 1,
  "request_key": "client-generated UUIDv4",
  "binding_id": "receiver installation ID",
  "binding_revision": 3
}
```

The existing `message`, `graph_id`, `input_method`, `model_choice` remain the
caller intent. Owner/session/home are server-derived, never payload authority.
The trusted app creates a fresh random key only on an explicit new Send and
retains the complete original request locally until resolved. Transport loss
reuses the exact original object, never a new key or a rewritten message.
Connector callers can use the same object; no new top-level MCP tool exists.

Authenticate/current-home-check first, then lookup the key in that exact scope,
BEFORE resolving today's installation/history/model defaults. A matching admitted
request observes its original run; changed caller intent returns
`consumer_request_conflict` without execution. Changed binding selection after
admission cannot retarget that request. On FIRST admission, the declared binding
ID/revision must match the unique eligible current installation or return
`consumer_selection_conflict` before effects.

With an active custom handler, omitting this object returns
`consumer_request_required` and the current installation ID/revision, without
calling either writer. With no selected handler, a request without the object
keeps the legacy default path unchanged. Supplying the object when no handler is
selected returns `consumer_not_selected` unless an earlier admission matches.
Never silently downgrade a keyed custom request into an untracked default turn.

Add owner-scoped `read_graph target="conversation_turn"`, taking existing
`graph_id` plus new `request_key` (same UUID format). It returns only the current
owner/session's admission, uniform `not_found` for absent/unreachable rows, and
never starts work. Ordinary `read_graph` run reads and existing run cancellation
still work by the returned `run_id`. Keep `converse`'s MCP idempotent hint false:
the legacy unkeyed path remains non-idempotent.

Keyed converse/replay and status share this envelope:

```json
{
  "universe_id": "receiver universe",
  "consumer_turn": {
    "version": 1,
    "turn_id": "server admission ID",
    "run_id": "the single reserved run",
    "state": "pending",
    "run_status": "queued",
    "projection": "pending"
  }
}
```

`state` is pending/completed/failed/cancelled/interrupted/held/expired.
`projection` is pending/committed/held/expired. Pending or held contains no
fabricated `reply`. Successful terminal + committed projection adds existing
`reply` and actual execution attribution; failed terminal uses the existing
platform failure form, not a fake agent reply. Held explains the exact missing
progress/persistence prerequisite; work may already have occurred. The app keys
visible terminal messages by `turn_id`, never by each poll response. Status is a
logical observation which may idempotently repair terminal history projection,
as may terminal callback or exact keyed converse replay; none may re-execute.
This lead-approved correction (September 19 origin review) makes lost callbacks
recoverable by ordinary polling, without requiring a user resend.

## 2. Stable identity, captured server context

Strictly validate the request object. Store SHA-256 of canonical UUIDv4 bytes,
not a raw key; random 122-bit key entropy plus owner-scoped lookup avoids a new
HMAC secret/configuration dependency. Unique scope is `(owner_user_id,
universe_id, session_id, request_key_hash)`; collision/conflict fails, not rekeys.
The versioned intent digest covers exact message bytes, effective input-method
enum, resolved target universe, explicit model-choice document with omitted
versus explicit automatic distinguished, and declared installation ID/revision.
Canonicalize JSON structurally; never normalize/rewrite message text.

Current history, saved preferences, discovery and policy generations are NOT
recomputed into replay comparison. Capture bounded existing permitted history
and validated effective preference DATA once at new admission, with provenance/
generation and schema version. A same-key resend after another conversation turn
or a default change still observes its original admission. Explicitly changed
message/model choice conflicts. Fresh current authority may refuse future run
effects; it never changes the historical request or grants stale access.

## 3. Minimal runs-database aggregate

One new private table `conversation_run_admissions`, version 1:

| Column | Meaning |
|---|---|
| `admission_id` primary key | random canonical turn ID, never execution authority |
| `owner_user_id`, `universe_id`, `session_id` | trusted scope |
| `request_key_hash`, `intent_digest` | unique scoped key and stable caller-intent binding |
| `intent_json` | strict versioned original message/input/explicit choice/install intent |
| `context_json` | captured permitted history plus effective preference data/generation |
| `selection_json` | binding ID/revision, definition fingerprint/component/adapter, branch version ID/content hash, declared input/output mapping |
| `run_id` unique | same existing runs row; logical/SQLite foreign-key invariant |
| `terminal_json` nullable | immutable normalized terminal reply/failure + output digest/actual model evidence, frozen once from this run |
| `projection_state` | pending/committed/held/expired |
| `conversation_turn_no` nullable | committed founder row number; reply is the paired following row |
| `created_at`, `updated_at` | factual lifecycle timestamps |

JSON columns have exact typed schemas/version and existing message/history bounds,
not an arbitrary authority bag. Do not place credentials/carriers in any column.
Initialize additive schemas before transaction. One `BEGIN IMMEDIATE` performs
scoped replay/conflict lookup, selection pin comparison, reservation insert and
`runs._insert_run_in_transaction` for that SAME random run ID. No provider/network
work or second database calls while holding it. Prepared context is captured only
by the transaction's winning new admission; a racing loser observes the winner.

After commit, the existing executor gets the already-reserved ID through the
common run-owned prepared-start/dispatch guard owned by the file-delivery lane.
Do not call `_execute_branch_core`'s current `_prepare_run` and create a second
row. Canonical admission has NO independent launch claim, queue state or worker
lease. The common run guard alone decides submission/recovery; its failure is
reported from that run. A reconnect never resets it or grants another start.
An unstarted/orphan run follows the common primitive's proven recovery contract,
not a consumer-specific restart loop. A new explicit user send gets a new key/run.

Reuse the file lane's run-input admission/manifest/dispatch guard and cloud lane's
family root/epoch against this run. Canonical admission neither substitutes either record
nor invents its own provider/resource authority. Coordinate schema ownership
before runtime edits. Comparison `run_lineage` remains comparison history.

## 4. Mandatory two-database terminal projection

Runs remain execution truth. Freeze `terminal_json` once when the exact run is
terminal; validate declared output type and attach truthful producer evidence.
Missing/ambiguous output fails visibly instead of invoking a fallback writer.
History projection is an idempotent projection, not execution or a new model call.

Add `conversation_terminal_projections` to the EXISTING per-universe conversation
database: `(admission_id PRIMARY KEY, session_id, terminal_digest,
founder_turn_no, reply_turn_no, committed_at)`. One local transaction checks this
row, inserts both conversation rows and the projection row, then commits. A
matching existing row returns its original numbers; differing session/digest is
held corruption, never a second append. No best-effort-success return here.
Only after that commit does runs admission CAS to projection committed with the
same terminal digest and first row number.

Crash obligations:

- Before runs reservation commit: no run/admission and no effects.
- After reservation/launch uncertainty: same run held/interrupted, never replayed.
- After terminal freeze but before pair commit: project from frozen terminal.
- After pair commit but before runs projection flag: dedupe returns original pair
  and repairs flag; no duplicate history, provider call or external effect.
- After reply transport loss: return same committed terminal/turn ID.

Repair is bounded per admission on terminal callback, authenticated exact keyed
replay or owner-authorized status observation. Status can converge the existing
terminal projection but cannot dispatch work or authorize effects. Do not
create a fleet, independent queue or cross-user background capability to repair.
Default unkeyed conversation writes retain their existing behavior.

## 5. Current source authorization and executable scope

Use `branch_versions.branch_version_def_id` metadata-only lookup before snapshot
load, then `api.branches.resolve_branch_id_for_read` under the authenticated
receiver and require exact ID equality; missing/private-unreadable is uniformly
unavailable. Verify current home/admin and installation principal separately.
Only then load the version, require active status and exact content hash/branch
ID, and validate self-contained executable closure. Repeat current source checks
at execution admission; if authorization cannot be stabilized across prepare/
reserve, hold rather than execute a stale unchecked snapshot. New helper may
factor these existing rules, never call bare version execution as authorization.

Keep current `runs._caller_provenance` and compiler restrictions. Foreign public
code already refuses and can be receiver-remixed using ordinary lineage-preserving
operations; public prompt-only content is not blanket-banned just for authorship.
No creator permissions are inherited. Reject nested invoke variants and unresolved
executable references for v1; unknown portable components remain inert. Preserve
engine `agent_binding` mutation refusal, and do not treat founder principal alone
as a human install event. No operator-built private test fixture/design is needed.

## 6. Preference bridge and execution receipt

Captured preference data gives current-turn order first, then the receiver's
saved/default behavior resolved at admission; current connection/model eligibility
and spend/refusal checks still run for every invocation. Node policy may narrow
compatible candidates but cannot replace explicit receiver selection. No declared
node fallback chain means no additional graph restriction; a nonempty explicit
chain intersects the user's order without adding candidates. Contradictory explicit
primary requirements refuse; do not silently choose another primary. Recompute
bounded invocation allowances from the effective chain with existing retry limits.

Pass only validated preference data and its admission reference into run admission,
never a served capability/agent_model_plan. Actual producing node's receipt drives
single-model attribution. For combined/derived multi-provider outputs, use honest
multi-contributor evidence or unknown, not the first provider response. Final
wire details reuse the existing execution receipt where truthful; do not loosen
its strict schema to smuggle run correlation, which has its own `consumer_turn`.

## 7. Migration, privacy, rollback and scope

Add tables/indexes idempotently, no historical inference/backfill. Existing runs,
conversation rows and bindings stay valid. No active custom handler until the
serving build advertises this adapter/schema version and required tables exist;
missing schema holds before effects. Legacy clients can still use default chat;
selected custom-handler turns require the explicit request object above.

Keep admission and projection dedupe tombstones until universe/account deletion.
Ordinary history trimming must not delete projection identity and reappend old
history on replay. If existing retention expires detailed terminal/context data,
keep only scoped key/digest/run correlation identity (not detailed selection or
install mapping), and return expired without execution
or history reconstruction. New tables participate in existing owner deletion;
never recreate them for a deleted or replaced home. No public history exposure.

Rollback first disables custom selection through trusted controls for future
turns and retains admission readers/dedupe for in-flight/history observations.
Feature-off holds selected handlers rather than silently running the default.
Do not downgrade to a binary unaware of active selections/admissions; forward
compatibility or verified removal of active selections is a release prerequisite.

This slice does not complete nested harnesses, arbitrary UI/foreign loaders,
whole-setup migration, or two-owner live adoption. Strict proposal validity is
not runtime proof. Root must approve this exact API/storage contract before build.
