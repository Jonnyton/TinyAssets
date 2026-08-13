# Delta: universe-personification-and-relay — founder-scoped read-only engine MCP

## MODIFIED Requirement: The engine turn is confined by a fail-closed sandbox

Every universe-intelligence engine turn SHALL run with `sandbox_workspace=True`
(cwd pinned to the universe's own directory) and a fail-closed tool policy.
By default the policy requests `WebFetch` as the sole allowed tool and denies
every other currently-enumerated tool by name — including `Bash`, `Monitor`,
filesystem tools, scheduling/messaging tools, and all MCP server tools via the
`mcp__*` wildcard.

**Flag-gated founder-scoped read-only MCP exception.** When
`TINYASSETS_ENGINE_MCP_TOOLS` is enabled AND the turn is FOUNDER-tier AND a
verified request principal is present (`ProviderRequestCapability.principal_id`;
the raw conversation `actor_id` SHALL NOT be used — on app-channel paths it is a
`slack:<workspace>:<sender>` identifier, not the founder's subject), the engine
turn MAY additionally receive a LOCAL stdio TinyAssets MCP server wired via
`--mcp-config` + `--strict-mcp-config`, subject to ALL of:

- The server SHALL expose exactly two read-only handles: `read_graph` with
  targets restricted to `{status, graph}` and `graph_id` PINNED to the turn's
  own universe (never caller-suppliable), and `get_status` pinned via
  `universe_id`. No write, run, page, or converse handle is exposed.
- Both status paths (`get_status` and `read_graph target=status`) SHALL return a
  universe-scoped WHITELIST projection (`schema_version`, `universe_id`,
  `universe_exists`, `persona`, `universe_serving`); host/global fields and any
  future unlisted field SHALL be projected away (fail-closed).
- The server SHALL bind request identity to the verified principal with
  least-privilege read capabilities (`read`, `list` — no write, no
  submit_request), and SHALL refuse every call when the principal or the pinned
  universe id is absent.
- When the exception is active, the `mcp__*` wildcard deny MAY be dropped so the
  granted handles are admittable; isolation from ambient/account MCP connectors
  SHALL then come from `--strict-mcp-config`. If the strict MCP configuration
  cannot be installed, the turn SHALL FAIL rather than run with the relaxed
  policy.
- The learning-extraction turn SHALL NEVER receive MCP tools.
- Enabling the flag in a deployment SHALL be preceded by a negative canary on
  that deployment's pinned `claude` CLI version proving ambient account
  connectors are unreachable under `--strict-mcp-config`.

The universe's own soul and canon SHALL reach the engine via context injection
into the system prompt, NOT via a filesystem read tool, and brain writes SHALL
go through the separate governed learning path rather than the engine's tools.
As-built limitation: the denylist remains rot-prone as the CLI adds tools, and
true filesystem/OS-level confinement (bwrap/container) is deferred to the
`engine-os-sandbox` lane — which, when it lands, supersedes this policy-level
exception and requires re-authorizing the MCP grant inside its closed
workspace-projection model.

#### Scenario: the sandbox config locks the engine down (flag off)
- **WHEN** the engine `ModelConfig` for a universe turn is built with
  `TINYASSETS_ENGINE_MCP_TOOLS` unset
- **THEN** it pins the workspace to the universe's directory, requests
  `WebFetch` as the sole allowed tool, and denies the enumerated shell,
  filesystem, messaging, scheduling, and `mcp__*` tools

#### Scenario: founder turn gains read-only MCP handles (flag on)
- **WHEN** the flag is enabled and a FOUNDER-tier turn runs with a verified
  request principal
- **THEN** the engine additionally receives exactly
  `mcp__tinyassets__read_graph` and `mcp__tinyassets__get_status`, wired via
  `--mcp-config` + `--strict-mcp-config`, pinned to the turn's own universe

#### Scenario: non-founder and unverified turns stay WebFetch-only
- **WHEN** the flag is enabled but the turn is not FOUNDER-tier, or no verified
  request principal is present
- **THEN** the tool policy is identical to the flag-off default

#### Scenario: strict-config failure fails the turn
- **WHEN** the engine MCP exception is active but the strict MCP configuration
  cannot be written/installed
- **THEN** the provider call raises rather than launching with the relaxed
  (`mcp__*`-undenied) policy

#### Scenario: the status projection is a whitelist
- **WHEN** the engine calls `get_status` or `read_graph target=status`
- **THEN** the result contains only the universe-scoped whitelist fields, and
  host/global fields (including deployment receipt passthrough) are absent

#### Scenario: both engine turns stay sandboxed
- **WHEN** `converse` runs its reply turn and its learning-extraction turn
- **THEN** both turns use the fail-closed sandboxed config, and the
  learning-extraction turn never receives MCP tools
