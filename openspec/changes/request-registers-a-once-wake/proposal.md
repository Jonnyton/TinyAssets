# write_graph target="request" registers a one-shot wake

## Why

`write_graph target="request"` is documented to every chatbot as how to hand
the universe work (`tinyassets/api/prompts.py`, the "Submit collaborative
input" and "Give direct daemon guidance" rows). Today it commits a
`branch_tasks_v2` row for the universe's declared loop branch
(`_action_admit_request_v2`, `tinyassets/api/universe.py`). Nothing in the cloud
runs that row:

- The only cloud executor, `AssignedQueueConsumer`, only ever claimed rows that
  carried a fleet-era cloud-automation activation. A request row carries none,
  so the consumer skipped it (`consumer_not_applicable`). That claim pass was
  deleted with the fleet-era pump (dark-code deletion plan C2).
- What remains to claim a request row is a host daemon's Epoch2 loop
  (`fantasy_daemon`), which needs a host online. The Forever Rule is zero hosts
  online.

So a request is accepted and then waits forever. Production holds one such row,
pending since 2026-08-05.

The platform already has the primitive this needs. `node-scheduled-wake`
(#4067) added a `once` automation: a durable row that the automation pump fires
once, with every run-time check an automation has.

## What Changes

- **An owner's request registers a `once` wake** of the universe's declared
  loop branch, due now. The request's text and type become the run's inputs
  (`request`, `request_type`). The pump fires it with the checks it already
  applies: owner admin, own home, authored branch, current serving provider,
  per-universe run admission, and the lease fence.
- **Idempotency is kept.** The request-admission ledger still records one row
  per `idempotency_key`. The row now names the wake's `automation_id` instead
  of creating a `branch_tasks_v2` task. A replay returns the first result.
- **A request from anyone but the universe's owner is refused**, with
  `request_owner_only`. A once wake runs on the owner's own subscription, and a
  non-owner spending it is a cross-user effect (the floor). Collaborative input
  from other users goes through the owner's own channels, which the owner
  builds.
- **Fields that only meant something to the old queue are refused when set.**
  These are `priority_weight` above 0, `directed_daemon_id`,
  `directed_daemon_instruction` and `pickup_incentive`; each is refused with
  `request_field_retired:<field>`. At their defaults they are accepted, so a
  client that always sends them still works.
- **The pending 2026-08-05 row gets a recorded disposition**, not a silent
  drop. A migration marks every pending request-admission task `refused` with
  the reason `request_retired_to_wake`. The owner can re-send the request.
- The chatbot guidance in `tinyassets/api/prompts.py` changes to match: a
  request asks your own universe to run its loop now.

## Impact

Code:
- `tinyassets/api/universe.py`: `_action_admit_request_v2`.
- `tinyassets/storage/request_admissions.py`: the ledger names the wake, plus
  the migration that records the disposition.
- `tinyassets/api/prompts.py`: the guidance rows.

Surface: `write_graph target="request"` keeps its parameters. Its result gains
`automation_id` and `not_before`, and loses `branch_task_id`. The canary handle
set does not change.

Out of scope: deleting `branch_tasks_v2` and the host daemon's Epoch2 loop.
Those still serve self-hosted daemons.
