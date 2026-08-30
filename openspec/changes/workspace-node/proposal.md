## Why

Founder question 2026-08-30: can a user's universe scope, build and merge
complex PRs to any GitHub project — even build a whole project — through the
app? After `sandboxed-code-node` (live 2026-08-30 with #2720/#2728):
single-file changes yes, proven uncoached; complex changes and whole projects
no, for three concrete reasons:

1. a served build could carry at most 5 effect nodes and 100 nodes — removed
   by the companion change `no-graph-size-caps` (founder: "no silly limit on
   how many nodes a user can build into a branch"; usage bounds, never shape);
2. **reading a codebase** is one file per effect node through a contents
   API — a universe cannot look at a project the way a developer does;
3. **no execution environment** — code nodes are network-less, stdlib-only,
   512 MiB; the universe cannot run a project's tests or build.

Founder direction: build the primitive that solves 2 and 3. A project checked
out in a sandbox the universe's code can read and run commands in is the
primitive that turns "edit one line" into "build the project".

## What Changes

A **workspace**: a git checkout of a repository the user connected, held as
**scratch storage leased to one job** (or, on request, as an immutable
generation in the universe's permanent space), that the universe's code nodes read, modify and
run commands in — inside the OS jail code nodes already run in, with no
network and no credentials.

- A new effect sink `workspace` — `checkout`, `push`, `discard` — on the
  credentialed, credential-blind worker. Credentialed git never touches a
  directory user code can write: every clone/fetch/push runs against a
  worker-private staging repository with a real credential helper, a
  from-empty environment and forced safe options; the workspace is
  populated from staging without credentials. Git transport is its own
  grant kind (`git_read` / `git_write` per host and repository).
- A code node that declares `workspace: "<checkout node>"` runs with the
  lease bound read-write at `/workspace` and gets a sanctioned `ws.run` /
  `ws.read` / `ws.write` / `ws.glob`; larger jail limits; a command timeout
  ends the whole node.
- Provisioning (second slice): a platform-owned resolver downloads the
  declared Python/Node dependencies from public registries in a jail that
  holds no checkout; the install runs offline in the workspace. Consent
  kinds `workspace_checkout`, `workspace_push`, `workspace_provision`, each
  per connection and repository, through the request rail.
- **Storage:** scratch by default — leases in a shared pool, released when
  the run ends and wiped before any reuse, never charged to the universe's
  quota; a universe working on a 5 GB codebase is not a 5 GB universe.
  `storage: "universe"` for work that should outlive the run.
- **Limits are usage:** one workspace job at a time (per universe and, in
  this change, box-wide), a `workspace` admission kind (jobs and bytes per
  hour), best-effort disk bounds with a named follow-up for kernel quotas,
  and — replacing the removed shape caps — per-run and per-hour effect
  dispatch and byte budgets (companion change `run-usage-budgets`).
- `write_graph` teaches the shape: `checkout → code (read, edit, run tests,
  commit) → push → open_pr → merge`.

## Impact

- Specs (deltas in this change, before code): `external-effect-adapters`
  (ADDED: the `workspace` sink, its packets, consents, evidence, branch
  policy), `graph-execution-substrate` (MODIFIED: workspace-bound code nodes,
  `ws.*`, limits, taxonomy), `engine-run-admissions` (ADDED: the `workspace`
  admission kind; checkout settles as a read), `credential-vault` (ADDED:
  credentialed git from an empty environment through an in-memory broker,
  address pinned in the transport),
  `scratch-storage` (NEW: leases, state machine, pool).
- Code: `tinyassets/effectors/workspace.py` (new sink), outbound worker (git
  helper + staging), `tinyassets/scratch.py` (leases, sweepers, outbox),
  `node_sandbox.py` (workspace bind, `ws.*`, limits profile, watchdog),
  `graph_compiler.py` (`workspace` attribute via the chain), admissions kind,
  `engine_mcp_server.py` (docs, validation), tests, plugin mirror.
- Authority surface (new sink, new consent kinds, credentialed git, storage
  lifecycle) → proposal + design + delta specs before code; founder approved
  the direction 2026-08-30; Codex rounds 1-3 folded (three is the cap); build proceeds with the
  residual reported to the founder.
- Live proof: the founder's universe checks out its own repository, answers a
  question only the checkout can answer (how many Python files the project
  has), runs a command in it (`python -m compileall tinyassets`), commits,
  pushes a `tiny/…` branch, opens and merges the PR — uncoached. Slice B's
  live proof provisions a checked-in hash-locked fixture
  (`tests/fixtures/workspace/requirements-locked.txt`), not the runtime
  `requirements.txt` (ranges, no hashes — the grammar refuses it).
