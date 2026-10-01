# user-owned-automations (delta)

## ADDED Requirements

### Requirement: The owner's new message wakes an owner_message subscription once per burst

The engine SHALL emit `owner_message` once the owner's message is stored in their own conversation thread, stamped with the verified sender. It SHALL wake only that principal's own subscriptions in their own home universe, and a `universe:<id>` principal or a visitor SHALL wake nothing. While a wake stored by the subscription has not started, a further message SHALL store no second wake. The event SHALL carry no filter keys.

#### Scenario: A burst is one wake
- **GIVEN** an owner's `owner_message` subscription
- **WHEN** the owner sends three messages before the wake starts
- **THEN** exactly one wake is stored and the pump runs it once; a message after it started stores a new wake

#### Scenario: The universe's own reply wakes nothing
- **WHEN** the universe answers, or another user talks in the owner's universe
- **THEN** no wake is stored

### Requirement: A served agent can set its own next wake

Automation create SHALL accept `not_before` (an ISO-8601 instant) or `delay_seconds` (a number >= 0) as a one-shot trigger, exclusive with every other trigger, and the pump SHALL fire it once at or after that instant.

#### Scenario: A wake set an hour out fires at its time
- **WHEN** the agent creates an automation with `delay_seconds: 3600` through `write_graph`
- **THEN** it is not due before the hour and is due after it

#### Scenario: Two triggers are refused
- **WHEN** create names `delay_seconds` with `interval_seconds`, or `delay_seconds` with `not_before`
- **THEN** nothing is stored and the refusal names the reason
