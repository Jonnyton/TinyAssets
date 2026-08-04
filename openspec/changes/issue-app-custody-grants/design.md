# Design

`AppConversationAuthority` accepts only sealed `AuthenticatedAppEvent` evidence. It asks `AppPrincipalMappingService.resolve` to revalidate the external principal against current founder home, exact admin ACL, configured binding, revision, and mapping generation. A separate server-owned storage resolver supplies the registered private-universe path and platform data root; event payload and message content never reach it.

The authority validates an allow-listed custody action, canonical request and idempotency digests, bounded TTL, and a configured Ed25519 private key. It creates `ConversationCustodyGrantEvidence` using the current mapping generation as `selection_generation` and returns a signed, content-free handoff. The existing custody domain remains responsible for converting that handoff into its opaque non-serializable grant once the packaged mirror lane can accept the matching factory.

Failures are fail-closed: malformed keys, stale mappings, unavailable storage, invalid paths, expired windows, unsupported actions, and replayed grants are rejected. No credentials, payload, conversation text, or provider tokens are persisted.
