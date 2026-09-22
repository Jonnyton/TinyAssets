# Design — lossless app history

Status: **implementation candidate after lead shape review, not released.**

## Verified starting state (2026-09-21, worktree at `4b6430ed`)

| Claim | Evidence |
|---|---|
| The cut is a status-side preview bound, not storage | `tinyassets/api/status.py:1724-1733` — `_cap = 4000`, `text[:_cap]`, `truncated` sibling |
| The app ignores `truncated` | `tinyassets/onboarding/app.html:5812-5860` — `loadHistory` reads only `speaker/text/ts/consumer_turn_id/failure/execution` |
| A lossless reader exists | `tinyassets/conversation_retrieval.py:18` — keyset catalogue + `chunk` with `offset_unit="unicode_code_points"` and `next_offset` |
| It is engine-only | `tinyassets/engine_mcp_server.py:438` routes `target="conversation"`; `tinyassets/universe_server.py:558` routes only `conversation_turn` |
| The app speaks the public surface | `app.html:1451` `getConversation()` → `callTool("get_status", {include_conversation:true})` over `/mcp` |
| `id` is stable | `conversation_store.py:80` — `id INTEGER PRIMARY KEY AUTOINCREMENT` |
| No collision | `python scripts/check_primitive_exists.py action conversation` → CLEAN on `origin/main` |
| The local retained-store fixture is lossless | `tests/test_conversation_failure_readers.py::test_a_long_reply_reaches_the_status_feed_whole` records and reads a >4000-char Unicode fixture exactly; this does not establish retained bytes of the production message |
| The current server reports the cut | `test_status_peek_labels_failure_and_marks_long_original_truncated:113` asserts `truncated` is set and `len(text) == 4000` |

**The source demonstrates a presentation defect.** The current server has
told the truth about the bound; the client discards the flag and has no handle to
act on it. That is why item 1 below is an id, not a bigger cap — the only missing
piece on the status side is a way to *name* the message whose rest you want.

## Why an id, not a match

`get_status` builds turns from `conversation_store._read_messages`, which selects
`turn_no` and orders by `ts DESC, turn_no DESC`. `read_conversation_page` keys and
orders on `id`. The two orderings can disagree on an equal-timestamp tie, and
`Msg` carries no id at all today. A client pairing a truncated preview to a
catalogue row by text prefix or timestamp would mis-pair exactly the ties that
already bite this thread. The id is therefore load-bearing, not convenience.

`turn_no` is deliberately not used: it is per-session and `read_conversation_page`
does not accept it.

## Authorization

Unchanged and re-derived per call, never inherited:

- `get_status` already gates the peek on `permissions.universe_access_allows(uid,
  write=True)` and keys the session as `principal:{current_actor_id()}`. Adding
  `id`/`total_chars` widens nothing — it names a row the caller is already being
  shown.
- The new `read_graph target="conversation"` derives its own principal at call
  time (`is_authenticated_request()` + `current_actor_id()`), resolves the
  caller's own home, and passes `session_id=f"principal:{actor}"`. It never
  accepts a caller-supplied session, universe path or principal. An unauthenticated
  call returns the same `not_found` envelope `conversation_turn` uses.
- An `execution` receipt on a turn is display metadata. It is never consulted to
  decide whether a read is allowed.

## Client behaviour

- The preview still renders immediately; the thread never waits on a chunk read.
- A turn with `truncated: true` renders the preview plus a control naming the real
  size ("Show the full reply — N characters"). Nothing auto-fetches: a long thread
  must not turn one refresh into thirty tool calls.
- Paging follows the **server's** `next_offset` only. JS `String.length` counts
  UTF-16 code units and would desynchronise on any astral character (emoji), so the
  client never computes an offset itself.
- Every chunk load re-checks `MCP._loginEpoch`, `queueOwner` and `queueScope`
  before painting, and drops silently if any changed — a response belonging to the
  previous account paints nothing.
- Failure is stated in place ("Couldn't load the rest of this reply") with the
  preview intact and the control re-armed. No partial text is discarded and no
  failure is swallowed.
- Existing thread behaviour is untouched: chronological order from each turn's own
  `ts`, `platform` speaker failure notices, answering provider/model labels from
  `execution`, `consumer_turn_id` dedupe, and the unconfirmed/in-flight recovery
  path. The chunk read is additive and read-only; it replays no mutation.

## Rejected alternatives

- **Raise `_cap`.** Moves the cliff, inflates every founder `get_status`, still
  silent at the new bound.
- **Send the full text unbounded in `get_status`.** Unbounds a routine read and the
  untrusted-transcript fence with it.
- **Reconstruct from `target="run_output"` via the execution receipt.** Treats
  receipt metadata as a retrieval handle; a `converse` reply is not always a run
  output; and it invites exactly the receipt-as-authorization confusion.
- **A new app-only HTTP endpoint under `/mcp/app`.** A second retrieval path over
  the same store, when a principal-bound one already exists.

## Reviewed scope and verification

Lead chose the existing catalogue AND chunk modes under the same owner/home
binding, not an artificial public-only sub-mode. The app retains the status
preview's display metadata and expands using its stable id; it need not render
from the catalogue. An explicit foreign graph id refuses rather than returning
current-home bytes under a foreign label.

Chunk requests carry the rendered home and check login/owner/home both before
requesting and after awaiting. A terminal marker must be explicit and consistent
with total code-point length; malformed or non-advancing continuation fails
visibly. There is no arbitrary page-count limit.

Windows,2026-09-22:52 focused tests pass after four new regressions reproduced
stale-control requests, omitted home binding, a512-page cutoff and missing terminal
marker acceptance. Broader cohort199pass/1fail: existing symlink test raises
WinError1314 before reaching its assertion. The exact test also fails at clean
base4b6430ed. Docker Linux engine is unavailable; it was not started. Linux and
live proof remain outstanding. No production-message preservation claim yet.
