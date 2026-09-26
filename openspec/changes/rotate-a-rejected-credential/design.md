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

The 403 test has two rules, on generic vocabulary only — no service names, and
the body is never inspected for anything else.

**Compact:** a credential noun and a finality word **within one intervening
word, in either order**. One word of slack is what the real strings need
(`expired_access_token`, `invalid api key`, `bad credentials`, `token_revoked`,
`invalid or expired token` — whose `expired token` is adjacent). Two words admits
`invalid repository for token`, which is a permission problem, so the gap is one.

**Copular:** `<credential noun> … is/was/has been <invalid|expired|revoked|not
valid|…>`, bounded by characters and stopped at a sentence break. A real 403 body
reads *"The security token included in the request is invalid."* — five words
between the noun and the word, which the compact rule deliberately will not span
(Codex refute-review, P1 #3). The wider reach is sound here and would not be for
the compact form, because a copula binds its predicate to its SUBJECT: the
decoy `"The repository is invalid"` has a non-credential subject and does not
match, and `"Invalid target selected for this token"` has no copula at all.

The search window is **one row's body**: from the status to the start of the next
delivered-status phrase, then capped at 220 characters (a row's preview is 160 or
200 chars plus its `[kind]` tag). A fixed 220-character window was wrong — Codex
refute-review, P1 #2: a 403 with a SHORT body borrowed `invalid_token` out of a
following 404 and classified as a dead key. A marker sitting past the producer's
own preview cut is still lost; that is a MISS, which leaves the row in its
existing class.

**Ordering:** after the bracketed refusal kinds (precise), before the refusal
WORD net (a heuristic that would otherwise read "revoked" out of a 401 body and
send the agent to `extend_http`).

## D2 — Rotation writes the vault and nothing else

`rotate_http` makes exactly one state change: the vault upsert for
`(http, destination)`. It never calls `create_connection`, `grant_connection`,
`set_access_mode` or `extend_http_connection_endpoints`. That is not a promise
kept by care — it is the absence of a code path, and the test proves it by
comparing `ledger.policy_json(connection_id)` and the grant row across the
rotation.

Consequences that fall out for free: the connection id, grant id, endpoints,
scopes, access mode, git host, effector consents and workspace consents survive,
because nothing touched them. The next outbound call picks the new secret up
with no invalidation, because the broker child resolves the vault per request
(`_GeneralVaultCredentialResolver.__call__`).

Two narrower statements than "it never touches the ledger", because that one is
falsifiable and a claim a reviewer can break is worse than a smaller one (Codex
refute-review, P2 #8): constructing `ConnectionLedger` migrates schema and
backfills an empty incarnation, as it does for every reader; and the vault upsert
reads the existing record in order to merge it, though the handler never looks at
the old secret itself.

What it refuses, all before any write:

| Condition | Answer |
|---|---|
| caller holds no admin ACL row on the universe | `not_found` (uniform, non-probing) |
| no connection stored for that destination | `not_found` |
| the connection is another principal's deposit | `not_found` |
| the connection is revoked | `not_found` |
| no live grant binds it to THIS universe | `not_found` |
| the connection does not read this vault slot (type/class/provider/`credential_ref`) | `not_found` |
| stored scheme is outside `_DEPOSITABLE_AUTH_SCHEMES` | `rotation_not_supported` |
| the stored record has no recorded depositor | `credential_ownership_transfer_unsupported` |
| the secret is malformed for the stored scheme | `connection_setup_invalid` |
| the observed incarnation is stale | `connection_changed` |

Three of those deserve their reason stated.

**The vault slot.** A rotation writes `vault://http/<destination>`. A connection
whose `credential_ref` names a different key would be reported as rotated while
the secret it actually presents was untouched — a success that changed nothing,
which is the worst outcome available here (hard rule 8). `connect_http` compares
every one of these as an immutable field; not comparing them would be the
inconsistency, not the check.

**The scheme set.** Fail closed on the set the deposit door accepts rather than on
a list of known exceptions, so a scheme the engine learns to sign later is not
rotatable by paste until someone decides it is. Two land there today and fail for
different reasons: `oauth2` (its value is a bundle naming where refresh tokens go,
so only the owner's own sign-in may write it) and `none` (no credential is sent at
all, so a pasted value would be stored, never used, and reported as a repair —
Codex refute-review, P2 #5).

**The depositor.** A record with no ownership row is refused by
`write_credential_vault` itself. `credential_vault.http_deposit_refusal()` is one
read-only predicate over the same rows that writer compares, so the preview can
apply it and the owner is never asked to paste into a card that cannot land
(Codex refute-review, P2 #4).

Cross-universe is refused twice over: the connection id is derived from
`(universe_id, destination)`, so universe B naming a destination addresses B's own
row; and the grant's `universe_id` is compared anyway, because a derivation is
not a check. Both halves have their own test — the derivation one passes with the
comparison deleted, which is why the second exists (Codex refute-review, P2 #6).

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

## D5b — An answer that lands must close its card, or say it did not

`resolve_request` catches a storage fault and returns `False`. If the vault write
succeeded and that returned `False`, reporting `"answered"` would leave a pending
card the owner believes is done — and because a rotation does not move the
incarnation, answering it again later would overwrite a NEWER key with the older
value the owner typed then (Codex refute-review, P1 #1).

So `_rotate_answer` checks the return and, when it is `False`, returns
`request_resolution_unconfirmed` + `request_pending`, saying the key WAS replaced
and that answering again with the same value settles it. Re-answering is
idempotent, which is what makes this recoverable rather than something to undo.
Same shape as the `bind_model_access` branch, which already did this.

The identical gap in `_deposit_answer`, `extend_http` and `remove_http` is
pre-existing and deliberately NOT changed here: altering what a deposit returns on
a rare failure path is its own change with its own tests, and folding it in would
put an untested contract change under an unrelated review. Filed as
`docs/concerns/2026-09-26-an-answer-can-land-while-its-card-stays-open.md`.

## D6 — The old secret is overwritten, never carried

`rotate_http` reads no existing secret: it has no reason to, and a value never
read cannot be logged or attached to an exception. The new one is a local
parameter passed to `write_credential_vault`, whose own error mapping is reused
verbatim — `deposit_failed` for an unexpected fault, with no exception chained
and no message interpolated. `_secret_shape_error` is the only function that
inspects the value, and it returns shape-only text. The projection returns the
connection's redacted fields; `credential_ref` is not among them.
