## Why

The production deploy workflow publishes durable release state only after a
successful forward deploy. A later failure can roll production back without
replacing that receipt, while the `deploy-failed` issue claims "Rolled back to"
even when rollback was skipped or failed. Release reconciliation, public
status, and image-pull recovery therefore cannot distinguish the attempted
release from the image actually active after the terminal path. The current
receipt also trusts configured image state without proving that the daemon
container runs that image, and a manual old-tag deploy can incorrectly attach
the workflow-definition `github.sha` to unrelated image bytes.

## What Changes

- Capture the active release receipt before production mutation so rollback can
  preserve prior source and immutable-image ancestry only when the bounded,
  validated receipt matches observed production.
- Make rollback publish explicit attempted/result/canary/reason outputs even
  when one of its commands fails.
- Classify active identity from both the configured immutable image reference
  and the actual running daemon container. `deployed` and `rolled_back` require
  exact agreement with the expected target plus the applicable green canary.
- Derive source Git SHA only from provenance bound to the immutable digest or a
  validated matching prior receipt. A manual tag never inherits `github.sha`.
- Add one terminal receipt step after rollback handling. For every path that
  reached production mutation it atomically replaces `/data/release-state.json`
  with a bounded record that distinguishes the attempted release from the
  active release and records rollback truth.
- Publish a bounded `terminal_receipt_result` step output
  (`published|failed|not_applicable`) before returning any writer failure, so
  the issue step can report whether durable terminal truth was actually saved.
- Keep the existing successful-deploy fields for compatibility while adding a
  versioned terminal outcome, attempted/active identities, and structured
  rollback state. Define every legacy field and every `rollback_target` outcome
  so no failure path invents provenance or a future repair target.
- Make `deploy-failed` issue wording derive from bounded outputs; never say
  rollback succeeded when rollback was unavailable, skipped, red, or not proven
  by configured/running identity agreement.
- Put classification and receipt construction in a small pure executable with
  table-driven unit tests; keep workflow shell responsible only for observation,
  mutation, transport, and atomic installation.
- Preserve the workflow's red result after a failed deploy or rollback; receipt
  publication is evidence, not recovery.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `uptime-and-alarms`: Require truthful terminal release-state publication,
  dual-observation active-image agreement, safe rollback ancestry, and
  outcome-conditional deploy failure reporting after production mutation.

## Impact

The change affects `.github/workflows/deploy-prod.yml`, its structural workflow
tests, a small pure receipt-classifier/builder and its matrix tests, and the
canonical uptime-and-alarms contract after implementation sync. It does not
change build admission, deployment concurrency, the public MCP schema, provider
credentials, compute selection, or rollback eligibility policy. A merged
workflow still requires an observed live failure/rollback exercise before the
host is claimed to have produced the new terminal evidence.
