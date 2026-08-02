## ADDED Requirements

### Requirement: Full get_status responses expose cached sandbox readiness without making the read fail

Full live `get_status` responses SHALL include cached sandbox readiness. When
the path reaches full daemon-status assembly, the response includes
`sandbox_status` from the production
`tinyassets.providers.base.get_sandbox_status` cache. Its ordinary shape SHALL
include boolean `bwrap_available` and nullable or explanatory `reason`. If
obtaining the cached result raises, the sandbox lookup failure SHALL be caught
and substituted with `{"bwrap_available": false, "reason": "probe_error:
<exception>"}` without itself aborting the remaining assembly.

This evidence is a best-effort, process-cached readiness observation. Reading
status SHALL not refresh the probe, provision a universe, gate execution, or
assert OS confinement. Early no-home, access-denied, or configuration-load
responses return before full status assembly and do not include this field.

#### Scenario: Full status returns the cached readiness dictionary

- **WHEN** `get_status` passes its early gates and obtains a cached unavailable or available sandbox result
- **THEN** its response includes that dictionary under `sandbox_status`

#### Scenario: A probe error does not break status

- **WHEN** obtaining sandbox status raises an exception
- **THEN** the lookup failure is caught and does not itself abort full daemon-status assembly
- **AND** `sandbox_status.bwrap_available` is false with a `probe_error` reason

#### Scenario: Early status responses omit sandbox evidence

- **WHEN** `get_status` returns early for no bound home, denied access, or configuration-load failure
- **THEN** that early response does not include `sandbox_status`
