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

- [ ] P0 — contributed ids were ADMITTED, not display-only. `catalog = filtered =
      _native_models(...)` handed one object to both, so a learned id arrived with
      `in_candidate_catalog=true` and only execution refused it. Split, as the HTTP
      branch already did, with `model_access_optin_required` so the dropdown files
      it under "Needs access". The artefact test was written FIRST and reproduced
      the P0 (`assert True is False`) before the fix.
- [x] P1 — the published id was `reported_model`, chosen by the SOURCE. Now it is
      the id this universe REQUESTED and that succeeded, so a source cannot inject
      a string into every other user's list, and `provider-default` can no longer
      be published as a verified model.
- [ ] P1 — validation was "printable, <=200 chars", which accepted
      `owner-alice@example.com-private-9`. Now a strict ASCII identifier charset,
      alphanumeric at both ends.
- [x] P1 — the write sat on the reply path with a 30s busy timeout (measured 318 ms
      stall). Now a 250 ms bound: learning is optional and repeatable.
- [x] P1 — `served_model_plan`'s bare `except Exception` disguised corruption as
      "nothing learned yet". Narrowed to OSError / DatabaseError / ValueError, and
      logged.
- [ ] P2 — `some_model` and `some-model` collapsed into one class and one was
      discarded. Version tokens are now removed IN PLACE, so every separator
      survives; an equal version-and-timestamp tie falls back to the model id
      rather than to input order.
- [ ] Resolve the remaining floor through the primitive rule, then sync the spec
      delta and archive. No round 3 under the two-round review policy.

Round-2 verification at `b655942b`: **blocked**. The native manifest path is fixed,
but the legacy picker still admits learned-only rows; the validator still permits
private account-bearing selectors to be published. Exact unversioned separator
and tie examples are fixed, but version removal can still erase a namespace.
The reopened checkboxes reflect those residuals, not a claim the fixes did nothing.
Evidence: the round-2 verdict summary is a comment on PR #4028; the two findings
still open carry their own evidence inline in `docs/concerns/`. Review transcripts
are not kept in the repo (founder process cut, 2026-09-26).
Latency and client-visible read degradation are recorded as nonblocking concerns.

## Round 3 shape change — the founder's threshold (2026-09-26)

The round-2 P1 was resolved by the FOUNDER choosing a threshold instead of a rule
about strings: an owner-typed id is public once at least two DISTINCT OWNERS have
made it work. A private selector is unique to its owner by construction, so it can
never cross it, and nothing has to classify a string or name a vendor.

- [x] Two tables: `learned_model_evidence` (PRIVATE, owner-keyed, counts distinct
      owners) and `learned_models` (SHARED, still exactly three columns and no user
      data). The promotion count stays in the private table and is returned to
      nobody.
- [x] `PROMOTION_OWNERS = 2`, named with the founder's rationale. Evidence and
      promotion happen in one transaction; the published first-verified time is the
      EARLIEST across contributing owners, so it stays a property of the id.
- [x] The same owner's several universes count as ONE owner — the store is not even
      told which universe.
- [x] Charset relaxed to basic identifier sanity (printable ASCII, no whitespace,
      bounded). `sonnet[1m]` and `opus[1m]` are usable again; the threshold carries
      the privacy boundary.
- [x] The private table classified as its owner's data in BOTH sweeps
      (`preserve_or_block` in scoped_reset, picked up by account deletion via its
      `owner_user_id` column). A published id survives its contributors' deletion.
- [x] Tests: the ARN never leaves one owner however often it is used; two distinct
      owners publish `claude-fable-5-1` and a third owner sees it under "needs
      access" with the grant path; one owner's two universes do not promote;
      the count is returned to nobody.
- [x] `docs/concerns/2026-09-26-learned-catalog-private-selectors.md` DELETED — the
      threshold resolves it. The contention concern stays open.
- [x] Round 3 Codex verdict (final; the cap is spent). Two must-fix, one of which
      was not mine to fix:
      - [x] P2 FIXED — `evidence_ids` had no production caller, so a solo owner's
            verified id was stored and never listed. `_own_verified_candidates`
            unions their own history into their own candidates with its own basis
            (`owner_verified_here`), asserted on the options DOCUMENT this time,
            because asserting the store is what hid it.
      - [x] Accuracy FIXED — the private table was `preserve_or_block`, which
            promised a blocking check it does not have. Now `preserve`, which is
            what actually happens; account deletion removes it by column.
      - [ ] P1 ESCALATED — two account subjects do not make a selector public, and
            neither would two verified PEOPLE: colleagues share one org's private
            deployment id. No threshold value or charset fixes that; it needs an
            explicit sharing boundary (the per-universe opt-in that was option 2).
            Founder decision. docs/concerns/2026-09-26-learned-catalog-private-selectors.md
- [ ] Rebase onto bounded-results' dispatch ceiling when it lands, then sync the
      spec delta and archive — after the publication boundary is settled.
