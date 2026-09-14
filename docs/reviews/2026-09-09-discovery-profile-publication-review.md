Independent Claude review, September9,2026: exact c8d0dbab, exit0 after264s. APPROVE; no actionable defects. Optional coverage and diagnostics noted below. No new integration is approved by implication.

Independent review of head c8d0dbab380aadd573f2ecf4e28454c39c5652fe, diff 4e21c3d5..c8d0dbab. Worktree verified clean at that head.

**What I actually reviewed.** All three documents. The full post-change text of the storage transaction, the readback path, the spec table and both validators, the new protocol module, the whole API handler, and the server dispatch region. The helpers the new code depends on: verb-within-scopes, endpoint allowlist including query rules, URL canonicalization, the universe resolver, ACL listing, the verified definition lookup, and the compute grant gate. All forty new tests. I confirmed the four runtime mirror copies are byte-identical to source. I ran only the scoped test file:

```
python -m pytest -q -p no:cacheprovider tests/test_model_discovery_capability.py
40 passed in 4.93s
```

I did not run the voice, HTTP, policy or mirror groups. The 279 figure is the author's claim. I verified voice by reading, not by execution.

## AGREE

Every claimed property is backed by code I read.

- **Spec table is the single dispatch point.** Kind validation, configure and readback all resolve through one table (`tinyassets/storage/outbound_connections.py:1907-1927`). Readback re-validates through the same dispatcher (`outbound_connections.py:3504`), so a corrupted row with an added flag raises rather than loading. Test covers this.
- **Voice is unchanged.** The voice validator is the old body with the kind pinned. The verb check is the same membership test with the same error string (`outbound_connections.py:3446-3450`). The single-URL allowlist call is the same. The fence is skipped when no expected grant is passed. The API keeps home resolution, admin ACL, current-serving resolution and the voice-specific error in their original order, since the discovery branch parses the payload with swallowed errors and only diverts on an exact kind match (`tinyassets/api/provider_capability.py:46-55`).
- **No serving dependency for discovery.** The handler never touches founder home or the serving resolver. The fixture makes both raise and the API path passes.
- **Verified definition and owner/universe isolation.** Lookup recomputes the content address and checks the universe bucket (`tinyassets/providers/definition.py:272-303`). The store's error is a ValueError subclass (`definition.py:67`), so the handler's except clause catches tampering as uniform not_found. Owner mismatch, foreign universe, tampered ref and copied row all return the same envelope. The ACL and universe resolution match connect_compute exactly (`tinyassets/api/compute_connection.py:143-150`).
- **Grant gate then fence.** The handler reuses the compute grant validator (`compute_connection.py:74-120`), then re-reads the grant row under BEGIN IMMEDIATE and compares id, revocation, connection, owner against both grant and resource, universe and granted_at (`outbound_connections.py:3416-3434`). Revoking between handler read and write is refused, and the fence applies to removal too.
- **GET, query, benchmark, bearer.** Discovery uses the same verb-within-scopes function as the transport, so full-channel admits GET on declared hosts only (`outbound_connections.py:531-559`). In exact mode the allowlist refuses any undeclared query parameter (`outbound_connections.py:1751-1810`), so the pinned output_modalities=all query must already be granted. The protocol compares path and query as exact strings, and the benchmark path rejects any query (`tinyassets/providers/discovery_protocols.py:19-26`). Auth scheme must equal the protocol's bearer requirement (`outbound_connections.py:3451-3457`). Each URL field is allowlist-checked in the same transaction (`outbound_connections.py:3459-3465`).
- **Closed payload and descriptor.** The API field set is exact for both enable and disable. Caller-supplied owner, connection or grant fields are refused. The stored document is only protocol, catalogue_url and optional benchmark_url. No owner_filtered flag exists anywhere in the value type.
- **Connection-scoped sharing and no mutation.** Row keyed by connection and kind. Removal through a second definition sharing the grant clears it. Tests assert the connection view, grant and definition are identical after publish.

## DISAGREE_EVIDENCE

None. I found no claim in the proof document contradicted by the code.

## DISAGREE_CONCERN

None blocking.

**Actionable bugs:** none found.

**Optional hardening:**

- **Envelope inconsistency for the owner's own connection.** A missing GET scope or wrong auth scheme becomes uniform not_found (`provider_capability.py:189-190`), while an allowlist miss becomes provider_capability_invalid. Ownership was already proven before either, so nothing leaks. The owner just cannot tell "add GET scope" from "no such definition".
- **Non-string benchmark_url is silently dropped.** A list or number for the optional field coerces to absent and publication reports configured (`outbound_connections.py:1825-1835`). Voice's privacy_url has the same pre-existing behavior. Fail-closed, but surprising.
- **Untested paths.** No test publishes on a full-channel connection, and none proves a path-allowed endpoint without a declared query refuses the pinned query. Both behaviors are correct by the existing allowlist code, but this kind has no fixture for them.
- **Whitespace-padded kind via the voice path.** A voice caller sending a padded kind reaches the storage layer, where the fence refuses it for lack of grant context. Correct outcome, odd message.

**Future integration, not regressions:** ACL is not re-read under the write transaction, matching voice and connect_compute. The definition store is not re-read under the transaction, but the grant it points to is fenced. Refresh, snapshot provenance, selection, HTTP tools and UI remain unimplemented as the design states.

VERDICT: APPROVE
