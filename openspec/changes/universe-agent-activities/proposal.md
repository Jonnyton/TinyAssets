## Why

The universe-agent-harness design (#4172, founder-approved 2026-10-01) makes a
new user's command center work like a ChatGPT dot: one always-on agent that
works on several things at once, with no chat open, and picks up where it left
off after a restart. The harness requirement *An agent works on several
activities at once, without a connected client, and recovers them after a
restart* says what that does. It does not yet say where the records live, how an
effect is recorded before it fires, or how a schedule names an activity instead
of a branch.

Those are storage shape, a served-tool contract and a migration: the things a
wrong guess makes expensive. Design §6 D2 therefore opens this storage proposal
before any D2 code.

What main has today (verified 2026-10-01 at origin/main):
- Nothing runs an agent turn for a session key without a request. `converse`
  derives the principal, provider carrier and sandboxed config from the
  authenticated request (`universe_intelligence.converse`). The only client-less
  turn is an agent node inside a branch run (`shared_self`, `workflow_agent`).
- A served turn caught by a deploy is settled as held, abandoned or
  indeterminate at boot (`agent_turn_reconcile.reconcile_orphaned_turns`). It is
  never operation=stop|pause|resumed.
- `authenticated_external_call` records nothing before a send. Reserve-before-send
  exists in `storage/external_write_receipts.py`, but that store lives inside
  the universe folder, and only `wiki_write_back` and hand-offs use it.
- Automations require a branch: `automations.branch_def_id TEXT NOT NULL`.
- Seats have four kinds (`chat_turn`, `agent_node`, `automation`, `wake`), and
  the ceiling depends on class, never kind.

## What Changes

- **New platform store** `.agent-sessions/<universe>/agent-activities.db`,
  outside every universe folder, beside `rules.db`. It holds activity records,
  pending effects and status lines. No agent-controlled environment can reach
  it.
- **New session keys:** `activity:<id>` for an activity and `agent:<id>:thread`
  for a further roster agent's main session. Parentage is in the record. The
  main agent keeps `thread:principal:<owner>`.
- **Pending effects.** An external effect from an activity is written as
  `planned` with an idempotency key before it is attempted. After a restart a
  `sent`-but-unconfirmed effect is `unknown`. Before anything retries, it is
  reconciled through its receipt; if that fails, the activity waits on the owner
  ("this may already have happened").
- **A seat kind `activity`** in the background class. It is held while the
  activity runs and released while it waits on the owner or is operation=stop|pause|resumed.
- **Served-tool contract:**
  - `write_graph target=activity` with `start`, `stop`, `operation=stop|pause|resume` and `operation=stop|pause|resume`;
  - `read_graph target=activities|activity`, complete and cursor-paged.
  - D6's `ta activity start/list/stop` wraps these, and adds no second
    definition.
- **Automations migration.** It adds two columns with `ALTER TABLE ADD COLUMN`:
  - `target_kind`, default `branch`;
  - `activity_template_json`, default `''`.

  An activity target keeps `branch_def_id` as `''`, so `NOT NULL` stands and
  there is no table rebuild. Code from before the change that meets such a row
  fails that one automation with "branch not found", rather than the table.
- **Owner door** `/app/activities`: list, stop, operation=stop|pause|resume and operation=stop|pause|resume, own home only.
  The Activity tab reads it.

Not in this change:
- the execution context beyond agent id and approval id (D8);
- research turns (D3);
- browser contexts (D5);
- the `ta` command itself (D6).

## Capabilities

### New Capabilities
- `universe-agent-activities`: where activity records and pending effects live,
  the session keys, the served-tool contract, and the automation activity target.

### Modified Capabilities
- `user-owned-automations`: a second target kind, under the same owner,
  assignment, budget and firing-fence contract.

## Impact

- **Storage:**
  - a new root-side DB declared in `storage_accounting.ROOT_ENTRIES`;
  - two additive automations columns;
  - account deletion already removes `.agent-sessions/<home>` once S2 (#4188)
    lands.
- **Code:**
  - `tinyassets/agent_activities.py` (new);
  - a client-less activity runner;
  - `universe_seats` (one kind);
  - `effectors/authenticated_external_call` (record before send, for activities);
  - `automations.py`;
  - `engine_mcp_server` (two targets);
  - the onboarding door;
  - `app.html` (Activity tab).
- **No public connector change.** The six connector handles are unchanged. The
  new targets are on the universe agent's served tools.
