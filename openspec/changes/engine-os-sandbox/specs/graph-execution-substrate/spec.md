## RENAMED Requirements

- FROM: `source_code nodes execute in-process behind a fail-closed approval gate`
- TO: `source_code nodes execute through the runner behind a fail-closed approval gate`

## MODIFIED Requirements

### Requirement: source_code nodes execute through the runner behind a fail-closed approval gate

A `source_code` node SHALL execute only after `_validate_source_code` confirms `approved=true`, a non-empty `approved_source_hash` equal to `sha256` of the effective source, and the existing source-policy checks. These checks are authoring eligibility only: they SHALL NOT attest containment, select a backend, or authorize in-process `exec`.

After eligibility, the trusted graph or NodeBid call site SHALL derive an
immutable logical `ExecutionRequirement` with `workload=source_exec`,
`profile=runner_source_exec`, and exact policy, isolation, source-projection,
egress, credential, and authority references plus digests. The
distributed-execution owner SHALL seal that requirement into an outer capsule
keyed to the inner job's `job_id`, then dispatch through `SandboxRunner` using
the existing `JobCapability.SOURCE_EXEC`. Graph compilation and NodeBid
execution SHALL NOT invoke the source in the daemon process or fall back to
`NodeSandbox`, a same-UID child, provider execution, or another
`JobCapability`. Accepted-market work SHALL use its B2/B13 authority evidence
in the outer capsule without entering ordinary provider routing.

`inference_only` SHALL remain execution-admission vocabulary only and SHALL
NOT be added to `JobCapability`. `JOB_REQUEST_SCHEMA_VERSION` SHALL remain
exactly `runner-job/v1`; `JOB_RESULT_SCHEMA_VERSION` SHALL remain exactly
`runner-result/v1`; the existing `JobCapability` values and immutable
capability/action mapping SHALL remain unchanged. No admission field SHALL be
added to request or result wire objects or `EnforcementReceipt` in this lane.
Runner result statuses SHALL remain exactly `succeeded`, `failed`, and
`cancelled`; graph run statuses SHALL remain exactly `queued`, `running`,
`completed`, `failed`, `cancelled`, `interrupted`, and `resumed`.
Source execution SHALL remain disabled until distributed execution supplies
the sealed outer capsule or explicitly versions its own inner wire.

The source projection SHALL contain no caller-selected host path, repository
root, universe root, current working directory, home, auth home,
credential/vault path, or ambient data root. Admission SHALL verify every
policy, isolation, projection, egress, credential, and authority binding and
the outer capsule. The combined pre-launch and post-launch checks SHALL prove
the complete `os_isolated` guarantee set for the exact execution:
kernel-enforced daemon separation, exact default-deny filesystem and network
policy, explicit resource limits, absent platform secrets and undeclared
devices, bounded cleanup, and binding to the requirement and actual launch. A
`vm_isolated` label is stronger only when the combined checks prove every base
guarantee plus a distinct guest-kernel boundary and default-deny host-device
passthrough.

Missing, stale, mismatched, unknown, malformed, unsupported, or unsatisfied
pre-launch requirement/capsule/profile/property data SHALL become shared
`ExecutionAdmissionError` with a closed reason code. Graph/NodeBid SHALL
normalize runner preflight and protocol refusals into that type and terminate
the run as `failed` without in-process execution or fallback.
Pre-launch property evidence SHALL prove support for the required enforcement
mechanisms and bind the exact planned launch configuration and protocol
commitment to return request-bound launch evidence; it SHALL NOT attest the
future execution, enforcement, cleanup, or result.

Post-launch validation SHALL verify returned evidence bound to the same outer
capsule, inner `job_id`, and actual execution and SHALL alone prove the
complete guarantee set for that execution. Missing or invalid actual-launch
evidence SHALL become
`ExecutionAdmissionError(reason=backend_evidence_invalid)`; the output SHALL
NOT become a successful runner result, graph output, or fallback input.
Backend execution failure with valid evidence after successful dispatch
remains a runner result rather than an admission error.

`ExecutionAdmissionError.reason` SHALL be exactly one of
`requirement_missing`, `requirement_untrusted`, `requirement_malformed`,
`binding_mismatch`, `profile_unsupported`, `isolation_unsatisfied`,
`backend_unavailable`, `backend_protocol_mismatch`, or
`backend_evidence_invalid`. It SHALL remain distinct from provider authority
hold, provider failure/exhaustion, cooldown, provider-attempt evidence, native
runner exceptions, and backend results. Provider, universe, runner, and B2/B13
owners SHALL map their pre-launch refusals into this shared taxonomy without
changing its meaning.

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
- **THEN** trusted code derives `source_exec/runner_source_exec` with matching policy, isolation, projection, owner-defined deny-all-egress/no-credential, and authority-evidence bindings
- **AND** a sealed outer capsule binds that requirement to the inner `job_id` before `SandboxRunner` receives existing `JobCapability.SOURCE_EXEC`
- **AND** neither the daemon process nor the legacy same-UID child executes the source

#### Scenario: source projection is closed

- **WHEN** trusted code constructs a source_exec request
- **THEN** its projection contains only the approved source and declared JSON-object inputs
- **AND** no complete universe, repository, host, credential, vault, auth-home, or ambient data path is projected

#### Scenario: runner wire and capability vocabulary stay frozen

- **WHEN** source_exec admission and guarantee-set comparison are implemented
- **THEN** request and result schema versions remain `runner-job/v1` and `runner-result/v1`
- **AND** no `inference_only` or other new `JobCapability` or capability action is introduced
- **AND** runner result and graph run status vocabularies remain unchanged
- **AND** the complete requirement and backend evidence are bound outside the inner wire by `job_id`

#### Scenario: unavailable execution admission terminates the run

- **WHEN** the requirement, outer capsule, one of its bound references/digests, or backend evidence is missing, stale, mismatched, unknown, malformed, unsupported, or fails property-set inclusion, or runner preflight refuses
- **THEN** the graph or NodeBid execution ends as `failed` with shared `ExecutionAdmissionError`
- **AND** it does not execute in-process or fall back to another provider, runner capability, or execution mode

#### Scenario: invalid actual-launch evidence cannot succeed

- **WHEN** returned backend evidence does not bind to the admitted outer capsule, inner `job_id`, and actual execution
- **THEN** the run ends `failed` with `ExecutionAdmissionError(reason=backend_evidence_invalid)`
- **AND** no backend output becomes a successful runner result, graph output, or fallback input

### Requirement: Branch sandbox demand is advisory metadata and never an execution gate

`NodeDefinition.requires_sandbox` SHALL default to false, serialize, and
round-trip as advisory metadata for branch listing and filtering, but SHALL
NOT be an authority input and SHALL NOT lower, replace, or satisfy a trusted
logical `ExecutionRequirement`. The trusted compiler SHALL derive the
requirement from executable node shape regardless of that flag: prompt nodes
use `inference_only/provider_cli/tool_denied`; `source_code` nodes use
`source_exec/runner_source_exec`.

For rows admitted by ordinary branch visibility and scope rules, branch
listing SHALL continue to report `has_sandbox_nodes`. The
`requires_sandbox` filter SHALL be stripped and lowercased; `none` returns
only branches without marked nodes, `any` returns only branches with at least
one marked node, and an empty or other value applies no sandbox-demand filter.

Branch validation SHALL best-effort read the cached sandbox diagnostic. When
it is falsey and the branch contains marked nodes, validation SHALL add exactly
one non-fatal diagnostic warning listing the sorted marked node IDs, diagnostic
reason, and remediation. It SHALL not warn for a truthy diagnostic or an
unmarked branch; an exception while reading status SHALL suppress only this
advisory. The warning SHALL NOT claim runtime executability, backend admission,
or OS isolation, and neither it nor the flag may affect the derived
requirement.

The metadata SHALL NOT affect structural validity or `runnable`; structural
validation may therefore report a branch runnable before backend admission. At
execution, every executable node SHALL pass the closed
workload/profile/reference/guarantee predicate. The graph SHALL preserve
shared `ExecutionAdmissionError` before generic provider wrapping or fallback,
normalize runner preflight/protocol refusal into its closed reason taxonomy,
and terminate the run as `failed`; provider/backend errors after successful
admission remain distinct. False or absent `requires_sandbox` metadata SHALL
never authorize unconfined execution.

#### Scenario: prompt nodes are always tool-denied inference

- **WHEN** a structurally runnable branch contains a prompt node with `requires_sandbox` absent, false, or true
- **THEN** the trusted compiler derives `inference_only/provider_cli/tool_denied` with matching bound references, digests, and required isolation guarantees
- **AND** the node receives no Bash, filesystem, WebFetch, scheduling, messaging, MCP, or future unenumerated tool

#### Scenario: source nodes are always runner-backed source_exec

- **WHEN** a structurally runnable branch contains an eligible source_code node with `requires_sandbox` absent, false, or true
- **THEN** the trusted compiler derives `source_exec/runner_source_exec` with matching bound references, digests, and required isolation guarantees
- **AND** execution uses existing `JobCapability.SOURCE_EXEC`

#### Scenario: advisory metadata still filters admitted branch rows

- **WHEN** scope-eligible branches are listed with `requires_sandbox=none` or `requires_sandbox=any`
- **THEN** the result contains respectively only unmarked branches or only branches with at least one marked node
- **AND** each returned row reports `has_sandbox_nodes`

#### Scenario: empty and unknown filters preserve otherwise-admitted rows

- **WHEN** scope-eligible rows are listed with an empty or unrecognized `requires_sandbox` filter
- **THEN** every otherwise-admitted row remains
- **AND** each row still reports `has_sandbox_nodes`

#### Scenario: unavailable diagnostic emits one non-authoritative warning

- **WHEN** validation sees a falsey cached diagnostic and multiple marked nodes
- **THEN** it emits exactly one non-fatal warning with sorted node IDs, reason, and remediation
- **AND** the warning does not change structural validity, `runnable`, or execution admission

#### Scenario: available and unmarked branches have no diagnostic warning

- **WHEN** the cached diagnostic is truthy or the branch contains no marked node
- **THEN** validation emits no sandbox-compatibility warning

#### Scenario: diagnostic failure suppresses only the advisory

- **WHEN** reading cached sandbox status raises during validation
- **THEN** validation continues without the warning
- **AND** ordinary structural, approval, and `runnable` results are preserved

#### Scenario: metadata and diagnostics cannot bypass admission

- **WHEN** `requires_sandbox` is false or cached sandbox status reports available
- **THEN** neither signal satisfies, lowers, or replaces the trusted requirement
- **AND** missing or incompatible backend admission terminates execution as `failed` with shared `ExecutionAdmissionError`
