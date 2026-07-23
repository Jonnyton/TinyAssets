## ADDED Requirements

### Requirement: get_status exposes cached sandbox readiness without making the read fail

The live `get_status` response SHALL include `sandbox_status` from the
production `tinyassets.providers.base.get_sandbox_status` cache. Its ordinary
shape SHALL include boolean `bwrap_available` and nullable or explanatory
`reason`. If obtaining the cached result raises, `get_status` SHALL still
succeed and substitute `{"bwrap_available": false, "reason":
"probe_error: <exception>"}`.

This evidence is a best-effort, process-cached readiness observation. Reading
status SHALL not refresh the probe, provision a universe, gate execution, or
assert OS confinement.

#### Scenario: Status returns the cached readiness dictionary

- **WHEN** `get_status` obtains a cached unavailable or available sandbox result
- **THEN** its response includes that dictionary under `sandbox_status`

#### Scenario: A probe error does not break status

- **WHEN** obtaining sandbox status raises an exception
- **THEN** the broader `get_status` call still succeeds
- **AND** `sandbox_status.bwrap_available` is false with a `probe_error` reason
