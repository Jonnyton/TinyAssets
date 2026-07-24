## Why

The DNS and LLM-binding canaries publish red probe outputs from tolerated
steps, but their probe jobs still conclude success. Their alarm sinks use the
prior workflow conclusion as the consecutive-red signal, so repeated red
probes can remain permanently below the incident threshold.

## What Changes

- Preserve probe output publication from a tolerated probe step.
- Preserve the always-running alarm sink so it can process the current result.
- Add a final probe-job status propagation step that fails exactly when the
  published overall result is red, making the current workflow failure visible
  to the next scheduled run.
- Apply the same controller shape to the DNS and LLM-binding canaries.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `uptime-and-alarms`: DNS and LLM-binding red results must propagate to the
  workflow conclusion after current-run alarm processing remains available.

## Impact

Affected surfaces are `.github/workflows/dns-canary.yml`,
`.github/workflows/llm-binding-canary.yml`, their structural tests, and the
canonical uptime-and-alarms behavioral contract. No API, dependency, secret,
or alarm-threshold change is introduced.
