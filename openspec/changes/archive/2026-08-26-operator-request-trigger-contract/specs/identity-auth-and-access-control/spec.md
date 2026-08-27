## MODIFIED Requirements

### Requirement: Access is controlled on two orthogonal axes — visibility and ownership
Universe access SHALL be decided on two independent axes: visibility
(`public_read`, where a universe with no recorded rule is publicly readable by
default, private only when explicitly set, and failing closed on any real
rules-read error) and ownership (a `universe_acl` grant set of
`read`/`write`/`admin`). Anonymous callers SHALL be able to read public
universes only; reads of a private universe and all writes SHALL require the
appropriate grant (`write` or `admin` for writes). An admin grant SHALL NOT
make a universe private. Privileged dispatch actions SHALL additionally pass a
per-action scope gate that normally accepts either the fine-grained action
scope or its coarse effect grant. The ordinary `submit_request` leg of priority
admission follows that normal rule. The separate `submit_priority_request`
elevation leg and capability administration's `grant_capabilities` leg are
least-privilege exceptions: each requires its exact named, exact-universe grant
and SHALL NOT be satisfied by a coarse effect, ACL role, wildcard, host, or
environment identity. This model lives in `tinyassets/api/permissions.py` and
the scope gate in `tinyassets/auth/middleware.py`.

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

#### Scenario: exact elevation grants are not coarse effects
- **WHEN** an actor passes ordinary submit through its fine-grained or coarse-write route but lacks exact `submit_priority_request`
- **THEN** the actor has no priority elevation authority
- **AND** write/admin/costly effects or ACL roles cannot substitute for that exact grant

## ADDED Requirements

### Requirement: Operator priority is an exact-universe capability composed with ordinary write authority
A new operator-priority admission SHALL require one request-local conjunction
of an authenticated subject, ordinary `submit_request` action authorization,
`write` or `admin` ACL access to the exact target universe, a requested
priority weight greater than zero, and an active `submit_priority_request`
capability grant for that same subject and universe. The ordinary submit leg
MAY use the canonical fine-grained-or-coarse-effect rule, but coarse effects,
ACL roles, host/runtime identity, environment variables, caller-supplied
evidence, and wildcard capability grants SHALL NOT satisfy the separate
priority leg.

#### Scenario: all authority elements admit positive priority
- **WHEN** the authenticated subject passes ordinary submit authorization, has target-universe write/admin ACL, requests positive priority, and holds an active exact-universe priority grant
- **THEN** the verdict permits `operator_request`, or retains `owner_queued` for a valid directed assignment
- **AND** binds subject, universe, grant generation, accepted weight, and policy version

#### Scenario: zero weight is an explicit ordinary opt-out
- **WHEN** the subject may submit, has write/admin ACL, and requests priority weight zero
- **THEN** the request is admitted as `user_request` with accepted weight zero, or `owner_queued` when validly directed
- **AND** holding a priority grant does not relabel the zero-weight request as operator work

#### Scenario: non-zero priority without the exact grant fails
- **WHEN** an ordinarily authorized subject requests positive priority but lacks an active exact-universe priority grant
- **THEN** admission returns `priority_authorization_required` with zero persistence
- **AND** the request is not silently demoted to ordinary work

#### Scenario: missing ordinary authority rejects all admission
- **WHEN** the subject lacks authentication, ordinary submit authorization, or target-universe write/admin ACL
- **THEN** admission fails before idempotency lookup or persistence
- **AND** holding a priority grant alone does not create ordinary write authority

### Requirement: Priority grants are versioned, expirable, revocable, and administratively controlled
Only a trusted capability-administration service SHALL issue or revoke
`submit_priority_request`. The authenticated issuer SHALL hold both `admin` ACL
on the exact universe and exact `grant_capabilities` action authorization. Each
grant SHALL record subject, universe, issuer, issue time, optional expiry,
revocation time, and monotonically increasing generation. Wildcard priority
grants SHALL be rejected. Repeated revocation SHALL be idempotent; regrant after
revocation SHALL create a higher generation instead of erasing history. An
optional expiry SHALL be exclusive: the grant is active strictly before
`expires_at` and inactive at or after that instant.

#### Scenario: authorized exact-universe issuance records a generation
- **WHEN** an authenticated issuer has universe admin ACL and exact `grant_capabilities`
- **THEN** the service may issue an exact-universe priority grant with generation, issue time, and optional expiry
- **AND** the service stores no credential or bearer token

#### Scenario: unauthorized issuance fails closed
- **WHEN** an issuer lacks either exact-universe admin ACL or exact `grant_capabilities`
- **THEN** no priority-grant row is created or changed
- **AND** the attempt cannot fall back to host, environment, or coarse-effect authority

#### Scenario: revocation is prospective
- **WHEN** a priority grant is revoked after an admission committed
- **THEN** new admissions cannot use that generation
- **AND** the committed task is not silently relabeled, demoted, or cancelled

#### Scenario: expiry is enforced at an exact boundary
- **WHEN** a grant is evaluated before, exactly at, and after its `expires_at`
- **THEN** only the pre-expiry evaluation can authorize a new positive-priority admission
- **AND** exact-boundary or later requests return `priority_authorization_required` with zero persistence

### Requirement: Replay reauthorizes access before revealing admission state
Every replay SHALL authenticate the caller and re-evaluate ordinary submit
authorization plus current target-universe write/admin ACL before looking up or
returning an idempotency record. ACL loss SHALL return
`universe_access_denied` without revealing whether the key, admission, Request,
or task exists. With ACL intact, later revocation or expiry of only the
priority grant SHALL not duplicate or rewrite a committed admission;
same-key/same-body replay SHALL return its historical result, while a new
admission SHALL use current authority.

#### Scenario: replay after ACL loss is non-enumerating
- **WHEN** the original actor replays after losing target-universe write/admin ACL
- **THEN** authorization fails before idempotency lookup
- **AND** the response contains no admission, Request, task, digest, receipt, or key-existence evidence
- **AND** the original task remains unchanged

#### Scenario: replay after priority revocation or expiry returns committed history
- **WHEN** ACL and ordinary submit authorization remain valid but the historical priority grant is revoked or expired
- **THEN** same-key/same-body replay returns the original result with `idempotent_replay=true`
- **AND** a new key re-evaluates current priority authority
