## ADDED Requirements

### Requirement: Canonical page writes accept an explicit target scope

Canonical `/mcp` `write_page` SHALL accept `scope="commons" | "universe"` as an additive target
selector. The selector SHALL be validated before any mutation. `scope="commons"` SHALL keep the
authenticated shared-commons write path available even when the caller has a founder-home
universe. `scope="universe"` SHALL use the existing sole-writer relay path. An explicit universe
scope that resolves neither an explicit universe nor a founder home SHALL fail before mutation.
Typed `kind=` commons filings SHALL reject `scope="universe"` rather than silently ignoring it.
Authentication rejection SHALL retain precedence over target validation. Omission SHALL retain
the historical target-resolution behavior for existing clients.

#### Scenario: an authenticated founder explicitly writes shared knowledge

- **WHEN** an authenticated founder calls `write_page` with `scope="commons"`
- **THEN** the content is written to the shared commons rather than relayed to the founder's home universe

#### Scenario: contradictory targets fail closed

- **WHEN** a caller supplies `scope="commons"` together with `universe_id`
- **THEN** the call returns a validation error before any page is mutated

#### Scenario: an unknown scope fails closed

- **WHEN** a caller supplies a scope other than `commons` or `universe`
- **THEN** the call returns a validation error naming the valid values before any page is mutated

#### Scenario: explicit universe scope never falls through to commons

- **WHEN** `scope="universe"` resolves no explicit universe or founder home
- **THEN** the call fails before mutation instead of writing the shared commons

#### Scenario: a universe-scoped filing is contradictory

- **WHEN** `scope="universe"` is combined with a typed `kind=` commons filing
- **THEN** the call fails before filing the commons page

#### Scenario: legacy omission remains compatible

- **WHEN** an existing caller omits `scope`
- **THEN** canonical `write_page` retains its existing universe-resolution and commons-fallback behavior
