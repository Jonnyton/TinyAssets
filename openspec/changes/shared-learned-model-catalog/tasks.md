## Tasks

- [ ] 1. `model_class_and_version(model_id)` in one module: numeric runs and date
      stamps are version tokens, every other token is class, an unparseable id is
      its own class. No vendor or model names.
- [ ] 2. Table-driven tests for it over varied shapes — dashes, dots, date stamps,
      named suffixes (`-sol`, `-astra`), no version at all, and ids that cannot be
      split. Include the ordering cases (different tuple lengths, ties).
- [ ] 3. `learned_models` table and store: read-only listing plus an idempotent
      record of (source kind, model id, first-verified time). Exactly three
      columns; the primary key makes a repeat verification a no-op.
- [ ] 4. Test the cross-user floor: the schema has no user or universe column, and
      a recorded row plus a full table dump contain no user id, universe id,
      prompt or credential under any input.
- [ ] 5. Record on verified success only, at the coordinator's native terminal.
      Best-effort: a failure to learn never fails the turn that worked.
- [ ] 6. Test that a refusal, a capacity hold, an unconfirmed outcome and an owner
      declaration all record nothing.
- [ ] 7. `newest_per_class(rows)` — reduce catalog rows for one source kind to the
      newest of each class, tie-broken by first-verified time.
- [ ] 8. Surface: contribute those rows to the advisory options document for each
      source kind on the universe's connections, unioned with the universe's own
      ids, with a distinct availability basis. No new MCP handle; the selection
      API is unchanged.
- [ ] 9. Test the union: a user's own id is never removed by a newer catalog
      sibling, and the currently-saved model keeps its "current" tick even when it
      is absent from the union and when it is not usable.
- [ ] 10. Cross-family review (Codex, server half), then sync the spec delta and
      archive.
