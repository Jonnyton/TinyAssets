# Contract review round 6 — blocked

- Reviewed head: `896c0814c0ed2ea2f87412551e37940785e87356`
- Base: `62ce277d77738d18a734f155410bc3245b775725`
- Reviewer: independent Codex peer fallback
- Opposite-family availability: Claude CLI had already failed twice in this
  lane with exit 1 and empty stderr; those attempts are not review evidence.

No Critical findings.

- Important: Non-canonical base64url encodings remain admissible. A key ending with 42 `A`s plus `B` matches the grammar and permissively decodes to 32 zero bytes, despite not being the canonical encoding. Different implementations may therefore accept or reject it. Require zero trailing pad bits—such as by decoding and re-encoding for exact equality—and test rejection. `openspec/changes/establish-private-conversation-custody/design.md:206-216`; `openspec/changes/establish-private-conversation-custody/specs/conversation-custody/spec.md:64-73`; `openspec/changes/establish-private-conversation-custody/tasks.md:7`.

- Important: Rejecting a “raw provider event identifier” before grant consumption is unimplementable. A provider identifier that happens to match the key grammar is indistinguishable from randomly generated key text, and detached evidence contains only its digest. Make this an issuer-side prohibition or add verifiable issuance provenance and consume it before applying that check. `openspec/changes/establish-private-conversation-custody/design.md:206-216`; `openspec/changes/establish-private-conversation-custody/specs/conversation-custody/spec.md:64-73`; `openspec/changes/establish-private-conversation-custody/tasks.md:7`.

Round 5’s separate directory/file predicates and universe-local idempotency findings are closed. The full-string key digest and all request/deleted-target vectors recompute correctly. Exact-tree OpenSpec change validation, all 70 strict validations, flow admission, and `git diff --check` passed.

VERDICT: BLOCK
