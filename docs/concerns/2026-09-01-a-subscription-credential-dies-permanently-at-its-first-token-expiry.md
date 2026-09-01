# A subscription credential dies permanently at its first token expiry

**Filed:** 2026-09-01, from the founder's universe
`u-01kxm1vszd8hwp7em418asq8h9` going dark and staying dark.
**Severity:** P0 — it ends every universe's ability to run turns, it is
guaranteed rather than probabilistic, and re-depositing only restarts the timer.
**Cross-family review:** Codex, **CONFIRMED**, and it corrected the mechanism I
proposed. See *What review changed*.

## The finding

A served universe's Codex OAuth bundle **cannot be refreshed**, so it works
until its tokens expire and then never works again.

The served call path:

1. authority copies the vault bytes into a unique snapshot
   (`provider_assignment.py:1321`);
2. that snapshot directory goes into the routed call config
   (`providers/router.py:597`);
3. `subprocess_env_for_provider` replaces vault materialization entirely and
   points `CODEX_HOME` at the snapshot (`providers/base.py:589`);
4. the Linux launcher remaps it again to `/codex-home`
   (`providers/codex_provider.py:704`, `:794`);
5. the snapshot is **deleted after the call** (`provider_assignment.py:1371`).

The Codex CLI is told to persist credentials to a file
(`cli_auth_credentials_store = "file"`), so it refreshes into `CODEX_HOME` —
which is a disposable copy. Nothing promotes a changed `auth.json` back to the
vault; `cleanup_llm_credential_snapshot` (`credential_vault.py:1532`) only
deletes.

So the vault's `auth_json_b64` is frozen at deposit time, forever.

## What review changed

I filed this as "the materializer overwrites the refreshed token on the next
call" (`credential_vault.py:1876`). **That overwrite is real but is not the
served path** — it is reachable for non-snapshot universe calls through
`provider_auth_env_overrides` (`credential_vault.py:2013`). For a served turn
the truth is worse and simpler: *the refresh cannot be persisted in the first
place*, because the directory it lands in is disposable. Codex also confirmed
the child's copy is effectively read-only for this purpose.

The distinction matters for the fix: this is not a clobber to avoid, it is a
promotion path that does not exist.

## Live evidence

Captured through the app, `provider_diagnosis` on a served turn:

```json
{"provider": "codex", "status": "failed", "skip_class": "auth_invalid"}
```

`codex exec` exits 1 in under 5s with auth tells in stderr
(`providers/codex_provider.py:932` → `diagnostics.classify_unavailable`).
Failures began **2026-09-01T03:23:56Z** and never self-recovered across several
container restarts. `codex exec` from the HOST works normally throughout —
because the host's own `auth.json` refreshes in place.

## Why re-depositing is not the fix

It works, until the new bundle expires, and then the universe dies the same way.
Anyone told to "just reconnect" will be back. Say so when telling them.

## The shape of a correct fix (Codex, F3)

None of the obvious three is safe alone:

* *only write when absent* — preserves a refresh but cannot tell a refresh from
  a genuine re-deposit, and does not help the disposable served snapshot;
* *blind copy-back* — the right direction, unsafe without the machinery below;
* *compare token expiry* — expiry and `last_refresh` prove neither authority nor
  refresh lineage, and concurrent users of a single-use refresh token still
  invalidate one another.

The smallest design compatible with sealed launches:

* give Codex a **writable per-call working copy**, never direct vault access;
* hold **one cross-process lock for the whole credential lineage** — not the
  current per-snapshot `.lock` — across refresh and promotion;
* have the trusted parent promote a changed `auth.json` by **compare-and-swap
  against the exact starting deposit generation**;
* **reject promotion** if the vault was re-deposited concurrently, or if the
  stable principal/account identity changed;
* treat OAuth refresh as volatile evolution *within* one credential generation;
  an authenticated re-deposit remains an authority-generation change.

## Why it is not fixed in the change that found it

That is a vault write on an authority path, from a provider-call path, with
concurrency — the four properties that most want their own change, their own
review and a test that can fail. Codex supplied a reproduction route that needs
no live OpenAI account (F5).
