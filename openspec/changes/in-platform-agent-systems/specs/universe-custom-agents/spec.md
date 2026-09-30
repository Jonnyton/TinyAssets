# universe-custom-agents (delta)

## ADDED Requirements

### Requirement: Publishing a universe's work is an owner-confirmed ask
A pending request with action type `publish` SHALL be acted on only through an answer from the person's own surface, and a served turn SHALL NOT be able to answer it.

The request names a public name and description and one or more branches the owner authored in that universe. It may also name a UI in the owner's own app_ui library, and automations the owner owns that drive listed branches.

At ask time the platform SHALL pin a content digest of every item. It SHALL write the request's title and body itself, listing every item that becomes public.

On confirmation the platform SHALL re-check every digest. If any differs, it SHALL publish nothing and leave the request pending. Otherwise it SHALL:
- make each branch public and publish a version of each;
- publish exactly one definition whose components are the UI, one `tinyassets.branch-ref.v1` per branch naming its published version, and one `tinyassets.automation-spec.v1` per automation. Each automation-spec carries the trigger and overlap, never the inputs.

The definition publish SHALL be idempotent on the request.

#### Scenario: The owner confirms what they were shown
- **GIVEN** the universe asked to publish two workflows, a UI and one heartbeat
- **WHEN** the owner accepts the tab unchanged
- **THEN** both workflows are public with a published version each
- **AND** one definition carries the UI, two branch-refs and one automation-spec without inputs

#### Scenario: The work changed after the tab was shown
- **WHEN** a listed branch or the UI is edited between the ask and the accept
- **THEN** nothing is published and the request stays pending with the reason

#### Scenario: The agent tries to consent for its owner
- **WHEN** a served turn tries to answer the publish ask
- **THEN** no served operation answers it, and nothing is published

#### Scenario: The agent names something that is not the owner's
- **WHEN** the ask names a branch another user authored, a UI not in the owner's library, or an automation that drives an unlisted branch
- **THEN** the ask is refused at creation

### Requirement: An installed copy is private and runs as its installer
A published definition's branch-refs SHALL be copyable only through the existing remix path, and that path SHALL create a private branch owned by the installer. Its UI component SHALL be installable only into the installer's own app_ui library, and there its bridge SHALL act as the viewing installer in their own home. Nothing installed SHALL address the author's universe.

#### Scenario: A second user installs a published system
- **WHEN** another user's universe remixes each branch-ref, saves the UI, and recreates the automations from their specs
- **THEN** every copy is private to that user and runs on that user's compute
- **AND** the UI's reads return that user's automations and runs
