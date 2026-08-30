## ADDED Requirements

### Requirement: Credentialed git runs from an empty environment through a trusted helper, never in a directory user code can write

When the outbound worker performs a git operation with a stored credential,
it SHALL build the child's environment from empty (`GIT_CONFIG_SYSTEM` and
`GIT_CONFIG_GLOBAL` pointing at `/dev/null`, `GIT_CONFIG_NOSYSTEM=1`,
`GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=/bin/false`, an empty `HOME`, no
`GIT_TRACE*`, `RLIMIT_CORE=0`), SHALL force `core.hooksPath=/dev/null`,
`core.fsmonitor=false`, an emptied then trusted `credential.helper`,
`credential.useHttpPath=true`, `protocol.allow=never`,
`protocol.https.allow=always`, `http.followRedirects=false` and
`submodule.recurse=false`, SHALL address the validated canonical URL (never
a stored remote name), and SHALL operate only on a worker-private staging
repository. The trusted helper SHALL answer only `get`, SHALL verify the
request's `protocol`, `host` and `path` against the grant's exact
repository, and SHALL obtain the token once over a one-shot pipe from the
worker. The token SHALL never appear in argv, in the environment of a
process other than the helper's answer stream, in any file, in evidence or
in an error message; raw git stderr SHALL be scrubbed by exact-secret
detection and mapped to fixed error classes.

#### Scenario: the token is not in argv, environment, files or evidence
- **WHEN** a checkout runs against a repository whose credential is `tok-…`
- **THEN** no process's `cmdline` or `environ` contains it, the staging and workspace directories contain no file with it, and the evidence and any error message contain none of it

#### Scenario: a helper request for another repository is refused
- **WHEN** git asks the helper for a credential for a host or path other than the grant's repository
- **THEN** the helper answers nothing and the operation fails as `workspace_checkout_failed`
