## 1. Slice A — checkout, run, push (scratch and permanent)

- [x] 1.1 Scratch pool: lease table + `workspace_outbox` (actions `wipe_scratch` / `discard_permanent_generation` / `release_lock_only`) in the workspace-owning runs database; one `BEGIN IMMEDIATE` admission (storage reservation, pool total, job lock, byte-ledger maximum, `ACTIVE`); same-database terminal status + outbox atomicity, plus immediate universe outbox enqueue and root-status sweep repair when the canonical run row is stored separately; at-least-once processor with claim tokens, deterministic quarantine names and reconcile-every-combination retries; `AVAILABLE`/`LOST` + both locks released in the final transaction; startup sweeper as an admission barrier; permanent workspaces as immutable generations switched atomically; no `pin`, no `reuse`
- [x] 1.2 Credential broker in the outbound worker (in-memory, exact `(protocol, host, path)`, repeated `get`, `store`/`erase` ignored, torn down per operation); empty-environment git launcher with the forced options; address pinning via `http.curloptResolve` from the HTTP driver's per-address classification; stderr scrub to fixed classes; `git_read`/`git_write` grant scopes
- [x] 1.3 `workspace` sink `checkout`: full clone into staging → prerequisite-free bundle → delete staging → populate a fresh unpublished generation from the bundle → publish; intent journal; resolved-SHA receipt; typed consents `workspace_checkout`/`workspace_push`/`workspace_provision`; evidence without token or host path
- [x] 1.4 Code node `workspace:` binding: chain-only capability, exact-path bind rule, `ws.run/read/write/glob/bundle` with relative beneath-only paths, bounded drains, cumulative caps, workspace rlimit profile, RSS watchdog, parent-side outer-bwrap kill on timeout with verified exit
- [x] 1.5 `workspace` sink `push`: bundle copied through the held lease dirfd (beneath/no-symlink, bounded regular file) → credential-free staging `bundle verify` + fsck-checked `index-pack` + strict `fsck` → branch policy → credentialed fast-forward push from staging → `ls-remote` reconciliation; `discard`
- [x] 1.6 Admissions kind `workspace` (jobs/hour, bytes/hour), the MODIFIED checkout-as-read exception, the workspace bytes excluded from HTTP budgets, the seven failure classes with suggested actions
- [x] 1.7 Tests: gitfile/alternates/replace-ref workspace cannot make staging read another repository; hook/config in the checkout never runs credentialed; token absent from cmdline/environ/files/evidence; 401 retry succeeds; two concurrent admissions cannot oversubscribe; crash between terminal status and release repaired at startup before admission; `setsid` descendant dies with the namespace; default-branch push refused; checkout settles as read
- [ ] 1.8 Live proof on the founder universe through the app: checkout TinyAssets, run `compileall` in a workspace node, push a one-line change on a `tiny/…` branch, open the PR; deployed sha asserted

## 2. Slice B — provisioning

- [x] 2.1 Manifest extraction through the held lease dirfd (beneath/no-symlink, bounded regular files, digests); Python requirement grammar (`name[extras]==version ; marker --hash=…` only) and npm lockfile validator (`https://registry.npmjs.org/` tarballs only). Runtime checkout now checks resolved connection consent before extracting all manifests together; refusal precedes any resolver network. Local integration and Linux extraction tests pass; release acceptance remains in 2.3/3.1.
- [ ] 2.2 Resolver jail (no checkout, admitted manifests + empty cache, own network namespace, egress allowlist with per-address validation); `pip download --only-binary=:all: --require-hashes`; `npm ci --ignore-scripts` fetch; offline install in the workspace jail bound to the digests; `workspace_provision` consent; `workspace_provision_refused`
- [ ] 2.3 Tests: URL/path/VCS/include/option lines refused before network; sdist-only package refused; git-URL npm dependency refused; resolver cannot reach loopback/private/neighbours; offline install runs with no network; live proof: provision the checked-in hash-locked fixture `tests/fixtures/workspace/requirements-locked.txt` and run `pytest -q tests/test_docview.py` in a workspace node

## 2b. Drop-first operational exec migration

Design + approved amendment + delta scenarios:
`drop-first-operational-exec-amendment.md`; coordinator disposition and
opposite-family compatibility review (both 2026-09-20) in
`docs/reviews/2026-09-20-drop-first-ops-shape-disposition.md`. Shape APPROVED;
no further shape review needed.

**Carried as prose, not checkboxes.** This slice is one bounded migration, and
splitting it into nine rows pushed the change past its 12-checkbox ceiling
without adding any decision the reviewer had to make. What shipped: the static
root-owned `0555` `/usr/local/libexec/ta-op` outside `/app` and `/data`, with
the exact-five-cap root branch (full UID/GID/groups/cap retirement plus
whole-line readback) and the legacy-rootless verification branch (all four UID
and GID positions 1001, all five cap sets 0, NNP 1, supplementary groups
empty-or-gid-1001), every other entry refused, descriptors above stderr closed
before any exec; the closed nine-mode table preserving existing argv
(`version`, `env-summary`, `pulse`, `canary`, `printenv`, `claude-keepalive`,
`codex-keepalive`, `bwrap-oracle`, `claude-login`) with no shell, path or
interpreter switch from any callsite; the static build and install in the
existing builder stage; every real caller migrated (`droplet.py env`/`canary`,
`apply-daemon-env-remote.sh:88,118`, the compose healthcheck, both keepalive
workflows by argv only with schedules and enabled state untouched, the
bwrap-oracle docstring, `DEPLOY.md`, `README.md`, `tinyassets-env.template`,
`apply-daemon-env.yml`); the version preflight above the fail-open read and
above every mutation, refusing with no restart and no bare fallback; and
`scripts/check_drop_first_exec.py` registered as an invariant with no
grandfather allowlist and no exemption tier, sharing `ta_op_modes.tsv` with the
runtime under a parity test. Tests: gate red on the pre-migration content of
five real callsites and on every TTY form, green on the migrated ones; mode
parity; fail-before-mutation/no-restart; rollback-order regression on both
paths; the anchored identity-readback regression.

Outstanding native, CI, deploy and live gates are carried by 3.1 below — they
are the release gate for this slice, not separate delivery work.

## 3. Land

- [ ] 3.1 Release gate and land: native proof per `deploy/native/NATIVE-TEST-PLAN.md` (root ran rows 1–16 and 18 on local fixtures 2026-09-21, row 17 on a local fixture install only — `docs/reviews/2026-09-21-drop-first-native-local-proof.md`; the installed production image is still unchecked), CI image build, live `ta-op pulse` healthcheck green, public canary, rendered `ui-test`; deltas synced into `openspec/specs/daemon-runtime-and-dispatch/spec.md` 2026-09-21 (done — see the amendment); still to do: archive the change, PLAN.md pointer, plugin mirror parity, `deployed_sha.py --assert-contains`
