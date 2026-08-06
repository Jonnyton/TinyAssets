# Tasks — verified founder recognition on chat surfaces

## 1. Identity key (LANDED)

- [x] 1.1 `event_of` exposes `actor_team_id` — the sender's own workspace, from
      `user_team`/`source_team`, falling back to delivery team only when Slack
      supplies neither. Landed `eac5bbb9`.
- [x] 1.2 Tests for the reviewer's Slack Connect counterexample (foreign
      `U_COLLIDE` on our delivery team). Mutation-verified.

## 2. Evidence type

- [x] 2.1 `SocketModeAppEvent` in `app_event_ingress.py`, its own
      `_SOCKET_MODE_SEAL`. Carries `team_id` (delivery) AND `actor_team_id`
      (the sender's own workspace) because Slack ids are unique only within a
      workspace.
- [x] 2.2 **Found while implementing:** neither `app_conversation_authority.issue`
      nor `app_reply_authority.authorize` checked the seal at all — both
      delegated to `mapping.resolve`, so `_external_key`'s
      `is_authenticated_app_event` was the SOLE gate on signed Ed25519 custody
      grants. Widening it for founder recognition would silently have let
      socket events mint thread grants. Both now assert the request seal
      themselves; `is_admissible_principal_event` is the deliberately weaker
      identity-only predicate.

## 3. Durable replay admission

- [x] 3.1 `SlackSocketModeBoundary` composes identity with the existing
      `AppEventAdmissionStore`. Required adding `event_id` to `event_of`'s
      normalisation (payload wins; absent means absent) — it is the ledger key,
      so an inner value must not be able to stand in for it.
- [x] 3.2 Tested with a fresh boundary AND store object (a real restart), plus
      the resolver-level test that a redelivery mints no second grant.

## 4. The grant

- [x] 4.1 Sealed `FounderGrant` in `tinyassets/founder_grant.py`; the
      constructor refuses without the recognizer's seal.
- [x] 4.2 `FounderRecognizer.recognize` re-derives per call and returns `None`
      for every failure, never distinguishing why.
- [x] 4.3 **Decided: exactly one admin on the universe, and it must be this
      subject.** `resolve` only asserts *this subject* holds one admin row, so
      two subjects could each hold one and "the verified founder" would stop
      being a single answerable fact.
- [x] 4.4 Each failure mode tested independently: stranger, Connect guest with
      a colliding id, revoked admin, second admin, rotated binding, deleted
      universe, unsealed evidence.

## 5. Wire it (fail-closed)

- [x] 5.1 `converse` takes `founder_grant`; passing both it and `tier` raises.
      A forged or wrong-universe grant is downgraded to the floor, not refused
      — an attacker must not be able to tell "rejected" from "unknown".
- [x] 5.2 `converse_as_external_sender` is the surface entry point and has **no
      `tier` parameter**, so a transport cannot claim authority even by
      mistake. `build_resolver` mints the grant; the handler only carries it.
- [x] 5.3 `SLACK_SENDER_TIER` deleted.
- [x] 5.4 12 guards mutation-verified (each disabled in turn; the named test
      must go red). Two findings from the probe itself: the Connect test was
      **vacuous** — it passed with the guard disabled because the lookup had
      already missed, so it now asserts the key derivation directly and a
      second test covers the guard; and the reply-path guard had no failing
      test at all.

## 6. Gates

- [ ] 6.1 Live proof: founder teaches Tiny through Slack, `origin.md` changes;
      a non-founder in the same channel teaches nothing and cannot read
      `founder.md`.
- [ ] 6.2 Cross-family review of the implementation, framed as "refute that a
      non-founder can reach founder capability".
- [ ] 6.3 State the account-principal-not-human-presence invariant in the
      capability spec, not just this proposal.
