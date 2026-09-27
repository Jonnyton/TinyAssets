# The public connector's `structuredContent` carries the whole payload

**Filed:** 2026-09-26
**Verified:** 2026-09-26 — read of `tinyassets/universe_server.py`, `pytest tests/test_model_options_api.py` (91 passed)
**Severity:** P2

## Source (verbatim)

From the live bug that produced the bounded-results fix (free account, turn
`8dc8ada56b8e4d1cbfd2e4f37a111e7d`, 2026-09-26 23:27Z):

> The user asked their universe to build a custom UI. The agent called
> `read_graph target="model_options"` and got a **1,274,067-byte** tool result,
> the whole provider model catalogue. That blew the free model's context
> ("selected model cannot fit this inference context"), and the turn was
> abandoned after 5 rounds.

## The finding

The fix landed a ceiling on the **engine** MCP surface — the served agent's own
tool results (`tinyassets/engine_result_bounds.py`, applied as one middleware in
`engine_mcp_server.py`). The **public** connector surface is still unbounded on
the half that most clients actually parse:

- `universe_server._faithful_text_content` bounds the **text** block at
  `_MCP_TEXT_CONTENT_MAX_CHARS = 6000` and appends a truncation pointer;
- `universe_server._structured_return` sets `structured_content` to the **full**
  parsed payload, with no ceiling at all.

So a chatbot client reading `structuredContent` — which is the shape the Apps
SDK path exists to serve — receives the same 1.27 MB that killed the engine turn.
The text-block cap is not protection for those clients; it is protection only for
text-only ones.

## Why it was not fixed in the same change

Narrowing what `read_graph target=model_options` returns on the public surface
contradicts an as-built requirement:

> `openspec/specs/live-mcp-connector-surface/spec.md`, "Shared unpowered model
> catalogue": *The read_graph handle SHALL accept target=model_options without
> changing its arguments or direct string/structured-adapter return contract.*
> … Scenario "Complete choices, not a first-page sample": *all protocol-bounded
> choices survive in structured content* … *limit does not silently hide models
> from this catalogue target.*

`tests/test_model_options_api.py::test_full_catalogue_survives_read_limit_and_adapter`
asserts exactly that (71 models survive `limit=1`), and it is right to: the
owner's own model picker in the app reads this and must see every choice. A
ceiling on `structured_content` would break the picker, so this is a spec change
(public MCP surface → OpenSpec change directory required), not a bug fix.

## What resolving it looks like

An OpenSpec change that separates the two readers of one document, because they
want opposite things:

- the **app picker** needs the complete catalogue (today's requirement, keep it);
- a **model** reading the same handle needs a bounded projection.

Candidate shape: keep the complete document as the picker's contract and give the
connector surface the same compact projection the engine now uses
(`tinyassets/engine_read_views.compact_model_options`), selected by the caller
rather than by the server guessing. Do not resolve it by capping
`structured_content` generically — that turns the picker's complete read into a
silently clipped one, which is the failure mode the spec scenario was written
against.

## Re-verification

Check that `_structured_return` still hands `structured_content` the unbounded
parsed payload, and that the spec scenario above is still present, before acting
on this.
