# universe-connection-lifecycle (delta)

## ADDED Requirements

### Requirement: A rejected credential is replaced in one card

When a connection's stored secret stops being accepted, the owner SHALL be able
to replace it by answering ONE pending request that asks for the new secret and
nothing else. The action type is `rotate_http`, it carries a `destination`, and
the card's fields are secret fields only.

Answering it SHALL replace the secret in the per-universe vault and SHALL make
no other mutation. The connection id, grant id, allowed endpoints, scopes,
access mode, git host, effector consents and workspace consents SHALL be
unchanged, and the next outbound call on that connection SHALL use the new
secret.

The owner SHALL NOT be asked to re-approve reach they already approved, and the
agent SHALL NOT be required to reproduce the endpoint list or the scopes in
order to replace a key.

#### Scenario: the key is replaced and the policy is not
- **WHEN** the owner answers a `rotate_http` card with a new secret
- **THEN** the stored secret is the new one, the connection's stored endpoint
  and scope policy is byte-identical to what it was, and the grant row is the
  same row

#### Scenario: the next call uses the new secret
- **WHEN** an outbound call fires after a rotation
- **THEN** it presents the new secret, with no re-provision and no cache
  invalidation

#### Scenario: nothing is deposited for a destination that holds no key
- **WHEN** a `rotate_http` ask names a destination with no stored connection
- **THEN** the ask is refused when it is RAISED, naming the deposit as the
  correct action, and no tab is shown to the owner

### Requirement: Rotation is bounded to the owner's own connection

A `rotate_http` SHALL be refused, before any write, when the caller holds no
admin ACL row on the universe, when the stored connection belongs to another
principal, when the connection is revoked, or when no live grant binds it to the
universe named in the request. Each refusal SHALL use the uniform absent-resource
envelope, so the surface cannot be used to probe which destinations exist.

A connection whose stored auth scheme is `oauth2` SHALL NOT be rotated by paste:
its secret is a token bundle naming where refresh tokens are sent, so signing in
again is the only rotation.

The number and names of the card's secret fields SHALL come from the STORED auth
scheme, read when the ask is raised and re-checked when it is answered; an ask
whose scheme no longer matches SHALL be refused rather than half-honoured. A
stale observed incarnation SHALL be refused, so a card raised for one deposit can
never rotate a different one.

#### Scenario: another user's deposit
- **WHEN** an admin of the universe who is not the credential's depositor rotates it
- **THEN** it is refused as absent, and the stored secret is unchanged

#### Scenario: another universe's card
- **WHEN** a rotation names a destination that exists in a different universe
- **THEN** it resolves only within the caller's own universe and is refused as
  absent, and the other universe's secret is unchanged

### Requirement: An http credential record records when its secret was stored

Every vault record written for an http connection SHALL carry `deposited_at`,
the time the secret now stored was stored, whether it was written by a deposit,
a rotation, or an oauth2 refresh. The value SHALL come from one shared builder,
because the vault merge replaces the whole slot for this credential type.

#### Scenario: a rotation restamps it
- **WHEN** a connection's secret is rotated
- **THEN** the record's `deposited_at` is the rotation's time, not the original
  deposit's

### Requirement: Removal is not the repair path for a rejected key

Removal remains the way to RETIRE a key: it deletes the secret, the connection
and its grants, frees the destination name, and returns `removed_endpoints` and
`removed_scopes` so a deliberate re-deposit does not start from memory.

Removal SHALL NOT be the repair path for a key the provider stopped accepting.
The served guidance SHALL direct a rotation to `rotate_http` and SHALL say why:
an owner reads a removal card as deletion, and a remove-then-connect pair costs
them a second approval of reach they already granted.

#### Scenario: a key that stopped working
- **WHEN** the agent needs to replace a credential the far side rejected
- **THEN** the guidance it is served names `rotate_http`, not remove-and-connect

#### Scenario: a key the owner wants gone
- **WHEN** the owner asks for a credential to be taken away
- **THEN** `remove_http` is still the action, and its readback is unchanged
