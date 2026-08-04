# Design

`AppOutboundAdapter` is a server-owned boundary between the already-landed `AppReplyAuthorization` and a trusted transport callback. The callback receives only the validated `ReplyDestination` and private body; callers cannot provide credentials, provider identifiers, or arbitrary URLs.

The adapter computes `sha256:<hex>` over the exact UTF-8 response body using `app-reply/body/v1\0`, and requires it to equal the authorization's response digest. It derives an idempotency key from the authorization digest, reserves that key in a SQLite receipt table, and stores no body. A successful callback result is reduced to a digest of its provider receipt reference. Replays with the same authorization and body return the existing receipt; mismatched authorization or body is rejected. Callback failures are recorded as failed redacted receipts and never leak exception text or credentials.

The transport callback is deliberately injected as a server-owned callable in this slice. A later cloud/Slack lane supplies the real credential-blind implementation and remains responsible for live effect, retry reconciliation, and deployment proof.
