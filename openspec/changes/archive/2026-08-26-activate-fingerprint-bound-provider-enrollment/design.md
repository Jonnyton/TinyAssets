## Identity binding

An enrollment entry's `owner_user_id` may be either a canonical raw WorkOS
subject or `v1:<64 lowercase hex>` produced by the existing
`TINYASSETS_IDENTITY_FINGERPRINT_KEY` HMAC. The resolver computes the
fingerprint for the request's raw subject and compares it in constant time.

Fingerprint entries are request-bound: a matching seed is materialized with
the current raw subject before `ProviderWorkBindingService.issue`, so the
ledger never stores a fingerprint in an owner column. Missing or invalid key,
unknown version, duplicate entries, or a fingerprint that matches zero or more
than one entry all remain held.

No new public MCP action or credential path is introduced. The manifest remains
server-only and all caller-supplied owner, fingerprint, budget, digest, and
credential fields remain ignored.
