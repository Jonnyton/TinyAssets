# One lease per agent, with a declared overlap policy

## Why

Plan item 5 of the approved primitives plan (founder, 2026-09-27). The
automation fence is a lease per universe. While one automation in a universe
runs (up to its 3h timeout), every other automation in that universe waits,
so two agents in one universe can never run at the same time. There is also
no way to say what should happen when a run falls due while its own previous
run is still going.

## What Changes

- **The lease is per agent.** An automation's lease key is its universe plus
  its branch (`automation_lease_key`). Different branches in one universe run
  side by side. One branch never overlaps itself: its cadence, the one-shot
  wakes it enqueues, and event wakes are separate rows of one agent, and all
  of them share the key.
- **A declared overlap policy per automation**, `overlap` on create:
  - `queue` (default): wait, and start when the running one ends. Instants a
    cadence passes meanwhile collapse into that one run. This is exactly how
    every automation behaved under the per-universe lease, so nothing
    existing changes.
  - `skip`: drop this due run; a cadence moves on to its next instant. A
    one-shot wake is never dropped: it waits as under `queue`. (Revised
    2026-09-29: retiring it as `skipped_overlap` silently ended a
    self-waking loop whose `run_completed` wake fell due while the run that
    fired it still held the agent.)
  - `cancel_previous`: ask the running run to cancel (the lease row records
    its run id), then start once it has stopped.
- **The dead-holder proof is kept** from #4065. The OS liveness lock and the
  worker-future check are unchanged. An unstopped run keeps its agent's key
  busy, even for its own consumer, until the worker has ended.
- **Legacy queue work still owns its whole universe.** A legacy task's
  universe lease and any agent lease in that universe exclude each other. The
  check runs in the acquiring transaction.
- **Fair slots.** Free slots go first to the universe running the fewest
  agents, one agent per universe per pass, with a rotation to break ties. One
  owner's long-running agents therefore cannot keep reclaiming every slot that
  frees while another owner waits. A run that ignored cancellation still holds
  its slot. Only one row per agent is started per poll. A second due row is
  judged on the next poll, under its own policy. Policies are applied even
  when every slot is full.
- **Unambiguous keys.** An agent key is `agent:<len>:<universe>:<branch>`, so
  no key and no universe prefix can reach another universe whatever the ids
  contain.

## Impact

- Code: `tinyassets/automations.py` (lease key, overlap, conflict-checked
  acquire, lease run id, skip), `tinyassets/runtime/assigned_queue_consumer.py`
  (per-agent submission, overlap, fair passes), `tinyassets/api/automations.py`
  (create field and projection), `tinyassets/engine_mcp_server.py` (served
  guidance).
- Storage: `automations.overlap` (default `queue`) and `universe_leases.run_id`,
  both added on connect. The lease table keeps its name, and its key column
  now holds `agent:<len>:<universe>:<branch>` for agents.
- Public surface: an `overlap` create field and projection field.
