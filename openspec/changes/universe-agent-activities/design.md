## Context

Two harness requirements (change `universe-agent-harness`) already specify the
behaviour:
- *An agent works on several activities at once, without a connected client,
  and recovers them after a restart*;
- *The agent's activities and schedules are read completely*.

This design covers only what they leave open:
- where the records live;
- under what authority an activity runs with no request;
- how an effect is recorded before it fires;
- how an activity is fenced, dispatched and resumed;
- how a schedule names an activity.

Facts from origin/main, 2026-10-01. Revised after the gpt-6-astra refute
(ADAPT), with its citations re-checked.

| Fact | Where |
|---|---|
| A served turn needs the request's verified identity. Its provider capability is request-scoped and dies with the request | `universe_intelligence.converse`; `auth/middleware.provider_request_capability` |
| Background compute admission exists only for a work subject the authority store knows. Work items are typed (`run`, `background_attempt`, `branch_task`, `agent_invocation`), and receipts are unique per `(universe, kind, id)` with a generation | `provider_work_authority._WORK_ITEM_KINDS`; `storage/provider_work_authority._RECEIPT_TABLE_SCHEMA` |
| The foreground lane admits a `run` subject: founder-home check, assignment and manifest admission, credential path, budget. It requires a branch snapshot and a run record | `foreground_run_provider._ForegroundRunProviderSession` (`prepare`, `_validate_founder_home`, `_validate_run`, `_admit`) |
| Run recovery interrupts a run only when its owner's liveness lock exists and nobody holds it. Alive or unknown owners are never touched | `runs.recover_in_flight_runs` (owner token, `process_liveness`) |
| Seats keep an ALIVE holder past lease expiry. `try_acquire` keeps a queue ticket without holding a thread | `universe_seats._reap`, `try_acquire` |
| `authenticated_external_call` receives run and node identifiers, never an agent tool-call id. It records nothing before the send | `effectors/authenticated_external_call.py` (`_run`, the proxy request) |
| The existing reserve-before-send store lives inside the universe folder, which a provider jail binds read-write | `storage/external_write_receipts.py`; `providers/provider_jail` |
| Automations take a lease keyed by `branch_def_id` and apply overlap policies in the consumer before execution | `automations.automation_lease_key`; `runtime/assigned_queue_consumer.py` |
| Account deletion stages `<root>/<home>`. Removing `.agent-sessions/<home>` is in S2 (#4188), which has not landed | `account_deletion.py` |

## Goals / Non-Goals

**Goals**
- A durable record per activity, which no agent can forge.
- Compute admitted under the owner's own authority, with no request present.
- At most one live runner per activity.
- No external effect sent twice across a crash.
- Durable dispatch that does not depend on boot.
- Complete, paged reads.
- A schedule can start an activity.

**Non-Goals**
- Delegated authority, and the research flag (D8, D3).
- Browser contexts (D5).
- The `ta` command (D6), which wraps this contract.
- Nested activities.

## Decisions

### 1. Records live outside the universe, beside `rules.db`

The store is `<data root>/.agent-sessions/<universe>/agent-activities.db`. A
provider jail binds the universe read-write, so anything inside it could be
forged. The name avoids S4's `activity.db` (the tool journal).

The schema uses SQLite with WAL and `busy_timeout`. Every transition runs under
`BEGIN IMMEDIATE`, with compare-and-set on `revision` and on `runner_generation`.

```sql
CREATE TABLE activities (
  activity_id        TEXT PRIMARY KEY,           -- 'act_' + 16 hex, platform-minted
  agent_id           TEXT NOT NULL DEFAULT 'main',
  parent_activity_id TEXT NOT NULL DEFAULT '',   -- recorded for D8; always '' here
  session_key        TEXT NOT NULL UNIQUE,       -- 'activity:<activity_id>'
  owner_principal    TEXT NOT NULL,              -- derived server-side at creation
  title              TEXT NOT NULL,              -- one line, <= 200 chars
  brief              TEXT NOT NULL,              -- <= 16 KiB
  origin_kind        TEXT NOT NULL CHECK (origin_kind IN ('ask','proposal','schedule')),
  origin_ref         TEXT NOT NULL DEFAULT '',   -- turn id | proposal id | '<automation_id>@<due_at>'
  approval_id        TEXT NOT NULL DEFAULT '',
  status             TEXT NOT NULL CHECK (status IN
                       ('scheduled','in_progress','waiting_on_you','paused','completed','failed')),
  outcome            TEXT NOT NULL DEFAULT '',   -- done | stopped | failed:<class>
  waiting_reason     TEXT NOT NULL DEFAULT '',
  waiting_request_id TEXT NOT NULL DEFAULT '',   -- the owner request it waits on
  result_summary     TEXT NOT NULL DEFAULT '',   -- <= 4,000 chars; full result in a workspace file
  result_path        TEXT NOT NULL DEFAULT '',
  last_tool_seq      INTEGER NOT NULL DEFAULT 0,
  runner_token       TEXT NOT NULL DEFAULT '',   -- process_liveness owner token of the live runner
  runner_generation  INTEGER NOT NULL DEFAULT 0, -- fences every write a runner makes
  revision           INTEGER NOT NULL DEFAULT 1,
  created_at REAL NOT NULL, updated_at REAL NOT NULL, finished_at REAL NOT NULL DEFAULT 0
);
CREATE INDEX activities_by_update ON activities(updated_at DESC, activity_id DESC);
CREATE UNIQUE INDEX activities_by_schedule ON activities(origin_ref) WHERE origin_kind = 'schedule';

CREATE TABLE effect_intents (
  intent_key     TEXT PRIMARY KEY,   -- sha256(run_id, node_key, effect_index, wire_digest)
  activity_id    TEXT NOT NULL,
  run_id         TEXT NOT NULL,
  node_key       TEXT NOT NULL,
  effect_index   INTEGER NOT NULL,
  wire_digest    TEXT NOT NULL,      -- digest of the RESOLVED request: method, URL, transformed body
  connection_id  TEXT NOT NULL, operation TEXT NOT NULL, path TEXT NOT NULL,
  state          TEXT NOT NULL CHECK (state IN
                   ('planned','sent','confirmed','failed','unknown','owner_resolved')),
  resolution     TEXT NOT NULL DEFAULT '',  -- happened | not_happened | try_again
  receipt_json   TEXT NOT NULL DEFAULT '',  -- status code + safe summary only
  created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE INDEX effect_intents_by_activity ON effect_intents(activity_id, created_at);

CREATE TABLE activity_events (
  activity_id TEXT NOT NULL, seq INTEGER NOT NULL, ts REAL NOT NULL,
  kind TEXT NOT NULL,   -- created | in_progress | waiting_for_seat | waiting_on_you | paused
                        -- | scheduled | completed | failed | stopped | resumed
  line TEXT NOT NULL,   -- platform-composed, <= 300 chars
  delivered INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (activity_id, seq)
);
```

**Status lines** are composed by the platform. The only agent-supplied text a
line carries is the activity's title: quoted, one line, at most 80 characters.

**Lifecycle**
- *Retention.* Records stay until the owner deletes an activity (owner door) or
  the account is deleted.
- *Events.* Each activity keeps at most 200 events. Older delivered events are
  dropped and the newest are kept.
- *Effect intents.* Kept while their activity exists. Reads of them are paged.
- *Quota.* The bytes in `.agent-sessions/<universe>/` count against that
  universe's quota through the same usage function that measures the universe.
  D2a wires and tests this; the `ROOT_ENTRIES` declaration alone does not.
- *Account deletion.* S2's removal of `.agent-sessions/<home>` is a
  prerequisite and lands first. Before that removal, deletion fences every
  activity: it advances `runner_generation` and marks them `failed:account_deleted`.
  A runner still alive therefore cannot recreate the store.

### 2. Session keys

- An activity is `activity:<activity_id>`.
- A further roster agent (D8) is `agent:<agent_id>:thread`.
- The main agent keeps `thread:principal:<owner>`.
- Parentage is recorded in the record, not in the key. `agent_sessions`
  validates no key prefix.

### 3. Authority: an `activity` work item in the foreground lane

An activity is compute the owner's universe spends with no request. The
authority store already admits typed work items, so `activity` is added to
`_WORK_ITEM_KINDS` with `work_item_id = activity_id`.

An activity provider session reuses the foreground lane's admission core
unchanged: assignment and manifest admission, serving binding, credential path,
budget accounting and receipts. Only the subject differs:

| Foreground `run` subject | `activity` subject |
|---|---|
| `prepare(run_id, branch, …)` takes a branch snapshot | `prepare_activity(activity_id, runner_generation)` reads the activity record |
| Prompt nodes and roles come from the branch | One synthetic prompt node, role `writer` |
| `_validate_run` checks status, actor, branch ids and cancel | `_validate_activity` checks status `in_progress`, the same `runner_token` and `runner_generation`, and `owner_principal` unchanged |
| `_validate_founder_home` | the same check, plus the admin ACL check `owner_run_identity` makes, whose boolean result is consumed. Both must pass, or the activity fails `owner_lost` |

- **Fencing.** A resumed runner advances the receipt `generation`, which fences
  the previous runner's receipt. A stalled old process cannot make another
  model call under it.
- **Budget.** Spend is recorded and charged exactly like a run's; only the work
  item differs.
- **Ownership.** Owners are derived on the server and never taken from tool
  arguments or templates:
  - *Served turn:* the verified actor, as automations do (`api/automations.py`).
  - *Owner door:* the authenticated identity, for its own home.
  - *Automation:* the row's owner, revalidated when it fires.

### 4. Dispatch and fencing: one live runner, never boot-only

A dispatcher runs in the serving process on the automation pump's cadence
(every 30 s) and on demand when an activity is created or answered.
1. It selects the activities that need a runner:
   - `scheduled` activities;
   - `in_progress` activities whose `runner_token`'s liveness lock exists and
     is unheld. These are the same semantics as run recovery. A live or
     unknown runner is never taken over.
2. For each, it calls `try_acquire(work_key=activity_id, kind=activity)`:
   - with a seat: it claims the activity by compare-and-set (status, set its own
     `runner_token`, `runner_generation + 1`) and submits the runner;
   - without one: it keeps the queue ticket, writes one `waiting_for_seat`
     event, and moves on. No thread blocks on a seat.
3. Every runner write (progress, transition, effect intent) carries
   `runner_generation`. A write from a superseded generation affects no row,
   and that runner stops.

**Waiting releases the seat.** When an action asks first, or the auto-review
asks for approval inside an activity, the activity:
- raises one owner request and records its id in `waiting_request_id`;
- moves `in_progress -> waiting_on_you`;
- ends its turn and releases the seat.

The owner's answer moves it `waiting_on_you -> scheduled`, by compare-and-set on
`waiting_request_id`. A stale or duplicate answer changes nothing.

### 5. Effects: a platform intent recorded before the wire

Inside an activity, external effects fire in runs the activity started (through
`run_graph`). The effector never has an agent tool-call id, so the platform
mints the intent identity from what it does have:

`intent_key = sha256(run_id, node_key, effect_index, wire_digest)`

`wire_digest` hashes the resolved request: method, URL and transformed body.
The identity is stable for as long as the run exists. A run is never replayed
past an interrupted node (`interrupted` is terminal), so a re-attempt is a new
run with a new key, and it happens only after the owner answers.

Requests from the agent's own bash, through the egress proxy, are not effector
calls. They are governed as `shell.egress` by the owner's rules and are not
recorded here.

**Activity linkage.** A run started from an activity's turn records that
`activity_id`, minted by the platform from the bound runner and never accepted
as input. The effector applies the following only to runs that carry one:
1. `INSERT planned`. A primary-key conflict means it was already attempted, and
   nothing is sent.
2. Commit `sent` durably before the wire. If that commit fails, nothing is sent.
3. After the wire, record `confirmed` or `failed` with a safe receipt.
   Transport uncertainty is `unknown`, never `failed`: a timeout or a reset
   after the request was written.

**Recovery.** A row is changed only after its run is interrupted, which happens
only once its owner's liveness lock is provably dead:
- `planned` becomes `failed` (`not_sent`), because `sent` commits before the
  wire;
- `sent` becomes `unknown`.

The activity sees its child run interrupted and its unknown intents. It goes to
`waiting_on_you` with "this may already have happened: <operation> <path> on
<connection>". The owner answers *happened*, *not happened* or *try again*,
which becomes `owner_resolved` with that resolution. Only *try again* lets the
agent start a new run for that action.

### 6. Resume

A runner taking over an `in_progress` activity continues `activity:<id>`:
- **Natively** when the adapter resumes (S1 `native_resume`).
- **Otherwise from a session built from the record:**
  - the brief;
  - completed tool calls up to `last_tool_seq`, taken from the durable agent
    turn journal (`storage/agent_turn_journal.py`) where the turn was journaled,
    or from S4 safe summaries where it was not;
  - the partial result;
  - effect resolutions.

The session is told plainly that it was interrupted. Its runs are their own
records, so it never re-executes a completed tool call by replay.

### 7. Automations target an activity

The migration is additive: two `_MIGRATIONS` rows, `target_kind` (default
`branch`) and `activity_template_json` (default `''`). An activity target has
`branch_def_id = ''`, so `NOT NULL` stands.
- **Validation.**
  - A branch target needs a branch and no template.
  - An activity target needs a template and no branch.
  - The owner comes from the authenticated creator and is never taken from the
    template.
- **Lease key.** A branch target keeps `agent:<len>:<universe>:<branch_def_id>`.
  An activity target uses `agent:<len>:<universe>:activity:<automation_id>`,
  which cannot collide with any branch id.
- **Firing.** Firing keeps the owner revalidation, serving assignment, budget
  and the `automation_attempts` fence. The activity is created with
  `origin_ref = '<automation_id>@<due_at>'` under a unique index. Attempt and
  activity live in different databases, so a crash between them is recovered by
  re-firing the same attempt: the insert is idempotent, and it returns the
  existing activity.
- **Overlap policies** see the automation's latest activity:
  - `skip` and `queue` apply while it is not resting;
  - `cancel_previous` stops it.
- **Rollback.** Code from before this change computes every activity target's
  lease key as `…:<universe>:` and they collide. Before a downgrade, activity
  targets are paused (`desired_state='paused'`). The migration plan makes that a
  release step.

### 8. Served-tool contract and reads

These calls are on the universe agent's served tools. The public connector is
unchanged.

| Call | Effect |
|---|---|
| `write_graph target=activity operation=start` `{title, brief}` | creates `scheduled`, wakes the dispatcher, returns `{activity_id, status}` |
| `write_graph target=activity operation=stop` / `pause` / `resume` `{activity_id}` | a checked transition, own universe only |
| `read_graph target=activities` `{status?, cursor?}` | every activity, 50 per page, keyset cursor `(updated_at, activity_id)` |
| `read_graph target=activity` `{activity_id, cursor?}` | the record plus one page of its events and effect intents |

- A page is complete or carries `next_cursor`. Nothing is cut for size.
- `operation=start` from inside an activity is refused with
  `nested_activity_unavailable`.
- **The owner door** `/app/activities` offers the same list, stop, pause, resume
  and delete, for the authenticated owner's own home only, with compare-and-set
  on `revision`.

## Risks / Trade-offs

- **A deploy during a send becomes an owner question.** That is deliberate. A
  duplicate payment or email costs more than a question.
- **The activity subject adds a fifth work item kind** to an authority store
  that guards credentials. The admission core is reused unchanged, and only the
  subject validation is new. That is the narrowest addition that gives
  background compute without a request. The alternative was representing each
  activity as a platform-authored branch run, which would put a platform branch
  in every universe.
- **No generic receipt read-back.** Unknown effects are owner questions until
  connections can declare idempotency headers. The intent key is already
  recorded, so that needs no storage change.

## Migration Plan

1. Land S2 (#4188) first, for account deletion of `.agent-sessions/<home>`.
2. Ship the store, the `activity` work item, the dispatcher and the served-tool
   targets. Nothing creates activities until the agent calls `operation=start`.
3. Ship the additive automations columns. Existing rows read as
   `target_kind='branch'`.
4. Live proof: two activities in parallel after the chat is closed, and one
   surviving a deploy with an effect in flight.

**Rollback.** Pause activity-target automations, then revert. Old code ignores
the store and the new columns.

## Open Questions

None blocking. Per-connection idempotency headers would narrow owner questions
later.
