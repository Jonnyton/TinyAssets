# Design

## D1 — The trigger is a DELIVERED response, not a word in a message

Every other class in `_classify_external_write` keys on a bracketed
`[error_kind]` tag or on a word anywhere in the summary. Neither works here.
The refusal kinds (`missing_consent`, `soul_authority_denied`,
`no_universe_authority`) are refusals the platform made BEFORE the wire; a dead
credential is the opposite — the request reached the far side and the far side
said no.

`first_effect_failure` writes a delivered failure as
`far side answered HTTP <status>: <body preview>`, and that phrase exists for no
other case. So the class keys on it:

- **401 → `credential_rejected`, unconditionally.** RFC 7235: a 401 means the
  request lacked valid authentication credentials. There is no 401 that a retry
  of the same secret fixes.
- **403 → only where the body says the credential itself is finished.** Most
  403s are "this key may not do that", which is a widening
  (`external_write_refused`) or a permission the owner must change at the
  provider — replacing a working key would be the wrong ask and would cost the
  owner a paste for nothing.

The 403 test is a credential noun and a finality word **within one intervening
word, in either order**, on generic vocabulary only — no service names, and the
body is never inspected for anything else. One word of slack is what real
strings need (`expired_access_token`, `invalid api key`, `bad credentials`,
`token_revoked`, `invalid or expired token` — whose `expired token` is
adjacent). Two words of slack admits `invalid repository for token`, which is a
permission problem, so the gap is one.

The search window is bounded to the ~220 characters after the status, which is
one row's body preview (capped at 160/200 chars) plus its `[kind]` tag. Without
that bound a 401-shaped word in a LATER row of a five-row summary would decide
an earlier row's class.

**Ordering:** after the bracketed refusal kinds (precise), before the refusal
WORD net (a heuristic that would otherwise read "revoked" out of a 401 body and
send the agent to `extend_http`).

## D2 — Rotation writes the vault and nothing else

`rotate_http` performs exactly one mutation: the vault upsert for
`(http, destination)`. It never calls `create_connection`, `grant_connection`,
`set_access_mode` or `extend_http_connection_endpoints`. That is not a promise
kept by care — it is the absence of a code path, and the test proves it by
comparing `ledger.policy_json(connection_id)` and the grant row across the
rotation.

Consequences that fall out for free: the connection id, grant id, endpoints,
scopes, access mode, git host, effector consents and workspace consents survive,
because nothing touched them. The next outbound call picks the new secret up
with no invalidation, because the broker child resolves the vault per request
(`_VaultCredentialResolver.__call__`).

What it refuses, all before any write:

| Condition | Answer |
|---|---|
| caller holds no admin ACL row on the universe | `not_found` (uniform, non-probing) |
| no connection stored for that destination | `not_found` |
| the connection is another principal's deposit | `not_found` |
| the connection is revoked | `not_found` |
| no live grant binds it to THIS universe | `not_found` |
| stored scheme is `oauth2` | `rotation_not_supported` — signing in again is the rotation |
| the secret is malformed for the stored scheme | `connection_setup_invalid` |
| the observed incarnation is stale | `connection_changed` |

Cross-universe is refused twice over: the connection id is derived from
`(universe_id, destination)`, so universe B naming `github` addresses B's own
row; and the grant's `universe_id` is compared anyway, because a derivation is
not a check.

## D3 — The scheme comes from the connection, never from the ask

A rotation carries no `auth_scheme`. The stored one decides how many secret
fields the card has and how they assemble — one box for `bearer`/`header`, two
for `basic`, four for `oauth1a`, using the field names
`_MULTI_VALUE_FIELD_NAMES` already fixes. The scheme is read when the ask is
RAISED, recorded on the action so the owner's tab and the write agree, and
re-read at answer time: if it changed, the answer is refused rather than
half-honoured. Same shape as `remove_http`'s `incarnation` capture.

This is why the ask is verdicted at raise time (`_rotate_ask_verdict`): the owner
must never see a tab that cannot be honoured, which is the rule `extend_http`
already follows.

## D4 — A secret field on a non-deposit action

`_validated_fields` allows `type: "secret"` only on `_DEPOSIT_TYPES`
(`connect_http`, `connect`) — the boundary that stops "compose requests however
you like" from becoming a password harvester. A rotation needs a secret field
and is not a deposit, so the boundary widens to a named set,
`_SECRET_FIELD_TYPES = _DEPOSIT_TYPES | {"rotate_http"}`, and the reason holds
unchanged: the value goes to the vault through a typed handler and is never
recorded as an answer. `_DEPOSIT_TYPES` keeps its own meaning (an action that
CREATES a connection), so nothing that branches on it changes behaviour.

## D5 — One builder for an http vault record

Three writers put a secret in an http slot: the deposit, the rotation, and an
oauth2 refresh. `_merge_single_record` replaces the whole slot for any
non-subscription type, so a field only one writer sets disappears on the next
write by another. `http_credential_record()` is therefore the single definition,
and `deposited_at` means "when the secret now stored was stored" on all three
paths.

## D6 — The old secret is overwritten, never carried

`rotate_http` reads no existing secret: it has no reason to, and a value never
read cannot be logged or attached to an exception. The new one is a local
parameter passed to `write_credential_vault`, whose own error mapping is reused
verbatim — `deposit_failed` for an unexpected fault, with no exception chained
and no message interpolated. `_secret_shape_error` is the only function that
inspects the value, and it returns shape-only text. The projection returns the
connection's redacted fields; `credential_ref` is not among them.
