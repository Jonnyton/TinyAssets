# Cloud agent-command duplication fence

Freshness: 2026-08-02 14:12 PT. Current main is `47248cf1`; open draft PR #2145 is conflicting, and its active cloud worktree and remote are clean at docs-only head `672698d1`, based on merge-base `244266f2`. Runtime/continuation code was last changed by `fe624bc9`.

## Current contradiction

Main now owns the independently reviewed invocation seams:

- PR #2155: the inert invocation root in `tinyassets/agent_runtime_invocation.py` and its read-only store.
- PR #2160: the inert command and typed budget in `tinyassets/agent_runtime_command.py` and its read-only store.

The active cloud branch still carries a second `AgentInvocationCommand`, `AgentInvocation`, admission writer, and SQLite aggregate in `tinyassets/agent_runtime_invocation.py` and `tinyassets/storage/agent_runtime_invocation.py`. Its command pins `authorizing_principal_digest`, `grant_evidence_set_digest`, and `grant_evaluated_at`. The #2160 design review rejected that shape because command derivation would depend on invocation-derived principal evidence and would freeze grants that must remain live-checked.

The new `fe624bc9` continuation code consumes this duplicate aggregate and compares those frozen digests before minting provider authority. Publishing it without reconciliation would restore a second command/root owner beside #2155/#2160 and make the exact-head reviews inapplicable.

## Required reconciliation before draft #2145 can advance

1. Rebase the cloud lane onto current main and preserve the canonical #2155/#2160 record shapes instead of resolving conflicts back to the duplicate types.
2. Keep `authorizing_grant_generation` scoped to the authenticated request/admission grant. Revalidate manifest/runtime grants live after admission; do not pin runtime-principal or live grant-set digests into the command.
3. Put the only future writer inside one atomic transaction that consumes the authenticated provider-work draft and creates the linked `ProviderWorkBinding`, command, and invocation root—or none.
4. Rework provider receipt/claim/reservation/continuation code to consume those canonical records, with forged self-consistent rows unable to mint a carrier or positive authority.
5. Re-run the combined authority/runtime suite and obtain fresh independent exact-head security review after reconciliation.

This is a coordination fence, not a rejection of the continuation goal. The generic cloud continuation is required for the approved MVP; it must sit downstream of the one canonical admission authority rather than become a parallel mint root.
