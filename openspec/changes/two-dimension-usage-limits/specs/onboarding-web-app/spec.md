# onboarding-web-app (delta)

## ADDED Requirements

### Requirement: The app's existing route opens the upgrade flow from a link, and billing status reports the two enforced numbers

The app SHALL open its existing checkout flow when its own served route is
requested with an upgrade query parameter, so that a message elsewhere in the
product can carry a clickable upgrade link without a new route, a second
checkout path or an invented URL. The link SHALL be built by one function, from
the canonical public origin, so there is exactly one string to verify. Inside
the native Android shell the parameter SHALL be ignored for the same reason the
plan control is hidden there: a digital subscription bought inside a
Play-installed app must use Play Billing. The billing status route SHALL report
the account's enforced seat count rather than an empty list.

#### Scenario: The upgrade link opens the same flow as the header control
- **WHEN** the app's served route is requested with the upgrade parameter
- **THEN** the app starts the same checkout flow its own upgrade control starts, with no second route involved

#### Scenario: One link string
- **WHEN** a seat wait renders an upgrade link
- **THEN** both use the same builder, the same canonical origin and the same existing route

#### Scenario: The native shell does not sell subscriptions
- **WHEN** the app runs inside the native Android shell and the upgrade parameter is present
- **THEN** no checkout is started and the user is told plans are managed on the web

#### Scenario: Billing status names what is enforced
- **WHEN** a signed-in owner reads billing status
- **THEN** it reports the tier and its seat count
