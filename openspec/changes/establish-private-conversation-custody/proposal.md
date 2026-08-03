## Why

The approved remix-to-running-agent demo cannot admit app conversations until
private conversation state has a durable owner. Today agent definitions and
bindings correctly reject conversations, but no exportable universe-scoped
custody contract can retain a thread without leaking it into public lineage or
letting an app adapter become the canonical store.

## What Changes

- Introduce a custody-neutral conversation contract and implement its first
  `private_universe` mode inside the user's selected private universe data
  boundary.
- Persist immutable thread identity plus append-only message records with
  universe, agent binding, interlocutor, source-event, and reply lineage.
- Require owner-scoped idempotency, strict reads, bounded content, explicit
  retention, export, and deletion receipts.
- Keep credentials, app installation authority, delivery effects, provider
  output, and public agent definition/remix data outside this store.
- Leave host-resident, external-vault, and platform-held modes open for later
  independently admitted implementations; this change does not select them.

## Capabilities

### New Capabilities

- `conversation-custody`: Private, exportable, mode-declared conversation
  threads and messages with strict ownership, retention, and deletion.

### Modified Capabilities

None.

## Impact

- Adds a canonical conversation-custody domain and SQLite storage owner with a
  packaged runtime mirror.
- Adds no MCP handle, app adapter, Slack-specific schema, provider call,
  outbound effect, public definition field, or production activation.
- Supplies one prerequisite handoff for the future
  `connect-custom-agent-app-conversations` delivery change.
