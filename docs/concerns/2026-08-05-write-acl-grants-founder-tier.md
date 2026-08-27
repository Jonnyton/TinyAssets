# `resolve_interlocutor_tier` grants founder tier to any write-ACL holder

**Filed:** 2026-08-05
**Re-verified:** 2026-08-26 (premise holds; migrated from the retired board)
**Severity:** unlabelled on the board; treat as authority-sensitive

## Source (verbatim)

> **`resolve_interlocutor_tier` grants T2/FOUNDER to any `write` ACL holder**
> (`api/interlocutor.py:130`) -- on the MCP path a collaborator reads `founder.md` + commits
> learning. Codex-found 2026-08-05, outside PR #2348's diff.

## Why this file exists

Dropped by the 2026-08-25 board migration -- see
[the LAN/CSRF concern](2026-07-21-unauth-lan-session-leak-csrf.md) for how the gap was found. It sat
in the board's Work table rather than its Concerns list, which is likely why the migration passed
over it; it is a security finding either way.

## Premise, re-verified 2026-08-26

`tinyassets/api/interlocutor.py:129-130` (the cited `:130` is within one line):

```python
if uid and permissions.universe_access_allows(uid, write=True):
    return Interlocutor(tier=T2, actor_id=actor, universe_id=uid)
```

`T2` is the founder tier, and `disclosure_permits` short-circuits to `True` for `T2` (same file)
once the visibility ceiling passes. So a **collaborator** holding a write grant -- not the founder
-- resolves as founder on the MCP path, which is what lets them read `founder.md` and commit
learning as founder-taught canon.

The code comments this as deliberate ("Founder authority is the write/admin grant on THIS
universe"). The concern is that write-collaborator and founder are then indistinguishable, and
founder tier is the one that bypasses the non-founder narrowing.

## Interaction

Compounds [founder-taught canon defaults public](2026-08-06-founder-canon-defaults-public.md): a
write collaborator can commit learning that inherits public visibility.
