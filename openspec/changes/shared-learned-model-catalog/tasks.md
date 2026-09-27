## Tasks

The founder chose the simple design on 2026-09-26 after three more elaborate ones were
built and refuted. `design.md` keeps the refutations, because they are the reason this
shape is the shape.

- [x] 1. A typed id is personal forever: `OwnModelHistory`, one per-owner table, no
      shared table at all, and `_own_verified_candidates` putting it on that owner's own
      list.
- [x] 2. `models/<source-kind>.json` plus `public_model_lists.py`: sorted,
      duplicate-free, well-formed identifiers, a malformed file raises rather than
      reading as empty, mtime-keyed cache so a merged PR is picked up without a restart.
- [x] 3. `models/subscription.json` seeded with the known ids including
      `claude-fable-5-1`, so the founder can select Fable.
- [x] 4. `scripts/check_model_lists.py`: valid JSON, known source kind, identifier
      charset, no duplicates, sorted, non-empty. The mechanical half of moderating an
      agent-opened PR; review is the other half, and there is no auto-merge path.
- [x] 5. `_listed_candidates` unions the list into the picker, newest-per-class by the
      id's own shape, never removing an id the universe already had.
- [x] 6. Listed and own-history rows are candidates to GRANT, never admitted, never in
      the routing order, each with its own basis and a needs-access reason.
- [x] 7. Deleted: the shared table, the pending state, the confirmations, the promotion
      threshold, the attestation code and `superseded_by`, plus their spec text and the
      private-selectors concern (resolved -- typed ids never leave the owner).
- [x] 8. The per-owner table classified in both deletion sweeps, with `owner_user_id`
      named so account deletion's by-column sweep finds it.
- [x] 9. Tests: 28 for the list mechanism and the personal store, 9 driving the real
      options document for the grant boundary, 44 for the id-shape derivation. Four
      existing modules had assertions over the FULL offered list made basis-specific or
      admitted-specific, which is more precise than they were.
- [ ] 10. One Codex round (cross-user surface), rebase after #4037, then sync the spec
      delta and archive.
