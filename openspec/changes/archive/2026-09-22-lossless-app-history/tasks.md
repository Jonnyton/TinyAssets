# Tasks — lossless app history

Lead shape review approved the two additive public-surface changes, with both
existing reader modes and unchanged owner/home authority. PR3916 is deployed
at68913d87e96a7fbba0f273ff42832443bc9223ca; evidence below.

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
- [x] 3.5 Regression: chronological order incl. equal-`ts` ties, `platform`
      failure notices, provider/model labels, `consumer_turn_id` dedupe and
      unconfirmed-turn recovery all unchanged.

## 4. Land

- [x] 4.1 `ruff check`, targeted pytest (temp root outside the repo), plugin
      mirror rebuild, Codex regression/refutation plus independent Claude
      approval and hosted Linux required suite. Local Docker oracle was
      unavailable and never started; hosted Linux CI supplies the Linux result.
- [x] 4.2 Live proof: a >4000-char reply survives an app refresh intact, then
      sync + archive this change.

## Verification receipt — 2026-09-22 UTC

- Windows52 focused tests plus3 structured-MCP tests passed. Broader199 passed,
  one symlink-privilege failure reproduced unchanged at base4b6430ed.
- Root reproduced/fixed four actual-JavaScript regressions before release.
  Claude Opus42895 approved runtimef21c27d6; Opus1171 approved receipt-only
  delta370a2c8b. Required Linux CI35694487522 passed; no gate relaxed.
- Hosted image35696481962/deploy35696730874 succeeded; public handles and
  protected SHA passed06:52UTC. Production receipt contains68913d87.
- Ordinary primary app, Chrome4/1346521126, known owner: Show full message
  (4,886 characters) recovers original20:13PDT diagnostic reply after history
  reload through its final five unknowns. Model label remains; no replay.
- Long founder messages, Unicode, account fencing and failure behavior are
  fixture-tested; no organic post-fix owner use or live long-founder-message
  expansion claimed. Long platform notices and non-home writable previews
  remain followups, not grounds to widen owner/home access.
