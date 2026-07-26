## MODIFIED Requirements

### Requirement: Access is controlled on two orthogonal axes — visibility and ownership

Universe access SHALL be decided on two independent axes: visibility (`public_read`, where a universe
with no recorded rule is publicly readable by default, private only when explicitly set, and failing
closed on any real rules-read error) and ownership (a `universe_acl` grant set of `read`/`write`/`admin`).
Anonymous callers SHALL be able to read public universes only; reads of a private universe and all writes
SHALL require the appropriate grant (`write` or `admin` for writes). An admin grant SHALL NOT make a
universe private — visibility and ownership are not conflated — and SHALL NOT confer authority to
attach, resolve, use, replace, rotate, or delete a provider credential binding owned by another principal.
Provider credential use SHALL additionally require the exact credential-owner principal persisted in
verified request and assignment authority plus matching universe, provider,
`host_principal_id`, current active `host_principal_generation`, assignment
scope, and provider-assignment generation from trusted control-plane state; a
mismatch, revoked/expired host principal, or stale generation SHALL fail closed
even when the caller is a universe admin. Background, resumed,
retried, and scheduled execution SHALL NOT substitute an ambient HTTP subject, daemon process identity,
current workspace member, changed ACL member, founder, or maintainer for that persisted credential owner.
Privileged dispatch actions SHALL additionally pass a per-action scope gate that accepts either the
fine-grained action scope or the coarse effect grant. This model lives in
`tinyassets/api/permissions.py` and the scope gate in `tinyassets/auth/middleware.py`.

#### Scenario: anonymous reads public but not private
- **WHEN** an anonymous caller reads a universe with no visibility rule
- **THEN** the read is allowed
- **AND** the same caller reading a `public_read=False` universe is denied

#### Scenario: write requires a write or admin grant
- **WHEN** an authenticated actor without a `write`/`admin` grant attempts a universe write
- **THEN** the write is denied even though the actor is authenticated

#### Scenario: rules-read error fails closed
- **WHEN** the visibility rule for a universe cannot be read due to a real error
- **THEN** the universe is treated as not publicly readable

#### Scenario: universe admin is not provider credential authority
- **WHEN** an admin presents a credential binding owned by another principal or host
- **THEN** configuration refuses to attach it and credential resolution and provider launch fail closed
- **AND** the admin grant does not permit attachment, use, replacement, rotation, or deletion of that binding

#### Scenario: resumed work retains the persisted credential owner
- **WHEN** work resumes after the original request session ends or universe membership changes
- **THEN** credential checks use the owner frozen in verified request and assignment authority
- **AND** no ambient or newly privileged identity substitutes for that owner

#### Scenario: host-principal lifecycle fences provider consumers
- **WHEN** device-key rotation advances the host-principal generation or revocation/lost-key recovery terminates the old host principal
- **THEN** provider launch and every protected custody/assignment commit recheck current host-principal status and generation independently from provider-assignment generation
- **AND** prior-generation or revoked consumers cannot dereference a new secret, start a launch, or commit an in-flight result/cutover

#### Scenario: broader administration cannot widen credential scope
- **WHEN** a principal has universe admin or another broad grant but the binding excludes the requested provider action or capability
- **THEN** credential attachment, resolution, and provider launch fail closed
- **AND** no role, empty capability ceiling, or opaque reference widens the exact binding scope
