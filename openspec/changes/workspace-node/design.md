## Context

Survey of the production host (2026-08-30): the daemon container has `git`
2.47, `node`/`npm`, `bwrap`, Python 3 in a read-only `/opt/venv`; the image
omits build toolchains; the host has 4 CPUs and 8 GiB RAM but the daemon
container is capped at 4 GiB (`deploy/compose.yml`), allows four concurrent
top-level runs, has no `pids_limit`, and stores `/data` on an ordinary named
volume (no filesystem quotas). The container runs as uid 1001. Code nodes
already run in a bwrap jail (`node_sandbox.py`) with the authorship gate and
the run's ContextVars; outbound HTTP already runs in a spawned
credential-blind worker with a per-connection endpoint allowlist enforced
inside a fixed HTTP driver.

Ceiling 2 (reading a codebase) and ceiling 3 (executing it) are one missing
thing: a filesystem the universe's code can read and run against.

**Review history.** Codex round 1 (design only) returned REJECT: the
credential mechanism, the provision jail's network, per-process rlimits as
a box-wide bound, disk bounds on a plain volume, and the companion cap
removal without usage budgets were all shown unsafe or unfounded. Every
finding is folded below and marked *(R1)*. Two rounds remain; then the
founder.

## Decisions

### D0. Two kinds of storage: the universe's permanent space, and scratch leased per job

Founder 2026-08-30: permanent storage (your universe's cloud space) is a
different thing from temp storage used by one user's run and later by
another user's run; a universe never needs to be bigger than the codebase
it works on.

- **Permanent** (`<data>/<universe>/…`): the universe — brain, pages,
  branches, evidence — bounded by the tier's storage quota.
- **Scratch**: a shared pool (`<data>/scratch/`) of **leases**, one per job.
  A lease is a random opaque id bound server-side to `(universe,
  connection, canonical repo, storage class, generation)`; its directory is
  created fresh under a validated parent (parent resolved without following
  links; an opened directory handle is held across bind setup so a rename
  cannot swap it) *(R1)*. A lease is never charged to the universe's
  permanent quota.
- **Lease state machine, persisted:** `ACTIVE(run, universe, generation)` →
  `QUARANTINED` → `WIPING` → `AVAILABLE`. Release is an idempotent outbox
  entry written in the run's terminal-status transaction and processed
  *after* commit (never inside `update_run_status`, which can run more than
  once and is bypassed by startup recovery *(R1)*); a startup sweeper and a
  periodic sweeper reconcile dead owners. A directory is **never recycled in
  place**: it is atomically renamed into quarantine, deleted without
  following links, and a *new* random directory is created for the next
  lease only after the deletion verified; a failed wipe permanently reduces
  the pool's available bytes *(R1)*. **No grace reuse** in this change: pin
  explicitly or check out fresh *(R1)*.
- **Pinned** (`storage: "universe"`): the workspace lives under
  `<data>/<universe>/workspaces/<id>` and counts against the permanent
  quota; it is never aged out — only quota-refused or explicitly discarded
  *(R1 P2)*.

### D1. Credentialed git never touches a directory user code can write

Every network git operation runs in the outbound worker against a
**worker-private bare staging repository** that is never mounted into any
jail *(R1 P0)*:

- **checkout**: `git clone --bare --no-recurse-submodules --depth <n>
  <https-url> <staging>` with a **real credential helper** (not
  `GIT_ASKPASS`): a helper program that reads git's `protocol`, `host`,
  `path` request, requires `credential.useHttpPath=true` and the exact
  canonical repository, obtains the token once over a one-shot pipe from
  the worker, and answers only `get`. Then the workspace is populated
  **without credentials** from staging (`git clone --no-hardlinks
  <staging> <lease>/repo` or a bundle) and staging is deleted.
- **push**: the worker fetches the code node's local commit *from* the
  workspace into a fresh staging repo as a plain local path remote
  (credential-free, `--no-hooks` semantics by construction: fetching does
  not run the source's hooks), verifies the object graph, then pushes from
  staging with the helper — user-controlled `.git/config`, hooks,
  `credential.helper`, attributes and filters in the checkout never execute
  in a process that holds a credential *(R1)*.
- Git's environment is **built from empty** (the credential-vault
  precedent): `GIT_CONFIG_SYSTEM=/dev/null GIT_CONFIG_GLOBAL=/dev/null
  GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false
  HOME=<empty tmp>`, no `GIT_TRACE*`, `RLIMIT_CORE=0`; forced options
  `-c core.hooksPath=/dev/null -c core.fsmonitor=false -c
  credential.helper= -c credential.helper=<trusted> -c
  credential.useHttpPath=true -c protocol.allow=never -c
  protocol.https.allow=always -c http.followRedirects=false -c
  submodule.recurse=false`; the URL is the validated canonical URL, never
  `origin` *(R1)*. Raw git stderr is scrubbed by exact-secret detection and
  mapped to fixed error classes before it reaches evidence.
- **Transport policy is its own grant kind** *(R1 P0)*: `git_read` /
  `git_write` scopes bound to `(host, owner/repo)`; the helper refuses any
  other host or path; HTTPS:443 only; the same DNS/IP classification the
  HTTP driver applies runs on the host before the clone (public unicast
  only). The HTTP endpoint allowlist is not reused for git.
- **Crash safety:** before the wire, the worker journals the intent
  `(connection, repo, remote_ref, commit_sha, expected_old_sha)`; on an
  ambiguous outcome it reconciles with `ls-remote`, and a repeated non-force
  push of the same SHA to the same ref is success *(R1)*. Checkout records
  the resolved SHA before the workspace is populated.
- **Branch policy:** resolve the remote `HEAD`; refuse pushing to that ref,
  ever; never force, never delete; push only a TinyAssets-namespaced branch
  (`tiny/<universe-short>/<slug>`) by exact commit SHA as a fast-forward
  refspec; host protection remains an additional remote refusal. No
  `allow_default_branch` *(R1)*.

### D2. A code node with `workspace: "<checkout node>"` runs inside the lease

- The compiler resolves `workspace:` **only** through the run's effect
  chain: the named node must be a graph ancestor whose `workspace/checkout`
  delivered in this run; the chain hands the sandbox an internal,
  non-serialisable capability (lease id + validated path), never a string a
  branch could forge via `$ta.ref` or state *(R1)*. Reopening a pinned
  workspace is itself a fresh `checkout` effect (`storage: "universe"`),
  authority-checked again.
- The jail gains exactly one extra bind — `--bind <lease>/repo /workspace
  --chdir /workspace` — through a dedicated exact-path rule, not by
  loosening `_NEVER_BIND_PREFIXES` *(R1)*; everything else is unchanged
  (`--unshare-all`, `--clearenv`, no `/data`, the authorship gate, the
  ContextVar-carrying RPC). Symlinks inside the checkout cannot escape the
  mount namespace (`/data` does not exist there) *(R1 agreed)*.
- The runner exposes **`ws`**: `ws.run(argv, *, timeout=None, cwd=None,
  env=None)` → `{"code", "stdout_tail", "stderr_tail", "duration_s"}`,
  `ws.read(relpath, max_bytes)`, `ws.write(relpath, text)`,
  `ws.glob(pattern)`. `ws.run` streams the child's output through the same
  incremental bounded drains the sandbox uses, caps cumulative output, and
  a command timeout **terminates the whole jail** (the node fails with
  `workspace_command_timeout`) rather than returning while descendants keep
  running *(R1)*. Paths are relative only and resolved beneath
  `/workspace` with no-magic-link semantics; the host path is never
  exposed *(R1)*. Per node: at most 64 commands and 1 MiB of cumulative
  returned output; the persisted evidence keeps a smaller preview and a
  digest *(R1 P2)*.
- `git` is available inside the jail for **local** operations only (no
  remotes, no network); commits use the identity `TinyAssets Universe
  <universe-short> <<universe-id>@universes.tinyassets.io>`.

### D3. Provisioning: a trusted resolver downloads, the jail installs offline

No user code ever runs with both network and the checkout *(R1 P0)*.
`checkout` may declare `provision: {"python": "<requirements file>",
"node": true}`:

- A **resolver step**, owned by the platform (not user code), runs in a
  fresh network-enabled jail that holds **no checkout** — only the
  requirement text (a `requirements.txt`/lockfile the worker copied out,
  rejected if it contains option lines such as `--index-url`) and an empty
  cache directory. It runs a fixed command: `pip download --isolated
  --no-config --index-url https://pypi.org/simple -r <req> -d <cache>` /
  `npm ci --ignore-scripts --cache <cache> --userconfig /dev/null
  --registry https://registry.npmjs.org` (package fetch only), in its own
  network namespace with userspace egress that permits only the declared
  public registries after DNS/IP validation — never loopback, private,
  link-local or container neighbours *(R1)*. Its exfiltration surface is
  the requirement names.
- The **install step** runs offline in the workspace jail: `python -m venv
  /workspace/.venv && .venv/bin/pip install --no-index --find-links
  <cache>` (a workspace-local venv; `/opt/venv` stays read-only *(R1)*),
  `npm ci --offline` (install scripts run here, without network).
- Consent kind `workspace_provision` per `(connection, repo)`, worded
  exactly: "download this repository's declared dependencies from the
  public Python/Node registries and install them offline in the workspace".
- This change supports the shipped toolchain only — Python and Node.
  "Any project" needs immutable runner profiles/images with declared
  toolchains: named follow-up *(R1)*. Provisioning is **built second**,
  after checkout/run/push are live.

### D4. Limits are usage, and the box is shared

- **Concurrency:** one workspace job at a time per universe **and one
  box-wide** in this change (`workspace_busy`, retry later) — per-process
  rlimits are not an aggregate bound and the container is capped at 4 GiB
  *(R1)*. Jail rlimits for workspace nodes: `RLIMIT_AS` 1.5 GiB per
  process, `RLIMIT_NPROC` 128, `RLIMIT_NOFILE` 1024, `RLIMIT_FSIZE` 512
  MiB, `RLIMIT_CORE` 0; plus a drain-side watchdog that sums the jail's
  process-tree RSS and kills at 2 GiB. **Named follow-up:** a
  credential-free runner sidecar / delegated cgroup with aggregate
  `memory.max`, `pids.max`, CPU quota and `cgroup.kill`, which is also what
  lifts the box-wide serialisation.
- **Disk:** per lease 4 GiB and a pool of 20 GiB — enforced **best-effort**
  in this change (repository size from the API before cloning, `--depth`,
  a watcher during clone/run that kills at the bound, pool admission on
  reserved bytes) — an honest label, because a plain volume has no kernel
  quota; **named follow-up:** a dedicated scratch filesystem with project
  quotas (host action) *(R1)*.
- **Admissions:** a new ledger kind `workspace` (jobs/hour and bytes/hour
  per universe: 10 jobs, 20 GiB by default, tier-raisable). `checkout`
  consumes a workspace admission and settles the run's *external-write*
  admission as a read; `push` is an external write; `pin`/`discard` are
  storage mutations charged as workspace jobs *(R1)*.
- **Usage budgets that replace the removed shape caps** *(R1 P0)*, in the
  companion change `run-usage-budgets`: per root run at most 500 effect
  dispatches and 256 MiB of outbound bytes; per universe per rolling hour
  5,000 dispatches and 2 GiB; refusals name the exhausted budget
  (`effect_budget_exhausted`) — tier-raisable numbers, never shape.

### D5. Authority and consent

- Typed consent records, each per `(connection, canonical repo)`:
  `workspace_checkout`, `workspace_push`, `workspace_provision`; a remix
  re-requests all three under the remixer's connection *(R1)*. The
  destination consent the HTTP sink uses is not reused.
- The authorship gate is unchanged (code runs only in the universe that
  authored it); a workspace is never shared across universes; the model
  never sees a token; the jail never has a token or network.
- No new MCP handle: `workspace` is a sink name plus a node attribute
  (actions under `write.graph`).

### D6. Failure taxonomy

`workspace_checkout_failed` (auth/transport/quota — an effect failure,
fails the node), `workspace_busy`, `workspace_quota_exceeded`,
`workspace_command_timeout`, `workspace_push_refused` (default branch,
non-fast-forward, host protection), `code_node_failed` for exceptions in
`run()`. A non-zero `ws.run` exit is data.

## Alternatives rejected

- `GIT_ASKPASS` with an inherited fd in the checkout: hooks and
  `credential.helper` in a code-writable `.git` run in the credentialed
  process *(R1)*. `http.extraHeader` via argv or `GIT_CONFIG_VALUE_n`: the
  secret in argv/environment, inherited by children *(R1)*.
- Network in the workspace jail under a consent: `--share-net` is the
  container's namespace — internal ports and neighbours reachable; and
  "allow network while installing" is not informed consent for arbitrary
  exfiltration *(R1)*. Resolver-offline instead.
- A command node kind: not in this change; `code(ws.run) → LLM → code`
  already interleaves *(R1 agreed)*.
- Grace-window lease reuse: reserved-but-released is a contradiction;
  pin or fresh *(R1)*.

## Risks the reviewer should attack (round 2)

1. The staging-repo bridge: any path where the workspace's `.git` content
   (config, hooks, refs, replace objects, alternates) influences the
   credentialed process, including the local-path fetch into staging.
2. The credential helper protocol and the one-shot token pipe.
3. The resolver step: pip/npm option injection through requirement files
   and lockfiles; the egress allowlist for registries and CDNs.
4. The lease state machine and the release outbox versus crash and restart.
5. The box-wide serialisation and watchdog as an interim bound; what the
   sidecar follow-up must provide.
6. The companion budgets: are 500 dispatches / 256 MiB per run and the
   hourly numbers the right first bound, and do refusals carry enough for
   the universe to act?
