# `sync_universes_from_filesystem` clears `universes.metadata_json`

**Filed:** 2026-09-27 | **Verified:** 2026-09-27 | **Severity:** P2
**Source:** cross-family review of PR #4045 (gpt-6-astra), which called it
floor-class. Downgraded to P2 here on evidence, stated below so the call can be
checked rather than trusted.

## The defect

`daemon_server.sync_universes_from_filesystem` calls `ensure_universe_registered`
with `display_name=` but no `metadata=`. That helper's conflict clause is
`display_name=excluded.display_name, metadata_json=excluded.metadata_json`, and
`metadata` defaults to `{}` — so every sync resets each universe's
`metadata_json` to `{}`. The display name survives, because sync passes it.

Reviewer's reproduction: register metadata `{"only_copy": "owner data"}`, write a
`universe.json` carrying the owner's name, call `sync_universes_from_filesystem`.
The name survives; the metadata becomes `{}`. Sync reads no replacement metadata,
so "an intended re-sync from disk" does not explain destroying it.

That reasoning is sound, and PR #4045 fixed the same shape in eight other callers.

## Why P2 and not floor

The floor is *unrecoverable loss of user data*. Nothing is lost here, because
nothing writes the field:

- **No production caller passes `metadata=` to `ensure_universe_registered`.**
  Checked 2026-09-27 across `tinyassets/` and `scripts/`: zero call sites. The
  reviewer's `{"only_copy": "owner data"}` was constructed in the probe, not
  produced by any code path.
- **Nothing reads `universes.metadata_json` either** — no reader of
  `get_universe(...)["metadata"]` outside the tests added by #4045.
- `display_name`, the field that *is* populated (a learned universe name, via
  `set_universe_display_name` from `api/universe.py`), is passed by sync and
  survives. It is also a projection of the universe's own `identity.md`, so it has
  a second copy.

So the bug is real and currently inert: it destroys a field no code fills or uses.
It becomes floor-class the moment anything stores something in it, which is exactly
why it is written down rather than forgotten.

## The fix

The root fix is one line and removes the whole class rather than this instance:
make `ensure_universe_registered` build its conflict clause from what the caller
actually passed — update `display_name` only when given, `metadata_json` only when
given, `host_path` always. Then no FK-only or partial caller can ever clobber, and
`register_universe_if_absent` stops being the only safe door.

It was left out of #4045 because the lead scoped `sync_universes_from_filesystem`
out of that lane, and because changing a shared helper's conflict semantics wants
its own diff and its own measurement rather than riding a data-loss fix.

Delete this file when `ensure_universe_registered` stops overwriting fields the
caller did not supply.
