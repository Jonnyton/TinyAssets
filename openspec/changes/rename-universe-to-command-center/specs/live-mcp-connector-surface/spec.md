## MODIFIED Requirements

### Requirement: Remote Streamable-HTTP MCP Endpoint

The platform SHALL expose a single remote MCP server over Streamable-HTTP transport (`tinyassets/universe_server.py`, built on FastMCP) that any MCP-compatible chatbot can connect to by URL with no local installation. The server SHALL register exactly the following prompt catalog so a connecting chatbot receives behavioral instructions on how to act as the user's control interface:

| Prompt name | Title | Tags |
|---|---|---|
| `control_station` | `Control Station Guide` | `control`, `daemon`, `multiplayer`, `operations` |
| `meet_command_center` | `Meet Your Command Center` | `first-contact`, `onboarding`, `persona`, `tinyassets` |
| `extension_guide` | `Extension Authoring Guide` | `extensions`, `nodes`, `plugins`, `tinyassets` |
| `branch_design_guide` | `Branch Design Guide` | `branches`, `customization`, `extensions`, `graph` |

Each prompt SHALL return its registered behavioral guide and SHALL expose its function docstring as discoverability text.

#### Scenario: Chatbot completes an MCP handshake and lists tools

- **WHEN** an MCP client sends `initialize`, then `notifications/initialized`, then `tools/list` to the server
- **THEN** the server responds with a valid MCP `serverInfo` + `protocolVersion` and returns a non-empty advertised tool list
- **AND** the response is delivered as either JSON or an SSE `event: message` frame, both of which are valid Streamable-HTTP responses

#### Scenario: Prompt listing returns the exact catalog
- **WHEN** an MCP client lists prompts on the live server
- **THEN** the response contains the four names, titles, and tag sets above with no additional registered prompt, and no prompt named `meet_universe`

#### Scenario: Prompt invocation returns the owned guide
- **WHEN** an MCP client invokes any catalogued prompt
- **THEN** the server returns that prompt's registered control, first-contact, extension-authoring, or branch-design guide

## ADDED Requirements

### Requirement: The served surface names the user's command center, and refuses the retired universe names

Every advertised tool description, parameter name, `target` value, enum value, prompt, and the server instructions SHALL use "command center" (`command_center`, `command_center_id`) for the person's workspace and SHALL NOT contain "universe", except names stored inside people's branch definitions until the storage migration renames them. The seven handle names SHALL NOT change. A call that uses a retired name (`universe_id`, `target=universe`, `universe_files`, `universe_file`, `scope=universe`) SHALL be refused as `renamed`, naming the current name, before the tool runs, and SHALL change nothing. No retired name SHALL be accepted as an alias. Every JSON tool result SHALL carry only current key and error-code spellings, and a stored actor id `universe:<id>` SHALL be presented as `command_center:<id>`, except in results that return a person's own content verbatim. `get_status` SHALL report `schema_version` 3.

#### Scenario: A retired argument name is refused with a pointer
- **WHEN** a client calls `get_status(universe_id="u-abc")`
- **THEN** the result is an error `renamed` with `retired` `universe_id` and `current` `command_center_id`, and nothing is read

#### Scenario: A retired target is refused with a pointer
- **WHEN** a client calls `read_graph(target="universe_files")`
- **THEN** the result is an error `renamed` naming `target=command_center_files`

#### Scenario: The advertised schema carries no retired name
- **WHEN** a client reads `tools/list` and `prompts/list`
- **THEN** no description, parameter, target value, or prompt name contains "universe" apart from stored branch-definition field names, and the handle set is still exactly the seven canonical handles

#### Scenario: Responses carry current spellings only, and a person's content is untouched
- **WHEN** a handler returns `{"universe_id": "u-1", "actor": "universe:u-1"}`
- **THEN** the client receives `{"command_center_id": "u-1", "actor": "command_center:u-1"}`, while a run output or file read containing the same keys is returned unchanged
