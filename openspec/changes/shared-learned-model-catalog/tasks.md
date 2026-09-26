## Tasks

- [x] 1. `model_class_and_version(model_id)` in one module: numeric runs and date
      stamps are version tokens, every other token is class, an unparseable id is
      its own class. No vendor or model names.
- [x] 2. Table-driven tests for it over varied shapes — dashes, dots, date stamps,
      named suffixes (`-sol`, `-astra`), no version at all, and ids that cannot be
      split. Include the ordering cases (different tuple lengths, ties).
- [x] 3. `learned_models` table and store: read-only listing plus an idempotent
      record of (source kind, model id, first-verified time). Exactly three
      columns; the primary key makes a repeat verification a no-op.
- [x] 4. Test the cross-user floor: the schema has no user or universe column, and
      a recorded row plus a full table dump contain no user id, universe id,
      prompt or credential under any input.
- [x] 5. Record on verified success only, at the coordinator's native terminal.
      Best-effort: a failure to learn never fails the turn that worked.
- [x] 6. Test that a refusal, a capacity hold, an unconfirmed outcome and an owner
      declaration all record nothing.
- [x] 7. `newest_per_class(rows)` — reduce catalog rows for one source kind to the
      newest of each class, tie-broken by first-verified time.
- [x] 8. Surface: contribute those rows to the advisory options document for each
      source kind on the universe's connections, unioned with the universe's own
      ids, with a distinct availability basis. No new MCP handle; the selection
      API is unchanged.
- [x] 9. Test the union: a user's own id is never removed by a newer catalog
      sibling, and the currently-saved model keeps its "current" tick even when it
      is absent from the union and when it is not usable.
- [ ] 10. Cross-family review (Codex, server half), then sync the spec delta and
      archive.

## Round 2 (Codex `gpt-6-astra` on `03a6828c`: "block this branch")

- [x] P0 — contributed ids were ADMITTED, not display-only. `catalog = filtered =
      _native_models(...)` handed one object to both, so a learned id arrived with
      `in_candidate_catalog=true` and only execution refused it. Split, as the HTTP
      branch already did, with `model_access_optin_required` so the dropdown files
      it under "Needs access". The artefact test was written FIRST and reproduced
      the P0 (`assert True is False`) before the fix.
- [x] P1 — the published id was `reported_model`, chosen by the SOURCE. Now it is
      the id this universe REQUESTED and that succeeded, so a source cannot inject
      a string into every other user's list, and `provider-default` can no longer
      be published as a verified model.
- [x] P1 — validation was "printable, <=200 chars", which accepted
      `owner-alice@example.com-private-9`. Now a strict ASCII identifier charset,
      alphanumeric at both ends.
- [x] P1 — the write sat on the reply path with a 30s busy timeout (measured 318 ms
      stall). Now a 250 ms bound: learning is optional and repeatable.
- [x] P1 — `served_model_plan`'s bare `except Exception` disguised corruption as
      "nothing learned yet". Narrowed to OSError / DatabaseError / ValueError, and
      logged.
- [x] P2 — `some_model` and `some-model` collapsed into one class and one was
      discarded. Version tokens are now removed IN PLACE, so every separator
      survives; an equal version-and-timestamp tie falls back to the model id
      rather than to input order.
- [ ] Round 3 if needed, then sync the spec delta and archive.
