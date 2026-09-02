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

## The part that makes it permanent rather than merely stale

The jail cannot write the file at all. `/codex-home` is a **tmpfs** with the
credential files bound in **read-only** (`providers/codex_provider.py:161`,
`--ro-bind ... /codex-home/auth.json`), and the mount comment states the intent
plainly: *"The credential bytes stay immutable; only scratch files can be
created beside them."*

That comment also records the same class of bug from **2026-08-22**: a read-only
home broke codex's own lock file -- *"cannot open lock file /codex-home/.lock:
Read-only file system", exit 73 in 56 ms -> "codex exhausted"*. The fix made the
HOME a tmpfs so scratch files could be written, and left `auth.json` read-only.

**OAuth refresh tokens rotate on use.** So the first refresh a universe attempts
either fails outright (read-only) or, if it ever succeeded anywhere, invalidated
the stored token while the new value was discarded. Either way the deposited
bundle becomes permanently unusable at the first rotation, which is exactly the
observed shape: working for weeks, dying at a precise instant, never recovering.

"Immutable credential bytes" is a coherent security stance for a static secret
and is simply incompatible with a rotating one.

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


## First implementation attempt: REJECTED (2026-09-01)

Built on `claude/honest-provider-failure` and rejected by Codex before landing.
Three defects, recorded because the next attempt must not repeat them.

**The lock topology makes the chosen location impossible.** The provider holds
`provider_assignment_admission().shared(universe)` across the call AND its
`finally` (`provider_assignment.py:1177`, `:1366-1386`). Promotion asked for
`exclusive(universe)` inside that, and the admission explicitly rejects
shared-to-exclusive reentrancy (`:923-928`). Independently,
`write_credential_vault` takes that same exclusive lock again
(`credential_vault.py:634`), so even outside the shared context it
double-acquires. Both raise `RuntimeError`, which the promotion's own
`except` converted to `return False`.

So it would have shipped, silently done nothing, and reported nothing. **The
promotion cannot live inside the provider's `finally`.** It needs a location
outside the shared admission, or an admission API that supports upgrade.

**The identity gate is forgeable.** `_codex_identity` trusted the
child-controlled `account_id` without binding it to the tokens. A hostile bundle
keeps the original `account_id` and swaps the principal, or sets
`auth_mode: "apikey"` with an attacker-chosen `OPENAI_API_KEY` that the record
merge then persists. An identity check the writer can satisfy is not one.

**Concurrent single-use rotation is unresolved.** Two overlapping calls both
refresh; one necessarily holds an invalidated token; nothing decides which
promotion wins, so the vault can end up storing the dead one.

**And the tests did not catch any of it**, because they call the promotion
directly and never through the provider path that holds the lock — the same
"tested the helper, not the wiring" gap that this repo hit twice more the same
day. A test for the next attempt has to drive the real call path, where a
silent `False` is indistinguishable from success.


## A simpler design the rejection points at (recommended over patching the promotion)

Every defect in the rejected attempt is a cost of ROUND-TRIPPING the credential:
the lock topology, the forgeable identity gate, and the concurrent-rotation
winner problem all exist only because a refresh has to travel from a disposable
snapshot back into the vault.

**The host does not have this problem**, and the reason is instructive: the host
refreshes `auth.json` in place, in a directory that persists. Nothing is
promoted because nothing is copied.

So the alternative is to give a universe the same shape: a **persistent,
per-universe, writable CODEX_HOME**, bound into that universe's own jail. The
scaffolding already exists -- `resolve_codex_home` (`credential_vault.py:1970`),
`_codex_home_from_record` (`:1959`), `_secret_artifact_dir` (`:108`) -- and the
non-snapshot path already uses it.

What it removes:

* no promotion, so no CAS, no lock ordering, no shared-to-exclusive upgrade;
* no identity gate to forge, because the refreshed bytes never re-enter the
  vault as a decision -- the file IS that universe's credential store;
* no concurrent-rotation winner problem beyond what the CLI itself handles,
  which is the same situation every ordinary codex user is already in.

What it must preserve, and what a review has to attack:

* **the isolation floor** -- one universe must never reach another's home. This
  is the property that actually matters, and it is per-universe directory
  containment rather than per-call disposability;
* the sealed-snapshot design was chosen deliberately ("rotation-stable,
  sandbox-read-only"), so the case for replacing it has to be made against the
  threat it was defending, not merely asserted;
* plaintext credential material now persists between calls rather than being
  reclaimed per call, which is a real change to the exposure window and
  interacts with `scavenge_orphaned_launch_credentials`.

**Recommendation for the next session:** cost this against fixing the promotion
before writing either. The promotion path is known to need a location outside
the shared admission, an unforgeable identity binding and a rotation winner --
three hard problems. The persistent-home path removes all three and trades them
for one question about the exposure window, which is a question with an answer.
