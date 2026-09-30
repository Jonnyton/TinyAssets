# live-mcp-connector-surface (delta)

## ADDED Requirements

### Requirement: The owner reads their universe's files through read_graph
`read_graph target="universe_files"` SHALL list one directory, and `target="universe_file"` SHALL return one file in bounded chunks. Both take a path relative to the universe folder in `query`. Both SHALL be readable only by a caller holding admin on the universe named by `graph_id`. A caller without admin, an absent path, an absolute or `..` path, and a path through a symlink SHALL all receive the same `not_found` envelope. A file read SHALL return UTF-8 text as `text` and other bytes as `base64`, with `next_offset` and `eof`, at most 262,144 bytes per read. A listing SHALL return at most 500 entries, with `truncated`.

#### Scenario: The owner reads a board file their agents write
- **WHEN** the owner reads `target="universe_file" query="notes/board.md"` on their own universe
- **THEN** they receive the file's text, paged by `file_offset` until `eof`

#### Scenario: Another user names the universe
- **WHEN** a different user reads any path in it, including a user who can see the universe because it is public
- **THEN** the answer is `not_found`, identical to an absent path

#### Scenario: A path escapes the folder
- **WHEN** the path is absolute, contains `..`, or passes through a symlink
- **THEN** the answer is `not_found` and nothing outside the folder is read

### Requirement: run_graph emits an app event to the caller's own subscriptions
`run_graph operation="emit_event"` SHALL take `inputs_json {"name", "data"}` and emit an `app_event` stamped with the verified request principal, for the universe named by `graph_id`. `name` must match `[a-z0-9][a-z0-9_.-]{0,63}`, and `data` must be a JSON object of at most 8192 canonical bytes. A wake SHALL run in the emitter's own home, on that universe's own compute. An emit SHALL never spend another user's compute, and a UI installed from someone else SHALL spend only its viewer's compute. The emit SHALL be charged to the caller's engine run admission before any wake is stored. It SHALL reply only with whether it was emitted and how many wakes it stored.

#### Scenario: A UI click wakes the owner's agent
- **GIVEN** the owner has an active `app_event` subscription filtered on the name `visit`
- **WHEN** the owner's session emits `{"name": "visit", "data": {"who": "baker"}}`
- **THEN** one wake of the subscribed branch is stored with `inputs.event.data` equal to the sent data

#### Scenario: Over the usage limit
- **WHEN** the caller's engine run admission refuses
- **THEN** nothing is stored and the refusal names the limit
