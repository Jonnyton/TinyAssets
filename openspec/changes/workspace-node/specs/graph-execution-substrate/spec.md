## MODIFIED Requirements

### Requirement: source_code nodes execute in an OS-isolated subprocess with data and no credentials

A `source_code` node that declares `workspace: "<node id>"` SHALL run with the named ancestor checkout's generation bound read-write at `/workspace` as the jail's only additional bind, resolved solely through the run's effect chain into an internal capability that never round-trips through state, `$ta.ref` or JSON.
Every other property of the jail (no network, cleared environment, no data
directory, the authorship gate, the request's context on RPC) is unchanged.
The runner SHALL expose `ws.run(argv, timeout=, cwd=, env=)`,
`ws.read(relpath, max_bytes=)`, `ws.write(relpath, text)`, `ws.glob(pattern)`
and `ws.bundle(commit_sha)` (a self-contained, prerequisite-free bundle
from one synthetic ref at that commit, hooks and replacements disabled,
created without credentials inside the jail — its reading of the
workspace's own `.git` is accepted residual parser input because the
process stays in the jail and its output is treated as hostile); paths
SHALL be relative and resolved beneath `/workspace` without following links
out of it; `ws.run` SHALL stream output through bounded incremental drains
and cap cumulative output; on a command timeout the runner SHALL exit and
the parent SHALL SIGKILL the tracked bwrap supervisor, confirm its exit and
rely on the `--die-with-parent` cascade to end the sandbox, so
double-forked descendants die with it and the node fails as
`workspace_command_timeout`. A workspace node SHALL run under the workspace
limits profile (`RLIMIT_AS` 1.5 GiB, `RLIMIT_NPROC` 1024, `RLIMIT_NOFILE`
1024, `RLIMIT_FSIZE` 512 MiB, `RLIMIT_CORE` 0) with a process-tree RSS
watchdog at 2 GiB, at most 64 commands and 1 MiB of returned output per
node, and MAY declare `timeout_seconds` up to 1800. After a `discard`, the
capability SHALL be revoked immediately and any later `ws.*` call in the
run SHALL raise inside `run()`. All other clauses of this requirement are
unchanged.

#### Scenario: a code node reads and runs the checked-out project
- **WHEN** a node declares `workspace: "checkout"` and its ancestor `checkout` delivered
- **THEN** `run(state, effects)` sees the repository at `/workspace`, `ws.run(["python", "-m", "compileall", "tinyassets"])` returns an exit code and bounded tails, and no network is reachable

#### Scenario: a workspace reference outside the chain refuses
- **WHEN** a node's `workspace:` names a node that is not an ancestor checkout in this run, or a branch tries to supply a lease id through state
- **THEN** compilation (or the node) fails before any command runs, naming the rule

#### Scenario: a command that outlives its timeout ends the whole sandbox
- **WHEN** `ws.run` runs a command that double-forks a `setsid` sleeper and exceeds the timeout
- **THEN** the parent SIGKILLs the tracked bwrap supervisor and confirms its exit; the Linux integration test proves the sleeper no longer exists; the node fails as `workspace_command_timeout`

### Requirement: Run failures map to a terminal status taxonomy

The executor SHALL additionally classify `workspace_checkout_failed`, `workspace_push_refused`, `workspace_busy`, `workspace_pool_busy`, `workspace_quota_exceeded`, `workspace_command_timeout`, `workspace_provision_refused`, `workspace_provision_failed` and `workspace_discard_failed`, each actionable by the chatbot with a fixed suggested action.
All other clauses of this requirement are unchanged.

#### Scenario: a busy workspace is a wait, not a crash
- **WHEN** a second workspace job starts while the universe's (or the host's) slot is held
- **THEN** it waits up to its timeout and then fails as `workspace_busy` with the advice to retry

## ADDED Requirements

### Requirement: Guarded run execution preserves ownership through actual scoped use

An internal prepared execution SHALL require its exact held run-keyed OS guard
for start and terminal expected-status transitions, whether or not the run has a
managed resource-family association. A derivative same-process execution-use
receipt MAY pin that owner's lifetime through code-node and RPC operations, but
SHALL NOT satisfy owner-only mutation or release checks. Owner retirement SHALL
refuse new pins and drain entered scopes before releasing the original OS lock.
Family closure and fresh effect authority SHALL remain separate from lifetime.

#### Scenario: a delayed prepared worker loses its queued state
- **WHEN** cancellation, interruption, completion or another valid transition changed its queued run before start
- **THEN** the expected-status start refuses before invocation, including for a run without a resource-family association
- **AND** the losing worker does not overwrite the winner's status or output

#### Scenario: a real RPC callback outlives the node's drain join
- **WHEN** an entered callback continues after the node returns
- **THEN** the original owner lock remains held until that actual scoped callback exits
- **AND** new effects still require fresh authority and cannot reopen a closed family

#### Scenario: a queued durable admission has no local Future
- **WHEN** its OS guard is temporarily free while an unstarted worker handoff may still be queued elsewhere
- **THEN** legacy recovery does not infer abandonment or execution permission from age, missing process-local Future or guard availability alone

### Requirement: Workspace jobs hold one durable lock per universe and one host-wide slot

The runtime SHALL acquire, in the checkout's admission transaction, a durable job lock keyed by universe and a host-wide slot (one slot in this change), SHALL treat it as reentrant for that run's later workspace nodes and its push, and SHALL release it only through the run's terminal outbox entry.
`workspace_busy` is the refusal when the lock cannot be acquired within the
node's timeout. The runner sidecar / cgroup follow-up is what lifts the
host-wide slot.

#### Scenario: the lock outlives the checkout node
- **WHEN** a run checks out, runs tests in a later node, and pushes in a third
- **THEN** one lock is held from the checkout's admission until the run's terminal outbox entry is processed, and another universe's checkout waits meanwhile
