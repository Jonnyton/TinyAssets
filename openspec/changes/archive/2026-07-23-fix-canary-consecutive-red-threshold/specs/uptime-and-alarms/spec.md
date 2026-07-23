## MODIFIED Requirements

### Requirement: DNS resolution canary reports probe state through a prior-conclusion alarm sink
The system SHALL declare the DNS canary on GitHub-hosted infrastructure with a `*/15 * * * *` schedule, manual dispatch, and a `dns-canary` concurrency group whose `cancel-in-progress` value is false. That setting SHALL preserve an already running job, while GitHub's concurrency controller MAY replace an older pending same-group run when another run queues; neither the declared schedule nor the group SHALL promise actual dispatch latency or one execution per schedule tick. The probe SHALL call `socket.gethostbyname` once for `tinyassets.io` and once for `mcp.tinyassets.io`, report green only when both calls return without error, and report red otherwise. It SHALL NOT claim that the returned address is public, current across all resolvers, or reachable. The probe job SHALL publish its overall result and diagnostics from a tolerated probe step, then a final non-tolerated step SHALL fail if and only if the published overall result is red. The alarm sink, when the workflow executes, SHALL run regardless of probe-job success, consume the published current-run outputs, create the `dns-red` label if absent, open an issue only when the immediately preceding completed workflow run also failed, append later red evidence to an open issue, and comment recovery before closing an open issue on green.

#### Scenario: Both names resolve
- **WHEN** both single-address resolver calls return without error
- **THEN** the probe reports green even though it does not classify or connect to either returned address, and the final propagation step succeeds

#### Scenario: First red does not page
- **WHEN** the probe is red, there is no open `dns-red` issue, and the immediately prior completed workflow run did not fail
- **THEN** the alarm sink records first-red output without opening an issue and the probe job concludes failure after publishing that output

#### Scenario: Consecutive red opens or updates the incident
- **WHEN** the probe is red and either the immediately prior completed run failed or a `dns-red` issue is already open
- **THEN** the sink opens the threshold-crossing issue or appends the new resolver evidence to the existing issue

#### Scenario: Red conclusion becomes threshold evidence
- **WHEN** the tolerated probe step publishes red
- **THEN** the final probe-job step exits non-zero, the current alarm sink still receives the published red output, and the completed workflow exposes failure to the next run

#### Scenario: Green closes an open DNS incident
- **WHEN** the probe is green and a `dns-red` issue is open
- **THEN** the sink comments `GREEN — RECOVERED` evidence and closes the issue as completed

### Requirement: LLM binding canary verifies status presence rather than provider execution
The system SHALL declare the LLM-binding canary on GitHub-hosted infrastructure with a `0 */6 * * *` schedule, manual dispatch, and an `llm-binding-canary` concurrency group whose `cancel-in-progress` value is false. That setting SHALL preserve an already running job, while GitHub's concurrency controller MAY replace an older pending same-group run when another run queues; neither the declared schedule nor the group SHALL promise actual dispatch latency or one execution per schedule tick. When executed, the canary SHALL initialize an MCP session at `https://tinyassets.io/mcp`, call `get_status`, and select `active_host.llm_endpoint_bound` whenever `active_host` is an object containing that key, including when its value is unset; it SHALL use the historical top-level `llm_endpoint_bound` only when the nested key is absent. It SHALL report red when the selected value is `unset`, empty, false, or none. The workflow SHALL NOT require the optional sandbox check and SHALL NOT execute a model request, so green proves only a reported binding. The probe job SHALL publish its overall result and diagnostics from a tolerated probe step, then a final non-tolerated step SHALL fail if and only if the published overall result is red. Its alarm sink SHALL run regardless of probe-job success, consume the published current-run outputs, and use the same first-red, immediately-prior-failed-run threshold, open-issue append, and green-recovery close lifecycle under `llm-binding-red`.

#### Scenario: Reported endpoint is bound
- **WHEN** MCP initialization and `get_status` succeed and the accepted status field contains a non-empty value other than unset, false, or none
- **THEN** the canary reports green without proving that the provider can complete a model call, and the final propagation step succeeds

#### Scenario: Missing binding or probe failure is red
- **WHEN** the status reports an unset binding or the MCP protocol, network, response shape, or tool call fails
- **THEN** the probe returns non-zero and the workflow exposes red to the alarm sink

#### Scenario: Nested unset binding shadows a historical top-level value
- **WHEN** `active_host` contains `llm_endpoint_bound = "unset"` while the top-level field contains a non-empty historical value
- **THEN** the canary selects the nested unset value and reports red

#### Scenario: Two workflow failures open the binding incident
- **WHEN** the current probe is red, no issue is open, and the immediately prior completed workflow run concluded failure
- **THEN** the sink opens an `llm-binding-red` issue with endpoint, exit, output, run, likely-cause, and runbook evidence

#### Scenario: Red conclusion becomes threshold evidence
- **WHEN** the tolerated probe step publishes red
- **THEN** the final probe-job step exits non-zero, the current alarm sink still receives the published red output, and the completed workflow exposes failure to the next run

#### Scenario: Binding recovery closes the incident
- **WHEN** the probe is green and an `llm-binding-red` issue is open
- **THEN** the sink comments recovery evidence and closes the issue as completed
