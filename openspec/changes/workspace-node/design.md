## Context

Survey of the production host (2026-08-30): the daemon container has `git`
2.47 (`http.curloptResolve` available), `node`/`npm`, `bwrap`, Python 3 in a
read-only `/opt/venv`; the image omits build toolchains; the host has 4 CPUs
and 8 GiB RAM but the daemon container is capped at 4 GiB, allows four
concurrent top-level runs, has no `pids_limit`, and stores `/data` on an
ordinary named volume (no filesystem quotas). Code nodes already run in a
bwrap jail (`node_sandbox.py`) with the authorship gate and the run's
ContextVars; outbound HTTP already runs in a spawned credential-blind worker
whose driver validates every resolved address and connects to a validated
IP.

Ceiling 2 (reading a codebase) and ceiling 3 (executing it) are one missing
thing: a filesystem the universe's code can read and run against.

**Review history (three rounds, the cap).** Codex R1 REJECT: credential
mechanism, provision network, aggregate limits, disk bounds, budgets. R2
REJECT: local-path fetch bridge is a confused-deputy read, DNS re-resolution,
`pip download` runs build code, npm manifests admit arbitrary tarballs,
consent/lock/outbox/pool not normative, one-shot helper, `setsid`
descendants, strict validation, `pin`, taxonomy. R3 REJECT: shallow clones
cannot cross a bundle-only bridge; permanent refresh-in-place re-opens
user-written `.git`; outbox rename/delete windows; grammar precision; plus
IPv6/address selection, the boundary statement, byte reservation, proposal
drift, `discard`, the bwrap kill target. Every R3 finding is folded below,
marked *(R3)*. Per `AGENTS.md` (three rounds, then escalate) there is no
round 4: the fold and the residual go to the founder with the build.

## Decisions

### D0. Two storage classes: the universe's permanent space, and scratch leased per job

Founder 2026-08-30: permanent storage (your universe's cloud space) is a
different thing from temp storage used by one user's run and later by
another's; a universe never needs to be bigger than the codebase it works on.

- **Permanent** (`<data>/<universe>/workspaces/<repo-key>/<generation>/`):
  bounded by the tier quota. A permanent workspace is a sequence of
  **immutable-by-host generations** *(R3)*: every `storage: "universe"`
  checkout builds a **new** opaque generation from staging's bundle beneath
  a no-follow universe directory handle, publishes it by atomically
  switching the repo-key's authoritative generation pointer (a DB row), and
  enqueues the previous generation for `discard_permanent_generation`
  through the outbox. Host git never opens an old generation. There is no
  `reuse` and no refresh-in-place; keeping local work across turns means
  pushing it (a `tiny/…` branch) or leaving it in the current generation
  until the next checkout replaces it. A quota refusal leaves the existing
  generation untouched.
- **Scratch**: a shared pool (`<data>/scratch/<lease_id>/`) of leases, one
  per job. A lease is a random opaque id bound server-side to `(universe,
  connection, canonical repo, generation)`; its directory is created fresh
  under a parent resolved without following links, with an opened directory
  handle held for every later host-side access (bind setup, manifest copy,
  bundle copy) *(R1, R2)*.
- **Admission is one transaction** *(R2)*: reservation of the lease bound
  (or the universe quota), the pool-total check, the job-lock acquisition,
  the **byte-ledger reservation of the operation's maximum charge** *(R3)*
  and the `ACTIVE` transition happen in one `BEGIN IMMEDIATE` transaction in
  the runs database; the reservation is reconciled downward to measured
  bytes after the transfer, and an unknown or interrupted transfer keeps
  the maximum.
- **Terminal workspace outbox** *(R2, R3)*: a run's terminal status and its
  outbox entries are written in one transaction into `workspace_outbox`
  (runs database). Entries carry an action — `wipe_scratch(lease,
  generation)`, `discard_permanent_generation(repo_key, generation)`,
  `release_lock_only` — plus the universe and host locks to release. A
  single in-process processor claims entries at-least-once with a claim
  token and `claimed_at`, performs the filesystem steps **idempotently
  against a deterministic quarantine name**
  (`<pool>/.quarantine/<lease_id>.<generation>` or
  `<universe>/workspaces/.quarantine/<repo_key>.<generation>`), and
  reconciles every combination on retry: source present & quarantine
  absent → rename; source absent & quarantine present → delete; both
  absent → done; both present → delete quarantine, then rename. Deletion
  never follows links. The final transaction marks the lease `AVAILABLE`
  (or `LOST` on a failed wipe — bytes stay charged and it is reported),
  releases both locks, and acknowledges the entry by claim-token compare.
  This protocol **replaces both existing terminal paths coherently** — the
  direct terminal write in `update_run_status` and the startup bulk rewrite
  of in-flight runs (`runs.py` ~884 / ~4334) — so startup recovery enqueues
  `wipe_scratch`/`release_lock_only` for every interrupted run in the same
  transaction that rewrites it. **A startup sweeper runs to completion
  before any new workspace job is admitted** (admission barrier); a
  periodic sweeper reclaims entries whose claim expired. No directory is
  recycled in place; **no grace reuse** *(R1)*.
- **Storage class is chosen at checkout**; there is no `pin` operation
  *(R2)*.

### D1. Credentialed git never opens a workspace — bundles, staging, pinned addresses

**The boundary, stated exactly** *(R3)*: no credentialed git process ever
opens a workspace or reads its `.git`; no host-side git process opens a
workspace's `.git` after the workspace is **published** (its capability
handed to user code); a host-side, credential-free initializer populates a
fresh, **unpublished** generation from a verified bundle, and publication
happens only after fetch, checkout, `fsck` and staging deletion all
succeed.

- **Full clones only** *(R3)*: a git bundle cannot represent a shallow
  boundary, and a bundle with prerequisites cannot be imported into an
  empty repository, so `checkout` performs a full clone (`--no-recurse-
  submodules --single-branch` at the requested ref) and both directions use
  **self-contained** bundles. Measured on git 2.53 (builder, 2026-08-31):
  `git bundle verify` in an empty repository ACCEPTS a bundle made from a
  `--depth 1` clone - a shallow boundary is not a declared prerequisite -
  so `bundle verify` alone is never the gate; self-containedness is
  proven by the fsck-checked import into an empty repository ("did not
  send all necessary objects" refuses), which both the checkout population
  and the push staging run, in that order after `verify`. `depth` is not a packet field; a prerequisite protocol
  (staging proves it holds the exact base objects before importing a thin
  bundle) is the named follow-up for very large repositories. The API
  size precheck and the lease bound refuse repositories that do not fit.
- **checkout**: in the outbound worker, `git clone --bare … <canonical
  https url> <staging>` with the environment built from empty, the forced
  options below and the **address pinned in the transport**
  (`http.curloptResolve`), then bundle → delete staging → `git init` +
  fetch-from-bundle + checkout + `fsck` in the unpublished generation →
  publish. `.git/config` holds no remote, no host path, no credential.
- **push**: user code commits locally and calls `ws.bundle(commit_sha)`,
  which — inside the credential-free, network-less jail — creates a
  self-contained bundle from one synthetic ref at that exact commit with
  `core.hooksPath` nulled and `--no-replace-objects`; the jail's own
  reading of adversarial `.git` state is accepted residual parser input
  because that process stays inside the jail and its output is treated as
  hostile *(R3)*. The worker copies the bundle as a bounded regular file
  through the held directory handle with beneath/no-symlink semantics,
  then in **fresh credential-free staging** runs `bundle verify` (refusing
  prerequisites), an fsck-checked `index-pack`/fetch and a strict `fsck`;
  only then does the **credentialed** push run from staging.
- **Address pinning** *(R2, R3)*: the worker resolves the host, applies the
  HTTP driver's classification to **every** address (public unicast only;
  a mixed answer is a refusal), lower-cases the host, brackets IPv6, and
  emits one `http.curloptResolve=<host>:443:<a1>,<a2>,…` rule when the
  runtime libcurl is ≥ 7.59 (checked once at worker start from
  `libcurl/X.Y.Z`, fail-loud) — otherwise one validated address per whole
  operation, with a push retry reconciling the remote ref before it sends
  again. The rule matches exact host+port for every request of the
  operation; TLS still verifies the hostname; `http.followRedirects=false`
  prevents cross-host redirection. What the pin defends is rebinding
  between validation and connect — not a host that legitimately moved;
  identity is the hostname's TLS verification, and a git operation that
  hangs on the wire lands as `workspace_checkout_failed` /
  `workspace_push_refused` with the distinct stderr class `timeout`, not
  `transport` (builder finding, 2026-08-30).
- **Environment and options** (credential-vault delta): environment built
  from empty (`GIT_CONFIG_SYSTEM`/`GIT_CONFIG_GLOBAL` null device,
  `GIT_CONFIG_NOSYSTEM=1`, `GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS` false,
  empty `HOME`, no `GIT_TRACE*`, `RLIMIT_CORE=0`); options `core.hooksPath`
  null, `core.fsmonitor=false`, `credential.helper=` then the broker,
  `credential.useHttpPath=true`, `protocol.allow=never`,
  `protocol.https.allow=always`, `http.followRedirects=false`,
  `submodule.recurse=false`, `transfer.fsckObjects=true`; canonical URL,
  never a stored remote. Raw stderr scrubbed to fixed classes.
- **Credential broker** *(R2)*: worker-side, in-memory, answers `get` for
  the exact `(protocol, host, path)` as many times as one operation asks,
  outputs `username` and `password`, ignores `store`/`erase`, torn down per
  operation; the token is never persisted, never in argv, never in any
  process environment.
- **Grant kinds** *(R1)*: `git_read` / `git_write` bound to `(host,
  owner/repo)`; HTTPS:443 only.
- **Crash safety** *(R1)*: intent journaled before the wire; ambiguous
  outcomes reconciled with `ls-remote`; a repeated non-force push of the
  same SHA to the same ref is success; checkout records the resolved SHA
  before the generation is populated.
- **Branch policy** *(R1)*: refuse the remote `HEAD` always; only
  `tiny/<universe-short>/<slug>` by exact SHA as a fast-forward refspec;
  never force, never delete.

### D2. A code node with `workspace: "<checkout node>"` runs inside the generation

- Resolved only through the run's effect chain into an internal capability;
  never through state or `$ta.ref` *(R1)*.
- Exactly one extra bind (`--bind <generation>/repo /workspace --chdir
  /workspace`) via a dedicated exact-path rule; everything else unchanged
  *(R1)*.
- `ws.run(argv, timeout=, cwd=, env=)`, `ws.read`, `ws.write`, `ws.glob`,
  `ws.bundle(commit_sha)`; relative beneath-only paths; bounded incremental
  drains; cumulative caps (64 commands, 1 MiB per node) *(R1)*. The export
  path is a contract between the jail and the sink: `ws.bundle(sha)` writes
  `/workspace/.tiny-export/<sha>.bundle` and returns that relative path; the
  push reads exactly `repo/.tiny-export/<sha>.bundle` through the held lease
  handle (builder finding, 2026-08-31).
- **Whole-jail termination** *(R2, R3)*: bwrap installs its own trivial PID
  1 reaper and runs as a tracked supervisor with `--die-with-parent`; on a
  command timeout the parent SIGKILLs the **tracked bwrap supervisor**,
  confirms its exit, and relies on the `--die-with-parent` cascade to end
  the sandbox; the existing kill helper (`_kill_process_tree`) verifies
  only the tracked process, so the Linux integration test must prove that
  a double-forked `setsid` sleeper no longer exists after the timeout. The
  node fails as `workspace_command_timeout`. `cgroup.kill` in the runner
  sidecar is the named follow-up.
- **discard** *(R3)*: a generation-checked outbox transition
  (`wipe_scratch` or `discard_permanent_generation`) that **immediately
  revokes the capability**; later `ws.*` calls in the same run raise inside
  `run()` and the node fails as `code_node_failed` naming the discard;
  failures of the discard itself are `workspace_discard_failed`.
- **Residual (builder finding, 2026-08-31):** the capability is resolved once
  at node start, so a `discard` fired by a PARALLEL branch during a long
  `run()` does not make a later `ws.*` call in that same node raise - the
  next node refuses, this one finishes. Enforcing it inside the child needs a
  parent-to-child signal on the RPC pipe; named follow-up, not in this slice.
- Local `git` only; commit identity `TinyAssets Universe <universe-short>
  <<universe-id>@universes.tinyassets.io>`.

### D3. Provisioning (slice B): a platform-owned resolver, an offline install, and a real grammar

No user code ever runs with both network and the checkout *(R1)*.
`checkout` may declare `provision: {"python": "<requirements path>",
"node": true}`:

- **Manifests leave the checkout safely**: read through the held directory
  handle with beneath/no-symlink semantics, bounded regular files, strict
  UTF-8; the later offline install is bound to their digests *(R2)*.
- **Python admission is a grammar, canonicalised by a real parser**
  *(R3)*: pre-checks refuse option lines, includes, direct URLs, local
  paths, VCS references and environment references with a precise reason;
  each logical record (continuations joined) is then parsed with
  `packaging.requirements.Requirement` and admitted only if it has no URL,
  exactly one `==` specifier with no wildcard and a PEP 440 version, at
  least one `--hash=sha256:<64 hex>`, and a marker (optional) using only
  `python_version`, `python_full_version`, `sys_platform`,
  `platform_machine`, `platform_system`, `implementation_name`, `os_name`.
  Extras are optional. The resolver receives **only the reconstructed
  canonical text** (`<name>[extras]==<version> ; <marker> --hash=…`,
  sorted), never the original file, and runs `pip download --isolated
  --no-config --only-binary=:all: --require-hashes --index-url
  https://pypi.org/simple -r <canonical> -d <cache>` *(R2)*; the offline
  install is `python -m venv /workspace/.venv && .venv/bin/pip install
  --no-index --find-links <cache> …` in the jail.
- **Node admission** *(R3)*: `package-lock.json` (v2/v3) required;
  workspaces and `link:` entries are **refused in this slice**; every
  installable lock entry must carry `resolved` parsing to
  `https://registry.npmjs.org/…tgz` exactly and a `sha512-` integrity; all
  of `dependencies`, `devDependencies`, `optionalDependencies` and
  `peerDependencies` (top level and nested) must be semver ranges. The
  resolver stages only the canonical JSON and runs `npm ci --ignore-scripts
  --cache <cache> --userconfig /dev/null --registry
  https://registry.npmjs.org` (fetch only); the offline `npm ci --offline`
  in the credential-free, network-less jail may run dependency lifecycle
  scripts. The staged manifests are RECONSTRUCTED from validated fields
  only (lockfile emitted as v3 with no legacy graph; `scripts` not carried,
  so the root manifest's own lifecycle hooks do not run offline - a
  tightening over the first draft, builder 2026-08-31).
- The resolver jail holds no checkout, only the canonical manifests and an
  empty cache; its own network namespace with userspace egress that permits
  only the declared registry hosts after per-address validation *(R1)*.
- **Consent `workspace_provision`** per `(connection, canonical repo)` is a
  normative clause *(R2)*; a remix re-requests it.
- Provisioning failures are typed *(R3)*: admission and consent →
  `workspace_provision_refused`; resolver transport, cache-bound and
  offline-install failures → `workspace_provision_failed`.
- Shipped toolchain only (Python, Node) *(R1)*.

### D4. Limits are usage, and the box is shared

- **Job lock** *(R2)*: durable, keyed by universe **and** a host-wide slot
  (one in this change), acquired in the checkout's admission transaction,
  reentrant for that run, released only by the outbox processor;
  `workspace_busy` when unavailable within the node's timeout.
- Jail limits for workspace nodes: `RLIMIT_AS` 1.5 GiB, `RLIMIT_NPROC` 128,
  `RLIMIT_NOFILE` 1024, `RLIMIT_FSIZE` 512 MiB, `RLIMIT_CORE` 0; RSS
  watchdog at 2 GiB *(R1)*.
- **Disk**: 4 GiB per lease, 20 GiB pool, best-effort enforcement with
  reservations in the admission transaction and `LOST` bytes retained;
  kernel project quotas are the named follow-up *(R1, R2)*.
- **Admissions**: ledger kind `workspace` (10 jobs / 20 GiB per universe-
  hour, tier-raisable) with **pre-wire reservation of the maximum charge**
  (lease bound for checkout, bounded bundle size for push, cache cap for
  provisioning) reconciled downward after transfer *(R3)*. `checkout`
  settles the run's external-write admission as a read (MODIFIED clause of
  the as-built settlement rule); `push` is an external write.
- **HTTP usage budgets** (`run-usage-budgets`, landed as #2731) bound
  `authenticated_external_call` only; workspace bytes are excluded *(R2)*.

### D5. Authority and consent

Typed consents per `(connection, canonical repo)`: `workspace_checkout`,
`workspace_push`, `workspace_provision`, keyed as
`<op>:<connection_id>:<host>/<owner>/<name>` so two connections to one
repository hold independent consents; a remix re-requests all three.
`discard` needs no consent — dropping what you already hold is not a new
reach (builder finding, 2026-08-31). Git scopes are `git_read:owner/name`
/ `git_write:owner/name` on the connection, validated at the storage
boundary, preserved across the endpoint-derived scope rewrite, and never
accepted as HTTP verbs. The
authorship gate is unchanged; a workspace is never shared across universes;
the model never sees a token; the jail never has a token or network. No new
MCP handle.

### D6. Failure taxonomy — one actionable class per refusal

`workspace_checkout_failed` (auth, transport, bundle verification, fit),
`workspace_push_refused` (default branch, non-fast-forward, host
protection, verification), `workspace_busy` (job lock),
`workspace_pool_busy` (pool reservation), `workspace_quota_exceeded` (lease,
universe or hourly bound), `workspace_command_timeout`,
`workspace_provision_refused` (admission, consent),
`workspace_provision_failed` (resolver/install), `workspace_discard_failed`.
A non-zero `ws.run` exit is data; `code_node_failed` for exceptions in
`run()`.

## Alternatives rejected

- Shallow clones over the bundle bridge: bundles cannot carry the boundary
  *(R3)* — full clones, prerequisite protocol as follow-up.
- Refreshing a permanent workspace in place: re-opens user-written `.git`
  *(R3)* — immutable generations switched atomically.
- Local-path fetch from the workspace *(R2)*; DNS preflight then git's own
  resolution *(R2)*; `pip download` of sdists *(R2)*; `GIT_ASKPASS` /
  `http.extraHeader` / one-shot pipe *(R1, R2)*; network in the workspace
  jail; grace-window reuse; a `pin` operation; a command node kind.

## Residual after three rounds (for the founder, not a fourth round)

- **Code review ledger (separate from the design's three rounds):** R1 on the
  substrate REJECT (16 P1, all folded by module owner); R2 on the whole branch
  REJECT - two P0 integration seams (the bind handle was the lease root, not
  the repository; the compiler dropped `pass_fds`) and fourteen P1s
  (provisioning advertised but unwired, no durable push-intent journal, the
  barrier failing open, `discard` counted as a read, an import-allowlist
  bypass through a `str` subclass, check-then-open `ws` paths, the timeout
  class never reaching the classifier, scope-only `extend_http` unable to
  execute, descriptor leaks, unverified staging deletion, capability lookup
  ignoring ancestry) - all folded 2026-08-31; R3 is the cap.

- **As-built deviations found at spec sync (2026-08-31), now named follow-ups
  rather than claims:** there is no process-tree RSS watchdog (the rlimit
  profile is the memory bound); there is no 1800 s ceiling on a workspace
  node's `timeout_seconds` (the declared timeout governs); and
  `workspace_provision_failed` is classified but never raised, because the
  resolver jail is slice B - provisioning admits, stages and refuses, it does
  not yet install. The as-built specs under `openspec/specs/` say the true
  thing; this design keeps the intent.
- `ws.bundle` shells out to a bare `git` and the sandbox child has no PATH
  on Windows, so a Windows tray host cannot push yet (Linux daemon first).

- Everything above is design; the build proves it. The Linux-only
  integration tests (bwrap kill cascade, bundle prerequisite refusal,
  dirfd beneath semantics) run in CI, not on the Windows dev host.
- Disk is best-effort until the kernel-quota follow-up; the host-wide slot
  serialises workspace jobs across universes until the runner sidecar.
- Very large repositories wait on the prerequisite protocol.
