## Context

Survey of the production host (2026-08-30): the daemon container has `git`
2.47 (`http.curloptResolve` available), `node`/`npm`, `bwrap`, Python 3 in a
read-only `/opt/venv`; the image omits build toolchains; the host has 4 CPUs
and 8 GiB RAM but the daemon container is capped at 4 GiB, allows four
concurrent top-level runs, has no `pids_limit`, and stores `/data` on an
ordinary named volume (no filesystem quotas). Code nodes already run in a
bwrap jail (`node_sandbox.py`) with the authorship gate and the run's
ContextVars; outbound HTTP already runs in a spawned credential-blind worker
whose driver validates every resolved address and connects to the validated
IP.

Ceiling 2 (reading a codebase) and ceiling 3 (executing it) are one missing
thing: a filesystem the universe's code can read and run against.

**Review history.** Codex round 1 (design) REJECT: credential mechanism,
provision network, aggregate limits, disk bounds, budgets. Round 2 (design +
deltas) REJECT: the local-path fetch bridge is a confused-deputy read (a
`.git` gitfile reproduced cross-repo), git re-resolves DNS after a preflight,
`pip download` runs sdist build code, npm manifests admit arbitrary tarballs,
provision consent / host-wide lock / outbox protocol / pool transaction not
normative, one-shot helper breaks on retry, `setsid` descendants outlive the
runner, deltas fail strict validation, `pin` inconsistent, taxonomy gaps.
Every finding is folded below and marked *(R1)* / *(R2)*. Round 3 is the
cap; what remains after it goes to the founder.

## Decisions

### D0. Two storage classes: the universe's permanent space, and scratch leased per job

Founder 2026-08-30: permanent storage (your universe's cloud space) is a
different thing from temp storage used by one user's run and later by
another's; a universe never needs to be bigger than the codebase it works on.

- **Permanent** (`<data>/<universe>/…`): the universe itself, bounded by the
  tier quota.
- **Scratch**: a shared pool (`<data>/scratch/`) of **leases**, one per job.
  A lease is a random opaque id bound server-side to `(universe, connection,
  canonical repo, storage class, generation)`; its directory is created
  fresh under a parent resolved without following links, with an opened
  directory handle held for every later host-side access (bind setup,
  manifest copy, bundle copy) *(R1, R2)*.
- **Lease state machine, persisted in the runs database** *(R2)*:
  `RESERVED → ACTIVE(run, universe, generation) → QUARANTINED(path) →
  WIPING → AVAILABLE`, plus `LOST` for a wipe that failed (its bytes stay
  charged against the pool forever, and it is reported). Reservation, the
  20 GiB pool check, the job-lock acquisition and the `ACTIVE` transition
  happen in **one `BEGIN IMMEDIATE` transaction** *(R2)*. The run's
  terminal status and the lease's release entry are written in **one
  transaction** into a `lease_outbox` table (runs database); a single
  in-process processor thread claims entries at-least-once
  (`claimed_by`, `claimed_at`, generation) after commit and performs
  quarantine-rename → delete-without-following-links → verify → `AVAILABLE`;
  a **startup sweeper runs before any new lease is admitted** (admission
  barrier) and a periodic sweeper reclaims entries whose claimant is dead
  *(R2)*. Startup recovery that rewrites in-flight runs to `interrupted`
  also enqueues their leases' release. A directory is never recycled in
  place. **No grace reuse** *(R1)*.
- **Storage class is chosen at checkout** (`storage: "scratch"` default or
  `"universe"`); there is **no `pin` operation** — keeping a workspace
  across turns means checking it out again with `storage: "universe"`,
  which is a fresh authority-checked checkout into permanent space that
  counts against the quota *(R2)*. Permanent workspaces are never aged
  out; only `discard` or a quota refusal removes them *(R1 P2)*.

### D1. Credentialed git never reads a directory user code can write — bundles, staging, pinned addresses

- **checkout**: in the outbound worker, `git clone --bare
  --no-recurse-submodules --depth <n> <canonical https url> <staging>` with
  the environment built from empty, the forced options below, and the
  **address pinned in the transport**: the worker resolves the host, applies
  the HTTP driver's classification to *every* address (public unicast
  only), and passes `-c http.curloptResolve=<host>:443:<validated ip>` so
  libcurl connects to that address (TLS still verifies the hostname) —
  never a preflight that git re-resolves *(R2)*. The worker then creates a
  **bundle** from staging (`git bundle create <file> <ref>`), deletes
  staging, and populates the lease from the bundle into a **freshly
  initialised** repository (`git init` + `git fetch <bundle>` + checkout)
  so `.git/config` holds no remote, no host path, no credential *(R2 P2)*.
- **push**: user code commits locally and calls `ws.bundle(commit_sha)`,
  which — **inside the jail, credential-free** — creates a self-contained
  bundle from one synthetic ref at that exact commit with
  `core.hooksPath=/dev/null`, replacements disabled
  (`--no-replace-objects`), alternates ignored; the worker copies the bundle
  as a **bounded regular file through the held lease dirfd with
  beneath/no-symlink semantics** *(R2)*, then in **credential-free staging**
  runs `git bundle verify`, `git fetch <bundle>` (`index-pack` with
  `transfer.fsckObjects=true`, `fetch.fsckObjects=true`) and a strict
  `fsck`; only then does the **credentialed** push run from staging with
  the pinned address. The workspace's `.git` (gitfiles, alternates, replace
  refs, packed refs, config, hooks) is never traversed by a host-side git
  process *(R2 P0)*. A crafted pack remains parser input; that is why
  verification is credential-free and bounded.
- **Environment and options** (credential-vault delta): `GIT_CONFIG_SYSTEM
  =/dev/null GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
  GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false HOME=<empty tmp>`, no
  `GIT_TRACE*`, `RLIMIT_CORE=0`; `-c core.hooksPath=/dev/null -c
  core.fsmonitor=false -c credential.helper= -c credential.helper=<broker>
  -c credential.useHttpPath=true -c protocol.allow=never -c
  protocol.https.allow=always -c http.followRedirects=false -c
  submodule.recurse=false -c transfer.fsckObjects=true`; canonical URL,
  never a stored remote *(R1)*. Raw stderr scrubbed to fixed classes.
- **Credential broker** *(R2)*: a worker-side in-memory broker (not a
  one-shot pipe) answers `get` for the exact `(protocol, host, path)` of the
  grant — as many times as git asks during one operation (a 401 retry is
  legitimate) — outputs `username` and `password`, ignores `store` and
  `erase`, and is torn down when the operation ends; the token is never
  persisted, never in argv, never in another process's environment.
- **Transport policy is its own grant kind** *(R1)*: `git_read` /
  `git_write` scopes bound to `(host, owner/repo)`; HTTPS:443 only.
- **Crash safety** *(R1)*: intent journaled before the wire
  `(connection, repo, remote_ref, commit_sha, expected_old_sha)`;
  ambiguous outcomes reconciled with `ls-remote`; a repeated non-force push
  of the same SHA to the same ref is success; checkout records the resolved
  SHA before the lease is populated.
- **Branch policy** *(R1)*: resolve remote `HEAD`, refuse it always; only
  `tiny/<universe-short>/<slug>` by exact SHA as a fast-forward refspec;
  never force, never delete; host protection is an additional remote
  refusal.

### D2. A code node with `workspace: "<checkout node>"` runs inside the lease

- Resolved only through the run's effect chain (ancestor checkout in this
  run) into an internal capability; never through state or `$ta.ref`
  *(R1)*. A permanent workspace is reopened only by a fresh `checkout`
  effect with `storage: "universe"`.
- Exactly one extra bind (`--bind <lease>/repo /workspace --chdir
  /workspace`) via a dedicated exact-path rule; everything else unchanged
  (no network, cleared environment, no `/data`, authorship gate, request
  context on RPC) *(R1)*.
- `ws.run(argv, timeout=, cwd=, env=)`, `ws.read`, `ws.write`, `ws.glob`,
  `ws.bundle(commit_sha)`; relative paths only, resolved beneath
  `/workspace` with no-magic-link semantics; incremental bounded drains;
  cumulative caps (64 commands, 1 MiB returned per node; persisted preview +
  digest) *(R1)*.
- **Whole-jail termination is a parent-side act** *(R2)*: on a command
  timeout the runner reports and exits; the **parent** then kills the outer
  bwrap process (the namespace's PID 1) and verifies its exit — a
  double-forked `setsid` descendant is reaped with the PID namespace; the
  node fails as `workspace_command_timeout`. `cgroup.kill` in the runner
  sidecar is the named follow-up that makes this cheaper.
- Local `git` only, commit identity `TinyAssets Universe <universe-short>
  <<universe-id>@universes.tinyassets.io>`.

### D3. Provisioning (slice B): a platform-owned resolver, an offline install, and a real grammar

No user code ever runs with both network and the checkout *(R1)*.
`checkout` may declare `provision: {"python": "<requirements path>",
"node": true}`:

- **Manifests leave the checkout safely**: the worker reads the
  requirements file / `package.json` + lockfile through the held lease
  dirfd with beneath/no-symlink semantics, requires bounded regular files,
  and binds the later offline install to their digests *(R2)*.
- **Python**: the requirements text is parsed and **only** records of the
  form `name[extras]==version ; marker --hash=…` are admitted — direct URLs,
  paths, VCS references, `-r`/`-c` includes and every option line are
  refused *(R2)*. The resolver runs `pip download --isolated --no-config
  --only-binary=:all: --index-url https://pypi.org/simple --require-hashes
  -r <admitted> -d <cache>` — no sdist, so no build backend ever executes
  *(R2)*; the offline install is `python -m venv /workspace/.venv &&
  .venv/bin/pip install --no-index --find-links <cache> …` in the jail
  (`/opt/venv` stays read-only *(R1)*).
- **Node**: every dependency in `package.json` and every `resolved` in the
  lockfile is validated to be a pinned `https://registry.npmjs.org/…`
  tarball; git/URL/file dependencies are refused *(R2)*; the resolver runs
  `npm ci --ignore-scripts --cache <cache> --userconfig /dev/null --registry
  https://registry.npmjs.org` (fetch only); the offline `npm ci --offline`
  in the credential-free, network-less jail may run lifecycle scripts,
  acceptable because whole-jail termination is real *(R2)*.
- The resolver jail holds **no checkout**, only the admitted manifest text
  and an empty cache; its own network namespace with userspace egress that
  permits only the declared registry/CDN hosts after per-address
  validation — never loopback, private, link-local or container neighbours
  *(R1)*.
- **Consent `workspace_provision`** per `(connection, canonical repo)` is a
  normative clause of the sink's requirement (external-effect-adapters
  delta) *(R2)*; a remix re-requests it.
- Shipped toolchain only (Python, Node); runner profiles/images are the
  named follow-up *(R1)*.

### D4. Limits are usage, and the box is shared

- **Job lock** *(R2)*: a durable lock in the runs database keyed by
  universe **and** a host-wide slot (one in this change), acquired in the
  checkout's admission transaction, reentrant for that run's later
  workspace nodes and its push, released only by the terminal outbox
  processor; `workspace_busy` when unavailable (bounded wait, then fail).
  The runner sidecar / cgroup follow-up is what lifts the host-wide slot.
- Jail limits for workspace nodes: `RLIMIT_AS` 1.5 GiB per process,
  `RLIMIT_NPROC` 128, `RLIMIT_NOFILE` 1024, `RLIMIT_FSIZE` 512 MiB,
  `RLIMIT_CORE` 0; a drain-side process-tree RSS watchdog kills the outer
  bwrap at 2 GiB *(R1)*.
- **Disk**: per lease 4 GiB and a 20 GiB pool, enforced best-effort (API
  size precheck, `--depth`, a clone/run watcher) with reservations in the
  admission transaction and `LOST` bytes retained; kernel project quotas on
  a dedicated scratch filesystem are the named follow-up *(R1, R2)*.
- **Admissions**: ledger kind `workspace` (10 jobs / 20 GiB per universe-
  hour, tier-raisable). `checkout` charges a workspace job and, as an
  **explicit exception to the as-built rule that every non-GET sink is a
  write** (engine-run-admissions delta, MODIFIED), settles the run's
  external-write admission as a read; `push` is an external write;
  `discard` is a workspace job *(R2)*.
- **HTTP usage budgets** (companion change `run-usage-budgets`, code
  landed as #2731): 500 dispatches / 256 MiB per root run, 5,000 / 2 GiB
  per universe-hour, unknown sizes charged at the per-call caps.
  **Workspace git transfers are excluded from those HTTP budgets** — they
  are bounded by the lease, the pool and the workspace hourly bytes
  *(R2)*.

### D5. Authority and consent

- Typed consents per `(connection, canonical repo)`: `workspace_checkout`,
  `workspace_push`, `workspace_provision`; a remix re-requests all three.
- Authorship gate unchanged; a workspace never shared across universes;
  the model never sees a token; the jail never has a token or network.
- No new MCP handle.

### D6. Failure taxonomy — one actionable class per refusal *(R2)*

`workspace_checkout_failed` (auth, transport, bundle verification),
`workspace_push_refused` (default branch, non-fast-forward, host
protection, verification), `workspace_busy` (job lock),
`workspace_pool_busy` (pool reservation), `workspace_quota_exceeded` (lease
or universe quota), `workspace_command_timeout`, `workspace_provision_refused`
(manifest grammar / consent). A non-zero `ws.run` exit is data;
`code_node_failed` for exceptions in `run()`.

## Alternatives rejected

- Local-path fetch from the workspace into staging: a gitfile in the
  workspace's `.git` made staging read another repository *(R2 P0)* —
  bundles only.
- DNS preflight then git's own resolution: a resolver can answer
  differently twice *(R2 P0)* — pin the address in the transport.
- `pip download` of sdists: build backends execute *(R2 P0)* —
  binary-only with a strict requirement grammar.
- `GIT_ASKPASS` / `http.extraHeader` / one-shot pipe: *(R1, R2)* — an
  in-memory broker answering bounded repeated `get`.
- Network in the workspace jail; grace-window reuse; a `pin` operation; a
  command node kind: rejected as before.

## Risks the reviewer should attack (round 3, the last)

1. The bundle path end to end: creation inside the jail, the dirfd copy,
   `bundle verify` / `index-pack` / `fsck` credential-free, and whether any
   remaining host-side git touches the lease.
2. `http.curloptResolve` pinning: port/host matching, IPv6, redirects still
   disabled, what happens when the host has several validated addresses.
3. The requirement grammar and the npm lockfile validator as the only
   admission for provisioning.
4. The single-transaction lease admission and the outbox processor's
   at-least-once protocol.
5. Whether the deltas are now strict-valid and consistent with each other
   and with the as-built specs.
