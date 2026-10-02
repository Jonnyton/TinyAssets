# The owner's message can wake their universe, and the universe can set its own next wake

## Why

Founder, 2026-10-01: a new owner message should be able to wake the background
self. Live the same day, the universe tried to create an automation triggered by
new owner messages; the engine refused it because no such event existed, and the
universe asked the founder to approve something approval could not create. A
second gap: `write_graph target=automation operation=create` refused
`not_before`, so a served agent could not set its own next wake. Only a code node
granted `enqueue_branch_run` could.

The unread-message counter that pairs with this is PR #4170, which the universe
built itself.

## What Changes

- **`owner_message` event type.** Emitted once the owner's message is stored in
  their conversation: answered, failed or interrupted turns, plus the selected
  consumer's projected turns. A burst coalesces into the subscription's wake that
  has not started yet, so it is one wake. It has no filter keys. A
  `universe:<id>` principal or a visitor wakes nothing.
- **Self-set wakes.** Automation create takes `not_before` (ISO-8601) or
  `delay_seconds` for a one-shot wake, so a timer heartbeat becomes optional.

## Impact

`automations.py`, `automation_events.py`, `api/automations.py`,
`universe_server.py`, `consumer_runtime.py`, and served guidance in
`engine_mcp_server.py`.
