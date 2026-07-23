## ADDED Requirements

### Requirement: The detached sandbox diagnostic API is uncached, Linux-only, and not a runner backend

`tinyassets.sandbox` SHALL export its own `SandboxStatus`,
`SandboxUnavailableError`, `detect_bwrap`, and `check_bwrap_output`.
`SandboxStatus` SHALL serialize `available`, `reason`, `bwrap_path`, and
`version`. This exception and status shape SHALL remain distinct from the
production provider-layer dictionary and exception.

`detect_bwrap` SHALL return unavailable immediately on non-Linux platforms,
when `bwrap` is absent from `PATH`, when `bwrap --version` exits nonzero, when
a minimal `bwrap --ro-bind / / /bin/sh -c true` launch exits nonzero, or when
launching either subprocess raises `OSError`; each subprocess SHALL have a
five-second timeout. It SHALL return available, the executable path, and the
reported version only after both subprocesses exit zero. It SHALL not cache
results, and exceptions other than `OSError`, including a subprocess timeout,
may propagate.

On Linux, `check_bwrap_output` SHALL case-insensitively recognize the four
landed Bubblewrap signatures and raise the diagnostic exception; on every
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

#### Scenario: A diagnostic timeout may escape

- **WHEN** either diagnostic subprocess exceeds its five-second timeout
- **THEN** the resulting timeout exception may propagate rather than becoming `SandboxStatus`

#### Scenario: The diagnostic is detached from production execution

- **WHEN** production provider, graph, or runner paths execute
- **THEN** they do not consume `detect_bwrap` or its exception class
- **AND** the existence of this API supplies no usable runner backend or confinement guarantee
