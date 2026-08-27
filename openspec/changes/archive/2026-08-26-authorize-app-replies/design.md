# Design

`AppReplyAuthority` accepts the sealed app event and `AppConversationGrant` handoff. It verifies the handoff with the configured custody public key and canonical signing bytes, requires the `append_message` action, then calls a server-owned destination resolver with only the current `AppPrincipalMappingRecord`. It re-resolves the event through `AppPrincipalMappingService` and compares subject, universe, binding, revision, and mapping generation to the signed evidence.

The result contains only the mapped identity references, destination provider/connection/address, response digest, and a server-derived authorization digest. Message body, prompt, model context, credentials, raw event payload, and effect tokens never enter the result. Invalid signatures, stale mappings, mismatched handoffs, malformed digests, unsupported providers, and resolver failures fail closed.
