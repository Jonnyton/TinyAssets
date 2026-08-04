# Contract review round 3 — blocked

- Reviewed head: `dee9ea458ca35e1ff968e32b6c472b02c6da74c4`
- Base: `62ce277d77738d18a734f155410bc3245b775725`
- Reviewer: independent Codex peer fallback
- Opposite-family availability: Claude CLI had already failed twice in this
  lane with exit 1 and empty stderr; those attempts are not review evidence.

Important: The round-2 filesystem correction is internally inconsistent. The design requires device/file identity continuity only for an existing primary database, while the normative scenario applies that requirement to directory, database, and WAL/SHM sidecars. The implementation cannot tell whether pre-existing sidecars must retain identity or which SQLite-created/deleted sidecar transitions are permitted. Reconcile the rule and add corresponding tests. `openspec/changes/establish-private-conversation-custody/design.md:93-97`; `openspec/changes/establish-private-conversation-custody/specs/conversation-custody/spec.md:10-12`; `openspec/changes/establish-private-conversation-custody/tasks.md:7`

Important: The retained deleted-target digest still lacks an exact preimage encoding. “Canonical owner/universe/binding/conversation-ID tuple” does not specify a domain/version marker, field names, framing, or whether it is an array or mapping; `tinyassets-canonical-json/v1` requires a root mapping and therefore does not resolve “tuple.” Since delete-request digests and retry correlation derive from this value, implementations can persist incompatible digests. Define the exact bytes and a normative vector. `openspec/changes/establish-private-conversation-custody/design.md:124-135`; `openspec/changes/establish-private-conversation-custody/design.md:206-218`; `openspec/changes/establish-private-conversation-custody/specs/conversation-custody/spec.md:150-156`

Important: The export envelope is structurally enumerated but remains non-canonical at the byte level. Its timestamp members permit any RFC 3339 UTC spelling—such as `Z` versus `+00:00` and varying fractional precision—and the separately returned digest’s representation is unspecified. Those strings remain distinct under the JSON canonicalizer, so conforming implementations can emit different bytes and digests. Specify one timestamp grammar/precision and the digest result format. `openspec/changes/establish-private-conversation-custody/design.md:148-183`; `openspec/changes/establish-private-conversation-custody/specs/conversation-custody/spec.md:109-114`

Important: Several persisted/exported metadata fields are described as “bounded” or “normalized” without an allowed domain, byte limit, or normalization rule. This includes message kind, interlocutor, participant, and source-event references. The promise is therefore neither portable nor testable and permits unbounded non-payload input despite the bounded-content goal. `openspec/changes/establish-private-conversation-custody/design.md:109-116`; `openspec/changes/establish-private-conversation-custody/specs/conversation-custody/spec.md:41-42`; `openspec/changes/establish-private-conversation-custody/specs/conversation-custody/spec.md:75-76`

Important: The corrected mirror-parity command is real, but it cannot prove Task 4.1’s acceptance criterion for these new modules. The invariant explicitly skips a canonical file when its mirror does not exist, so both packaged custody files may be omitted while the command exits successfully. Require the packaging build and/or an explicit existence-plus-byte-equality assertion for both paths. `openspec/changes/establish-private-conversation-custody/tasks.md:17`; `scripts/invariants/mirror_parity.py:57-70`

The exact two-reason deletion domain, deletion-time absence of caller-authored retention boundaries, root/depth/node counting, Unicode-scalar/control escaping, same-account trust boundary, corrected command name, eight-task ceiling, dark production boundary, and two-canonical-module implementation shape are otherwise present.

VERDICT: BLOCK
