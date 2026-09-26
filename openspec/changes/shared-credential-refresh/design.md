## Context

Two stores hold a refreshable OAuth credential for one universe:

- an `http` record whose token is the `oauth2` JSON bundle
  (`connection_oauth/tokens.py` encodes and decodes it), and
- an `llm_subscription` record whose `auth_json_b64` is the CLI's own
  `auth.json` document (`onboarding/openai_device.build_codex_auth_json` writes
  that shape after the one-tap sign-in).

Only the first is ever refreshed, and it owns its own locking. The second is
handed to a subprocess and hoped for.

## Goals / Non-Goals

Goals: one implementation of the refresh core; a subscription bundle that is
current before launch; a terminal refusal that keeps the turn alive.

Non-goals: a re-authentication card (own change); changing what the CLI does
inside the jail; any new user-visible surface.

## Decisions

### The primitive takes callbacks, not a credential type

`refresh_credential(...)` owns only the part both callers share — the ordering
and the locks — and knows nothing about either encoding:

```
refresh_credential(
    universe_dir, lock_id, owner_user_id, universe_id,
    read,      # re-read the stored value, INSIDE the locks
    stale,     # does this stored value still need replacing?
    spend,     # the network refresh; may raise RefreshRejected
    records,   # vault records for the rotated value
    failed,    # how this caller reports a failure
) -> T
```

The order is the load-bearing part, and it is the order `ConnectionTokens`
already established: take the per-credential thread lock, then the cross-process
file lock, then the vault's exclusive admission *before* anything is spent, then
re-read (another holder may already have rotated), then decide staleness again on
what was just read, then spend, then write while still holding the vault.

The vault hold comes before the spend because the cross-process admission is
bounded — a refresh that took it only to write could rotate at the provider and
then fail to save, losing the connection. Nothing is spent if the vault cannot be
held, so the caller can retry.

Alternative rejected: a base class with two subclasses. The two callers differ
only in four pure functions; a class hierarchy would put the ordering in a
template method and invite an override of exactly the part that must not vary.

### The credential says where to refresh it; the platform holds no endpoint

The brief said to reuse the token URL and client id the one-tap sign-in uses. The
channel-agnostic ratchet refuses that: it counts vendor names reaching the
runtime, and it can only go down, so importing a source's endpoint constants into
a new module fails the gate. That refusal is right, and the alternative is better.

The stored identity token already names both facts — `iss` is the authorization
server, `aud`/`azp`/`client_id` the client it was issued to — so the issuer is
read off the credential and its token endpoint off that issuer's own RFC 8414 /
OpenID metadata (`connection_oauth.discovery.fetch_server_metadata`, already in
the tree). The substrate learns nothing about any particular source, no URL is
ever constructed by string concatenation, and — unlike a field added at deposit
time — it works for credentials already deposited, which is the whole point when
the P0 is a credential deposited weeks ago.

A credential that does not say where it came from is not refreshed. Spending a
single-use refresh token against a guessed endpoint is the one move with no
undo.

### A rotation renews the accepted source; it does not re-consent it

`_subscription_record_digest` covers the credential material, and that digest
reaches the provider binding. Writing a rotated document therefore has to be
followed by renewal or serving breaks with "connect your provider before
enabling serving".

The renewal used is the landed `_reconnect_manifest` path, whose whole purpose is
"renew an accepted source without interpreting renewal as new model consent". A
refresh is exactly that: same account, same accepted model list, new bytes.

Alternative rejected: excluding the rotating material from the digest. The digest
exists to catch a credential swapped between custody resolution and launch;
narrowing it to make a write cheap would trade that detection for convenience.

### Staleness is decided from the stored document, not from a failure

The platform refreshes when the access token is within the skew of expiry, or
when `last_refresh` is older than the CLI's own refresh threshold — read from the
stored document before launch. Waiting for a failure would mean every stale
credential costs one dead turn first, which is the behaviour being fixed.

A document with no readable expiry and no `last_refresh` is NOT refreshed: it may
be a shape this code did not write, and spending its refresh token on a guess is
the one irreversible move here.

### A terminal refusal is typed; a transport failure is not

`invalid_grant`, a body naming the refresh token as already used, and an explicit
"sign in again" are terminal: the stored secret is finished and no retry of it
helps. Those become `ProviderAuthenticationError`, which the router already
handles by marking the source for reconnect (not cooling it) and continuing to
the next candidate — so the fallback is the router's existing behaviour, reached
by typing the error correctly rather than by new routing code.

A timeout, a 5xx, or an unreachable endpoint is not terminal and keeps its
existing transient classification: the credential is probably fine.

### The launch copy cannot hold a rotation, so nothing is recovered from it

Measured while building: the snapshot's `auth.json` is sealed `0o400`
(`_write_exclusive_snapshot_file`) and the served path binds each credential file
into the jail read-only (`_codex_home_file_mounts`). The CLI's write fails; there
is no rotation in the copy to save. A recovery hook on the cleanup path could
never fire, and an unreachable safety net reads as a guarantee that does not
exist, so there is none — and a test pins the fact the decision rests on.

The reachable case is a MATERIALIZED home the CLI can write (`0o600`). That is
what `adopt_newer_on_disk_document` takes into the vault, and it is the necessary
other half of the next decision: once the vault stops overwriting disk, a rotation
left on disk would otherwise exist only there, while the platform refresh — which
reads the vault — spent the older token beside it.

### Newest wins, decided under the lock

`ensure_codex_home_from_vault` writes the vault document over an on-disk one
whenever the bytes differ, with no notion of which is newer. The first attempt
here was "materialize when absent, never overwrite" — and an existing test
correctly refused it: an owner RE-DEPOSITING is also a rotation, and it has to
reach disk. Not overwriting would have made a re-deposit lose to whatever the CLI
last left.

So the comparison is made, from the `last_refresh` stamps both sides now carry.
A document holds its ground only when its own stamp is readable AND strictly
newer; an unstamped or older one is replaced, which is the previous behaviour for
every case that is not the bug. Unstamped never wins in either direction, because
preferring it is a guess and the refresh token is single-use. The vault side's
stamp is read from its stored DOCUMENT first and the record only as a fallback: a
legacy record carries no stamp, but the document inside it always does, so reading
the record alone would make every legacy deposit lose to its own copy.

### A terminal refusal advances the turn; only capacity used to

Measured, not assumed: `_next_after_capacity` is gated on `capacity_boundary`
returning non-None, so an `auth_invalid` round produced no advance and the turn
ended. The fallback chain did exclude auth, exactly as the brief suspected.
`_next_after_signin` is its sibling, reusing the same `_next_candidate` — so it
can only reach a model already in the owner's accepted order and never widens
authority — and fencing the same two states: a round that also hit capacity
belongs to the capacity path (which has narrowing to do), and a round that may
have committed a side effect is not replayable anywhere.

## Risks / Trade-offs

- Spending a refresh token is irreversible. Mitigated by the vault hold preceding
  the spend, the re-read inside the locks, and refusing to refresh a document
  whose freshness cannot be read.
- The renewal after a write is a second transaction, so a crash between them
  leaves a rotated record with a stale binding. That is the state a re-deposit
  already recovers, and it fails closed (serving refuses) rather than open.
- The primitive adds a module both credential families import. Kept to the
  ordering and the locks, with no knowledge of either encoding, so it cannot
  become a place where one family's rule leaks into the other's.

## Open Questions

None blocking. The re-authentication card is tracked as its own change.
