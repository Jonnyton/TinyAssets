## ADDED Requirements

### Requirement: Compiled provider nodes preserve the production sandbox error without generic wrapping

The direct provider bridge and policy-routed provider paths SHALL preserve
sandbox-specific failures. In `compile_branch` they SHALL re-raise
`tinyassets.providers.base.SandboxUnavailableError` before their generic
provider-error wrapping. After a provider returns nonempty text, the graph
path SHALL defensively pass that response through the production
`check_bwrap_failure` recognizer before propagating the text into state.
Recognized response text SHALL therefore raise the provider-layer sandbox error;
normal text SHALL proceed unchanged.

This contract covers only the provider-layer exception class and its
platform-gated signature recognizer. The distinct
`tinyassets.sandbox.detect.SandboxUnavailableError` is not interoperable with
this path. Non-sandbox exceptions raised while importing or invoking the
defensive response checker are swallowed, and win32 recognition remains a
no-op.

#### Scenario: A provider-layer sandbox error crosses the graph boundary unchanged

- **WHEN** an injected or policy-routed provider raises `tinyassets.providers.base.SandboxUnavailableError`
- **THEN** the compiled node re-raises that same sandbox-specific exception
- **AND** generic provider-error wrapping does not replace it

#### Scenario: Leaked sandbox text is rejected before state propagation

- **WHEN** a nonempty provider response contains a recognized Bubblewrap failure signature on a checked platform
- **THEN** the response checker raises the provider-layer sandbox error
- **AND** the text is not returned as successful node output

#### Scenario: Normal provider text proceeds

- **WHEN** a nonempty provider response contains no recognized sandbox signature
- **THEN** the graph node returns the normal provider text

### Requirement: Branch sandbox demand is advisory metadata and never an execution gate

`NodeDefinition.requires_sandbox` SHALL default to false, serialize, and
round-trip. For rows admitted by the ordinary branch visibility and scope
rules, branch listing SHALL report `has_sandbox_nodes`. The
`requires_sandbox` filter SHALL be stripped and lowercased; `none` returns only
branches without marked nodes, `any` returns only branches with at least one
marked node, and an empty or any other value applies no sandbox-demand filter.

Branch validation SHALL best-effort read the cached production sandbox status.
When it is falsey and the branch contains marked nodes, validation SHALL add
one non-fatal warning that lists the sorted marked node IDs, the probe reason,
and remediation. It SHALL not warn for an available probe or an unmarked
branch; an exception while obtaining status SHALL suppress this advisory.

The metadata SHALL NOT affect structural validity or `runnable`, and neither
`compile_branch` nor provider selection consumes it as an admission or
execution gate. The current warning's statement that marked nodes will fail at
runtime is advisory wording, not an enforced or universal outcome.

#### Scenario: An unavailable host discloses marked nodes without blocking the branch

- **WHEN** validation sees a falsey cached probe and a branch with multiple `requires_sandbox=true` nodes
- **THEN** it returns one warning containing the sorted marked node IDs, probe reason, and remediation
- **AND** sandbox availability alone does not change `valid` or `runnable`

#### Scenario: Available and unmarked branches have no sandbox warning

- **WHEN** the cached probe is available or the branch contains no marked node
- **THEN** branch validation emits no sandbox-compatibility warning

#### Scenario: A probe exception suppresses only the advisory

- **WHEN** reading cached sandbox status raises during branch validation
- **THEN** validation continues without the sandbox warning
- **AND** its ordinary structural and approval results remain authoritative

#### Scenario: Branch listing filters declared demand after ordinary scope admission

- **WHEN** scope-eligible branches are listed with `requires_sandbox=none` or `requires_sandbox=any`
- **THEN** it returns respectively only unmarked branches or only branches with at least one marked node
- **AND** each returned row reports its `has_sandbox_nodes` value

#### Scenario: Empty and unknown filters preserve all otherwise-admitted rows

- **WHEN** scope-eligible rows are listed with an empty or unrecognized `requires_sandbox` value
- **THEN** every otherwise-admitted row remains
- **AND** each row still reports `has_sandbox_nodes`

#### Scenario: Runtime ignores the advisory flag

- **WHEN** a structurally runnable branch contains a node marked `requires_sandbox=true`
- **THEN** the flag itself neither blocks compilation nor selects a sandbox-capable provider
