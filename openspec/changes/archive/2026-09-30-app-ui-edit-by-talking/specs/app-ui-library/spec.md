## ADDED Requirements

### Requirement: A person's UI row is changed one UI at a time without a revision
`write_graph target="app_ui"` SHALL accept the operations `activate`, `use_default`, `add_ui`, `replace_ui`, `edit_ui` and `remove_ui`, each naming one UI (or only the choice) in `payload_json` and none needing the row revision. Each SHALL apply to the row as stored at write time, keyed by the authenticated caller and universe, and SHALL NOT overwrite a change another writer saved concurrently. The row revision SHALL advance so a whole-row `save` sees the change.

#### Scenario: A universe switches a large library to one UI
- **WHEN** a universe calls `activate` with `{"ui_id": "gtm-village"}` for a library larger than one tool result
- **THEN** the choice becomes that UI and no UI in the library changes

#### Scenario: One component is edited and the rest are untouched
- **WHEN** `edit_ui` names one `ui_id` with `set` fields or `edits` whose `old` text occurs exactly once
- **THEN** only that UI changes; an `old` text occurring zero or several times is refused and nothing changes

#### Scenario: A concurrent save is not lost
- **WHEN** another writer saves the row after a targeted change read it and before it wrote
- **THEN** the targeted change is re-applied to the new row and both changes are stored

#### Scenario: A stale etag is refused
- **WHEN** `replace_ui`, `edit_ui` or `remove_ui` carries an `expected_etag` that no longer matches that UI
- **THEN** the change is refused as a conflict and nothing changes

#### Scenario: Another user cannot reach the row
- **WHEN** a user without access to the universe names it, or a collaborator names a UI only the owner has
- **THEN** the operation is refused or reports the UI not found, and the owner's row is unchanged

### Requirement: A model reads the UI row compactly
`read_graph target="app_ui"` SHALL return an index of the caller's UIs (id, name, etag, field sizes, no bodies) with the choice and revision for `query="index"`, one UI for `query=<ui_id>`, and one chunk of one field with `next_offset` when `field_name` is given. The universe's engine surface SHALL default to the index and SHALL NOT return the whole library.

#### Scenario: The engine index fits a bounded result
- **WHEN** a universe calls `read_graph target="app_ui"` for a library larger than one tool result
- **THEN** the result is the index, not truncated, and names every UI

### Requirement: The app shows a choice made by talking
After each delivered turn the app SHALL read the index and, only when the row revision moved, re-read and apply the row, so an activation made during the turn shows without a reload and an unchanged row never remounts the UI in use.

#### Scenario: Activation shows after the reply
- **WHEN** the universe activates a UI during a turn
- **THEN** the app mounts it after rendering the reply
