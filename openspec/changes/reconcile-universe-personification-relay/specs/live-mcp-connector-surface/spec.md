## ADDED Requirements

### Requirement: Free-form page writes use an explicit target scope with a bounded compatibility window

Every externally callable free-form page write or patch SHALL accept the same target selector,
`scope="commons" | "universe"`, across canonical `/mcp` `write_page`, `/mcp-directory`
`write_page`, and deprecated `/mcp` `wiki(action=write|patch)` while that hidden tool remains
callable. `scope="commons"` SHALL write only the shared public commons and SHALL reject a
simultaneous `universe_id`. `scope="universe"` SHALL resolve the explicit `universe_id` or the
authenticated founder's home and return the existing `relay_to_universe` result naming
`converse`; it SHALL NOT write a universe page substrate directly. Unknown scope values SHALL
fail closed without mutation.

For one bounded compatibility window, callers that do not yet send `scope` SHALL retain the
historical safe default of the surface they called: canonical `/mcp` `write_page` resolves to
`universe`; directory and deprecated-wiki calls without `universe_id` resolve to `commons`; and
any call that carries `universe_id` resolves to `universe` and is relayed rather than writing the
brain. The window SHALL end when the deprecated `wiki` tool is removed and the canonical and
directory tool schemas advertise the selector. After that transition, omission SHALL fail closed
with an actionable error naming both valid scopes. Typed `kind=` issue filings remain explicit
commons operations and do not require the selector.

#### Scenario: an existing canonical client keeps its universe-relay default during migration

- **WHEN** an authenticated client calls canonical `/mcp` `write_page` without `scope` during the compatibility window
- **THEN** the call resolves to `scope="universe"` and returns `relay_to_universe`
- **AND** no universe page substrate is written directly

#### Scenario: an existing no-target directory or legacy call keeps its commons default during migration

- **WHEN** a directory or deprecated-wiki free-form write omits both `scope` and `universe_id` during the compatibility window
- **THEN** the call resolves to `scope="commons"` and writes only the shared public commons

#### Scenario: a legacy explicit universe target stops bypassing the relay immediately

- **WHEN** a directory or deprecated-wiki free-form write carries `universe_id` but omits `scope` during the compatibility window
- **THEN** the call resolves to `scope="universe"` and returns `relay_to_universe`
- **AND** the universe brain is not written directly

#### Scenario: omission fails closed after the compatibility window

- **WHEN** the deprecated `wiki` tool has been removed, the surviving tool schemas advertise `scope`, and a free-form write omits the selector
- **THEN** no page is mutated and the error names `commons` and `universe` as the valid choices

