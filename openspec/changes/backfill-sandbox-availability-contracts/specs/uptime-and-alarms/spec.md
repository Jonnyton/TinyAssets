## ADDED Requirements

### Requirement: Production deploy verifies reported LLM binding and sandbox readiness after public canaries

The production deploy workflow SHALL run `scripts/verify_llm_binding.py` after
the public canaries in both the configured-auth-bundle and no-bundle branches
with `--timeout 20 --require-sandbox --retries 12 --retry-delay 10`. The
verifier SHALL first require a reported LLM binding. When sandbox checking is
enabled, a missing or falsey `sandbox_status.bwrap_available` SHALL raise
`VerifyError` code 5 carrying the reported reason. The CLI SHALL retry failed
verification up to the requested total attempt count and return the last error
code if no attempt recovers.

This post-deploy readiness gate is distinct from the scheduled LLM-binding
canary, which intentionally omits `--require-sandbox`. Neither path executes a
model request, and a green readiness observation is not proof of workload
confinement.

#### Scenario: Missing sandbox readiness produces exit code 5

- **WHEN** the verifier sees a reported LLM binding but missing or falsey `sandbox_status.bwrap_available`
- **THEN** the sandbox check raises `VerifyError` code 5 with the reported reason
- **AND** exhausting the configured attempts returns exit code 5

#### Scenario: A later green observation recovers within the retry budget

- **WHEN** an earlier attempt reports unavailable sandbox readiness and a later attempt reports `bwrap_available=true`
- **THEN** the CLI retries through the configured total-attempt budget
- **AND** returns exit code 0 after the green observation

#### Scenario: Both deploy auth branches require the same readiness evidence

- **WHEN** production deployment reaches post-canary verification with or without a configured Codex auth bundle
- **THEN** the selected branch invokes the verifier with timeout 20, required sandbox readiness, 12 total attempts, and a 10-second retry delay
