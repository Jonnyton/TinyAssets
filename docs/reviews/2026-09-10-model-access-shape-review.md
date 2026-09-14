# Explicit model access: shape review and disposition

September10 2026. Claude75211 reviewed8b5ff440 and model-access-confirmation.md,
exit0 after331s: ADAPT. The read-only legacy_source correction was accepted;
the next access UI needed three adaptations, all applied before implementation:

1. bind resets the agent to configured. The confirmation now explicitly includes
   reconnecting and the UI calls set_serving with the revision returned by bind.
2. Free-only conversion may have no compatible models. Show the fresh advisory
   count and refuse a zero-count conversion. If legacy bind succeeds but re-enable
   is not confirmed, offer explicit restoration through the same two primitives.
   The restore first verifies current home and exact still-configured revision;
   changed/working state is not overwritten. No uncertain write is replayed.
3. Return server-derived access_method on sources and legacy_source; the browser
   uses that discriminator and the server bind_key, never prefix reconstruction.

AGREE on the core complete-map/owner/revision shape and free-only default;
legacy projection is safe configuration, not a receipt or candidate. Full final
response: output/model-access-shape-review.md.

Optional observations retained: revoked accepted members are not silently dropped
to make expansion succeed; removal needs separate confirmation. A missing
legacy_source cannot offer conversion even if choice_authority says legacy.
Browser errors never string-match raw detail. Updated the stale binding docstring.
Generated definition IDs prevent native-alias collisions in normal registration.

This is pre-build shape evidence, not implementation or live approval. No host
grant, account, workflow or feedback-PR mutation was performed by the operator.
