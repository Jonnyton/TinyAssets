## MODIFIED Requirements

### Requirement: source_code nodes execute in an OS-isolated subprocess with data and no credentials

A `source_code` node MAY declare `workspace: "<node id>"`. The compiler SHALL
resolve it only through the run's effect chain: the named node MUST be a
graph ancestor whose `workspace/checkout` effect delivered in this run, and
the sandbox SHALL receive an internal capability (lease id and validated
path) that never round-trips through state, `$ta.ref` or JSON. The jail
SHALL gain exactly one additional bind — the lease's repository directory at
`/workspace`, read-write, with `--chdir /workspace` — through a dedicated
exact-path rule; every other property of the jail (no network, cleared
environment, no data directory, the authorship gate, the request's context
on RPC) is unchanged. The runner SHALL expose `ws.run(argv, timeout=,
cwd=, env=)`, `ws.read(relpath, max_bytes=)`, `ws.write(relpath, text)` and
`ws.glob(pattern)`; paths SHALL be relative and resolved beneath
`/workspace` without following links out of it; `ws.run` SHALL stream the
child's output through bounded incremental drains, SHALL cap cumulative
output, and on timeout SHALL terminate the whole jail so the node fails as
`workspace_command_timeout`. A workspace node SHALL run under the workspace
limits profile (`RLIMIT_AS` 1.5 GiB, `RLIMIT_NPROC` 128, `RLIMIT_NOFILE`
1024, `RLIMIT_FSIZE` 512 MiB, `RLIMIT_CORE` 0) with a process-tree RSS
watchdog at 2 GiB, at most 64 commands and 1 MiB of returned output per
node, and MAY declare `timeout_seconds` up to 1800. At most one workspace
node SHALL run at a time per universe and, in this change, per host
(`workspace_busy`). All other clauses of this requirement are unchanged.

#### Scenario: a code node reads and runs the checked-out project
- **WHEN** a node declares `workspace: "checkout"` and its ancestor `checkout` delivered
- **THEN** `run(state, effects)` sees the repository at `/workspace`, `ws.run(["python", "-m", "compileall", "tinyassets"])` returns an exit code and bounded tails, and no network is reachable

#### Scenario: a workspace reference outside the chain refuses
- **WHEN** a node's `workspace:` names a node that is not an ancestor checkout in this run, or a branch tries to supply a lease id through state
- **THEN** compilation (or the node) fails before any command runs, naming the rule

#### Scenario: a command that outlives its timeout ends the node, not just the child
- **WHEN** `ws.run` runs a command that spawns a sleeping grandchild and exceeds the timeout
- **THEN** the jail's whole process tree is terminated and the node fails as `workspace_command_timeout`

### Requirement: Run failures map to a terminal status taxonomy
The executor SHALL additionally classify `workspace_checkout_failed`,
`workspace_push_refused`, `workspace_busy`, `workspace_quota_exceeded` and
`workspace_command_timeout`, each actionable by the chatbot with a fixed
suggested action. All other clauses of this requirement are unchanged.

#### Scenario: a busy workspace is a wait, not a crash
- **WHEN** a second workspace node starts while one is running
- **THEN** it waits up to its timeout and then fails as `workspace_busy` with the advice to retry
