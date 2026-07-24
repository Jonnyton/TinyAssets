## Why

Exact-landed production DR run `30062035537` validated the selected backup, then
DigitalOcean rejected the pinned `debian-12-x64` image with bounded HTTP 422
`invalid image`. DigitalOcean's current distribution catalog lists Debian 13 as
`debian-13-x64`; a static retired slug prevents the fresh-host drill from
reaching provisioning, restore, or cleanup proof.

## What Changes

- Resolve the newest available public Debian x64 image for the configured
  DigitalOcean region across a bounded traversal of the live
  distribution-image catalog before any mutating API request.
- Keep catalog lookup inside the bounded, credential-redacted DigitalOcean
  helper and fail before resource creation when no eligible image exists.
- Add an executable workflow regression that prohibits the retired static slug
  plus behavioral selector tests for pagination, cycles, malformed inventory,
  exact eligibility, and region-aware Debian image selection.
- Persist the resolved image slug in PASS/failure evidence.
- Rerun drill #3 only from the exact landed commit.

## Capabilities

### Modified Capabilities

- `uptime-and-alarms`: the fresh-host DR drill selects an available Debian x64
  image from current provider state rather than relying on a retired pin.

## Impact

- `.github/workflows/dr-drill.yml`
- `scripts/select_do_image.py`
- `tests/test_select_do_image.py`
- `tests/test_dr_drill_workflow.py`
- `docs/ops/dr-drill-runbook.md`
- `openspec/specs/uptime-and-alarms/spec.md`
- production DR workflow evidence
