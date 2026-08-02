## ADDED Requirements

### Requirement: Custom agents route through canonical graph handles
The public MCP surface SHALL expose custom-agent operations only as targets of `read_graph` and `write_graph`, SHALL keep the advertised tool set at exactly seven canonical handles, and SHALL delegate those targets to the custom-agent API without weakening its public-definition or private-binding authorization rules.

#### Scenario: Anonymous caller browses the public agent commons
- **WHEN** an anonymous caller uses `read_graph` with target `agents` or `agent`
- **THEN** the router returns public agent definitions through the custom-agent API
- **AND** no private universe binding is exposed

#### Scenario: Authorized founder manages a private binding
- **WHEN** an authenticated universe writer uses `write_graph` target `agent_binding` and later reads target `agent_binding`
- **THEN** both calls delegate to the custom-agent API with the current request identity
- **AND** the binding is visible only under the universe authorization contract

#### Scenario: Agent targets do not expand the handle set
- **WHEN** a client lists tools after custom-agent targets are installed
- **THEN** the advertised set remains `{read_graph, write_graph, run_graph, read_page, write_page, converse, get_status}` and nothing else
