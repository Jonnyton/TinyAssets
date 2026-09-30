# user-owned-automations (delta)

## MODIFIED Requirements

### Requirement: A pending-request answer wakes the owner's subscription
The `pending_request_answered` event SHALL be emitted from the one place a request's resolution is written, for every surface that resolves it, and SHALL carry `request_id`, `kind`, `status` and — when one item was resolved rather than the whole request — `item_id`. Those four SHALL be the filter keys a subscription may name, and none SHALL be required, so an existing subscription keeps waking. Every cross-user rule of the engine event path SHALL apply unchanged: the event is stamped with the principal that resolved the request and wakes only that principal's own active subscriptions in their own current home.

#### Scenario: An item answer wakes the automation that follows that item
- **WHEN** the owner answers item `standup-notes` of a request, and an automation subscribes to `pending_request_answered` filtered on that `item_id`
- **THEN** exactly that subscription is woken, and one filtered on a different `item_id` is not

#### Scenario: An existing unfiltered subscription still wakes
- **WHEN** the owner answers a request with no items, and an automation subscribes to `pending_request_answered` with no filter
- **THEN** that subscription is woken exactly as before

#### Scenario: Another user's answer wakes nothing here
- **WHEN** a different user resolves a request in their own universe
- **THEN** no subscription in this universe is woken
