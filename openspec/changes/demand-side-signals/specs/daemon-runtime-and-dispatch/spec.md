> Supersession note. The as-built requirement below states outright that a cron
> schedule "does NOT backfill cron ticks missed while the daemon was down". A
> standing goal whose owner is absent for a week is exactly the case that
> limitation silently breaks, so the demand-side target contradicts canonical
> truth here. Per the `outbound-boundary-layer` precedent, that contradiction is
> carried as a MODIFIED delta rather than as a promise: an active change's delta
> describes post-change behavior and alters nothing canonical until sync, and
> `demand-side` SHALL NOT sync without this delta. This change modifies only the
> scheduler requirement; `operator-request-trigger-contract` owns the dispatcher
> requirement in this same capability and is untouched here.

## MODIFIED Requirements

### Requirement: Scheduled and event-triggered invocation is persisted and restart-recoverable
Scheduled and event-triggered branch invocation (`tinyassets.scheduler`) SHALL persist cron and interval schedules and event subscriptions in the universe's runs SQLite database so they survive daemon restart, with the tick loop reading the database each tick and firing due schedules. Every persisted cron-class schedule SHALL record the IANA timezone its expression is evaluated in; a schedule registered without a resolvable IANA timezone SHALL be rejected at registration rather than silently evaluated in the daemon's local zone. It SHALL deliver each event at most once per subscription through a persisted `scheduler_delivered_events` idempotency table, SHALL rate-limit active schedules and subscriptions per owner, and SHALL gate schedule removal to the owner or an admin. Each schedule SHALL additionally declare a missed-tick policy — `skip`, `fire_once`, or `backfill_bounded(n)` — recorded with the schedule and applied deterministically when the tick loop resumes after downtime, replacing the previous behavior in which a cron schedule silently dropped every tick missed while the daemon was down. A resumed schedule SHALL record which policy it applied and how many periods it skipped or replayed, so an absent owner can distinguish a quiet period from a lost one. A replay under `backfill_bounded(n)` SHALL reuse the missed period's schedule-period identity rather than minting a new one, so downstream effect and receipt owners deduplicate instead of double-firing, and SHALL replay at most `n` periods, recording the count discarded beyond the bound.

#### Scenario: schedules survive a restart and fire when due
- **WHEN** the scheduler starts and reads a persisted schedule whose next fire is due
- **THEN** it fires the schedule's branch and records `last_fired_at`

#### Scenario: an event is delivered exactly once per subscription
- **WHEN** the same `event_id` is emitted more than once to a subscription already recorded in `scheduler_delivered_events`
- **THEN** the subscription fires only once and the redelivery is a no-op

#### Scenario: per-owner rate limit and owner-gated removal are enforced
- **WHEN** an owner exceeds the per-owner active-schedule limit, or a non-owner non-admin requests removal
- **THEN** the registration is rejected for exceeding the limit and the removal is refused for lacking ownership

#### Scenario: a missed cron window resolves by declared policy, not by silence
- **WHEN** the daemon returns after downtime that spanned one or more due cron periods
- **THEN** the schedule applies its declared missed-tick policy — skipping, firing once, or replaying at most `n` bounded periods — and records the policy applied with the number of periods skipped or replayed
- **AND** a bounded replay reuses each missed period's own schedule-period identity

#### Scenario: a schedule without an IANA timezone is rejected at registration
- **WHEN** a cron-class schedule is registered with no timezone or with an unresolvable timezone
- **THEN** registration is refused with a reason naming the missing timezone
- **AND** no schedule row is persisted that would later be evaluated in the daemon's local zone
