# P1 - BYO-LLM refresh-token store is worker-readable and adopts a caller-supplied session ref

**Filed:** 2026-08-23
**Re-verified:** 2026-08-26 (premise holds; migrated from the retired board)
**Severity:** P1 -- MUST fix before a second real user

## Source (verbatim)

> **[P1 filed:2026-08-23]** BYO-LLM app refresh-token store (from #2474, now on `715067ce`) MUST fix
> before a 2nd real user (Codex): (1) raw WorkOS refresh tokens in worker-readable
> `/data/app_refresh_sessions/*.json` -> cross-user disclosure + readable by a universe's own
> executing/remixed code; (2) token endpoint adopts caller-supplied `session_ref` (session
> fixation); `session_ref` 7d cred in localStorage. NOT an active single-founder exploit; deferred
> per MVP ship-then-harden. Review: `.tmp/codex-2474-review.txt`.

## Why this file exists

Dropped by the 2026-08-25 board migration -- see
[the LAN/CSRF concern](2026-07-21-unauth-lan-session-leak-csrf.md) for how the gap was found.

## Premise, re-verified 2026-08-26

- `tinyassets/onboarding/__init__.py:58-63` -- `_refresh_store_dir()` is still
  `data_dir() / "app_refresh_sessions"`, one plaintext JSON per handle
  (`_write_refresh_session`, same file). Any code with read access to the data dir -- **including a
  universe's own executing or remixed code** -- can read every user's refresh token.
- `tinyassets/onboarding/__init__.py:304-322` -- the token endpoint still takes `session_ref` from
  the request body and calls `_read_refresh_session(session_ref)` on it. Validation is shape-only
  (`_valid_handle`), so a caller who supplies a handle adopts that session.
- The 7-day `session_ref` credential still lives in browser `localStorage`.

## Standing position

Not an active exploit while there is exactly one founder, and deliberately deferred under the
ship-then-harden rule. **The deferral expires when a second real user exists** -- the disclosure is
cross-user by construction.

Codex review artifact: `.tmp/codex-2474-review.txt` (untracked, local; re-request if absent).
