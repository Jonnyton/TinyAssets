# Universe Personification and Relay

## MODIFIED Requirements

### Requirement: The engine turn is confined by a fail-closed sandbox

Every universe-intelligence engine turn SHALL retain the existing `sandbox_workspace=True` CLI policy (`WebFetch` requested as the sole allowed tool, every currently enumerated non-WebFetch tool denied, `--setting-sources project`, and cwd scoped to the universe) AND, on Linux, SHALL run the local Claude CLI subprocess inside a fixed Bubblewrap policy. The OS policy SHALL expose a minimal read-only runtime, network access required by the provider and `WebFetch`, private proc/dev/tmp/home state, and the universe's own directory as the only read-write host bind. It SHALL NOT bind the repository, host filesystem root, host home, Codex/Claude configuration homes, or credential/vault paths. Both the reply and learning-extraction turns SHALL use the same policy.

If the existing two-stage functional bwrap probe is unavailable or unhealthy on Linux, the universe engine turn SHALL refuse before provider execution and SHALL NOT fall back to CLI-only confinement. Codex SHALL retain its existing sandbox-incapable refusal. On non-Linux development hosts, the existing cwd/tool-policy confinement MAY run without Bubblewrap and SHALL emit a warning that the path is development-only and not production-equivalent.

#### Scenario: both engine subprocesses receive OS confinement

- **WHEN** `converse` runs its reply turn and its learning-extraction turn on Linux
- **THEN** both Claude subprocesses are launched beneath the fixed Bubblewrap wrapper
- **AND** the existing allowed/disallowed tool flags remain present inside that wrapper

#### Scenario: only universe files are writable

- **WHEN** a command runs through the real Linux engine wrapper
- **THEN** it can create a file in the bound universe workspace
- **AND** it cannot read a host path outside the explicitly bound runtime and universe paths
- **AND** the repo, host homes, Claude/Codex config homes, and credential paths are absent

#### Scenario: unavailable Linux sandbox refuses the turn

- **WHEN** the functional bwrap probe reports unavailable on Linux
- **THEN** the engine turn raises a sandbox-unavailable error before any provider subprocess is launched
- **AND** it does not retry or fall back to flag-only confinement

#### Scenario: Windows development remains usable but is not production proof

- **WHEN** a contributor runs a sandboxed engine turn on Windows
- **THEN** the existing cwd and CLI tool controls remain usable for development
- **AND** a warning states that OS isolation was not applied
- **AND** this behavior is not treated as production-equivalent verification
