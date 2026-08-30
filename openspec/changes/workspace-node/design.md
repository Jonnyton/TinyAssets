## Context

Survey of the production host (2026-08-30): the daemon container has `git`
2.47, `node`/`npm`, `bwrap`, Python 3 in `/opt/venv`; the host has 4 CPUs,
8 GiB RAM (≈6.6 GiB available), 28 GiB free under `/data`; the container runs
as uid 1001 with per-universe directories under `/data/<universe>/`. Code
nodes already run in a bwrap jail (`node_sandbox.py`: `--unshare-all`,
`--clearenv`, private tmpfs, rlimits, capped incremental reads) with the
authorship gate and the run's ContextVars. Outbound calls already run in a
spawned credential-blind worker with a per-connection endpoint allowlist
(`OutboundEndpoint`), grants, consent, and receipts.

Ceiling 2 (reading a codebase) and ceiling 3 (executing it) are the same
missing thing: a filesystem the universe's code can read and run against.

## Decisions

### D0. Two kinds of storage: the universe's permanent space, and scratch leased per job

Founder 2026-08-30: "storage for a user can be treated differently depending
on whether it's permanent storage — cloud space for your universe — versus
temp storage used for a run by one user, then later used by a different user
for their run … users' universes don't need to be bigger than whatever
codebase they want to work on."

- **Permanent** (`<data>/<universe>/…`): the universe itself — brain, pages,
  branches, evidence. Bounded by the universe's storage quota (tier).
- **Scratch** (`<data>/scratch/<lease_id>/`, a shared pool): a **lease**
  held for one job — created when a checkout effect runs, released when the
  run reaches a terminal status (plus a short grace for a follow-up run in
  the same turn), then wiped so the space serves the next user's run.
  Bounded by a per-lease size and a pool size, never charged to the
  universe's permanent quota. A universe working on a 5 GB codebase does
  not become a 5 GB universe.
- A workspace is **scratch by default**. A universe may **pin** one
  (`storage: "universe"` on the checkout, or a later `pin` op) for
  incremental work across turns; a pinned workspace lives under the
  universe's permanent space and counts against its quota.

### D1. A workspace is a git checkout, created and pushed by the credentialed worker

- Path: scratch `<data>/scratch/<lease_id>/repo` (default) or pinned
  `<data>/<universe>/workspaces/<workspace_id>/repo`; `workspace_id` = a
  short hash of `(connection_id, repo, ref)`; the checkout effect is
  idempotent (a second `checkout` of a pinned workspace fetches and resets to
  the ref, unless the node says `reuse: true`, in which case local work is
  kept; a scratch checkout is always fresh).
- **`checkout`** runs in the outbound worker (the process that today holds
  the credential for HTTP): `git clone --depth <n> --branch <ref>` (or
  `fetch` into the existing checkout) with the token supplied through a
  **git credential helper** (`GIT_ASKPASS` pointing at a tiny script that
  reads the token from a file descriptor the worker opened) — the token is
  never in argv, never in `.git/config`, and the remote URL stored is the
  bare `https://<host>/<owner>/<repo>`. The connection's endpoint allowlist
  must cover the host and `/<owner>/<repo>` (the same grant that lets the
  universe call the API); `checkout` settles as a **read** admission.
- **`push`** runs the same way: `git push origin <local_ref>:refs/heads/<branch>`
  with the helper; it is a **write** admission and needs the destination
  consent every write needs (`effector_consents`), so the request rail asks
  once per repo like it does today. A push is refused when the branch is a
  protected default (`main`/`master`) unless the packet says
  `allow_default_branch: true` and the consent record carries it.
- **`discard`** removes the directory. A per-universe GC removes workspaces
  untouched for 14 days or beyond the quota (oldest first), recorded in the
  universe's evidence.
- Evidence (persisted, bounded): repo, ref, resolved commit sha, depth,
  size on disk, duration; for push: remote, branch, sha, bytes; never env,
  never the token.

### D2. A code node with `workspace: "<checkout node>"` runs inside the checkout

- The compiler resolves the reference like `$ta.effect` — the named node
  must be a graph **ancestor** whose `workspace/checkout` effect delivered in
  this run (or a `workspace_id` in state via `$ta.ref`) — and passes the
  directory to `NodeSandbox.run_sync(workspace=<path>)`.
- The jail gains `--bind <path> /workspace --chdir /workspace`; nothing else
  changes: `--unshare-all` (no network), `--clearenv`, no `/data`, the same
  authorship gate, the same ContextVar-carrying RPC. The workspace profile
  raises limits because it builds things: `RLIMIT_AS` 2 GiB, `RLIMIT_NOFILE`
  1024, `RLIMIT_FSIZE` 512 MiB, `RLIMIT_NPROC` 256; wall clock = the node's
  `timeout_seconds` (default 300 s; a node may declare up to 3600 s).
- The runner exposes **`ws`** in the node's namespace:
  `ws.run(argv, *, timeout=None, cwd=None, env=None) -> {"code", "stdout_tail",
  "stderr_tail", "duration_s"}` (tails 64 KiB, output beyond the tail
  discarded — a build log is not state), `ws.read(path, max_bytes=1 MiB)`,
  `ws.write(path, text)`, `ws.glob(pattern)`, `ws.path`. `ws.run` starts the
  child inside the same jail (a plain `subprocess.run` from the runner; the
  denylist still refuses `subprocess` in user source, so the helper is the
  sanctioned path). `git` is available in the jail (read-only bind of
  `/usr`); commits are made locally with the identity
  `TinyAssets Universe <universe_id> <universe_id>@universes.tinyassets.io>`.
- The node's return is still a dict into state (test summaries, file
  excerpts, the local branch name to push). Evidence for `read_graph`: the
  commands run, exit codes, tails.
- One workspace job per universe at a time (a lock file in the universe
  dir); a second concurrent workspace node waits up to its timeout, then
  fails as `workspace_busy`.

### D3. Provisioning with network is consented egress, not a hole

- `checkout` accepts `provision: [argv, …]` (e.g. `["pip", "install", "-e",
  "."]`, `["npm", "ci"]`). These run **after** the clone in a **separate
  jail** that has network (`--share-net`) but no credentials, no `/data`,
  only `/workspace` bound, `--clearenv` plus `PIP_INDEX_URL` /
  `npm_config_registry` hints — and only when the connection carries the
  consent kind **`workspace_network`** for that repo, granted through the
  request rail with the exact wording "allow network while installing
  dependencies for <owner>/<repo>". Without the consent, provisioning runs in
  the network-less jail (vendored dependencies only) and a network attempt
  fails loudly.
- Rationale: the egress rule from `sandboxed-code-node` stands — data leaves
  a universe only through consented channels. Installing dependencies *is* a
  channel; the user consents to it per repo, once.

### D4. Limits are usage

- Disk: scratch leases are bounded per lease (default 4 GiB, tier-raisable)
  and by the pool (a fixed slice of the box, e.g. 20 GiB, admission refuses
  a new lease when the pool is full — `workspace_pool_busy`, retry later,
  never a silent partial clone); pinned workspaces count against the
  universe's permanent quota. A checkout that would exceed its bound fails
  as `workspace_quota_exceeded` before cloning when the size is knowable
  (repository size from the API), else the clone is killed at the bound.
- Leases are released on the run's terminal status (`update_run_status`
  path, like effect settlement) with a grace of 15 minutes so a follow-up
  run in the same turn can reuse the checkout; unreleased leases are swept
  by age.
- Memory: the jail's `RLIMIT_AS`; the box has 8 GiB and one workspace job
  per universe at a time keeps the worst case bounded.
- Time: node timeout; admissions: checkout = read, push = write, every run
  still admitted through the per-universe ledger. **No cap on nodes,
  effect nodes or edges** (companion change `no-graph-size-caps`).

### D5. Authority

- The sink is channel-agnostic: any git-over-HTTPS host the user connected
  (`github.com`, `gitlab.com`, a self-hosted forge) — the grant's endpoint
  allowlist decides, exactly as for `authenticated_external_call`.
- The model never sees the token (worker-side helper), the jail never has
  the token or network, the checkout is the user's own data in the user's
  own universe directory, and only the user's own (authorship-gated) code
  runs in it. A remixed branch's checkout node re-runs under the remixer's
  connection — a workspace is never shared across universes.
- No new MCP handle: `workspace` is a sink name plus a node attribute, both
  actions under `write.graph`.

### D6. Failure taxonomy

`workspace_checkout_failed` (auth, missing repo, quota — an effect failure,
fails the node like any write), `workspace_busy`, `workspace_quota_exceeded`,
`code_node_failed` for exceptions in `run()`; a non-zero `ws.run` exit is
**data** (the code decides), so a test failure can be read and acted on in
the same run.

## Alternatives rejected

- Network in every code node: breaks the egress rule; consent-gated
  provisioning keeps the boundary explicit.
- Cloning from inside the jail with the token mounted: puts the credential
  in a process the user's code controls.
- The Git Data API from code nodes (blobs/trees/commits as packets): works
  for multi-file commits, still cannot read a project or run it.
- A separate container per workspace: heavier than bwrap, same isolation
  properties we already trust for served turns.

## Risks the reviewer should attack

1. The credential helper path: any way the token reaches argv, the checkout,
   `/proc`, the jail, or the evidence.
2. The provision jail: what `--share-net` + `/workspace` + no `/data` really
   exposes; whether the consent kind is bound to the repo and cannot be
   inherited by a remix.
3. Path safety: `workspace_id` construction, symlinks inside a checkout
   pointing outside `/workspace` (bind-mount semantics), `ws.read/write`
   containment.
4. Resource exhaustion on a shared 8 GiB box: `RLIMIT_AS` 2 GiB, fork bombs
   (`RLIMIT_NPROC`), disk quota enforcement timing, the one-job lock.
5. Push semantics: default-branch protection, force-push (refused), the
   admission kind, consent scoping.
6. Resume/at-most-once with a persistent workspace: a re-run after an
   interrupt must not double-commit or double-push.
