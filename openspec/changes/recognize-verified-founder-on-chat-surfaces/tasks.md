# Tasks — verified founder recognition on chat surfaces

## 1. Identity key (LANDED)

- [x] 1.1 `event_of` exposes `actor_team_id` — the sender's own workspace, from
      `user_team`/`source_team`, falling back to delivery team only when Slack
      supplies neither. Landed `eac5bbb9`.
- [x] 1.2 Tests for the reviewer's Slack Connect counterexample (foreign
      `U_COLLIDE` on our delivery team). Mutation-verified.

## 2. Evidence type

- [ ] 2.1 Add a Socket Mode evidence type distinct from `AuthenticatedAppEvent`.
      Do NOT mint the HMAC seal: it means "this exact HTTP body verified at this
      timestamp", and `app_conversation_authority` issues thread grants on it.
- [ ] 2.2 Test: the new type is NOT accepted anywhere the HMAC seal is required,
      and the HMAC seal's existing consumers are unchanged.

## 3. Durable replay admission

- [ ] 3.1 Admit `event_id` through a durable ledger before any founder-authority
      mint. Memory-only dedupe loses its window on restart.
- [ ] 3.2 Test: restart the process, redeliver the same founder `event_id`,
      assert exactly one learning commit across both runs.

## 4. The grant

- [ ] 4.1 Sealed `FounderGrant`, mintable only by the resolver, in the module
      owning the seal. A caller must not be able to construct one.
- [ ] 4.2 Resolver re-derives per call: founder home matches, exactly one admin
      ACL row, binding `configured`, revision matches, AND the universe
      directory exists. Any miss => no grant.
- [ ] 4.3 Decide and enforce founder cardinality — `founder_home` is unique by
      subject, so two subjects may name the same universe as home.
- [ ] 4.4 Test each failure mode independently: revoked mapping, revoked admin,
      rotated binding, generation mismatch, deleted universe, second admin.

## 5. Wire it (fail-closed)

- [ ] 5.1 `converse` accepts `founder_grant`; external-surface callers cannot
      pass a tier string. Floor tier when no grant.
- [ ] 5.2 Slack handler passes the grant or nothing — never a tier.
- [ ] 5.3 Delete `SLACK_SENDER_TIER`: authority policy leaves the transport.
- [ ] 5.4 Mutation test: forge a grant, pass `tier="T2"` from the external path,
      replay a founder event — each must fail to reach `commit_learning`.

## 6. Gates

- [ ] 6.1 Live proof: founder teaches Tiny through Slack, `origin.md` changes;
      a non-founder in the same channel teaches nothing and cannot read
      `founder.md`.
- [ ] 6.2 Cross-family review of the implementation, framed as "refute that a
      non-founder can reach founder capability".
- [ ] 6.3 State the account-principal-not-human-presence invariant in the
      capability spec, not just this proposal.
