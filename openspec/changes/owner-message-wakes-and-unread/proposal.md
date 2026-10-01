# The owner's messages reach a running universe, and can wake it

## Why

Founder, 2026-10-01: "the background self should just have an indicator of how
many messages have been sent since it looked last", and a new owner message
should be able to wake the background self. Two gaps:

- A running agent (a background wake or a chat turn) had no way to notice the
  owner said something new, short of re-reading the whole conversation on a
  hunch.
- No event fired on an owner message, and `write_graph target=automation
  operation=create` refused `not_before`, so a served agent could not set its
  own next wake (only a code node granted `enqueue_branch_run` could).

## What Changes

- **`owner_unread` on every served JSON tool result.** The number of the
  owner's messages in their own thread that this universe has not read. One
  marker per thread (universe + owner), shared by the universe's chat turns and
  wakes; a message is read when a served `read_graph target="conversation"`
  returns its text through its end. Cached against the store's file signature.
  Raw content tools (`read`/`write`/`edit`/`bash`) carry none.
- **`owner_message` event type.** Emitted once the owner's message is stored in
  their conversation (answered, failed or interrupted turns, and the selected
  consumer's projected turns). Coalesces into the subscription's wake that has
  not started yet, so a burst is one wake. No filter keys.
- **Self-set wakes.** Automation create takes `not_before` (ISO-8601) or
  `delay_seconds` for a one-shot wake; a timer heartbeat becomes optional.

## Impact

`tinyassets/conversation_unread.py` (new), `engine_mcp_server.py` (middleware,
read hook, resident text), `automations.py`, `automation_events.py`,
`api/automations.py`, `universe_server.py`, `consumer_runtime.py`.
