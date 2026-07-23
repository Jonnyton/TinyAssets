## ADDED Requirements

### Requirement: The live server publishes four behavioral prompts with exact metadata
The system SHALL register exactly the following prompt catalog on the live server:

| Prompt name | Title | Tags |
|---|---|---|
| `control_station` | `Control Station Guide` | `control`, `daemon`, `multiplayer`, `operations` |
| `meet_universe` | `Meet Your Universe` | `first-contact`, `onboarding`, `persona`, `tinyassets` |
| `extension_guide` | `Extension Authoring Guide` | `extensions`, `nodes`, `plugins`, `tinyassets` |
| `branch_design_guide` | `Branch Design Guide` | `branches`, `customization`, `extensions`, `graph` |

Each prompt SHALL return its registered behavioral guide and SHALL expose its function docstring as discoverability text.

#### Scenario: Prompt listing returns the exact catalog
- **WHEN** an MCP client lists prompts on the live server
- **THEN** the response contains the four names, titles, and tag sets above with no additional registered prompt

#### Scenario: Prompt invocation returns the owned guide
- **WHEN** an MCP client invokes any catalogued prompt
- **THEN** the server returns that prompt's registered control, first-contact, extension-authoring, or branch-design guide

### Requirement: Registered tools publish exact discoverability and behavior metadata
The system SHALL attach the following title, tag set, and four MCP behavior hints to every currently registered tool. In the hint columns, `T` means true and `F` means false, ordered as read-only, destructive, idempotent, and open-world:

| Tool | Title | Tags | R | D | I | O |
|---|---|---|---:|---:|---:|---:|
| `read_graph` | `Read Graph` | `graph`, `read`, `tinyassets` | T | F | T | F |
| `write_graph` | `Write Graph` | `graph`, `tinyassets`, `write` | F | F | F | F |
| `run_graph` | `Run Graph` | `graph`, `run`, `tinyassets` | F | F | F | F |
| `read_page` | `Read Page` | `page`, `read`, `tinyassets`, `wiki` | T | F | T | F |
| `write_page` | `Write Page` | `page`, `tinyassets`, `wiki`, `write` | F | F | F | T |
| `converse` | `Talk With Your Universe` | `relay`, `tinyassets`, `universe` | F | F | F | F |
| `universe` | `Universe Operations` | `agent-workflow`, `ai-builder`, `collaboration`, `custom-ai`, `daemon`, `general-purpose`, `tinyassets`, `universe`, `universe-builder`, `workflow-builder` | F | F | F | T |
| `community_change_context` | `Community Change Context` | `change-loop`, `community`, `github`, `plan`, `pull-request`, `review`, `tinyassets` | T | F | T | T |
| `extensions` | `Graph Extensions` | `customization`, `extensions`, `nodes`, `plugins` | F | F | F | T |
| `goals` | `Goals` | `community`, `discovery`, `goals`, `intent` | F | F | F | T |
| `gates` | `Outcome Gates` | `community`, `gates`, `impact`, `leaderboard`, `outcomes` | F | F | F | T |
| `wiki` | `Wiki Knowledge Base` | `drafts`, `knowledge`, `pages`, `research`, `wiki` | F | T | F | T |
| `get_status` | `Daemon Status + Routing Evidence` | `confidential-tier`, `privacy`, `routing`, `status`, `tinyassets`, `verification` | T | F | T | F |

These hints SHALL remain descriptive MCP metadata rather than authorization enforcement; the tool implementations and permission middleware retain authority over whether an invocation can mutate or access state.

#### Scenario: Raw registry listing carries exact metadata
- **WHEN** the server registry is listed without deprecated-tool visibility filtering
- **THEN** every registered tool has the exact title, tag set, and four behavior-hint values in the table

#### Scenario: Behavior hints do not grant authority
- **WHEN** a tool's metadata marks it non-destructive or open-world
- **THEN** that metadata alone does not bypass the tool's write gate, authentication, ownership, or action-specific validation

