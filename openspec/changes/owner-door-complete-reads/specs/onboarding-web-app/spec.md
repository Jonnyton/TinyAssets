# onboarding-web-app (delta)

## ADDED Requirements

### Requirement: The app reads its owner's data through the owner door, complete

Every read the app renders (the request rail, restore-access, bindings, the model
picker, status, conversation history and message expansion, and the reads a
custom UI bundle makes through the bridge) SHALL go through the owner door:
`POST /app/api/read` (the `read_graph` arguments) and `POST /app/api/status`
(the `get_status` arguments). The owner door SHALL be authenticated by the same
bearer middleware as every other `/app` route, SHALL execute each read under the
request identity through the same domain function and owner gate the connector
uses, and SHALL return the complete document. The owner door SHALL contain no
size, limit or truncation logic and SHALL NOT import the model-context ceiling or
projection modules. Actions (`converse`, `write_graph`) MAY stay on the connector.

The phone app (Capacitor, `server.url` = the live `/app`) and the desktop app
(Electron over the live SPA) load the same page and therefore the same doors.

#### Scenario: A heavy account gets its whole rail
- **WHEN** an owner has 40 pending requests totalling more than 60 KB
- **THEN** the owner door returns all 40, with no truncation marker
- **AND** the same read on the connector is bounded visibly

#### Scenario: Another account's data is refused exactly as on the connector
- **WHEN** a signed-in account names a universe it does not own
- **THEN** the owner door returns the same refusal the connector returns, and none of that universe's data

#### Scenario: Account type is the only per-account difference
- **WHEN** a free account and a subscription account with the same data read the rail, status and bindings
- **THEN** the documents are identical apart from tier-derived numbers

### Requirement: An owner surface never vanishes silently

A failed or unreadable owner read SHALL leave its surface visible with a
statement that it could not load and a way to retry. It SHALL NOT be drawn as
empty, and it SHALL NOT be hidden.

#### Scenario: The rail read fails
- **WHEN** the rail read errors, returns an error document, or returns no list
- **THEN** the rail is shown with a line saying it couldn't load what's waiting, and a retry
- **AND** items from an earlier successful load stay (a typed answer is not wiped) under that line, so they are not presented as freshly confirmed

### Requirement: History is paged by an explicit cursor

The status read SHALL report, with every conversation page, whether older turns
exist (`has_more`) and the cursor that reads them (`next_before`). The app SHALL
offer "Show earlier messages" whenever `has_more` is true. No default page SHALL
hide older turns without saying so.

#### Scenario: A long conversation
- **WHEN** an owner's thread holds more turns than one page
- **THEN** the page reports `has_more: true` and a `next_before` cursor
- **AND** following the cursor until `has_more` is false returns every turn exactly once
