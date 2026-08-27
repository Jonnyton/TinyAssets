# Requester provider enrollment

## MODIFIED Requirements

### Requirement: Fingerprint-keyed enrollment

The resolver SHALL accept an enrollment whose `owner_user_id` is either the
exact authenticated subject or the server-derived `v1:<64 lowercase hex>`
principal fingerprint. A fingerprint match SHALL materialize the seed with the
authenticated raw subject before persistence.

The resolver SHALL fail closed when fingerprint configuration is missing,
malformed, ambiguous, expired, or uses an unsupported version. It SHALL never
compare or persist caller-supplied identity fields.

#### Scenario: authenticated owner uses the status fingerprint

- **WHEN** an unexpired enrollment names the exact server-derived fingerprint
  for the authenticated subject and the request selects the matching universe
  and provider
- **THEN** the resolver returns a seed materialized with the authenticated raw
  subject and the binding service may persist it under that raw subject

#### Scenario: unknown fingerprint remains held

- **WHEN** the enrollment fingerprint does not match the authenticated subject
- **THEN** resolution returns no seed and no binding row is written

### Requirement: Raw-subject compatibility

Existing exact raw-subject enrollment entries SHALL continue to resolve with
the same owner, universe, provider, digest, budget, and expiry checks.

#### Scenario: existing raw subject entry

- **WHEN** an unexpired enrollment names the exact authenticated raw subject
- **THEN** it resolves exactly as before
