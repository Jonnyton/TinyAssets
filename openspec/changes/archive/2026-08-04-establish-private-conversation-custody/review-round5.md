# Contract review round 5 — blocked

- Reviewed head: `dd6aa89819f00b66663b56a767a279eef095c717`
- Base: `62ce277d77738d18a734f155410bc3245b775725`
- Reviewer: independent Codex peer fallback
- Opposite-family availability: Claude CLI had already failed twice in this
  lane with exit 1 and empty stderr; those attempts are not review evidence.

No Critical findings.

Important: The path predicate remains contradictory. The normative scenario applies “non-regular” and “hard-linked” to a `directory/database/sidecar path`; a valid registered directory is not a regular file. The design instead requires the registered path to be a directory and applies regular/single-link checks only to present database/sidecar files. A literal implementation either rejects every valid directory or violates the scenario. Split the directory and file predicates explicitly. `openspec/changes/establish-private-conversation-custody/specs/conversation-custody/spec.md:10-16`; `openspec/changes/establish-private-conversation-custody/design.md:84-100`; `openspec/changes/establish-private-conversation-custody/tasks.md:7`.

Important: The mutation idempotency-key digest remains underspecified. The contract says only “SHA-256 key digest,” without defining the key’s input type/byte encoding, digest representation, validation grammar, or a normative vector, although grant evidence, facade validation, and persistence must agree on it. Independently implemented authorities could hash UTF-8 text, decoded bytes, or another representation and produce incompatible evidence. `openspec/changes/establish-private-conversation-custody/design.md:63-68`; `openspec/changes/establish-private-conversation-custody/design.md:206-212`; `openspec/changes/establish-private-conversation-custody/design.md:245-248`; `openspec/changes/establish-private-conversation-custody/specs/conversation-custody/spec.md:26-31`; `openspec/changes/establish-private-conversation-custody/tasks.md:7`.

Important: The idempotency uniqueness scope is not implementable as written. It declares uniqueness as `(owner_user_id, operation_kind, idempotency_key_digest)`, but each universe has an independent database, so the same tuple can exist in multiple universe databases. This contradicts the proposal’s owner-scoped idempotency unless the namespace is explicitly database/universe-local or a global authority ledger is required. `openspec/changes/establish-private-conversation-custody/proposal.md:14-17`; `openspec/changes/establish-private-conversation-custody/design.md:204-212`; `openspec/changes/establish-private-conversation-custody/design.md:303-306`.

Round 4’s two explicit findings are otherwise closed:

- The registered directory must exist, while absent first-use DB/WAL/SHM files and normal sidecar transitions are permitted.
- All five operation mappings are exact and domain-separated. I independently recomputed create, append, read, export, delete, and deleted-target vectors; every committed digest matches.

The remaining earlier authority, deletion recovery, concurrency, canonical JSON, export, metadata, mirror-existence, test coverage, and dark-boundary findings are closed.

VERDICT: BLOCK
