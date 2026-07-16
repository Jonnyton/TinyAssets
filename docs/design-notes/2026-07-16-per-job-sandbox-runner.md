# Per-job sandboxed execution runner

**Status:** proposed for Claude-family review; implementation-directed by host 2026-07-16.
**Initial provider:** Codex. **Required reviewer:** Claude family. **Scope:** design only; no runtime code.
**Local basis:** `origin/feat/patch-loop-s3` at `a59e808e`, especially `tinyassets/sandbox_policy.py`, provider attestation gates, tests, and its Phase-2 exec plan; approved patch-loop reference design at `origin/docs/patch-loop-reference-design`.
**Source freshness:** primary sources re-checked 2026-07-16; URLs are at the end.

## Decision

Build one narrow `tinyassets-runnerd` service outside the production app containers, running as a dedicated unprivileged host user and launching disposable jobs with **rootless Podman**. The Dockerized daemon/workers receive only the runner's limited Unix socket—not Docker's or Podman's control socket. Rootless Podman maps container root into an unprivileged host user namespace; its full API still permits arbitrary code as that user, so the app must never receive that API either [S3][S4].

The model remains daemon-side. A fixed agent driver inside the job asks for model turns through one job-scoped broker socket; the daemon's existing provider layer owns subscription/API auth and returns bounded model responses. The job gets no provider, GitHub, vault, host, MCP, or universe credential and has no general network. This is preferable to injecting a provider token: current provider credentials are not truly per-job or least-privilege, while a broker can bind model, owner, turn/token/cost budget, expiry, and audit to one job. Claude Code documents both tool restriction and gateway-style centralized authentication/budgets, validating the shape [S11][S12].

This is a platform primitive: branch authors compose policies and tests, but only the platform can enforce a host isolation boundary.

## Target architectures

### Production droplet

`daemon/worker container -> /run/tinyassets-runner/runner.sock -> host systemd tinyassets-runnerd (UID tinyassets-runner) -> podman CLI -> rootless OCI job`

- `tinyassets-runnerd` calls the daemonless Podman CLI directly; it does not enable `podman system service`. Its own UDS is `0660`, group `tinyassets-runner-client`; requests are schema-validated, idempotent, quota-bound, and cannot choose image, mounts, env, namespaces, network, devices, or Podman flags.
- Provision `uidmap`, Podman, `crun`, `fuse-overlayfs`, and `passt`; allocate unique 65,536-entry subuid/subgid ranges and enable user lingering. Rootless prerequisites and cgroup-v2 limitations are explicit upstream [S3][S5]. Runner readiness refuses cgroup v1 or missing delegated CPU/memory/pids controllers.
- Resize the current 1-GB target before enabling jobs: minimum 2 vCPU/4 GiB RAM. Attach a 25-GiB XFS volume mounted with `pquota` at `/var/lib/tinyassets-runner`; Podman volume size/inode limits use XFS project quotas and must be proven by self-test [S6][S14]. One concurrent job is the safe initial production cap.
- Pin the job image by digest, pre-pull during deploy, and run with `--pull=never`; Podman supports digest pulls and a never-pull execution policy [S10]. No build or image pull occurs on a job request.
- Keep the existing `/data` volume entirely absent from jobs. Only the main app keeps `/data`; the runner receives source/result bytes through its API.

**Compose/provisioning delta:** add no runner container and mount no Docker/Podman control socket. `daemon` and the `worker` anchor receive only the narrow host-service directory:

```yaml
environment:
  TINYASSETS_RUNNER_SOCKET: /run/tinyassets-runner/runner.sock
group_add: ["${TINYASSETS_RUNNER_GID}"]
volumes:
  - /run/tinyassets-runner:/run/tinyassets-runner:ro
```

Bootstrap creates the user/group/subids, XFS+pquota mount, tmpfiles entry, pinned runner binary/policy/image, and `tinyassets-runner.service`; deploy updates runner artifacts, pre-pulls by digest, starts it, and requires a green self-test before advertising repo execution. Runner health gets its own watchdog/alarm. A down runner makes repo-node readiness false but must not make the public MCP healthcheck fail.

### Windows 11 Tier-2

- The tray installer probes `wsl --status`, `wsl --version`, virtualization, and `podman machine inspect`. With WSL2 already working: install/update Podman, `podman machine init --rootful=false --cpus 2 --memory 4096 --disk-size 40 --now tinyassets-runner`, provision runner/image inside the machine, start its user service, and maintain an SSH local forward to the runner UDS. Podman documents Windows machines as WSL2-backed and rootless-selectable [S7][S8].
- Stream source bundles into Linux volumes; never bind an NTFS checkout or the Windows home into a job. Podman Machine exposes Windows drives inside WSL by default, so the runner self-test must prove none is mounted into the job [S8].
- The <5-minute install SLO applies to the warm path (WSL2 present, virtualization enabled, normal broadband) and is a measured release gate including image availability. If WSL2 is absent/disabled, return `RUNNER_UNAVAILABLE_WSL2_REQUIRED` with `wsl --install` guidance and refuse repo nodes. Enabling WSL requires administrator action and a restart, so claiming a silent <5-minute fallback would be false [S9]. No native-Windows-process sandbox fallback.

### Rejected alternatives

- **Docker socket in daemon:** reject; Docker says daemon control can mount host `/` and its client keys are effectively a root password [S1][S2]. `:ro` on a socket does not make its API read-only.
- **Docker-socket sidecar:** better blast radius than direct mount, but its compromise remains host-root-equivalent; retain only as an emergency, separately approved fallback.
- **DinD:** reject; even rootless DinD requires `--privileged` to disable seccomp/AppArmor/mount masks and duplicates daemon/storage lifecycle [S13].
- **Direct rootless Podman socket:** reject; the upstream API grants full arbitrary-code execution as its user with no per-operation restriction [S4]. Wrap the CLI with the narrow service.
- **bwrap inside the app container:** reject as the runner. Bubblewrap requires user namespaces and is a policy construction tool, not a complete sandbox; nested Docker also needs syscall/capability exceptions. It does not supply checkout disposal, disk/cgroup quotas, broker scoping, or result extraction [S15]. S3's Codex bwrap remains defense in depth for non-runner calls.

## Job contract

States are `ACCEPTED -> PREPARING -> EXECUTING -> EXTRACTING -> DESTROYING -> SUCCEEDED|FAILED|CANCELLED`; any transition failure goes to `DESTROYING`. Repeating a caller idempotency key returns the same job/result.

1. **Prepare.** Daemon-side repo staging uses the universe vault to fetch the bound repo at an immutable commit, then closes credentials and uploads a credential-free Git bundle plus manifest/hash. Runner validates size/hash, creates a quota-backed job volume, clones the bundle into `/workspace/repo`, removes remotes/config hooks, and records the baseline tree. LFS/submodules are resolved daemon-side or the request is refused.
2. **Prefetch.** Optional ecosystem adapters parse only committed lockfiles and fetch through an allowlisted package-registry cache in a separate disposable fetch container: source read-only, no model socket, no credentials, lifecycle scripts disabled. Git/URL dependencies, unlocked resolution, or unsupported ecosystems fail `PREPARE_DEPENDENCIES_UNSUPPORTED`; execute never receives internet.
3. **Execute.** Launch the pinned image as UID/GID 65532 with rootfs read-only, `cap-drop=ALL`, `no-new-privileges`, default seccomp/AppArmor (never unconfined), no devices/host namespaces/runtime socket, job volume at `/workspace`, bounded tmpfs, and `network=none`. Podman defines these controls and notes rootless resource limits require cgroup v2 [S5].
4. **Model loop.** The fixed driver alternates local bounded actions (`list/read/write/exec`) with `POST /v1/model` on a per-job UDS. Runner queues each model request; the daemon worker polls it over the control UDS, calls exactly one pre-bound provider/model with sanitized text-only config and no fallback, and returns a response. Turn/token/cost/time budgets are fixed at create; arbitrary job code can spend only this job's remaining broker budget.
5. **Test.** Commands are data inside the container, never host shell/Podman arguments. The driver captures argv/shell text, cwd, start/end, exit/signal/timeout, bounded stdout/stderr hashes, and a clean/failed result. A final verify-only pass runs after the agent stops editing.
6. **Extract.** In an alternate Git index, stage the workspace after allowing only regular `100644`/`100755` files and rejecting special files, symlinks, gitlinks, case-collisions, `.git`, absolute/`..` paths, and out-of-root realpaths. Emit a no-renames full-index binary diff, changed-file manifest, receipts, logs, hashes, resource usage, and enforcement receipt. Defaults: 5-MiB patch, 200 files, 50k changed lines, 25-MiB combined logs.
7. **Destroy.** Revoke broker capability; stop/kill the cgroup; remove container, job/fetch volumes, socket, tmpfs, and scratch. Cleanup failure quarantines the job, makes readiness false, and pages/sweeps; results are copied out before deletion but are not `SUCCEEDED` until deletion is confirmed.
8. **Apply/PR.** Daemon parses the artifact, repeats every path/mode/size/hash check, creates a new clean worktree at the exact base SHA, runs `git apply --check --index` without `--unsafe-paths`, applies, and compares the resulting tree to the manifest. Git rejects outside-worktree patches by default and supports check-only/index validation [S16]. Only then may the daemon's GitHub effector use vault credentials to commit/push/open a PR. No job calls GitHub.

Default per-job limits: 1 CPU, 2 GiB memory with no added swap, 256 pids, 8 GiB/200k-inode workspace, 30-minute wall clock (60-minute host-policy ceiling), 512 MiB tmpfs, 32 model turns. All are server-clamped; profiles may lower, never raise, them beyond host policy.

`repo_read` gets a read-only repo and read/list actions; `repo_exec` gets a disposable writable overlay and exec but must return an empty patch; `coding` gets write/exec and the patch contract. All three use the same runner and destruction path.

## Interfaces

Control transport is local HTTP/JSON over UDS on Linux and the tray-owned SSH forward on Windows. Errors are `{error:{code,message,retryable,details}}`; unknown fields and oversized bodies fail closed.

```text
GET    /v1/capabilities
POST   /v1/blobs                         # content-addressed, bounded source upload
POST   /v1/jobs                          # fixed JobSpec; returns 202 + job_id
GET    /v1/jobs/{id}                     # state/progress, owner-scoped
GET    /v1/jobs/{id}/model-requests?wait=30
POST   /v1/jobs/{id}/model-responses     # daemon broker only; ordered turn id
GET    /v1/jobs/{id}/result              # RunnerResultV1 after cleanup confirmed
DELETE /v1/jobs/{id}                     # idempotent cancel -> destroy
```

`JobSpecV1 = {schema_version,idempotency_key,owner_scope,capability,source:{blob_sha256,base_commit,manifest_sha256},prompt_sha256,prompt,test_plan,provider_route,limits}`. `provider_route` names an already-authorized daemon route; it carries no secret. The service derives image, mounts, env, and policy.

```json
{"schema_version":"runner-result/v1","job_id":"uuid","status":"SUCCEEDED",
 "request_sha256":"…","runner":{"version":"…","backend":"podman-rootless","policy_sha256":"…","image_digest":"sha256:…"},
 "source":{"base_commit":"40hex","bundle_sha256":"…","baseline_tree":"40hex"},
 "patch":{"blob_sha256":"…","bytes":0,"files":0,"added_lines":0,"deleted_lines":0},
 "changes":[{"path":"relative/utf8","op":"ADD|MODIFY|DELETE","mode_before":"100644|null","mode_after":"100644|null","before_sha256":"…|null","after_sha256":"…|null","bytes":0}],
 "tests":[{"command_id":"…","argv":["…"],"cwd":".","started_at":"RFC3339","duration_ms":0,"exit_code":0,"signal":null,"timed_out":false,"stdout_sha256":"…","stderr_sha256":"…","truncated":false}],
 "logs":{"blob_sha256":"…","bytes":0,"truncated":false},"resources":{"cpu_ms":0,"peak_memory_bytes":0,"pids_peak":0,"workspace_bytes":0},
 "broker":{"provider_route":"…","turns":0,"input_tokens":0,"output_tokens":0,"budget_exhausted":false},
 "sandbox":{"network":"none","uid":65532,"rootfs_read_only":true,"caps":[],"no_new_privileges":true,"cleanup":"CONFIRMED"},
 "started_at":"RFC3339","finished_at":"RFC3339","artifact_sha256":"…"}
```

## Capability and attestation contract

`GET /v1/capabilities` returns `{protocol_version,runner_version,backend,host_id,profiles,limits,image_digest,policy_sha256,cgroup_v2,storage_quota,self_test:{suite_sha256,passed_at,expires_at},broker_routes,ready,failures}`. On startup and every 10 minutes, runner creates a real disposable probe job using the production image/options and checks path invisibility, network denial, runtime-socket absence, cgroup limits, quota ENOSPC, artifact extraction, and cleanup. `ready=true` requires a passing probe younger than 15 minutes; the job-create path rechecks hard prerequisites atomically.

Replace S3's hard false with `coding_nodes_runnable(profile, provider_route)`: connect with a 2-second deadline; require compatible protocol, expected policy/image digests, matching profile, fresh self-test, cgroup v2, hard storage quota, broker route, and `ready=true`. Cache only failures/answers for 30 seconds; `POST /jobs` remains authoritative. Socket missing, malformed/old response, mismatch, timeout, or self-test failure returns false and preserves enqueue/runtime refusal. `branch_sandbox_status` validates every repo node's profile/provider, not merely “some runner exists.”

`TINYASSETS_OS_SANDBOX_ATTESTED` is never read from operator/compose state to establish readiness and is never set on daemon/workers. Sole exception: the runner may create a stopped child with this reserved env, inspect that the exact image/options/mounts/namespaces match policy, then start it; this is only for compatibility with an in-job provider adapter, and clients cannot supply/override reserved env names. It means “this process is already inside this job sandbox,” not “the deployment has a runner.” Normally the brokered driver needs no such variable. There is no cryptographic attestation claim: local UDS/SSH identity, versioned capability response, self-test, and per-job enforcement receipt are operational evidence, not remote attestation.

## Acceptance canaries

Run on Linux prod-shaped CI, a staging droplet, and Windows 11/WSL2; then one rendered chatbot patch-loop conversation. Four concurrent jobs must leave MCP health green and remain mutually invisible.

1. Read host canary, `/data`, daemon source/auth homes, other job IDs, `/proc/1/root`, and Windows drives: secret never appears in output/log/patch.
2. Traverse/write outside `/workspace`, create symlink/gitlink/device/case-collision, alter rootfs: denied or artifact rejected.
3. DNS/TCP/UDP to internet, metadata `169.254.169.254`, host gateway, localhost services: fail; only job model UDS succeeds within budget.
4. Find/contact Docker/Podman/containerd sockets or Windows named pipes: absent/unconnectable.
5. Fork bomb, memory/CPU burn, disk/inode fill, log flood, sleep past deadline: only job is throttled/killed/ENOSPC/truncated; daemon stays healthy; cleanup confirms.
6. Smuggle absolute/`..`/`.git`/symlink/submodule/oversize/bad-hash patch: runner and daemon independently reject; no worktree/PR mutation.
7. Complete a real fixture bug: clean source bundle -> model edit -> tests -> bounded artifact -> destroy -> fresh daemon worktree apply -> second sandbox verify -> canary-repo PR; hashes/receipts link every step.
8. Stop runner, age self-test, change policy/image digest, or corrupt cleanup: `coding_nodes_runnable=false`, validate/enqueue/runtime fail closed, no provider spawn.

## What not to build; graduation

Do not build custom syscall/seccomp policy, a generic egress proxy, cryptographic attestation framework, DinD/Kubernetes scheduler, microVM orchestrator, provider-token minting, or arbitrary runtime API. Use runtime defaults plus explicit container flags, a narrow registry-prefetch adapter, and the local capability/self-test contract.

Rootless containers share the host kernel; this is acceptable for owner-authorized repos on an owner/platform-bound capacity host, not anonymous hostile multi-tenancy. Graduate without changing `JobSpecV1`/`RunnerResultV1`: first to gVisor `runsc` when kernel attack-surface reduction is needed (OCI-compatible, reimplements/intercepts the system-call surface) [S17][S18]; then Firecracker or a hosted sandbox when mutually hostile tenants/regulatory isolation justify per-job microVM operations [S19]. Graduation triggers: public anonymous execution, cross-customer secrets on one host, a container escape, or inability to meet isolation canaries with rootless OCI.

## Open risks and implementation handoff

- Provider disclosure is intentional: repo snippets/tests go only to the user-selected brokered model. Local-only routes are required for repos that may not leave the host.
- Dependency prefetch remains the likeliest exfil/supply-chain edge; start with locked, reviewed adapters and refuse arbitrary URLs/scripts.
- Debian 12's packaged Podman is older than current upstream [S20]. CI must run the exact production package and current Windows package; capability tests, not a version string alone, decide readiness.
- A compromised daemon can request many bounded jobs but cannot select host mounts/network/runtime options; enforce owner quotas/rate limits and audit every request.
- Implementation branch/worktree: `feat/sandbox-runner` / `../wf-sandbox-runner`, based on S3. First slice is runner API + rootless self-test + hard-false probe integration; then lifecycle/artifact, broker loop, prod provision, Windows installer, canaries. Draft PR stays blocked on `docs/audits/2026-07-16-per-job-sandbox-runner-claude-review.md` verdict `approve|adapt`.

## Sources (all accessed 2026-07-16)

- [S1] Docker Engine security, daemon attack surface: https://docs.docker.com/engine/security/
- [S2] Docker daemon socket protection/root-equivalent keys: https://docs.docker.com/engine/security/protect-access/
- [S3] Podman rootless tutorial/subuid model: https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md
- [S4] Podman system service security/full API authority: https://docs.podman.io/en/latest/markdown/podman-system-service.1.html
- [S5] Podman run isolation/resource options: https://docs.podman.io/en/latest/markdown/podman-run.1.html
- [S6] Podman XFS project-quota volumes: https://docs.podman.io/en/latest/markdown/podman-volume-create.1.html
- [S7] Podman Windows installation/WSL2 machine: https://podman.io/docs/installation
- [S8] Podman machine init/rootless/resources/Windows mounts: https://docs.podman.io/en/stable/markdown/podman-machine-init.1.html
- [S9] Microsoft WSL install/restart requirement: https://learn.microsoft.com/en-us/windows/wsl/install
- [S10] Podman digest pull and `--pull=never`: https://docs.podman.io/en/stable/markdown/podman-pull.1.html
- [S11] Claude Code CLI tool restriction: https://docs.anthropic.com/en/docs/claude-code/cli-usage
- [S12] Claude Code gateway authentication/budgets/base URL: https://docs.anthropic.com/en/docs/claude-code/llm-gateway
- [S13] Docker rootless DinD still requires privileged mode: https://docs.docker.com/engine/security/rootless/tips/
- [S14] DigitalOcean XFS block-volume support: https://docs.digitalocean.com/products/volumes/how-to/create/
- [S15] Bubblewrap user namespaces and policy responsibility: https://github.com/containers/bubblewrap/blob/main/README.md
- [S16] Git apply check/index/path safety: https://git-scm.com/docs/git-apply
- [S17] gVisor security model: https://gvisor.dev/docs/architecture_guide/security/
- [S18] gVisor OCI runtime: https://gvisor.dev/docs/
- [S19] Firecracker secure multi-tenant microVM scope: https://github.com/firecracker-microvm/firecracker
- [S20] Debian 12 Podman package/version: https://packages.debian.org/bookworm/podman
