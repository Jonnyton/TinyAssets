## ADDED Requirements

### Requirement: Credentialed git runs from an empty environment through an in-memory broker, never in a directory user code can write

The outbound worker SHALL run every credentialed git operation against a worker-private staging repository with the child's environment built from empty and the token supplied only by an in-memory credential broker that answers `get` for the grant's exact `(protocol, host, path)`.
The environment SHALL set `GIT_CONFIG_SYSTEM` and `GIT_CONFIG_GLOBAL` to
`/dev/null`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_TERMINAL_PROMPT=0`,
`GIT_ASKPASS=/bin/false`, an empty `HOME`, no `GIT_TRACE*`, and
`RLIMIT_CORE=0`; the command SHALL force `core.hooksPath=/dev/null`,
`core.fsmonitor=false`, an emptied then trusted `credential.helper`,
`credential.useHttpPath=true`, `protocol.allow=never`,
`protocol.https.allow=always`, `http.followRedirects=false`,
`submodule.recurse=false`, `transfer.fsckObjects=true` and
`http.curloptResolve=<host>:443:<validated address>`, and SHALL address the
validated canonical URL, never a stored remote. The broker SHALL answer
`username` and `password` for as many `get` requests as one operation
issues (a 401 retry is legitimate), SHALL ignore `store` and `erase`, SHALL
refuse any other host or path, and SHALL be torn down when the operation
ends; the token SHALL never appear in argv, in the environment of any
process, in any file, in evidence or in an error message. Raw git stderr
SHALL be scrubbed by exact-secret detection and mapped to fixed error
classes.

#### Scenario: the token is not in argv, environment, files or evidence
- **WHEN** a checkout runs against a repository whose credential is `tok-…`
- **THEN** no process's `cmdline` or `environ` contains it, staging and the lease contain no file with it, and evidence and error messages contain none of it

#### Scenario: a retried authentication still succeeds
- **WHEN** the remote answers 401 once and git asks the broker a second time
- **THEN** the broker answers again for the same repository and the operation completes

#### Scenario: a broker request for another repository is refused
- **WHEN** git asks for a credential for a host or path other than the grant's repository
- **THEN** the broker answers nothing and the operation fails as `workspace_checkout_failed`
