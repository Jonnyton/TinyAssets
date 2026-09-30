# user-owned-automations (delta)

## ADDED Requirements

### Requirement: An app event wakes only the owner's subscription with that name
The automation event types SHALL include `app_event`, whose only filter key is `name`, and registration SHALL refuse an `app_event` subscription that does not name one. An `app_event` SHALL follow every rule an engine event already follows. It SHALL wake only active subscriptions that the emitting principal owns, in that principal's own current home, and only when the emit names that home.

#### Scenario: An unnamed subscription is refused
- **WHEN** an owner creates an `app_event` automation with no `event_filter.name`
- **THEN** registration is refused, saying that the name is required

#### Scenario: Another user's event wakes nothing here
- **WHEN** a different user emits an `app_event` with the same name, naming this universe or their own
- **THEN** no subscription in this universe is woken
