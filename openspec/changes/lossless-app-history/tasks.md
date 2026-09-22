# Tasks — lossless app history

Lead shape review approved the two additive public-surface changes, with both
existing reader modes and unchanged owner/home authority. Candidate is unshipped.

Local fixture evidence (not production-message verification):
`tests/test_conversation_failure_readers.py::test_a_long_reply_reaches_the_status_feed_whole`
shows its stored text and status feed are lossless; the preview is bounded.

## 1. Public surface

- [x] 1.1 `conversation_store._read_messages` selects `id`; `Msg` gains
      `id: int | None = None`. Existing positional constructions audited.
- [x] 1.2 `api/status.py` emits `id` (decimal string) and `total_chars` on each
      `recent_conversation` turn; `truncated` unchanged.
- [x] 1.3 `universe_server.read_graph` routes `target="conversation"` to
      `read_conversation_page`, deriving principal + home per call, exposing both
      existing catalogue and chunk modes, refusing unauthenticated with
      the existing `not_found` envelope.

## 2. App

- [x] 2.1 `loadHistory` reads `truncated`/`total_chars`/`id` and renders the
      preview plus a "Show full message" control; the recovered text replaces
      the preview verbatim, with no reflow, summarise or trim.
- [x] 2.2 The control pages chunks by the server's `next_offset` only, fenced on
      login epoch + owner + scope, with visible loading and in-place failure.

## 3. Tests

- [x] 3.1 Add real-store public-route status coverage alongside the existing
      truncated-preview test to also assert `id` and
      `total_chars`, and that a short turn reports `truncated: false`.
- [x] 3.2 `tests/test_conversation_failure_readers.py`: public `read_graph
      target="conversation"` returns the exact tail for a >4000-char reply and
      for a founder message containing astral emoji; offsets are code points.
- [x] 3.3 Authorization: an unauthenticated call and a second account's call
      reach no bytes of the first account's thread.
- [x] 3.4 Node VM harness (`tests/test_onboarding_app.py` pattern): truncated turn
      draws the control, a chunk load paints the full text, a chunk load landing
      after a login-epoch change paints nothing, a failed chunk load shows the
      notice and keeps the preview.
- [ ] 3.5 Regression: chronological order incl. equal-`ts` ties, `platform`
      failure notices, provider/model labels, `consumer_turn_id` dedupe and
      unconfirmed-turn recovery all unchanged.

## 4. Land

- [ ] 4.1 `ruff check`, targeted pytest (temp root outside the repo), plugin
      mirror rebuild, then root's Linux oracle + Codex refute pass.
- [ ] 4.2 Live proof: a >4000-char reply survives an app refresh intact, then
      sync + archive this change.
