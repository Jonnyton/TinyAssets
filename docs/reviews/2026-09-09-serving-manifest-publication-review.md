# Independent storage/publication review

September 9, 2026. Claude returned ADAPT at exact clean head83fd8ec587ca188fb008d015a8fe4df5b6f1b8a0, terminal exit0 after428s. Reproduced30 focused tests and supplied an equality probe identifying the untested unsorted first-publication defect. The lead accepts the precise value-object canonicalization correction; regression evidence follows in the publication proof. This is not an APPROVE or live capability claim. No fourth repeat candidate-authority review is being launched merely to seek a clean verdict; remaining integration still needs its own actual code and required independent evidence before landing.

Review of exact head `83fd8ec587ca188fb008d015a8fe4df5b6f1b8a0` is complete. The storage and publication design holds up, but I found one actionable correctness defect in the fresh-publication path that also disables the failed-recovery fence, so the verdict is ADAPT with a single precise fix.

## What I actually reviewed

- Worktree at the exact head, confirmed clean before and after review. Read-only, no subagents, no edits.
- Full source of `tinyassets/provider_serving_binding.py`, `tinyassets/provider_assignment_manifest.py`, and the storage diff in `tinyassets/provider_assignment.py` across d38d150a..83fd8ec5.
- Both test files, the two proof docs, and the connection-model-authority design.
- Every non-test reader of the assignment root, every caller of the bind entry point, the store connection manager, and the packaging mirror.
- Ran the focused suite with cache writing disabled: 30 passed in 3.26s. Plus one in-memory equality probe against the manifest module.

## AGREE

- **v1 byte compatibility.** The digest payload is unchanged when no manifest is present and only switches to schema 2 with the extra field when one is, at `tinyassets/provider_assignment.py:1008-1021`. The storage test pins the legacy bytes.
- **Migration and read atomicity.** Column added idempotently, and the public loader now opens an explicit read transaction so root and children come from one snapshot at `tinyassets/provider_assignment.py:1184-1185`. The store uses WAL, so this is a true snapshot.
- **Root/member/anchor integrity.** Readback recomputes the manifest digest, requires the anchor child to equal the root fields, and rejects empty membership, at `tinyassets/provider_assignment.py:1060-1073`. Row digests bind universe and generation, so cross-universe copies fail.
- **Non-circular signing.** Candidate identity excludes binding generation and digest, the assignment digest covers the manifest, bindings carry the assignment digest, and the per-row digest covers the issued binding afterwards. Phase 2 asserts the ready and pending assignment digests agree at `tinyassets/provider_serving_binding.py:753`.
- **Replay equality.** Replay requires the same manifest presence, the same provider-to-access document map, then revalidates every member's binding, live custody, and all three ceilings inside one snapshot at `tinyassets/provider_serving_binding.py:558-603`. Adding the invocation ceiling makes legacy replay strictly stricter than before.
- **Independent fallback custody.** Member validation never consults the anchor's credential, at `tinyassets/provider_serving_binding.py:857-913`. Live grant checks go through the full owner, universe, revocation, and rotation gate.
- **Phase 1 durability and phase 2 all-or-nothing.** Pending commits complete membership first. Phase 2 verifies the exact pending root, revalidates custody per member, issues all bindings, updates the agent, and stores ready in one transaction on one database file. The store closes without commit on exception, so partial work rolls back.
- **Recovery fencing, isolation, removal, older rows.** All verified in source and covered by tests. Legacy roots ignore leftover children; removed members fail membership; older generations are never loaded.
- **The v2 hold cannot be bypassed.** The only place that mints serving authority is the shared validator, which refuses any manifest-backed root at `tinyassets/provider_serving_binding.py:810-813`. Authority revalidation in `provider_assignment.py:395-500` demands exact binding equality, and any rebind to v2 rotates the anchor binding, so a stale v1 authority cannot survive the transition. The API handler rejects any payload other than exactly `{"provider"}` at `tinyassets/api/custom_agents.py:286-295`, and the onboarding caller passes no model_access. No caller-owned ModelConfig or policy reaches this path.
- **Mirror parity.** All three mirrored runtime files are byte-identical to canonical.

## DISAGREE_EVIDENCE: caller-ordered ModelAccess breaks fresh publication and the recovery fence

The canonical form sorts model identifiers and cost caps only in the document, not in the dataclass. `document()` sorts at `tinyassets/provider_assignment_manifest.py:63-68`, and `from_json` rebuilds a sorted tuple at lines 80-83. Both dataclasses keep default equality, so an in-memory member built from the caller's object at `tinyassets/provider_serving_binding.py:459-468` and 638-646 is not equal to its own readback whenever the caller's order is not already sorted.

Probe output against the module at this head:

```
sorted model_ids   in-memory == readback: True
unsorted model_ids in-memory == readback: False
unsorted cost_caps in-memory == readback: False
documents equal despite dataclass inequality: True
```

Consequences on a fresh publish with, for example, `ModelAccess("explicit", ("y", "x"))`:

1. Phase 2 compares the readback to the in-memory pending with dataclass inequality at `tinyassets/provider_serving_binding.py:669` and raises `assignment changed before publication` every time.
2. The failed-recovery fence at `tinyassets/provider_serving_binding.py:186-195` performs the same comparison, mismatches for the same reason, and returns without writing `failed`. The root is left durably in `pending`.
3. Retrying advances the generation and repeats. The previous ready assignment is already gone. The owner cannot publish that membership at all.

The state is still deny-all, so this is a correctness defect, not a security hole. It is squarely in the code under review, contradicts the design's order-independence contract, and the existing reorder test does not catch it because its first publish is already sorted and its second call takes the replay path at `tests/test_serving_manifest_publication.py:136-156`.

Exact correction: canonicalize in the value object so equality and storage agree. In `ModelAccess.__post_init__`, after validation, set `model_ids` to its sorted tuple and `cost_caps` to its name-sorted tuple via `object.__setattr__`. Then add one publication test whose first publish supplies unsorted ids and caps and asserts a ready root. Comparing by document or digest at the two sites would also work, but canonicalizing the dataclass is the smaller and safer change.

## Non-blocking notes

- **Future work, not a regression:** the eligibility readers in automations registration, the scheduler auth check, and the assigned-queue runtime selector treat any `ready` root as serving-eligible without consulting the manifest hold. Once v2 activates, they should mirror admission to avoid an always-failing loop. Not reachable today.
- **Optional hardening:** a corrupted v2 manifest raises before the bind entry point's try block at `tinyassets/provider_serving_binding.py:556`, so an owner cannot rebind over corruption without operator repair. Fail-closed and arguably intended.
- **Optional hardening:** the one-time `ALTER TABLE` in the public loader runs outside a transaction, so two first-touch processes could race to a duplicate-column error. A retry heals it.

VERDICT: ADAPT
