## Why

The deployed requester-enrollment seam requires a raw WorkOS subject in a
server secret. The authenticated chatbot intentionally exposes only the
server-derived principal fingerprint, so a legitimate owner cannot enroll
without an opaque ID lookup and the phone path remains held.

## What Changes

- Accept a configured `v1:<hmac>` principal fingerprint as an enrollment key.
- Derive the same fingerprint server-side from the authenticated subject and
  the existing identity-fingerprint secret; never accept a caller-supplied
  identity or raw credential.
- Materialize a binding seed with the authenticated raw subject only after the
  fingerprint match, preserving existing owner/universe equality and replay
  fences.
- Keep raw-subject entries supported for migrations and fail closed on malformed
  or ambiguous fingerprint entries.

## Impact

The server-only enrollment resolver, focused security tests, and packaged
runtime mirror change. Deployment may now use the redacted fingerprint shown by
the authenticated status surface, but the server remains the sole authority
that converts it to the raw authenticated subject.
