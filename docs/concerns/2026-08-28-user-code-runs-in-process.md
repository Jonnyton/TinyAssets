# User code runs in the daemon process, and that is the real multi-user boundary

**Severity:** P1 · **Filed:** 2026-08-28 from a cross-family multi-user review
**Surface:** `tinyassets/graph_compiler.py`, and everything that shares its process

## The finding

An approved `source_code` node is executed with `exec()` and full builtins
(`graph_compiler.py:1809-1845`). The pattern denylist rejects a handful of substrings
(`:277-279, 1353-1407`) and leaves `open`, `pathlib`, `import os`, `os.environ`, sockets
and ordinary imports available.

So code a user gets approved can read **everything the daemon can read**:

- the live Stripe secret key, the webhook signing secret, the billing entitlement key
- every per-universe credential vault
- every user's WorkOS refresh token
- and it can write any database under the data dir, **including the one that decides who
  has paid** (`storage/subscription_state.py`)

## Why the obvious mitigations do not work

**Encryption at rest does not help.** The key would live in `os.environ` of the same
process the attacker is running in. Envelope encryption or a KMS does not change that:
if this process may call decrypt, so may the code running inside it. That was the plan
before this review and it would have been reassurance rather than defence.

**Narrowing file modes does not help either**, for the same reason. `0600` is worth
having against a detached disk or a stray backup. It is not a boundary against a reader
that is already inside.

## What was done instead, and what it is worth

`source_channel` approval is now limited to an explicit universe allowlist, dark by
default (PR #2629). That bounds **who holds the capability**. It does not bound **what
the capability can do**, and the difference matters: the deployment is safe because a
list is short and correct, not because the system refuses.

## What would actually close it

Either of:

- run universe/provider code in a real OS or container sandbox with no data dir, no
  secret environment, no process inspection, and no unrestricted egress; or
- move session and credential custody into a separate process under a distinct OS
  identity, reachable only through a narrow authenticated API, so the graph process
  never holds the material at all.

Until one exists, "safe for strangers" rests on the allowlist being right.

## Related

`docs/concerns/2026-07-02-no-os-engine-sandbox.md` records the same boundary from the
sandbox side ("in-process confinement only; the denylist fails open"). This file records
what that costs specifically once a second user exists, and why the credential-hardening
work does not substitute for it.
