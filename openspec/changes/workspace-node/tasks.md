## 1. Slice A — checkout, run, push (scratch and permanent)

- [ ] 1.1 Scratch pool: lease table + `lease_outbox` in the runs database; one `BEGIN IMMEDIATE` admission (reservation, pool total, job lock, `ACTIVE`); terminal status + release entry in one transaction; at-least-once processor (claim, quarantine-rename, delete-without-following, verify, `AVAILABLE`, `LOST` retained); startup sweeper as an admission barrier; periodic dead-claimant sweep; `storage: "universe"` path under the universe quota; no `pin`
- [ ] 1.2 Credential broker in the outbound worker (in-memory, exact `(protocol, host, path)`, repeated `get`, `store`/`erase` ignored, torn down per operation); empty-environment git launcher with the forced options; address pinning via `http.curloptResolve` from the HTTP driver's per-address classification; stderr scrub to fixed classes; `git_read`/`git_write` grant scopes
- [ ] 1.3 `workspace` sink `checkout`: clone into staging → bundle → delete staging → populate a fresh repository in the lease from the bundle; intent journal; resolved-SHA receipt; typed consents `workspace_checkout`/`workspace_push`/`workspace_provision`; evidence without token or host path
- [ ] 1.4 Code node `workspace:` binding: chain-only capability, exact-path bind rule, `ws.run/read/write/glob/bundle` with relative beneath-only paths, bounded drains, cumulative caps, workspace rlimit profile, RSS watchdog, parent-side outer-bwrap kill on timeout with verified exit
- [ ] 1.5 `workspace` sink `push`: bundle copied through the held lease dirfd (beneath/no-symlink, bounded regular file) → credential-free staging `bundle verify` + fsck-checked `index-pack` + strict `fsck` → branch policy → credentialed fast-forward push from staging → `ls-remote` reconciliation; `discard`
- [ ] 1.6 Admissions kind `workspace` (jobs/hour, bytes/hour), the MODIFIED checkout-as-read exception, the workspace bytes excluded from HTTP budgets, the seven failure classes with suggested actions
- [ ] 1.7 Tests: gitfile/alternates/replace-ref workspace cannot make staging read another repository; hook/config in the checkout never runs credentialed; token absent from cmdline/environ/files/evidence; 401 retry succeeds; two concurrent admissions cannot oversubscribe; crash between terminal status and release repaired at startup before admission; `setsid` descendant dies with the namespace; default-branch push refused; checkout settles as read
- [ ] 1.8 Live proof on the founder universe through the app: checkout TinyAssets, run `compileall` in a workspace node, push a one-line change on a `tiny/…` branch, open the PR; deployed sha asserted

## 2. Slice B — provisioning

- [ ] 2.1 Manifest extraction through the held lease dirfd (beneath/no-symlink, bounded regular files, digests); Python requirement grammar (`name[extras]==version ; marker --hash=…` only) and npm lockfile validator (`https://registry.npmjs.org/` tarballs only)
- [ ] 2.2 Resolver jail (no checkout, admitted manifests + empty cache, own network namespace, egress allowlist with per-address validation); `pip download --only-binary=:all: --require-hashes`; `npm ci --ignore-scripts` fetch; offline install in the workspace jail bound to the digests; `workspace_provision` consent; `workspace_provision_refused`
- [ ] 2.3 Tests: URL/path/VCS/include/option lines refused before network; sdist-only package refused; git-URL npm dependency refused; resolver cannot reach loopback/private/neighbours; offline install runs with no network; live proof: provision TinyAssets' requirements and run `pytest -q tests/test_docview.py` in a workspace node

## 3. Land

- [ ] 3.1 Sync the five deltas into `openspec/specs/`, archive the change, PLAN.md pointer, plugin mirror parity, `deployed_sha.py --assert-contains`
