# Contract review round 4 — blocked

- Reviewed head: `37452f4f1790de4d82c3a25b2c3f35f7dc12c528`
- Base: `62ce277d77738d18a734f155410bc3245b775725`
- Reviewer: independent Codex peer fallback
- Opposite-family availability: Claude CLI had already failed twice in this
  lane with exit 1 and empty stderr; those attempts are not review evidence.

Important: The filesystem contract still refuses a “nonexistent” database or sidecar, contradicting first-use database creation and permitted WAL/SHM creation/deletion. An empty registered universe therefore cannot both create `.tinyassets.db` and satisfy the normative scenario. Scope the existence requirement to the registered directory; database and sidecar paths should be validated only when present. `openspec/changes/establish-private-conversation-custody/specs/conversation-custody/spec.md:11`, `openspec/changes/establish-private-conversation-custody/specs/conversation-custody/spec.md:15`, `openspec/changes/establish-private-conversation-custody/design.md:93`, `openspec/changes/establish-private-conversation-custody/design.md:98`

Important: Operation request digests remain non-portable. Grants and idempotency require the future authority, facade, and ledger to agree on normalized/canonical request digests, but no per-operation preimage schema, domain marker, framing, hash representation, or vectors are defined. Delete is still only “derived” from target digest and reason. Independently implemented issuers/providers can therefore disagree or ambiguously encode requests. Define exact canonical mappings and digest vectors for every operation. `openspec/changes/establish-private-conversation-custody/design.md:63`, `openspec/changes/establish-private-conversation-custody/design.md:71`, `openspec/changes/establish-private-conversation-custody/design.md:212`, `openspec/changes/establish-private-conversation-custody/design.md:244`, `openspec/changes/establish-private-conversation-custody/specs/conversation-custody/spec.md:30`, `openspec/changes/establish-private-conversation-custody/tasks.md:8`

The deleted-target vector recomputes correctly. Exact-head change validation, all 70 strict OpenSpec validations, flow admission, and `git diff --check` passed.

VERDICT: BLOCK
