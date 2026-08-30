## Why

Founder question 2026-08-30: can a user's universe scope, build and merge
complex PRs to any GitHub project — even build a whole project — through the
app? Honest answer after the code-node change (`sandboxed-code-node`, live
2026-08-30 with #2720/#2728): single-file changes yes, proven uncoached;
complex changes and whole projects no, for three concrete reasons:

1. a served build could carry at most 5 effect nodes and 100 nodes
   (`_SERVED_MAX_EFFECT_NODES`, `_SERVED_MAX_NODES`) — removed by the
   companion change `no-graph-size-caps` (founder: "no silly limit on how
   many nodes a user can build into a branch");
2. **reading a codebase** is one file per effect node through the GitHub
   contents API — a universe cannot look at a project the way a developer
   does;
3. **no execution environment** — code nodes are network-less, stdlib-only,
   512 MiB; the universe cannot run a project's tests or build, so its only
   feedback loop is the target repo's own CI.

Founder direction: "lets build this primitive that solves 2 and 3 ... users
should be able to do these things." The founder's model is unchanged: the
user's agent builds any workflow from powerful primitives; a project checked
out in a sandbox it can run commands in is the primitive that turns
"edit one line" into "build the project".

## What Changes

A **workspace**: a git checkout of a repository the user connected, living
under the universe's own data directory, that the universe's code nodes can
read, modify and run commands in — inside the same OS jail code nodes already
run in, with no network and no credentials.

- A new effect sink `workspace` with three operations on the same
  credentialed, credential-blind worker path as `authenticated_external_call`:
  `checkout` (clone/fetch a repo+ref into `<data>/<universe>/workspaces/<id>`;
  the token is applied inside the worker via a git credential helper, never
  in argv, never stored in the checkout), `push` (push a local branch the
  code committed; consent-gated like any write), `discard`.
- A code node that declares `workspace: "<checkout node id>"` runs with
  that directory bound read-write at `/workspace` in its jail and receives a
  sanctioned `ws.run(argv, timeout=…)` helper that executes a command inside
  the same jail (no network), returning exit code and bounded output tails.
  Workspace nodes get larger limits (RLIMIT_AS 2 GiB, more descriptors,
  bigger files) because they build things.
- **Dependency provisioning with network is consent-gated**: `checkout` may
  run `provision` commands (`pip install -e .`, `npm ci`, …) in a jail with
  network but no credentials and nothing but `/workspace` bound — only when
  the user granted `workspace_network` for that connection through the
  request rail. Without it, provisioning runs network-less.
- Workspaces persist across runs (incremental work), are per-universe, and
  are bounded by **usage** limits — a disk quota per universe, one workspace
  job at a time per universe, command wall clock = node timeout — never by
  the graph's shape.
- `write_graph` teaches the shape: `checkout → code (read, edit, run tests,
  commit) → push → open_pr → merge`.

## Impact

- Specs: `external-effect-adapters` (ADDED: the `workspace` sink, its ops,
  consent and evidence), `graph-execution-substrate` (MODIFIED: workspace-
  bound code nodes, `ws.run`, limits), `engine-run-admissions` (checkout
  settles as a read, push as a write), `credential-vault`/outbound
  connections (git credential application in the worker).
- Code: `tinyassets/effectors/workspace.py` (new sink), `outbound_connections`
  (git credential helper path), `node_sandbox.py` (workspace bind, `ws.run`,
  limits profile, provision jail), `graph_compiler.py` (`workspace` node
  attribute → chain lookup → sandbox binding), `engine_mcp_server.py`
  (docs, validation), quota/GC, tests, plugin mirror.
- Authority surface (new sink, new consent kind, credentialed git) → this
  proposal + design before code; founder approved the direction 2026-08-30;
  one Codex shape round on the design.
- Live proof: the founder's universe checks out its own repo, answers a
  question only the checkout can answer (how many Python files the project
  has), runs a command in it (`python -m compileall tinyassets`), commits,
  pushes, opens and merges the PR — uncoached.
