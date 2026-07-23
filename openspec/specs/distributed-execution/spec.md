# distributed-execution Specification

## Purpose

Defines the shipped backend-neutral `runner/v1` per-job execution seam, its
fail-closed structural validation, the detached Linux-only sandbox diagnostic
API, and the explicit limitation that no OS-isolating `SandboxBackend` usable
by `SandboxRunner` or production caller exists.

## Requirements

### Requirement: The per-job runner exposes a versioned typed seam with a strict JSON-object payload

`tinyassets.sandbox_runner` SHALL define protocol `runner/v1`, request schema
`runner-job/v1`, and result schema `runner-result/v1`, with frozen typed carrier
dataclasses for requests, capability reports, enforcement receipts, and
results. A request wire object SHALL contain schema version, job ID,
idempotency key, owner scope, capability, derived actions, payload, workspace
reference, and credential-grant reference. The payload SHALL be detached
through strict JSON serialization, reject non-finite values and
non-JSON-serializable Python values, and be a JSON object. Actions SHALL be
derived from the immutable capability mapping rather than accepted from the
caller.

The supported capability/action pairs SHALL be:
`source_exec` → `source_exec`; `repo_read` → `list, read`; `repo_exec` →
`list, read, exec`; and `coding` → `list, read, write, exec`. The result status
vocabulary SHALL be exactly `succeeded`, `failed`, and `cancelled`.
The `job_id`, `idempotency_key`, `owner_scope`, `workspace_ref`, and
`credential_grant_ref` fields are carried through without runtime type,
nonempty, or JSON validation; their dataclass annotations are not an
authentication or shape check. The capability is instead dereferenced through
the enum and immutable action mapping.

#### Scenario: Capability determines the wire action list

- **WHEN** a `coding` request is serialized
- **THEN** its sorted actions are exactly `exec`, `list`, `read`, and `write`
- **AND** the wire object contains the nine landed request fields

#### Scenario: Non-JSON request data is refused before dispatch

- **WHEN** the payload contains a callable, another non-JSON-serializable value, or a non-finite number, or the payload is not an object
- **THEN** serialization raises `SandboxRequestError`
- **AND** no backend dispatch occurs

### Requirement: Backend capability preflight fails closed before dispatch

`SandboxRunner.dispatch` SHALL invoke the supplied backend's job-dispatch method
only when its capability report states `ready`, `isolation_enforced`,
`platform_secrets_absent`, and `self_test_passed`; advertises exact protocol
`runner/v1`; supports request schema `runner-job/v1`; and supports the requested
capability. A readiness, enforcement, self-test, or capability failure SHALL
raise `SandboxRunnerUnavailableError`. A protocol or request-schema mismatch
SHALL raise `SandboxRunnerProtocolError`. Every runner-created preflight failure
SHALL occur before `backend.dispatch(request)` receives the request. Exceptions
raised by `backend.capabilities()` or `backend.dispatch(request)` itself are not
normalized by this seam and propagate as supplied.

#### Scenario: Incomplete enforcement assertions never reach the backend

- **WHEN** any readiness, isolation, platform-secret-absence, or self-test flag is false
- **THEN** dispatch raises `SandboxRunnerUnavailableError`
- **AND** the backend receives no request

#### Scenario: Incompatible protocol or capability never reaches the backend

- **WHEN** the report has the wrong protocol, omits `runner-job/v1`, or omits the requested capability
- **THEN** dispatch raises the corresponding protocol or unavailable error
- **AND** the backend receives no request

### Requirement: Returned results are structurally validated and request-bound

A backend result SHALL be an object using `runner-result/v1`, one of the three
landed statuses, JSON-object output, and a string job ID. An omitted `error`
field SHALL default to an empty string, while a present `error` SHALL be a
string. Its enforcement receipt SHALL name a nonempty backend and a 64-character
`policy_sha256`, assert `job_isolated=true` and
`platform_secrets_absent=true`, and state `cleanup=confirmed`. The result job ID
SHALL equal the request job ID, and the receipt backend and policy value SHALL
equal the preflight report. Any violated condition SHALL raise
`SandboxRunnerProtocolError`; otherwise dispatch SHALL return a typed
`SandboxJobResult`.

These checks are structural backend assertions, not cryptographic attestation:
the runner does not authenticate or recompute isolation, secret absence,
cleanup, or policy, and it does not require `policy_sha256` to be hexadecimal.
Unknown top-level result and enforcement fields are tolerated and discarded
rather than rejected or retained.

#### Scenario: A matching valid result returns through the typed seam

- **WHEN** a usable backend returns a matching, structurally valid result
- **THEN** dispatch returns its typed status, output, error, and enforcement receipt

#### Scenario: Mismatched or incomplete result evidence is rejected

- **WHEN** the schema, status, output shape, job ID, backend, policy value, isolation assertions, or cleanup confirmation is invalid
- **THEN** dispatch raises `SandboxRunnerProtocolError`

### Requirement: The only built-in backend is unavailable and the seam is unwired

The built-in `UnavailableSandboxBackend` SHALL report no supported capability,
`ready=false`, `isolation_enforced=false`,
`platform_secrets_absent=false`, and `self_test_passed=false`, and SHALL refuse
dispatch. As built, the repository supplies no OS-isolating implementation of
the `SandboxBackend` protocol that is usable by `SandboxRunner`, and no
production execution path invokes the runner. The seam therefore SHALL NOT be
represented as current OS confinement or as removal of platform-secret
co-residency.

The seam also does not authenticate or resolve its opaque references, enforce
idempotency, scrub arbitrary JSON payload keys, persist or lease jobs, provide
timeouts or cancellation transport, execute cleanup, retry work, or create a
signed terminal attestation.

#### Scenario: The built-in unavailable backend refuses work

- **WHEN** `UnavailableSandboxBackend` is passed to `SandboxRunner`
- **THEN** dispatch fails readiness with `SandboxRunnerUnavailableError`
- **AND** the backend's job-dispatch method is not invoked

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
