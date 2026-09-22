# Lossless app history for long replies

## Why

A long diagnostic reply rendered complete in the app, then an idle refresh
redrew it cut to exactly 4000 characters with no marker, no control and no
error. Nothing in the app said bytes were missing.

Storage loss is unproven and, on inspection, unlikely: `converse` records the
full text via `conversation_store.record_exchange`, and the cut is exactly the
`_cap = 4000` per-turn bound applied in
`tinyassets/api/status.py:1724` when building `recent_conversation`. The app's
`loadHistory` (`tinyassets/onboarding/app.html:5812`) consumes that bounded
preview and never reads the sibling `truncated` flag, so a preview is drawn as
if it were the message.

The lossless reader already exists —
`tinyassets/conversation_retrieval.read_conversation_page` returns
principal-bound keyset pages plus exact Unicode-code-point chunks of one
message. **It is not reachable from the app.** `read_graph target="conversation"`
is routed only on the engine surface (`tinyassets/engine_mcp_server.py:438`, the
universe's own agent with a pinned actor). The public connector's `read_graph`
(`tinyassets/universe_server.py:482`) has no `conversation` target — only
`conversation_turn`, which reads a keyed consumer request, not the thread.

So the app has no way to ask for the rest of a message it already knows is
short. A client-only fix is impossible inside current public contracts, which is
why this is a proposal rather than a patch.

Raising the status cap is explicitly out of scope: it moves the cliff instead of
removing it, and grows every routine founder `get_status` payload.

## What Changes

Two additive public-surface changes, then a client fix that uses them.

1. **`recent_conversation` turns carry their stable store id.** Each turn object
   gains `id` (the `conversation_turns.id` primary key, as a decimal string) and
   `total_chars`. The existing `truncated` flag stays. Without an id the client
   would have to fuzzy-match a message back to a catalogue row by text or
   timestamp, which is exactly the class of bug this is meant to close.

2. **Public `read_graph` gains `target="conversation"`**, delegating to the
   existing `read_conversation_page` under the authenticated caller's own
   principal and own founder home — the same binding the engine route already
   uses, with no new storage, no new module and no new retrieval API.

3. **The app offers the rest of a truncated message.** `loadHistory` renders the
   bounded preview with an explicit "Show full reply" control; the control pages
   chunks by the server's `next_offset` until exhausted, behind the same
   login-epoch / account / home fence every other async load in `app.html`
   already carries. Loading and failure are visible; nothing is silently lost.

Not in scope: raising the status cap, unbinding `get_status`, any new retrieval
API or storage shape, any provider or workflow behaviour.

## Impact

- Affected specs: `live-mcp-connector-surface`
- Affected code: `tinyassets/api/status.py`, `tinyassets/conversation_store.py`
  (`Msg` gains `id`; `_read_messages` selects it), `tinyassets/universe_server.py`
  (one new read target), `tinyassets/onboarding/app.html`
- Mirror: `packaging/claude-plugin/build_plugin.py` rebuild (canonical
  `tinyassets/*` runtime files change)
- No migration: `conversation_turns.id` is an existing
  `INTEGER PRIMARY KEY AUTOINCREMENT` column.
