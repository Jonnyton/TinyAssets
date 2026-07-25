## ADDED Requirements

### Requirement: The detached sandbox diagnostic API is uncached, Linux-only, and not a runner backend

`tinyassets.sandbox` SHALL export its own `SandboxStatus`,
`SandboxUnavailableError`, `detect_bwrap`, and `check_bwrap_output`.
It SHALL also export `_BWRAP_FAILURE_PATTERNS`.
`SandboxStatus.to_dict()` SHALL return exactly `available`, `reason`,
`bwrap_path`, and `version`. This exception and status shape SHALL remain
distinct from the production provider-layer dictionary and exception.

`detect_bwrap` SHALL return unavailable immediately on non-Linux platforms,
when `bwrap` is absent from `PATH`, when `bwrap --version` exits nonzero, when
a minimal `bwrap --ro-bind / / /bin/sh -c true` launch exits nonzero, or when
launching either subprocess raises `OSError`; each subprocess SHALL have a
five-second timeout. It SHALL return available, the executable path, and the
reported version only after both subprocesses exit zero. It SHALL not cache
results. Exceptions other than `OSError` are not caught; in particular,
`subprocess.TimeoutExpired` SHALL propagate.

On Linux, `check_bwrap_output` SHALL case-insensitively recognize
`bwrap: No permissions to create a new namespace`,
`bwrap: No permissions to create new namespace`,
`bwrap: No such file or directory`, and
`sandbox initialization failed`, then raise the diagnostic exception; on every
non-Linux platform it SHALL be a no-op. As built, no production caller uses
this diagnostic API, and it is not a `SandboxBackend` implementation usable by
`SandboxRunner`. It therefore SHALL NOT be represented as provider readiness,
graph enforcement, workload confinement, or removal of platform-secret
co-residency.

#### Scenario: A healthy Linux diagnostic returns structured evidence

- **WHEN** `bwrap` is found and its version and minimal launch checks both exit zero on Linux
- **THEN** `detect_bwrap` returns `available=true` with its path and version
- **AND** a later call performs the probes again rather than reading a cache

#### Scenario: Unsupported, missing, failed, and OSError probes return unavailable

- **WHEN** the host is non-Linux, the executable is absent, either result is nonzero, or either launch raises `OSError`
- **THEN** `detect_bwrap` returns `available=false` with a reason and any evidence collected before the failure

#### Scenario: A diagnostic timeout propagates

- **WHEN** either diagnostic subprocess exceeds its five-second timeout
- **THEN** `subprocess.TimeoutExpired` propagates rather than becoming `SandboxStatus`

#### Scenario: The diagnostic is detached from production execution

- **WHEN** production provider, graph, or runner paths execute
- **THEN** they do not consume `detect_bwrap` or its exception class
- **AND** the existence of this API supplies no usable runner backend or confinement guarantee
