## ADDED Requirements

### Requirement: Bubblewrap readiness is a cached two-stage provider probe that selects ordinary Codex mode

`tinyassets.providers.base.probe_sandbox_available` SHALL return a dictionary
with `bwrap_available` and `reason`. It SHALL report unavailable immediately on
win32, when `bwrap` is absent from `PATH`, when `bwrap --version` exits
nonzero, when a minimal `bwrap --ro-bind / / /bin/sh -c true` launch exits
nonzero, or when either subprocess attempt raises; each subprocess SHALL have
a five-second timeout. It SHALL report available with a null reason only when
both subprocesses exit zero.

`get_sandbox_status` SHALL lazily cache and return the first probe dictionary
for the remainder of the process. It returns that same mutable dictionary,
does not refresh it, and does not copy it.

For an ordinary `CodexProvider.complete` call,
`bwrap_available` truthy SHALL select `--full-auto`, while falsey SHALL select
`--dangerously-bypass-approvals-and-sandbox`; both modes also include
`--skip-git-repo-check` and `--ephemeral`. A call with
`sandbox_workspace=True` SHALL refuse before probing or selecting either mode.
This probe is a CLI-readiness heuristic, not an OS backend or proof that the
subsequent workload is confined. In particular, an unavailable ordinary call
bypasses Codex approvals and sandboxing rather than failing closed.

#### Scenario: Successful version and functional probes select full-auto

- **WHEN** `bwrap` is found and its version and minimal launch subprocesses both exit zero
- **THEN** the first cached result is `{"bwrap_available": true, "reason": null}`
- **AND** an ordinary Codex call includes `--full-auto` and omits `--dangerously-bypass-approvals-and-sandbox`

#### Scenario: An unavailable probe selects the dangerous bypass

- **WHEN** the cached probe is false because of win32, a missing executable, a nonzero version or launch result, or a probe exception
- **THEN** an ordinary Codex call includes `--dangerously-bypass-approvals-and-sandbox` and omits `--full-auto`
- **AND** the result carries a reason for the unavailable classification

#### Scenario: Repeated status reads retain the first mutable result

- **WHEN** `get_sandbox_status` is called repeatedly and a caller mutates the returned dictionary
- **THEN** the underlying probe is invoked once
- **AND** every read returns the same cached dictionary, including the mutation

#### Scenario: Founder-facing sandbox configuration refuses before mode selection

- **WHEN** a Codex call has `sandbox_workspace=True`
- **THEN** it raises `ProviderError` before consulting Bubblewrap readiness
- **AND** no Codex subprocess is started

### Requirement: Recognized provider CLI sandbox failures are loud only after earlier quick-exit classification

On non-win32 paths, `tinyassets.providers.base.check_bwrap_failure` SHALL
case-insensitively recognize:
`bwrap: No permissions to create a new namespace`,
`bwrap: No permissions to create new namespace`,
`bwrap: No such file or directory`, and
`sandbox initialization failed`. A match SHALL raise the provider-layer
`SandboxUnavailableError` with at most the first 400 stderr characters and
three remediation options. Empty or unmatched text SHALL pass. On win32 the
helper SHALL be a no-op.

Claude text completion, Claude JSON completion, and Codex completion SHALL pass
stderr through this helper when control reaches their post-communicate sandbox
check, including an exit-zero invocation that emitted a recognized failure.
The check does not dominate every error path: each CLI provider's quick
return-code-1 classification at elapsed time under five seconds occurs first and raises
`ProviderUnavailableError`, so such a Bubblewrap failure is not guaranteed to
retain the sandbox-specific type.

#### Scenario: A recognized exit-zero stderr failure raises the provider sandbox error

- **WHEN** a provider invocation reaches the sandbox check with any recognized signature in mixed-case stderr
- **THEN** it raises `tinyassets.providers.base.SandboxUnavailableError`
- **AND** the error carries a bounded stderr excerpt and remediation guidance

#### Scenario: Normal output and win32 do not trigger the recognizer

- **WHEN** stderr is empty or unmatched, or the process platform is win32
- **THEN** `check_bwrap_failure` returns without raising a sandbox error

#### Scenario: A return-code-1 failure under five seconds is classified before sandbox recognition

- **WHEN** a Claude or Codex subprocess exits with return code 1 at elapsed time under five seconds and its stderr also contains a recognized signature
- **THEN** the provider's earlier quick-exit path raises `ProviderUnavailableError`
- **AND** the sandbox-specific recognizer is not reached for that invocation
