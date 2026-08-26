# P2 - `_current_actor` env fallback bypasses `permissions.py`

**Filed:** 2026-06-30 | **Verified:** 2026-07-22 | **Re-verified:** 2026-08-25 | **Severity:** P2

> Migrated verbatim from `STATUS.md` on 2026-08-25 when the board was retired.
> Source dates preserved. Premise re-verified against `origin/main` @ `8cbf9769`.

## Source (verbatim)

slice-3 F5 / escrow F1: `_current_actor` env fallback (engine_helpers.py:192) bypasses permissions.py.

## Re-verification 2026-08-25 - path corrected

The row cited `engine_helpers.py:192`. That path no longer exists; the function moved to
**`tinyassets/api/engine_helpers.py:177-192`**. The premise holds exactly:

```python
def _current_actor() -> str:
    try:
        from tinyassets.auth.middleware import current_identity
        identity = current_identity()
        subject = (getattr(identity, "user_id", "") or "").strip()
        if subject and subject != "anonymous":
            return subject
    except Exception:
        logger.exception("failed to resolve request auth identity")
    return os.environ.get("UNIVERSE_SERVER_USER", "anonymous")   # <- the fallback
```

An environment variable can name the acting identity for ledger attribution when authenticated
request state is unavailable - including when `current_identity()` raises. The docstring frames this
as intentional ("Authless paths and direct tests keep the legacy env-var fallback"), which is why it
is P2 and not higher, but it remains an identity that never passed through `permissions.py`.

Related: a retired or unresolved identity should fail closed, never inherit an ambient one.
