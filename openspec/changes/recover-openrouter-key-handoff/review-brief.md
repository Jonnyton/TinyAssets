# Independent shape review request

Review `proposal.md`, `design.md`, delta spec and tasks. No manual ingress
runtime has been written. UI-only branch work is incomplete recovery and not
offered for release. Owner: Codex cloud_runtime_mvp; reviewer: Claude Fable,
dispatched only by lead.

Please return AGREE / DISAGREE_EVIDENCE with a code citation /
DISAGREE_CONCERN, distinguishing basic MVP safety blockers from later hardening.

1. Is exact `{preset_id,key}` on existing authenticated same-origin
   `/mcp/app/model-connect/deposit_key` the smallest safe acquisition boundary,
   reusing `model_bootstrap.complete_bootstrap` and existing unanswered
   `bind_model_access` approval without generic inference or paid expansion?
2. Resolve the concrete inherited account-deletion/vault-write race described
   in design. Is coordinating `delete_account` with existing per-universe
   exclusive provider admission and checking tombstone/owner under the vault
   write lock sufficient and minimally scoped? Name additional mutation fences
   needed after discovery, avoiding deadlocking nested admission locks.
3. Validate direct secure-input mode, clear-before-await, login generation,
   non-replay and user-directed existing `resume` recovery semantics.

Supporting independent Codex inspection is not cross-family approval. Lead
owns the production browser and deploy. Another builder owns durable PKCE
pending state in `hosted_model_auth.py`; this lane has no edits to it.
