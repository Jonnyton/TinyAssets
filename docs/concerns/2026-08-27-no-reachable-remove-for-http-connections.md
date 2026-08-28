# An http connection cannot be removed once deposited

**Filed:** 2026-08-27
**Verified:** 2026-08-27 against `claude/paste-anything-implementation`
**Severity:** P2 — nothing is broken today, but a credential a user wants gone
cannot be taken away through any surface they can reach

## The finding

`ConnectionLedger` has `revoke_grant` and `revoke_connection`
(`tinyassets/storage/outbound_connections.py:3045`, `:3058`). **No operation
exposes either for an `http` connection.** `write_graph target=connection`
routes `connect_llm`, `connect_http`, `connect_compute`, `resolve_connection`
and otherwise falls through to `_cloud_connections_impl`, which is GitHub-Pipes
only. So a user who deposits a key — including one deposited against a host they
did not intend — has no way to withdraw it.

Found while implementing the paste-anything deposit: the receipt sentence was
drafted as *"Change or remove it below"*, and remove does not exist. The wording
now promises only what the surface can do. The spec requirement it partially
fails is `connection-inference` → *"The resulting grant is stated back and
revocable"*.

## Update 2026-08-27 — the ADD half is fixed

Adding endpoints to an existing connection no longer conflicts: a re-deposit
whose endpoint set is a strict SUPERSET extends the connection in place, so a
credential is deposited once and grows with the work. That was the half that
forced a new destination name (and a fresh paste) per endpoint.

**Removal is still unsupported, and this concern still stands for it.** The
reasoning below is unchanged — it is about taking access away, which is the
destructive direction and needs the design decision named there.

## Why it is not a one-liner

Revoking stamps `revoked_at`, and `connect_http`'s conflict check refuses any
re-provision when `resource.revoked_at is not None`
(`tinyassets/api/http_connection.py:~378`). Connection ids are **deterministic**
on `(universe_id, destination)`. So a naive remove permanently burns that
destination name for that universe: the user removes `github`, then cannot ever
deposit `github` again, and the refusal is the opaque `connection_conflict`
which — per
`docs/concerns/2026-08-27-credential-deposit-refusals-are-unobservable.md` —
carries no `detail` at all.

A correct remove therefore has to decide one of:

* re-provision after revoke is permitted when the new policy is otherwise
  identical (revive the row), or
* remove hard-deletes the connection + grant + vault record so the deterministic
  id is free again, or
* the destination is salted so a removed name is not reused.

That is a storage-shape and authority decision in the credential path — the
category `AGENTS.md` says to specify before building, and one needing the
cross-family gate.

## What matters more now

With the deposit confirmation step cut (founder, 2026-08-27), the receipt is the
only place a wrong inference becomes visible. It is currently visible and *not*
undoable. That is the strongest argument for doing this next.

## Related

- `docs/concerns/2026-08-27-credential-deposit-refusals-are-unobservable.md`
- PR #2604 (the deposit this was found in), change
  `openspec/changes/paste-anything-connection-deposit/`
