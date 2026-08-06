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
- [x] 4.3 **Decided, after two wrong answers: no cardinality rule at all.**
      "Exactly one admin on the universe" locked the real founder out the
      moment they added a co-admin. "Exactly one admin whose founder *home* is
      this universe" then broke multi-universe — `founder_home` holds one row
      per subject, so on a user's second and third universes the claimant set
      is empty and no grant could ever mint. Ownership is per-universe (the
      admin ACL row) and needs no uniqueness tiebreak; a non-owner stays
      structurally excluded, which is the property that matters.
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
      **Unblocked in code, still needs a signed-in browser.** The setup surface
      now exists (`write_graph target=chat_surface`), so a founder mapping CAN
      be created; the remaining gap is that the Slack round-trip needs the
      host's logged-in session.
      Historical note — this used to read:  There is no way for a user
      to say "this Slack account is me". `AppPrincipalMappingService.provision`
      needs a trusted-setup resolver and has no user-facing caller, so no
      founder mapping exists in production — `u-tiny` has no ACL rows at all.
      This is exactly the surface the host described: *editing your custom
      agent, list the founder accounts for the platforms it should recognise
      you from.* Until it exists only the non-founder half is live-provable.
- [x] 6.2 Cross-family review returned **reject** with two findings that
      survived; both are now closed or reported:
      - **Seal defeated by `dataclasses.replace`.** `_seal` was a dataclass
        *field*, so `replace` passed it back to the constructor: a legitimate
        grant became one for another universe, and — worse, on the
        *pre-existing* `AuthenticatedAppEvent` — one admitted event could be
        rewritten to another sender and keep its seal. Fixed on all three
        sealed types by taking the seal off the field list.
      - **Cardinality locked out the real founder.** "Exactly one admin" would
        revoke recognition the moment the founder adds a co-admin. The first
        replacement (unique founder *home*) was itself wrong — see 4.3 — and
        the rule is now gone entirely in favour of per-universe ownership.
      Still open, both **outside this change's diff**:
      - `interlocutor.resolve_interlocutor_tier` returns **T2/FOUNDER for any
        `write` ACL holder**, so on the MCP path a collaborator reads
        `founder.md` and commits learning. Pre-existing; needs its own lane.
      - The seal is an importable module global, so arbitrary in-process code
        can mint a grant. That is the honest limit of in-process capability
        sealing — such code can equally call `converse(tier="T2")` — so the
        seal defends against a transport passing the wrong thing, not against
        code execution. Documented rather than overclaimed.
- [ ] 6.3 State the account-principal-not-human-presence invariant in the
      capability spec, not just this proposal.

## 7. Multi-universe (host 2026-08-05: users keep several)

Users have work / personal / hobby universes, and billing is total storage
across all of them. That made two shipped assumptions category errors.

- [x] 7.1 Ownership is per-universe. Dropped the `founder_home == universe`
      check: `founder_home` holds ONE row per subject, so it made a user the
      founder of exactly one of their universes and a stranger on the rest.
      It is a first-contact default, not an ownership predicate.
- [x] 7.2 Channel routing — `app_channel_bindings`, separate from the principal
      mapping because identity and routing are different questions. Conflating
      them is what capped a workspace at one universe. One rule: most specific
      wins (channel > workspace > the socket's host universe).
- [x] 7.3 Recognition follows the routing. Owning the socket's host universe
      says nothing about the one a channel binding pointed a message at, so
      ownership is re-derived against the ROUTED universe.
- [x] 7.4 A routed message reads the ROUTED universe's directory. Reading the
      socket host's would answer about one universe while grounded in another.
- [x] 7.5 11 routing guards mutation-verified.

## 8. Setup surface (reachability)

- [x] 8.1 `write_graph target=chat_surface` — connect_account / bind_channel /
      unbind_channel; `read_graph target=chat_surface` for resolved routing.
      An ACTION on an existing handle: hard rule 11 pins the live catalog, and
      a test asserts the canonical seven are unchanged.
- [x] 8.2 Authority derived, never asserted. Ownership is checked FIRST (the
      binding lookup ran first and refused strangers with
      "no_unique_agent_binding", which reads like a fixable setup problem
      rather than a universe that is not theirs). `payload_json` is filtered to
      an allowlist, so `subject_id` cannot reach a handler that derives
      authority.
- [x] 8.3 Every write answers with the RESOLVED routing, not the row written —
      a forgotten channel binding is exactly what makes the default surprising.
- [x] 8.4 8 setup guards mutation-verified.

## 9. Incident

- [x] 9.1 **Production outage, self-inflicted, 2026-08-06.** Deploying the
      pre-merge overlay with `docker compose -p tinyassets -f compose.slack.yml`
      converged the main project down to that one service and destroyed the
      daemon, tunnel, logs and four workers; `tinyassets.io/mcp` served 502.
      Recovered via `systemctl start tinyassets-daemon`; canary green with
      `--assert-handles`. Fixed by running the overlay in its own project
      (`-p tinyassets-slack`) with external volume/network, PROVEN by re-running
      the exact outage command and watching the main stack survive. Postmortem:
      `docs/audits/2026-08-06-partial-compose-overlay-outage.md`. The durable
      fix is landing #2348, which removes the second compose file entirely.

- [x] 9.2 **Addendum — the overlay also FENCED production deploys, so the 24/7
      claim for it is retracted.** A container on `tinyassets-data` outside the
      main compose project is recorded as an "extra production-volume consumer"
      and the fence refuses to deploy
      (`retire_cheat_loop_deploy_fence.py:1619`). Two deploy runs failed until
      an operator dispatched `retire_extra_consumer=tinyassets-slack-agent`,
      which deletes it — so the agent silently stopped twice, with nothing in
      its own logs. A service a routine deploy is designed to delete is not
      continuously available. Integration is now proven in an EPHEMERAL
      container (prod image, temp data dir, no volume mount) instead; the
      durable fix is landing #2348.
