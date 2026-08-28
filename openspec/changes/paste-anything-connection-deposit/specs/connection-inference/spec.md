## Purpose

Derive a proposed outbound connection policy — destination name, auth scheme,
host, path template, and methods — from whatever credential material a user
pastes, so that connecting a service requires no knowledge of the platform's
egress vocabulary and works for services the platform has never been taught.

## ADDED Requirements

### Requirement: Inference is model-derived, never a service table

The resolver SHALL derive the proposed policy from a model's reading of the
pasted material's shape. It SHALL NOT depend on an enumerated list of known
services, because a table cannot cover the services the platform has not been
taught, which is the stated purpose of the capability.

#### Scenario: A service the platform has never been coded for

- **WHEN** a user pastes credential material for a service that appears nowhere
  in the codebase, with an intent line naming what it should do
- **THEN** the resolver returns a proposed policy for that service's real host
  and endpoint
- **AND** no code change was required to support it

#### Scenario: A preset exists for the same service

- **WHEN** a user pastes material for a service that also has a preset button
- **THEN** the resolver's proposal is produced by the same model path as any
  other service, and the preset remains only a form-filling convenience

### Requirement: Secret material is never transmitted for identification

The resolver SHALL receive only the non-secret shape of the pasted material:
field labels, public credential prefixes, hostnames and URLs present in the
paste, and value lengths. It SHALL NOT receive the high-entropy remainder of any
credential value. The secret SHALL continue to reach the server only through the
existing deposit call.

#### Scenario: A pasted bearer token

- **WHEN** the paste contains `github_pat_ABC...XYZ` (93 characters)
- **THEN** the resolver receives the prefix `github_pat_` and the length, and
  does not receive the remaining characters

#### Scenario: A paste containing several credentials

- **WHEN** the paste contains four OAuth values, a bearer token, and a client
  secret
- **THEN** the resolver receives each value's label, prefix and length only
- **AND** the confirmed deposit carries only the values the chosen auth scheme
  needs

### Requirement: Extra pasted material is tolerated, not refused

The resolver SHALL accept material containing values the connection does not
need, and SHALL ignore them rather than failing. Pasting more than necessary is
the expected user behaviour.

#### Scenario: A whole credentials page is pasted

- **WHEN** a user pastes an entire developer-portal page including unrelated
  ids, secrets, and prose
- **THEN** the resolver selects the values the proposed auth scheme requires and
  ignores the rest, returning a policy rather than an error

### Requirement: The user confirms a boundary stated in plain language

Before any deposit, the interface SHALL present the proposed policy as one plain
sentence naming the method, host, and path, and SHALL state that nothing else is
permitted. The deposit SHALL NOT proceed without the user's confirmation.

#### Scenario: Confirming a proposal

- **WHEN** the resolver proposes `POST api.github.com/repos/o/r/pulls`
- **THEN** the user is shown that this key may POST to that exact path and
  nothing else
- **AND** the credential is deposited only after the user confirms

#### Scenario: Declining a proposal

- **WHEN** the user does not confirm
- **THEN** no vault write, connection, or grant is created

### Requirement: A wrong or absent proposal is correctable, never a dead end

When the resolver cannot produce a policy, or produces one the user judges
wrong, the interface SHALL expose the explicit fields — destination, host, path,
methods, auth scheme — pre-filled with whatever was inferred, so the user can
correct and proceed.

#### Scenario: Inference fails

- **WHEN** the resolver cannot identify the service
- **THEN** the explicit fields are shown, empty or partially filled, with the
  paste preserved

#### Scenario: Inference is wrong

- **WHEN** the proposed path is not the endpoint the user wants
- **THEN** the user can edit the proposal before confirming, and the edited
  values are what get deposited

### Requirement: The egress boundary is unchanged by inference

Inference SHALL only decide what policy is proposed. The allow-list validator,
the per-endpoint method gate, and the requirement that a path template be an
absolute path SHALL apply unchanged to a confirmed proposal. A proposal SHALL
NOT be able to express a broader grant than a hand-authored deposit can.

#### Scenario: A proposal that would widen the grant

- **WHEN** the model proposes a host-wide or wildcard path
- **THEN** the proposal is rejected or narrowed before it is shown, because no
  such grant is expressible
- **AND** the confirmed deposit is validated by exactly the same code path as a
  manual one
