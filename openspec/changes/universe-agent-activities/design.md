## Context

Behaviour is already specified by the harness requirement *An agent works on
several activities at once, without a connected client, and recovers them after
a restart*, and by *The agent's activities and schedules are read completely*
(change `universe-agent-harness`). This design covers only what that leaves
open:
- where the records live;
- how an activity runs with no request;
- how an effect is recorded before it fires;
- how a schedule names an activity.

Facts from origin/main, 2026-10-01:

| Fact | Where |
|---|---|
| A served turn needs the request's verified identity and provider carrier | `universe_intelligence.converse` (`provider_request_capability`) |
| The only client-less agent turn is an agent node inside a branch run, bound to the owner by `owner_run_identity` | `shared_self.prepare_shared_self_turn`, `workflow_agent.call_background_work_agent` |
| Automations bind the owner's foreground session from the row, so they get foreground admission and budget | `automations._bind_automation_provider_call`; spec `user-owned-automations` |
| Session records are keyed by any string; only the adapter name is validated | `agent_sessions._record_path`, `load` |
| Seat ceilings depend on class, never kind; a dead holder's seat is reaped on the next acquire | `universe_seats` (`KIND_*`, `_reap`) |
| A served turn caught by a deploy is settled, never operation=stop|pause|resumed | `agent_turn_reconcile.reconcile_orphaned_turns` |
| The tool journal (planned, started, finished) exists for journaled turns | `storage/agent_turn_journal.py` |
| `authenticated_external_call` reserves nothing before a send. The existing reserve-before-send store lives in the universe folder | `storage/external_write_receipts.py` |
| `automations.branch_def_id` is `NOT NULL`; migrations add columns | `automations._AUTOMATIONS_TABLE`, `_MIGRATIONS` |

## Goals / Non-Goals

**Goals**
- A durable record per activity that survives a deploy and that no agent can
  forge.
- Resume after a restart from the last completed tool call, never sending an
  effect twice.
- A seat while running, none while waiting, and never a refusal for being over
  the seat count.
- A schedule can start an activity under the full user-owned automation contract.
- Complete, cursor-paged reads.

**Non-Goals**
- The full execution context: delegated authority and the research flag (D8,
  D3).
- Browser contexts (D5).
- The `ta` command (D6). It wraps the contract here.
- Cross-agent activities and their lesser-of-two authority (D8).

## Decisions

### 1. Records live outside the universe, beside `rules.db`

The store is `<data root>/.agent-sessions/<universe>/agent-activities.db`. This
is the same directory as the S1 session records, S2 `steering.db`, S4
`activity.db` (the tool journal) and D1 `rules.db`.
- **Why not the universe folder:** a workflow provider jail binds the universe
  read-write. An agent that can write its own `in_progress` or `confirmed` rows
  could forge a receipt or unlock a retry.
- **Name:** "activity" was taken by S4's tool journal, so the store is
  `agent-activities.db`. A shared name would be two definitions of one fact.
- **Lifecycle:** it is declared in `storage_accounting.ROOT_ENTRIES` and counted
  against the owning universe. Account deletion removes the whole
  `.agent-sessions/<home>`, which S2 (#4188) adds.

Schema (SQLite, WAL, `busy_timeout` 10 s, `BEGIN IMMEDIATE` for every transition):

```sql
CREATE TABLE activities (
  activity_id        TEXT PRIMARY KEY,          -- 'act_' + 16 hex, platform-minted
  agent_id           TEXT NOT NULL DEFAULT 'main',
  parent_activity_id TEXT NOT NULL DEFAULT '',
  session_key        TEXT NOT NULL UNIQUE,       -- 'activity:<activity_id>'
  owner_principal    TEXT NOT NULL,              -- authenticated at creation
  title              TEXT NOT NULL,              -- <= 200 chars
  brief              TEXT NOT NULL,              -- the task text, <= 16 KiB
  origin_kind        TEXT NOT NULL CHECK (origin_kind IN ('ask','proposal','schedule')),
  origin_ref         TEXT NOT NULL DEFAULT '',   -- turn id, proposal id or automation id
  approval_id        TEXT NOT NULL DEFAULT '',   -- D3: the pre-approved action, if any
  status             TEXT NOT NULL CHECK (status IN
                       ('scheduled','in_progress','waiting_on_you','operation=stop|pause|resumed','completed','failed')),
  outcome            TEXT NOT NULL DEFAULT '',   -- done | stopped | failed:<class>
  waiting_reason     TEXT NOT NULL DEFAULT '',
  result_summary     TEXT NOT NULL DEFAULT '',   -- <= 4,000 chars; full result is a workspace file
  result_path        TEXT NOT NULL DEFAULT '',
  last_tool_seq      INTEGER NOT NULL DEFAULT 0, -- last COMPLETED tool call
  lease_holder       TEXT NOT NULL DEFAULT '',   -- process_liveness owner token
  lease_expires_at   REAL NOT NULL DEFAULT 0,
  revision           INTEGER NOT NULL DEFAULT 1, -- compare-and-set for owner edits
  created_at         REAL NOT NULL,
  updated_at         REAL NOT NULL,
  finished_at        REAL NOT NULL DEFAULT 0
);
CREATE INDEX activities_by_update ON activities(updated_at DESC, activity_id DESC);

CREATE TABLE activity_effects (
  activity_id     TEXT NOT NULL,
  effect_seq      INTEGER NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,  -- sha256(activity_id, tool_call_id, action_digest)
  action_digest   TEXT NOT NULL,         -- agent_review.action_digest of the structured action
  connection_id   TEXT NOT NULL,
  operation       TEXT NOT NULL,
  path            TEXT NOT NULL,
  state           TEXT NOT NULL CHECK (state IN
                    ('planned','sent','confirmed','failed','unknown','owner_resolved')),
  receipt_json    TEXT NOT NULL DEFAULT '',  -- status code + safe summary, never a body or credential
  created_at      REAL NOT NULL,
  updated_at      REAL NOT NULL,
  PRIMARY KEY (activity_id, effect_seq)
);

CREATE TABLE activity_events (
  activity_id TEXT NOT NULL,
  seq         INTEGER NOT NULL,
  ts          REAL NOT NULL,
  kind        TEXT NOT NULL,   -- started | waiting_for_seat | waiting_on_you | operation=stop|pause|resumed | operation=stop|pause|resumed | completed | failed | stopped
  line        TEXT NOT NULL,   -- platform-computed, <= 300 chars
  delivered   INTEGER NOT NULL DEFAULT 0,  -- reached the main session
  PRIMARY KEY (activity_id, seq)
);
```

Event lines are composed by the platform from the record. They never contain
model text, so they cannot carry an injection into the main session.

### 2. Session keys and parentage

- **Activity:** `activity:<activity_id>`.
- **Further roster agent (D8):** `agent:<agent_id>:thread`.
- **Main agent:** keeps `thread:principal:<owner>`.
- `agent_sessions` hashes any key, so no change is needed there. Parentage is
  the record's `agent_id` and `parent_activity_id`, not part of the key.

### 3. Running with no request: the activity runner

`agent_activities.run(universe_dir, activity_id)` runs one activity to a resting
state: completed, failed, waiting_on_you or operation=stop|pause|resumed. Its inputs:
- **Identity.** It uses the record's `owner_principal`, proven again at every
  run start. This is the same founder-ownership check `shared_self` performs, and
  the same `owner_run_identity` binding. If the owner no longer owns the
  universe, the activity fails with `owner_lost`. Who could create the record:
  - an authenticated served turn, whose verified actor is the owner;
  - the owner door;
  - an automation whose row names the owner.
- **Compute.** It uses the owner's own provider, bound exactly as automations
  bind it (`_bind_automation_provider_call`): foreground admission and budget,
  never a platform model. With no compute connected, the activity waits on the
  owner with that reason. It does not fail.
- **Session.** The prompt is the persona plus a short activity preamble (title,
  brief, origin). Turns run on `activity:<id>` through the same adapter path as
  a served turn, so S1 operation=stop|pause|resume, S2 steering and S4 tool lines all apply by key.
- **Seat.** It takes one `KIND_ACTIVITY` seat (background class, new kind) with
  `acquire_blocking(wait_s=None)`. While it waits, it writes a
  `waiting_for_seat` event; it is never refused. The seat is released when the
  activity rests.
- **Stop and operation=stop|pause|resume.** The activity is registered with `turn_interrupt`, keyed by
  its session key, so stop and operation=stop|pause|resume take effect at the next tool boundary.
  Stop sets `outcome='stopped'` and keeps `result_summary`.

Runners execute on the serving process's background executor. One runner per
activity is guaranteed by the lease: `lease_holder` with a 120 s expiry,
refreshed on the seat refresh tick, taken by compare-and-set.

### 4. Waiting releases the seat

When a rule asks first, or the auto-review asks for approval inside an
activity, the activity does three things:
- it raises the request with the activity id attached;
- it sets `waiting_on_you`;
- it ends its turn, releasing the seat.

The owner's answer re-queues the activity. A new runner then takes a seat
through the same blocking acquire. The answer reaches the session as a
platform line, and the approval id rides into the context (D2/D3).

### 5. Effects are recorded before they fire

While an activity runner is bound (a contextvar, like the D1d review binding),
`authenticated_external_call` does the following around the wire:
1. Inserts `planned` with the idempotency key. The UNIQUE constraint makes a
   second attempt of the same tool call a conflict, not a send.
2. Moves to `sent` immediately before the wire.
3. Moves to `confirmed` or `failed` with a safe receipt immediately after.

**After a restart,** every `sent` row is set to `unknown`. Every `planned` row
was never sent and becomes `failed:not_sent`. The operation=stop|pause|resumed activity does not
continue until each `unknown` row is resolved:
- **Reconcile:** a receipt the effector can read back resolves it. V1 has none
  generic. An owner-declared idempotency header on the connection is a later
  extension, out of scope here.
- **Otherwise:** the activity goes to `waiting_on_you` with "this may already
  have happened: <operation> <path> on <connection>". The owner answers
  *it happened*, *it didn't* or *try again*, and the row becomes
  `owner_resolved`. Only *try again* permits a new attempt, under a new key.

**Why not `external_write_receipts`:** it lives in the universe folder, which a
provider jail binds read-write (Decision 1).

### 6. Resume after a deploy

**At boot,** a operation=stop|pause|resumer scans each `.agent-sessions/*/agent-activities.db` for
`in_progress` rows whose lease holder is dead or whose lease has lapsed. For
each, it applies Decision 5 and starts a runner.

**The operation=stop|pause|resumed turn gets:**
- the native session, when the adapter operation=stop|pause|resumes (S1 `native_operation=stop|pause|resume`);
- otherwise a fresh session built from the record:
  - the brief;
  - the completed tool calls up to `last_tool_seq`, from the S4 journal, safe
    summaries only;
  - the partial result;
  - the effect resolutions.

It is told plainly that it was interrupted and what completed. It never
replays a tool call past `last_tool_seq`, and an effect it re-issues hits the
key conflict of Decision 5.

### 7. Automations get an `activity` target

The migration is additive (two `_MIGRATIONS` rows, applied by `ALTER TABLE ADD COLUMN`):
- `target_kind TEXT NOT NULL DEFAULT 'branch'`;
- `activity_template_json TEXT NOT NULL DEFAULT ''` (title, brief, agent id).

**Validation:**
- a branch target needs a non-empty `branch_def_id` and an empty template;
- an activity target needs `branch_def_id=''` and a valid template;
- `NOT NULL` stands, so no table rebuild.

**Firing** keeps every `user-owned-automations` guarantee: the authenticated
owner from the row, the current serving assignment, foreground budget, and the
`automation_attempts` firing fence. It creates an activity record with
`origin_kind='schedule'` and `origin_ref=<automation_id>`, then hands it to the
runner.
- **Lease key:** `agent:<len>:<universe>:activity:<automation_id>`.
- **Overlap policies** apply against that automation's previous activity:
  `skip` and `queue` look at a non-resting previous activity, and
  `cancel_previous` stops it.

**Rollback:** code from before the change that meets an activity row fails that
one automation on `branch ''`. The failure counter then operation=stop|pause|resumes it; the pump is
unaffected.

### 8. Served-tool contract and reads

These are on the universe agent's served tools. The public connector is
unchanged.

| Call | Effect |
|---|---|
| `write_graph target=activity operation=start` `{title, brief}` | creates `scheduled`, starts a runner, returns `{activity_id, status}` |
| `write_graph target=activity operation=stop|pause|resume\|operation=stop|pause|resume\|operation=stop|pause|resume` `{activity_id}` | transition, own universe only |
| `read_graph target=activities` `{status?, cursor?}` | every item, 50 per page, keyset cursor `(updated_at, activity_id)` |
| `read_graph target=activity` `{activity_id}` | the record, its effects and its events |

- **No size cap.** A page is complete or carries `next_cursor`; nothing is cut
  for size. Fields are bounded at write time (Decision 1), so a page cannot grow
  without limit.
- **Activities may not start activities in this change.** `parent_activity_id`
  is recorded for D8, and `operation=start` from inside an activity is refused with
  `nested_activity_unavailable`.
- **The owner door** `/app/activities` offers the same list, stop, operation=stop|pause|resume and
  operation=stop|pause|resume, for the authenticated owner's own home only, with `revision`
  compare-and-set.

## Risks / Trade-offs

- **A deploy during a send can leave an effect `unknown`.** This is
  deliberately surfaced to the owner, never retried. The cost is a question
  after some deploys; the alternative is a duplicate email or payment.
- **No generic receipt read-back in v1,** so every unknown effect is an owner
  question. Declared idempotency headers can narrow this later without a
  storage change: the key is already recorded.
- **The runner lives in the serving process.** A second serving process would
  need the lease, which already exists. Single-writer assumptions elsewhere
  (`agent_turn_boot`) are unchanged.
- **Native operation=stop|pause|resume is adapter-dependent.** The record-built fallback is lossier
  (summaries, not full tool output), but it never re-executes completed tool
  calls.

## Migration Plan

1. Ship the store and the runner dark behind the served-tool targets. Nothing
   creates activities until the agent calls `operation=start`.
2. Run the additive automations columns. Existing rows read as
   `target_kind='branch'`, so behaviour is unchanged.
3. Live proof: two activities in parallel after the chat is closed, and one
   surviving a deploy with an effect in flight.

Rollback is a revert. The new DB file is ignored by old code, and the new
columns are ignored, except the per-automation failure described in Decision 7.

## Open Questions

None blocking. Generic receipt read-back is deferred: per-connection declared
idempotency headers are the likely path, and need no storage change.
