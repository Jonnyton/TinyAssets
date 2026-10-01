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

### Requirement: The served surface names the user's command center, and accepts the retired universe names as aliases

Every advertised tool description, parameter name, `target` value, enum value, error code, response key, prompt, and the server instructions SHALL use "command center" (`command_center`, `command_center_id`) for the person's workspace, and SHALL NOT contain "universe". The seven handle names SHALL NOT change. A call that uses a retired name (`universe_id`, `target=universe`, `universe_files`, `universe_file`, or any other entry in the single alias table) SHALL be rewritten to the new name before schema validation and SHALL behave exactly like the new name. A call carrying both a retired and a new name with different values SHALL be refused as `conflicting_alias`, naming both, and SHALL change nothing. Each accepted alias SHALL log one structured line naming the retired name and the handle. Aliases SHALL be removed only after production shows zero alias hits for 14 consecutive days. The custom UI bridge identity SHALL keep returning `universe_id` and `universe_name` beside `command_center_id` and `command_center_name` without a removal window.

#### Scenario: A cached old tool list still works
- **WHEN** a client calls `get_status(universe_id="u-abc")`
- **THEN** the result equals the result of `get_status(command_center_id="u-abc")`, and one `alias_used name=universe_id handle=get_status` line is logged

#### Scenario: Conflicting names are refused, not guessed
- **WHEN** a client calls `read_page(universe_id="u-abc", command_center_id="u-def")`
- **THEN** the result is an error `conflicting_alias` naming both parameters, and nothing is read on either id's behalf

#### Scenario: The advertised schema carries no retired name
- **WHEN** a client reads `tools/list` and `prompts/list`
- **THEN** no description, parameter, target value, or prompt name contains "universe", and the handle set is still exactly the seven canonical handles

#### Scenario: A stored custom UI keeps working
- **WHEN** a custom UI bundle saved before the rename reads `universe_id` from the bridge identity
- **THEN** it receives the viewer's command center id, equal to `command_center_id`
