# Independent pre-build review

September 19, 2026 UTC. Claude Fable 5.1, peer session 78007, terminal exit 0 after 225 seconds. Read-only; no recursive delegation or full suite. Base origin/main bcac8d1a. This is shape evidence, not exact-head approval or deployment proof.

I'll read the proposal and the cited source paths in parallel, then check the specific helpers named in the brief.

One last read: what `_source_custody` derives the credential reference digest from, since that decides whether a redeposit can match the old assignment.

**Decision: DISAGREE_EVIDENCE on two points of the proposed shape, AGREE on the rest. VERDICT at the end.**

The stale concern is confirmed stale. `remove_http` exists at `tinyassets/api/http_connection.py:757`, is routed at `tinyassets/universe_server.py:1186`, and the pending-request path applies it at `tinyassets/api/pending_requests.py:1490`. Delete `docs/concerns/2026-08-27-no-reachable-remove-for-http-connections.md` in the same change.

## Release-blocking

- **Lock choice is wrong as written.** The shape says "the same per-universe lifecycle serialization as connect_http", but `connect_http` holds no lifecycle lock at all. The only serialization is inside `write_credential_vault` (`credential_vault.py:635`) and `forget_credential` (`credential_vault.py:586`), both taking the exclusive admission lock, which raises on re-entry (`provider_assignment.py:1020`). Wrapping `remove_http` in that lock will crash. The suitable lock is `_gesture_lock(uid)` at `onboarding/serving.py:69`, already the outer lock for `ensure_founder_serving` (`serving.py:210`) and `ensure_bootstrap_binding` (`model_bootstrap_binding.py:23`). Hold it around the whole disconnect and let each inner step take admission itself.

- **Resurrection on redeposit is real and must be closed.** The custody record digest is built from grant id, connection id, credential ref, owner and universe (`credential_vault.py:1208`). All of those are deterministic on universe plus destination. So after removal and redeposit, `adopt_connection_grant_custody` finds the digest unchanged (`credential_vault.py:1229`) and hands back the old reference id, generation and digest. `_same_custody` (`provider_serving_binding.py:483`) then matches the stale assignment candidate, and the new key inherits the old approval. Fix: delete the `llm_credential_custody` row for the connection's service key inside the fence transaction. Do not fold incarnation into the digest formula. That would bump generation on every existing connection at its next adopt and push every user into recovery.

- **The `unassigned` state has no writer and a manifest hazard.** The schema allows it (`provider_assignment.py:1051`) but nothing stores it. `store_provider_assignment_in_transaction` (`:1195`) will accept it, but `_validate_assignment_manifest` (`:1152`) does `next(...)` for the anchor and raises a bare StopIteration if the removed source was the anchor and you drop it from candidates. Policy: if the removed source is a non-anchor candidate, rewrite the manifest without it at a new assignment generation and keep state `ready`. If it is the anchor with other candidates, re-anchor to one of them. If it is the only source, keep the last-known fields as the tombstone and set state `unassigned`. `_reconnect_manifest` already refuses anything not `ready` (`serving.py:254`), so the tombstone cannot be renewed silently.

- **Classification must recognize the tombstone.** `model_setup_state` returns recovery on any assignment row (`model_setup.py:35`) before it looks at definitions (`:37`). Add a `disconnected` outcome for state `unassigned` owned by the caller, checked first. Definitions have no unregister (`providers/definition.py`) and should stay, since they are user config.

- **Bootstrap reconnect cannot reuse `ensure_bootstrap_binding`.** It raises on any assignment (`model_bootstrap_binding.py:26`) and requires revision 1, default payload, and status `configured` (`:39`). A disconnected universe's agent will be at a higher revision. Keep those guards intact. Add a separate explicit owner "begin reconnect" that accepts the `unassigned` tombstone and passes the existing binding id at its current revision into the normal `bind_model_access` request. Do not touch the agent binding during disconnect; `set_serving(enabled=False)` changes its revision, which the user said must not happen.

## Existing helpers to reuse

- Work authority fence: `revoke_in_transaction` with `ProviderWorkBindingFence(current)` (`provider_work_authority.py:1990`), same pattern as `provider_serving_binding.py:744`.
- Crash ordering: fence binding, rewrite assignment, delete custody row in one store transaction first. Then call `remove_http`. A crash between the two leaves authority gone and the inventory still listing the connection, so a retry is idempotent and fail-closed.
- Inventory projection: `_project` (`http_connection.py:282`) is already secret-free. Auth checks: mirror `remove_http:787-827` plus `require_founder_home`.

## Follow-up hardening, not blocking

- `delete_connection` has no `expected_incarnation` parameter, unlike the CAS at `outbound_connections.py:3594`. Add it so the UI's observed incarnation is enforced at the delete, not only checked before it.
- A stale `bind_model_access` approval stays pending on refusal (`pending_requests.py:1441`). I did not read `execute_action`; verify it re-derives custody from the current row, then have disconnect resolve open requests as superseded.
- The gesture lock is process-local. Cross-process deposit versus remove remains unserialized. Acceptable for a single daemon; note it.

VERDICT: ADAPT

My lane was a bounded, read-only, six-minute independent review, and the verdict above is complete. The listed dispatches belong to other lanes in a different worktree, and the running connection-removal review is this one, so there is nothing further I can advance within my read-only mandate.


