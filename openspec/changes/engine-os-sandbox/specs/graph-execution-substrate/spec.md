## MODIFIED Requirements

### Requirement: source_code nodes execute in-process behind a fail-closed approval gate

A `source_code` node SHALL execute only after `_validate_source_code` confirms `approved=true`, a non-empty `approved_source_hash` equal to `sha256` of the effective source, and the existing source-policy checks. These checks are authoring eligibility only: they SHALL NOT attest containment, select a backend, or authorize in-process `exec`.

After eligibility, the trusted graph or NodeBid call site SHALL derive an immutable `ExecutionRequirement` with `workload=source_exec`, `profile=runner_source_exec`, the exact runner source-policy digest, `minimum_isolation=os_isolated`, a closed source-projection reference and digest, an explicit deny-all egress requirement reference and digest, credential delivery `none`, and the applicable #1784- or B2/B13-owned authority-evidence reference. It SHALL dispatch through `SandboxRunner` using the existing `JobCapability.SOURCE_EXEC`. Graph compilation and NodeBid execution SHALL NOT invoke the source in the daemon process or fall back to `NodeSandbox`, a same-UID child, provider execution, or another `JobCapability`.

`inference_only` SHALL remain execution-admission vocabulary only and SHALL NOT be added to `JobCapability`. `JOB_REQUEST_SCHEMA_VERSION` SHALL remain exactly `runner-job/v1`; `JOB_RESULT_SCHEMA_VERSION` SHALL remain exactly `runner-result/v1`; the existing `JobCapability` values and immutable capability/action mapping SHALL remain unchanged. An isolation tier may be an additive in-process `RunnerCapabilities` field owned by distributed execution, but SHALL NOT be added to request or result wire objects or `EnforcementReceipt`.

The source projection SHALL contain no caller-selected host path, repository root, universe root, current working directory, home, auth home, credential/vault path, or ambient data root. Admission SHALL verify every policy, projection, egress, credential-delivery, and authority-evidence binding as well as the backend's profile/tier binding. Missing, stale, mismatched, or unknown requirement/profile/tier data or bound reference, an unsatisfied backend binding, runner preflight refusal, or malformed backend evidence SHALL terminate the run as `failed` without in-process execution or fallback.

#### Scenario: an unapproved or hash-mismatched node is refused

- **WHEN** a source_code node runs without `approved=true`, or with a missing, stale, or forged `approved_source_hash`
- **THEN** `UnapprovedNodeError` is raised before runner dispatch
- **AND** approval or a matching hash does not itself claim isolation

#### Scenario: a disallowed source policy is refused

- **WHEN** an approved source_code node violates an existing source-policy check
- **THEN** `CompilerError` is raised before runner dispatch
- **AND** no execution backend receives the source

#### Scenario: eligible source executes only through source_exec

- **WHEN** a source_code node or NodeBid source passes its approval, hash, and input admission checks
- **THEN** trusted code derives `source_exec/runner_source_exec/os_isolated` with matching policy, projection, deny-all egress, no-credential, and authority-evidence bindings
- **AND** it submits the work through `SandboxRunner` as existing `JobCapability.SOURCE_EXEC`
- **AND** neither the daemon process nor the legacy same-UID child executes the source

#### Scenario: source projection is closed

- **WHEN** trusted code constructs a source_exec request
- **THEN** its projection contains only the approved source and declared JSON-object inputs
- **AND** no complete universe, repository, host, credential, vault, auth-home, or ambient data path is projected

#### Scenario: runner wire and capability vocabulary stay frozen

- **WHEN** source_exec admission and tier comparison are implemented
- **THEN** request and result schema versions remain `runner-job/v1` and `runner-result/v1`
- **AND** no `inference_only` or other new `JobCapability` or capability action is introduced

#### Scenario: unavailable execution admission terminates the run

- **WHEN** the requirement, one of its bound references/digests, or the backend binding is missing, stale, mismatched, unknown, malformed, or below `os_isolated`, or runner preflight refuses
- **THEN** the graph or NodeBid execution ends as `failed`
- **AND** it does not execute in-process or fall back to another provider, runner capability, or execution mode

### Requirement: Branch sandbox demand is advisory metadata and never an execution gate

`NodeDefinition.requires_sandbox` SHALL remain serializable advisory metadata for branch listing and filtering, but SHALL NOT be an authority input and SHALL NOT lower, replace, or satisfy a trusted `ExecutionRequirement`. The trusted compiler SHALL derive the requirement from executable node shape regardless of that flag: prompt nodes use `inference_only/provider_cli/tool_denied/os_isolated`; `source_code` nodes use `source_exec/runner_source_exec/os_isolated`.

For rows admitted by ordinary branch visibility and scope rules, branch listing SHALL continue to report `has_sandbox_nodes`. The `requires_sandbox` filter SHALL be stripped and lowercased; `none` returns only branches without marked nodes, `any` returns only branches with at least one marked node, and an empty or other value applies no sandbox-demand filter. Cached sandbox status MAY support a clearly diagnostic warning, but neither it nor the flag may affect the derived requirement or attest executability.

Structural validation MAY report a branch as structurally valid before backend admission. At execution, every executable node SHALL pass the closed workload/profile/policy/tier and bound-reference predicate. The graph SHALL preserve the provider owner’s non-fallbackable execution-admission exception unchanged before generic provider wrapping or fallback and terminate the run as `failed`; provider errors after successful admission remain distinct. False or absent `requires_sandbox` metadata SHALL never authorize unconfined execution.

#### Scenario: prompt nodes are always tool-denied inference

- **WHEN** a structurally runnable branch contains a prompt node with `requires_sandbox` absent, false, or true
- **THEN** the trusted compiler derives `inference_only/provider_cli/tool_denied/os_isolated` with matching bound references and digests
- **AND** the node receives no Bash, filesystem, WebFetch, scheduling, messaging, MCP, or future unenumerated tool

#### Scenario: source nodes are always runner-backed source_exec

- **WHEN** a structurally runnable branch contains an eligible source_code node with `requires_sandbox` absent, false, or true
- **THEN** the trusted compiler derives `source_exec/runner_source_exec/os_isolated` with matching bound references and digests
- **AND** execution uses existing `JobCapability.SOURCE_EXEC`

#### Scenario: advisory metadata still filters admitted branch rows

- **WHEN** scope-eligible branches are listed with `requires_sandbox=none` or `requires_sandbox=any`
- **THEN** the result contains respectively only unmarked branches or only branches with at least one marked node
- **AND** each returned row reports `has_sandbox_nodes`

#### Scenario: empty and unknown filters preserve otherwise-admitted rows

- **WHEN** scope-eligible rows are listed with an empty or unrecognized `requires_sandbox` filter
- **THEN** every otherwise-admitted row remains
- **AND** each row still reports `has_sandbox_nodes`

#### Scenario: metadata and diagnostics cannot bypass admission

- **WHEN** `requires_sandbox` is false or cached sandbox status reports available
- **THEN** neither signal satisfies, lowers, or replaces the trusted requirement
- **AND** missing or incompatible backend admission terminates execution as `failed`
