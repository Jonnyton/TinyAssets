## Why

A founder asked their universe, through the app as a naive user, for "a node that
any user's universe can send to directly" so other users could hand it patch
requests. The cross-owner delivery primitive already shipped
(`connect-cross-user-nodes`), and the agent did not use it. It minted a public
inbound webhook and published the URL instead — anonymous content, no sender
universe attached, outside every ownership check the primitive exists to enforce.

Three gaps caused that, all on `origin/main` at 31a1776c:

1. **No way to open a receiver.** `allowed_senders` must enumerate principal ids
   and an empty list permits nobody (`tinyassets/storage/receiver_links.py`
   `_permitted_receiver`). An owner who wants "anyone authenticated" has no
   expression for it, so a webhook is the only shape that fits the request.
2. **No way to find one.** Nothing lets user B learn user A's `receiver_id`, and
   nothing tells an agent how to learn a peer's id. A primitive addressable only
   by an id you cannot obtain is unreachable in practice.
3. **The served guidance never mentions it.** Absent from the `control_station`
   prompt and from every `write_graph` handbook chapter. Only the raw tool
   description carries it, so an agent composing a plan does not see it.

## What Changes

- An owner can mark a receiver **open** (`open_to_all`) so any authenticated
  principal may connect an output and deliver, and/or **discoverable** so other
  users can find it. Both default to closed; exposure stays the owner's explicit
  act. They are independent: an open receiver can stay unlisted, and a listed
  receiver need not accept strangers.
- Every delivery already records the sender's principal and universe; the owner
  can now *see* it (receiver-side receipt) and *act on* it (reserved state fields
  the receiver's own branch declares, which a sender can never supply).
- A per-sender delivery rate limit on each receiver, owner-configurable, refusing
  loudly by name. A usage bound, not a structural cap.
- Discovery through `read_graph target="receivers"`: any authenticated user lists
  or searches receivers whose owners marked them discoverable, sender view only.
- A `delivering` handbook chapter for `write_graph` plus a one-line pointer in
  `control_station`, so an agent asked to "let other users send me X" finds the
  primitive instead of a webhook.

Not in scope: a feedback/patch/bug system, a platform intake, an owner-side
review UI, or any change to universe visibility defaults. The platform ships the
primitive; users build their own intakes and gates on top of it.

The six canonical handles are unchanged: this extends `read_graph` and
`write_graph` targets and the existing extensions action set.

## Capabilities

### New Capabilities

- None. This extends the delivery boundary that `connect-cross-user-nodes`
  established; it adds no top-level primitive.

### Modified Capabilities

- `graph-execution-substrate`: owner-declared open/discoverable receiver
  exposure, sender attribution reaching the receiver's own run, per-sender
  delivery rate limiting.
- `live-mcp-connector-surface`: receiver discovery read, the open/discoverable/
  rate-limit payload fields, and the served guidance that makes them findable.

## Impact

`tinyassets/storage/receiver_links.py` (two new columns + a limit column, with an
additive migration), `tinyassets/storage/deliveries.py`,
`tinyassets/api/receiver_links.py`, `tinyassets/api/deliveries.py`,
`tinyassets/api/runs.py` (action registration), `tinyassets/universe_server.py`,
`tinyassets/engine_mcp_server.py`, `tinyassets/api/prompts.py`, tests, and the
plugin mirror. Storage shape + authority + public MCP surface, so this change
carries a design and needs cross-family review before landing.

Owner: Claude/open-receivers. Intended branch: `claude/open-receivers`.
One intent, one PR: make a receiver openable, findable, and attributed.
