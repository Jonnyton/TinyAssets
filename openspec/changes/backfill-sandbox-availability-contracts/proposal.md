## Why

The shipped Bubblewrap readiness probes, CLI mode selection, sandbox-failure
recognition, graph propagation, branch disclosure, and public status evidence
have focused tests but no canonical OpenSpec owner. A second exported
`tinyassets.sandbox` diagnostic API is also shipped and tested but remains
detached from the production provider path.

Without an as-built contract, future confinement work can easily overstate the
current system: ordinary Codex calls bypass its sandbox when the provider probe
is unavailable, `requires_sandbox` is advisory metadata rather than an
execution gate, and neither probe is an OS-isolating backend.

## What Changes

- Extend `provider-routing` with the production cached Bubblewrap probe, Codex
  CLI flag selection, and bounded stderr failure recognition.
- Extend `graph-execution-substrate` with provider-layer sandbox-error
  propagation and the non-fatal `requires_sandbox` branch disclosure.
- Extend `live-mcp-connector-surface` with the best-effort
  `get_status.sandbox_status` read contract.
- Extend `distributed-execution` with the separate, uncached
  `tinyassets.sandbox` diagnostic API and its explicit lack of production
  integration.
- Preserve the current gaps as normative limitations: no OS backend, no
  `converse` confinement, no fail-closed `requires_sandbox` admission, an
  ordinary Codex dangerous-bypass fallback, and a fast-exit ordering that can
  preempt typed sandbox-failure recognition.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-routing`: provider-facing sandbox readiness and CLI failure
  semantics.
- `graph-execution-substrate`: graph propagation and advisory sandbox-demand
  metadata.
- `live-mcp-connector-surface`: best-effort sandbox evidence in `get_status`.
- `distributed-execution`: the detached sandbox-detection compatibility API.

## Impact

This is current-behavior reconciliation only. It changes canonical OpenSpec,
the full-coverage audit, and coordination records. It does not change runtime
code, provider credentials, CLI flags, graph admission, public response
shapes, plugin payloads, deployments, or the active future confinement
changes. Primary evidence is the current provider, graph, branch, status, and
sandbox-detection source plus their focused tests.
