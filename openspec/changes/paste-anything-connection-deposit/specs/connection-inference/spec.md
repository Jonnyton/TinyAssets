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

### Requirement: The deposit completes without a confirmation step

Pasting SHALL be sufficient to create the connection. The interface SHALL NOT
interpose a confirmation click, a preview gate, or any other step between the
paste and the deposit (founder decision, 2026-08-27, on an explicitly offered
tradeoff).

#### Scenario: A paste that resolves

- **WHEN** a user pastes credential material that the resolver can identify
- **THEN** the connection is deposited and usable with no further interaction

### Requirement: The resulting grant is stated back and correctable

After depositing, the interface SHALL state in one plain sentence what the key
was granted — method, host, path — and SHALL offer changing it. This is a
receipt, not a gate: it appears after the connection exists and blocks nothing.

The receipt SHALL NOT offer an action the surface cannot perform.

Removal now exists (`forget_http`) and SHALL remove the grant, the connection
row, and the stored secret — all three. Revoking the grant alone leaves the
material on disk, and reporting that as removed would be false. The row is
DELETED rather than tombstoned, so the destination name is free for re-use: ids
are deterministic on `(universe, destination)`, and a `revoked_at` tombstone
would refuse every later deposit of that name.

#### Scenario: A deposit lands

- **WHEN** the connection is created
- **THEN** the user is told this key may POST to that exact path and nothing
  else, and how to change it

#### Scenario: The inference chose wrongly

- **WHEN** the receipt names a host or path the user did not intend
- **THEN** the user can correct it there by supplying the right values, without
  needing to know where connections are otherwise managed

### Requirement: Pasted material is data, never instructions

The resolver SHALL treat everything pasted as untrusted content to read, never
as instructions to follow. Prompt-injection content in a paste SHALL NOT be able
to steer the proposed host, path, or scheme.

This requirement carries the weight that a human confirmation step would
otherwise have carried: with no review before deposit, the paste is the only
thing steering where a credential becomes usable.

#### Scenario: An injected instruction in the paste

- **WHEN** the pasted material contains text directing the resolver to a
  different host or a broader path
- **THEN** the proposal is unaffected by it, and the host is derived only from
  credential shape and the user's own intent line

#### Scenario: A host that appears nowhere and cannot be justified

- **WHEN** the resolver cannot ground a host in either the credential's
  identity or the intent line
- **THEN** it reports that it could not resolve, rather than depositing against
  a guessed host

### Requirement: A wrong or absent proposal is correctable, never a dead end

When the resolver cannot produce a policy, or produces one the user judges
wrong, the interface SHALL expose the explicit fields — destination, host, path,
methods, auth scheme — so the user can supply the right values and proceed.

The pasted material SHALL still be cleared from the page before any request, as
the manual form already does: a credential must not sit in the DOM while a
request is in flight, and that outranks the convenience of not re-pasting. The
failure message SHALL therefore say the credential needs pasting again, rather
than leaving the user to discover an empty box.

#### Scenario: Inference fails

- **WHEN** the resolver cannot identify the service
- **THEN** the explicit fields are shown, and the message says what to do next
  including that the credential must be pasted again
- **AND** the pasted material is no longer present in the page

#### Scenario: Inference is wrong

- **WHEN** the proposed path is not the endpoint the user wants
- **THEN** the user can enter the values they want in the explicit fields, and
  those are what get deposited

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
