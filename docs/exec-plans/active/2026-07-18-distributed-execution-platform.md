# TinyAssets Distributed Patch-Loop Execution Platform

**Status:** Design specification / pre-implementation execution plan
**Review gate:** Fable-5 opposite-family review, then lead approval
**Target sequence:** B2 BYO daemon live test first; B3 market selection second
**Normative language:** “MUST”, “MUST NOT”, “SHOULD”, and “MAY” are requirements terms.

## 1. Objective

TinyAssets will provide a distributed patch-loop execution system with three hard boundaries:

1. **Platform control plane:** routing, authoritative universe/job/lease/result state, review surfaces, authentication, matching, and settlement.
2. **Immutable execution capsule:** signed, content-addressed instructions binding one job attempt to one daemon, universe scope, exact source, policy, resources, and lease fence.
3. **Host-local isolated execution:** a BYO or market daemon stages source, launches a disposable isolated child, brokers model access, extracts and revalidates results, and destroys the workspace.

The platform MUST NOT execute coding jobs or provide shared fallback compute. Every executable job runs on either:

- an owner-authorized BYO daemon, or
- a rented/donated resource-market host selected by B3.

The founder follows the same registration, claim, lease, execution, and result protocol as every other user. Users bring their own chatbot and, unless explicitly included in a market offer, their own model route.

B2 and B3 are validation slices of one end-state architecture, not competing architectures:

```text
Chatbot → TinyAssets control plane → selector → B2 claim/lease/result protocol
                                            ├─ owner BYO daemon
                                            └─ B3 market daemon
```

If no eligible daemon exists, the job remains pending. There is no platform-worker fallback.

## 2. Scope and non-goals

### 2.1 In scope

- Immutable execution capsules.
- Rootless, per-job isolated execution on Linux and Windows.
- Separate `repo` and `source_exec` executor classes.
- BYO device enrollment, authentication, revocation, polling, claims, leases, heartbeats, uploads, and completion.
- Server-side wrapping of the existing filesystem task queue for the B2 MVP.
- Market selection, verification, settlement, and reputation over the same B2 protocol.
- Public-repository B2 live test.
- Secure private-repository delivery design.
- Separate patch acceptance, review, GitHub, and merge effects.

### 2.2 Explicit non-goals for the first B2 live test

- PostgreSQL migration.
- Native Windows-process sandboxing.
- Automatic merge.
- Private-source execution on an untrusted market host.
- Hardware-backed confidential computing.
- General outbound internet access from a job.
- Treating a sandbox result as authority to push, open, approve, or merge a PR.
- Sending source archives, patches, or logs inside the current 4 MB graph request envelope.

## 3. Existing seams and required changes

### 3.1 Reusable seams

| Existing seam | Current behavior | Required use |
|---|---|---|
| `IsolatedExecutor` | Typed class, capability, schema, health, and serializable dispatch boundary | Implement host-local `repo` and `source_exec` executors behind this interface. `tinyassets/sandbox_policy.py:373-408` |
| Executor resolution | `resolve_isolated_executor()` returns no production executor and fails closed | Resolve only on an enrolled daemon whose backend and route pass current health and policy checks. `tinyassets/sandbox_policy.py:449-462` |
| Dispatch choke point | Graph nodes become a serializable request and pass through one dispatch boundary | Preserve this boundary; the execution capsule binds the request hash rather than a Python callable. `tinyassets/graph_compiler.py:2729-2750`, `tinyassets/graph_compiler.py:3039-3064`, `tinyassets/graph_compiler.py:3177-3222` |
| Strict request validation | Request schemas reject unexpected fields and raw `base_path`; workspace access is opaque | Keep strict validation and replace local workspace grants with stable universe capabilities. `tinyassets/graph_compiler.py:2814-2895` |
| Typed response envelope | `ok`, `error`, and `cancelled` responses are validated | Extend into the signed distributed result contract. `tinyassets/graph_compiler.py:2898-2980` |
| Repo/source separation | Separate readiness paths exist for `repo` and `source_exec` | Preserve separate executor types, images, policy hashes, and result types. `tinyassets/sandbox_policy.py:300-303`, `tinyassets/sandbox_policy.py:656-697` |
| OS sandbox gate | Environment attestation is required for isolated execution | Set it only inside the isolated child, never in the daemon or compose environment. `tinyassets/providers/base.py:778-816` |
| Per-route sandbox gate | `_sandbox_execution_attested()` currently returns `False` | Replace the global boolean with a typed daemon/universe/route capability decision. `tinyassets/engine_binding.py:174-202` |
| Filesystem queue | File-locked pending/running task transitions with a 1,800-second node heartbeat | Wrap server-side and add lease IDs, monotonic fencing, independent heartbeat, result references, and idempotency. `tinyassets/branch_tasks.py:1-17`, `tinyassets/branch_tasks.py:35-44`, `tinyassets/branch_tasks.py:472-581` |
| Declare-only engines | Self-hosted, market, and host-daemon choices are advertised but not executable | Convert them into externally dispatchable choices; never attach a platform-local executor. `tinyassets/api/universe.py:5253-5370` |
| Reference executor | Test simulator validates typed requests and models worker dispatch | Retain as a contract oracle, but remove production-equivalent legacy ambient fallback and path-bearing grants. `tests/_executor_sim.py:1-26`, `tests/_executor_sim.py:62-98`, `tests/_executor_sim.py:111-205` |

### 3.2 Mandatory legacy correction

`LEGACY_UNBOUND` currently permits ambient behavior in several paths:

- `ExecutionScope` describes legacy ambient execution as acceptable. `tinyassets/sandbox_policy.py:320-352`
- The graph compiler allows a legacy request without a scoped grant. `tinyassets/graph_compiler.py:3271-3334`
- Run construction maps missing universe identity to `LEGACY_UNBOUND`. `tinyassets/runs.py:2258-2275`, `tinyassets/runs.py:2339-2359`
- The reference executor falls back to a global provider when no scoped grant exists. `tests/_executor_sim.py:166-205`

After this design lands:

> `LEGACY_UNBOUND` MUST be permanently ineligible for both `repo` and `source_exec`.

Legacy compatibility may continue only for explicitly classified non-executing/text-only operations.

## 4. Authoritative state and locality

| State | Authority | Persistence |
|---|---|---|
| User, universe, branch, node, and version metadata | Platform API | Durable |
| Job state and immutable capsule hash | Platform API | Durable |
| Lease ID, fence, expiry, and current owner daemon | Platform API | Durable |
| Submitted and accepted result references | Platform API | Durable |
| Review, approval, effect, and settlement state | Platform API | Durable |
| Stable universe capability | Platform API | Durable; never a filesystem path |
| Daemon source cache | Daemon | Reconstructable |
| Resolved local repository path | Daemon only | MUST NOT enter a capsule, protocol request, result, or log |
| Staging directory and isolated workspace | Daemon | Disposable per job |
| Container/namespace/cgroup identifiers | Daemon | Disposable operational state |
| Model-broker session | Daemon or owner-controlled broker | Job scoped and revocable |
| Upload spool | Daemon | Reconstructable until acknowledged |

A stable universe capability identifies authorization scope. It does not reveal or resolve a `universe_dir`.

For a BYO private repository, the daemon maps the capability to its own local source outside the child. For a market host, the owner-side source courier produces an encrypted, credential-free source bundle.

`PLAN.md` currently says private work content is not stored by the platform, even encrypted, except for the credential vault. `PLAN.md:57`. Therefore:

- Public source and artifacts MAY use platform CAS.
- Private source and result bytes MUST initially use owner-controlled CAS or direct encrypted transfer.
- The platform stores opaque references, hashes, sizes, encryption metadata, and acceptance state.
- Adding platform-hosted ciphertext relay for private work requires an explicit PLAN amendment.

## 5. Execution capsule contract

### 5.1 Encoding and integrity

The capsule uses canonical JSON under RFC 8785/JCS.

- `capsule_sha256` is the lowercase SHA-256 hex digest of canonical `payload`.
- Signature input is:

```text
UTF8("tinyassets.execution-capsule.v1\0") || SHA256(canonical_payload)
```

- The platform signs with Ed25519.
- The daemon MUST verify the signature, key status, audience, timestamps, capsule hash, and lease before staging source.
- Reclaiming or extending work under a new fence creates a new capsule. Capsules are never edited in place.
- JSON integers MUST be non-negative and no greater than `2^53 - 1`.

### 5.2 `ExecutionCapsuleV1`

```typescript
type Sha256 = string;       // ^[0-9a-f]{64}$
type UUID = string;         // canonical RFC 4122
type Timestamp = string;    // RFC 3339 UTC with Z
type BlobRef = string;      // opaque registered CAS reference; never a path

interface ExecutionCapsuleV1 {
  payload: {
    schema_version: "execution-capsule/v1";

    capsule_id: UUID;
    job_id: UUID;
    attempt: number;
    audience_daemon_id: string;

    owner_user_id: string;

    universe_scope: {
      universe_id: string;
      capability_id: string;
      scope_version: number;
      permissions: Array<
        | "read_source"
        | "execute_repo"
        | "execute_source"
        | "produce_patch"
        | "produce_artifact"
      >;
    };

    branch: {
      branch_definition_id: string;
      branch_version_sha256: Sha256;
    };

    node: {
      node_id: string;
      node_version_sha256: Sha256;
      node_kind: string;
    };

    base: {
      vcs: "git";
      object_format: "sha1" | "sha256";
      commit: string;
      tree: string;
    };

    source_blob: {
      ref: BlobRef;
      media_type: "application/vnd.tinyassets.git-bundle.v1";
      content_sha256: Sha256;       // credential-free plaintext bundle
      transport_sha256: Sha256;     // ciphertext when encrypted
      size_bytes: number;
      manifest_sha256: Sha256;
      confidentiality: "public" | "owner_private" | "host_visible_private";

      encryption: null | {
        scheme: "x25519-chacha20poly1305-v1";
        recipient_device_key_id: string;
        wrapped_content_key_b64: string;
      };

      producer: {
        daemon_id: string;
        device_key_id: string;
        signature_b64: string;
      };
    };

    execution_request: {
      schema_version: number;
      ref: BlobRef | null;
      inline: object | null;
      sha256: Sha256;
      size_bytes: number;
    };

    allowed_capability: {
      class: "repo" | "source_exec";
      repo_mode: null | "repo_read" | "repo_exec" | "coding";
      action_policy_id: string;
      action_policy_sha256: Sha256;
      runner_policy_sha256: Sha256;
      image_digest: string;         // immutable OCI digest
    };

    model_broker_route: {
      route_id: string;
      route_version: number;
      policy_sha256: Sha256;
      grant_ref: string;            // opaque exchange handle, not a secret
      allowed_model_classes: string[];
      max_calls: number;
      max_input_tokens: number;
      max_output_tokens: number;
      expires_at: Timestamp;
    };

    resource_limits: {
      cpu_millis: number;
      memory_bytes: number;
      pids: number;
      workspace_bytes: number;
      workspace_inodes: number;
      tmpfs_bytes: number;
      wall_time_seconds: number;
      stdout_bytes: number;
      stderr_bytes: number;
      patch_bytes: number;
      patch_files: number;
      patch_changed_lines: number;
      network: "none" | "model_broker_only";
      egress_policy_id: string;
      egress_policy_sha256: Sha256;
    };

    lease: {
      lease_id: UUID;
      fence: number;
      issued_at: Timestamp;
      expires_at: Timestamp;
    };

    issued_at: Timestamp;
    not_before: Timestamp;
    expires_at: Timestamp;
  };

  integrity: {
    canonicalization: "RFC8785-JCS";
    hash_algorithm: "sha256";
    capsule_sha256: Sha256;
    signature_algorithm: "ed25519";
    signing_key_id: string;
    signature_b64: string;
  };
}
```

Exactly one of `execution_request.ref` and `execution_request.inline` MUST be non-null.

Inline requests remain subject to the existing 4,000,000-byte envelope limit. `tinyassets/graph_compiler.py:2734-2740`, `tinyassets/graph_compiler.py:2790-2805`. Source bundles, patches, logs, and generated artifacts MUST use content-addressed blob transport.

### 5.3 Initial policy defaults

The control plane MAY reduce limits per job but MUST NOT exceed the registered daemon policy:

| Limit | Initial maximum |
|---|---:|
| CPU | 1,000 millicores |
| Memory | 2 GiB |
| Processes | 256 |
| Workspace | 8 GiB |
| Workspace inodes | 200,000 |
| Temporary memory filesystem | 512 MiB |
| Wall time | 30 minutes |
| Standard output | 25 MiB |
| Standard error | 25 MiB |
| Patch | 5 MiB |
| Changed files | 200 |
| Changed lines | 50,000 |
| Model calls | 32 |

## 6. Layer A: host-local isolated executor

### 6.1 Process boundary

```text
daemon
  ├─ verifies capsule/auth/lease
  ├─ resolves universe capability locally
  ├─ stages credential-free source
  ├─ starts job-scoped model broker
  └─ narrow launcher
       └─ fixed-policy isolated child
            ├─ exact source workspace
            ├─ fixed driver
            ├─ no host credentials
            ├─ model-broker socket only
            └─ typed result spool
```

The launcher API is intentionally closed:

```typescript
interface JobLauncher {
  launch(input: {
    capsule_path: string;
    staged_source_path: string;
    result_spool_path: string;
    broker_socket_path: string;
  }): Promise<LauncherReceipt>;
}
```

The caller MUST NOT supply:

- an image name;
- arbitrary mounts;
- arbitrary environment variables;
- network mode;
- namespace or privilege flags;
- device mappings;
- seccomp/AppArmor configuration;
- container command or entrypoint.

Those are derived from the signed capsule and a locally installed fixed policy.

### 6.2 Source staging

Source staging happens outside the child:

1. Verify source producer signature and capsule binding.
2. Fetch or locate the credential-free source bundle.
3. Verify transport and plaintext hashes.
4. Reject absolute paths, `..`, devices, FIFOs, sockets, unsafe symlinks, unsupported file modes, and archive expansion beyond declared limits.
5. Materialize an exact-base repository without remotes, credential helpers, hooks, or inherited Git configuration.
6. Verify `base.commit` and `base.tree`.
7. Make the initial source tree read-only to the child; provide a disposable writable worktree or overlay.

GitHub, provider, vault, MCP, SSH-agent, and host environment credentials MUST NOT enter the staged bundle or child environment.

### 6.3 Model broker

The child receives a job-scoped local broker endpoint, preferably an inherited Unix-domain socket. It never receives a provider API key.

The broker MUST enforce:

- `job_id`, `capsule_id`, `lease_id`, and fence binding;
- allowed model class;
- call and token budgets;
- request and response size;
- lease validity;
- cancellation;
- audit hashes;
- revocation when the lease expires or is superseded.

The broker may use:

- owner credentials held outside the child on a BYO daemon;
- an owner-controlled remote broker using mutually authenticated transport; or
- model capacity explicitly included in a selected market offer.

It MUST NOT expose raw provider credentials to either the job child or an untrusted market daemon.

### 6.4 Closed action surface

The child has only:

- its isolated filesystem;
- the fixed job driver;
- process execution inside the sandbox;
- the job-scoped model broker;
- a write-only typed result spool.

It has no daemon RPC, Docker/Podman socket, host filesystem API, arbitrary local-tool bridge, browser session, vault API, GitHub API, or host network access.

Dependency acquisition is not ambient egress. A future dependency-fetch phase MUST use a separate fixed-policy fetcher with allowlisted registries, lockfile enforcement, immutable hashes, and lifecycle scripts disabled.

### 6.5 Repo and source-exec handles

| Executor | Input visibility | Writable area | Valid success result |
|---|---|---|---|
| `repo/repo_read` | Repository | Temporary output only | Typed observations; no patch |
| `repo/repo_exec` | Repository | Disposable worktree | Test/build receipt; patch MUST be empty |
| `repo/coding` | Repository | Disposable worktree | Typed patch candidate |
| `source_exec` | Explicit source payload only | Disposable workspace | Typed source output/artifact; never a repo patch |

`source_exec` MUST use a distinct executor registration, policy hash, image digest, readiness check, and result validator. A healthy repo executor does not imply source-execution readiness.

### 6.6 Sandbox gates

#### `resolve_isolated_executor`

On the daemon, resolution succeeds only if:

- the capsule class matches the executor class;
- request and result schema versions are supported;
- the capsule’s image and policy hashes are installed;
- current backend canaries pass;
- the daemon has capacity;
- the universe capability and route are eligible;
- the model broker is available;
- the lease remains current.

Otherwise it returns no executor and dispatch fails closed.

#### `os_sandbox_attested`

`TINYASSETS_OS_SANDBOX_ATTESTED=1` is set by the narrow launcher **inside the isolated child only**.

Its meaning is:

> This process is the isolated job process created under the verified fixed policy.

It MUST NOT be set:

- in platform compose;
- in the daemon service environment;
- in a login shell;
- in a parent worker;
- as a global host readiness shortcut.

#### `_sandbox_execution_attested`

Replace the current hardcoded/global gate with:

```typescript
sandbox_execution_attested({
  daemon_id,
  universe_capability_id,
  allowed_capability_class,
  model_broker_route_id,
  request_schema_version,
  runner_policy_sha256,
  image_digest
}) -> {
  eligible: boolean,
  reason_code: string,
  checked_at: Timestamp,
  expires_at: Timestamp
}
```

This is a per-daemon, per-universe, per-route capability decision. It MUST NOT depend on a resolved host path or a process-global environment flag.

### 6.7 OS backend matrix

| Host | Required backend | Required controls | Fallback |
|---|---|---|---|
| Linux | Bubblewrap plus user/mount/PID/IPC/UTS/network namespaces, cgroup v2, seccomp, and `no_new_privs`; or equivalently fixed rootless OCI policy | Private mount tree, no host network, bounded resources, pinned image/driver, no privilege escalation | None |
| Windows | WSL2 Linux VM plus rootless Podman/OCI child | No Windows or broad NTFS host mounts, fixed VM/container policy, resource limits, model-broker-only channel | None |
| macOS/other | Unsupported for initial launch | Future VM-backed rootless OCI backend requires a separate reviewed policy | Fail closed |

Bubblewrap supplies isolation primitives but explicitly leaves security policy to its command-line construction, which is why callers cannot choose launcher arguments. [Bubblewrap README](https://github.com/containers/bubblewrap/blob/main/README.md)

Podman’s `seccomp=unconfined` disables seccomp confinement and is prohibited. `no-new-privileges` and a fixed seccomp profile are required. [Podman run documentation](https://docs.podman.io/en/latest/markdown/podman-run.1.html)

On Windows, Podman runs through a Linux virtual machine, and WSL2 supplies the Linux kernel environment. [Podman machine documentation](https://docs.podman.io/en/stable/markdown/podman-machine-init.1.html), [Microsoft WSL documentation](https://learn.microsoft.com/en-us/windows/wsl/about)

Failure to install or attest WSL2/Podman makes the daemon ineligible. There is no native-process compatibility mode.

### 6.8 Result extraction and revalidation

After child exit, the daemon:

1. Stops broker access.
2. Parses a bounded typed result spool.
3. Rejects symlinks, devices, absolute paths, traversal, unsupported modes, oversized output, and undeclared result types.
4. Reconstructs a new credential-free checkout from the exact source bundle and exact base commit.
5. Applies the candidate patch outside the job child with hooks, filters, external diff tools, pagers, and credential helpers disabled.
6. Verifies path allowlists, mode changes, submodule changes, binary size limits, file count, line count, and resulting tree hash.
7. Runs any required verification in a second fresh isolated child, not in the trusted daemon process.
8. Uploads content-addressed artifacts.
9. Removes the job child, mounts, cgroup, network namespace, broker session, staging area, worktree, and transient secrets.
10. Uses backend inspection to confirm their absence.

A successful result requires `destruction.confirmed=true`. Cleanup failure yields an infrastructure failure, quarantines the local slot, and makes the backend unready until remediation.

## 7. Typed result contract

```typescript
interface ExecutionResultV1 {
  schema_version: "execution-result/v1";

  job_id: UUID;
  capsule_id: UUID;
  capsule_sha256: Sha256;
  lease_id: UUID;
  fence: number;

  outcome:
    | "succeeded"
    | "job_failed"
    | "cancelled"
    | "timed_out"
    | "policy_rejected"
    | "infrastructure_failed";

  executor: {
    daemon_id: string;
    device_key_id: string;
    capability_class: "repo" | "source_exec";
    backend: "linux-bwrap" | "linux-rootless-oci" | "windows-wsl2-podman";
    runner_policy_sha256: Sha256;
    image_digest: string;
  };

  repo_patch: null | {
    format: "git-diff-v1";
    blob_ref: BlobRef;
    blob_sha256: Sha256;
    size_bytes: number;
    base_commit: string;
    base_tree: string;
    resulting_tree: string;
    file_count: number;
    added_lines: number;
    deleted_lines: number;
  };

  source_output: null | {
    media_type: string;
    blob_ref: BlobRef;
    blob_sha256: Sha256;
    size_bytes: number;
  };

  logs: Array<{
    stream: "stdout" | "stderr" | "runner";
    blob_ref: BlobRef;
    blob_sha256: Sha256;
    size_bytes: number;
  }>;

  checks: Array<{
    check_id: string;
    outcome: "passed" | "failed" | "skipped";
    exit_code: number | null;
    duration_ms: number;
    stdout_sha256: Sha256 | null;
    stderr_sha256: Sha256 | null;
  }>;

  usage: {
    wall_time_ms: number;
    cpu_time_ms: number;
    peak_memory_bytes: number;
    model_calls: number;
    model_input_tokens: number;
    model_output_tokens: number;
  };

  revalidation: {
    exact_base_verified: boolean;
    patch_applies_cleanly: boolean;
    path_policy_passed: boolean;
    limits_passed: boolean;
    resulting_tree: string | null;
    verifier_policy_sha256: Sha256;
  };

  destruction: {
    confirmed: boolean;
    confirmed_at: Timestamp | null;
    backend_receipt_sha256: Sha256 | null;
  };

  completed_at: Timestamp;

  signature: {
    algorithm: "ed25519";
    device_key_id: string;
    result_sha256: Sha256;
    signature_b64: string;
  };
}
```

Rules:

- `repo/coding` may return `repo_patch`; `source_output` MUST be null.
- `repo_read` and `repo_exec` MUST return no patch.
- `source_exec` may return `source_output`; `repo_patch` MUST be null.
- A successful result with failed revalidation or unconfirmed destruction is invalid.
- A signed result is evidence of which device reported it, not proof that an untrusted host executed honestly.

## 8. Layer B2: daemon-to-platform protocol

### 8.1 Device enrollment and authentication

Each daemon creates:

- Ed25519 request/result signing key;
- X25519 source-transfer key;
- random installation nonce.

Private keys live in the OS key store and are non-exportable where supported.

Enrollment flow:

1. `POST /v1/daemon-enrollments`
2. Platform returns a short user verification code and enrollment ID.
3. User authenticates through their normal chatbot/browser control-plane session and approves the device.
4. `POST /v1/daemon-enrollments/{id}:complete`
5. Platform binds the public keys to `owner_user_id`, creates `daemon_id`, and records a credential epoch.
6. Daemon exchanges a signed challenge for a short-lived access token.

The existing host-pool client sends a Supabase service-role credential from each daemon. That MUST be removed before B2. `tinyassets/host_pool/client.py:130-167`

Access-token requirements:

- maximum lifetime: five minutes;
- bound to `daemon_id`, device key thumbprint, and credential epoch;
- every request signed over method, path, body hash, timestamp, and nonce;
- replay nonce retained at least for the token lifetime;
- maximum accepted clock skew: 60 seconds;
- owner revocation increments the device credential epoch and immediately blocks new operations.

### 8.2 Standard error contract

```typescript
interface ApiError {
  error: {
    code: string;
    message: string;
    retryable: boolean;
    request_id: string;
    details: object;
  };
}
```

Required status semantics:

| HTTP | Meaning |
|---|---|
| `400` | Malformed request |
| `401` | Invalid or expired authentication |
| `403` | Authenticated device lacks authorization |
| `404` | Unknown or undisclosed resource |
| `409` | Idempotency conflict, stale fence, or failed CAS |
| `410` | Revoked or permanently expired resource |
| `422` | Schema-valid but policy-invalid content |
| `429` | Rate/capacity limit |
| `503` | No safe backend or temporary control-plane failure |

### 8.3 Eligibility polling

```http
POST /v1/execution/jobs:poll
Idempotency-Key: <uuid>
Prefer: wait=30
```

```typescript
interface PollRequest {
  daemon_id: string;
  request_id: UUID;
  narrow_to?: {
    capability_classes?: Array<"repo" | "source_exec">;
    max_jobs?: number;
  };
}

interface JobOffer {
  offer_id: UUID;
  job_id: UUID;
  offer_version: number;
  capability_class: "repo" | "source_exec";
  resource_summary: object;
  confidentiality: "public" | "owner_private" | "host_visible_private";
  claim_deadline: Timestamp;
}
```

Registered capabilities are authoritative. A polling daemon may narrow them but may not expand them.

Polling is outbound from the daemon and waits at most 30 seconds. Offers do not contain source or a capsule.

### 8.4 Atomic claim

```http
POST /v1/execution/jobs/{job_id}:claim
Idempotency-Key: <uuid>
```

```typescript
interface ClaimRequest {
  daemon_id: string;
  offer_id: UUID;
  offer_version: number;
  runner_policy_sha256: Sha256;
  image_digest: string;
}

interface ClaimResponse {
  lease_id: UUID;
  fence: number;
  expires_at: Timestamp;
  heartbeat_interval_seconds: 30;
  capsule: ExecutionCapsuleV1;
  capsule_sha256: Sha256;
}
```

The server performs one atomic transition:

```text
pending → leased
```

Within the same lock/transaction it:

1. verifies offer and daemon eligibility;
2. increments the job’s monotonic fence;
3. creates a random lease ID;
4. sets an initial 120-second expiry;
5. creates and signs the audience-bound capsule;
6. persists the capsule hash and idempotency response.

Only one claim may win.

### 8.5 Independent lease heartbeat

```http
POST /v1/execution/leases/{lease_id}:heartbeat
Idempotency-Key: <uuid>
```

```typescript
interface LeaseHeartbeat {
  job_id: UUID;
  daemon_id: string;
  lease_id: UUID;
  fence: number;
  capsule_sha256: Sha256;
  sequence: number;
  local_phase:
    | "claimed"
    | "staging"
    | "running"
    | "extracting"
    | "revalidating"
    | "uploading"
    | "destroying";
}
```

The heartbeat runs in an independent daemon task. It MUST NOT depend on graph-node progress or model activity.

- Interval: 30 seconds.
- Lease duration after successful renewal: 120 seconds.
- `sequence` is strictly increasing per lease.
- Renewal is accepted only for the current lease ID, fence, daemon, and capsule.
- A stale heartbeat returns `409 stale_lease`.
- If safe renewal cannot be confirmed, the daemon cancels the child, destroys the workspace, and does not submit success.

This replaces the current 1,800-second node-driven heartbeat for distributed execution. `tinyassets/branch_tasks.py:35-44`

### 8.6 Content-addressed blob upload

```http
POST /v1/execution/blobs:init
PUT  <returned-upload-target>
POST /v1/execution/blobs/{sha256}:commit
```

Initialization declares:

```typescript
interface BlobDeclaration {
  sha256: Sha256;
  size_bytes: number;
  media_type: string;
  confidentiality: "public" | "owner_private" | "host_visible_private";
  job_id: UUID;
  lease_id: UUID;
  fence: number;
}
```

The commit operation verifies the stored hash and size before the blob becomes referenceable.

For owner-controlled storage, `blobs:init` instead validates and records an opaque owner-CAS reference and proof of possession. The platform does not fetch private plaintext merely to validate a result.

### 8.7 Result submission and completion CAS

Result upload and job completion are separate:

```http
PUT /v1/execution/jobs/{job_id}/candidate-result
POST /v1/execution/jobs/{job_id}:complete
```

The candidate-result request contains `ExecutionResultV1`. It is accepted for storage only after signature, schema, hash, job, capsule, lease, and fence validation.

Completion request:

```typescript
interface CompleteJobRequest {
  job_id: UUID;
  daemon_id: string;
  lease_id: UUID;
  fence: number;
  capsule_sha256: Sha256;
  result_sha256: Sha256;
}
```

Completion performs a CAS:

```text
leased(current lease/fence/capsule)
    → succeeded | failed | cancelled
```

It accepts only the current, unexpired lease and fence. A stale, expired, cancelled, or superseded result returns `409 stale_lease` and causes no effect or settlement.

Lease expiry moves an unfinished job back to `pending`; its fence value is retained, and the next claim increments it.

### 8.8 Idempotency

Every mutating operation requires `Idempotency-Key`.

Server rules:

1. Scope the key to authenticated device, operation, and target resource.
2. Store the canonical request hash and complete response.
3. Same key and same body returns the original response.
4. Same key and different body returns `409 idempotency_conflict`.
5. Blob commits are additionally idempotent by content hash.
6. Heartbeat sequence numbers are monotonic.
7. Completion receipts remain durable after job finalization.

### 8.9 MVP filesystem storage

The existing `branch_tasks.py` queue remains an internal server implementation for the first B2 live test.

Required additions to each durable task record:

```typescript
interface DistributedLeaseFields {
  lease_id: UUID | null;
  lease_fence: number;
  lease_expires_at: Timestamp | null;
  lease_daemon_id: string | null;
  capsule_sha256: Sha256 | null;
  candidate_result_sha256: Sha256 | null;
  accepted_result_sha256: Sha256 | null;
}
```

Additional server-side records persist:

- idempotency keys and response bodies;
- capsule payload/hash/signature;
- blob metadata;
- device revocation epochs;
- completion receipts.

The daemon sees only API objects. It MUST never receive the queue path, universe path, lock path, or sidecar filename.

The filesystem MVP supports one authoritative API writer deployment. File locks are not represented as cross-machine distributed locks. PostgreSQL or another transactional shared store is required before multi-writer API deployment.

### 8.10 Effect separation

A sandbox result is a candidate artifact, not an authority grant.

```text
sandbox result
  → fenced completion acceptance
  → review/revalidation state
  → separately authorized effect request
  → GitHub PR/push/merge effect
```

The job child and market daemon receive no GitHub or vault credentials.

A GitHub effect MUST independently verify:

- accepted result hash;
- exact base and expected repository head;
- review/approval state;
- owner authorization;
- target repository and branch policy;
- effect idempotency key.

A hosted control-plane effect may call GitHub APIs under a narrow user grant, but it may only apply an already accepted artifact. It does not execute a coding or model job.

## 9. Layer B3: market selector over B2

### 9.1 Selector placement

B3 adds a selector before B2 eligibility polling and claim:

```text
pending job
  → selector
      ├─ owner BYO binding
      └─ market matching
  → eligible daemon set
  → unchanged B2 offer/claim/lease/result/completion protocol
```

It MUST NOT introduce a separate worker protocol.

### 9.2 Matching contract

A market offer is eligible only when it satisfies:

- capability class;
- repo mode;
- runner policy and image compatibility;
- backend and policy version;
- resource limits;
- model-broker route compatibility;
- confidentiality class;
- geographic/organizational restrictions;
- host concurrency;
- price ceiling;
- minimum reputation;
- verification tier;
- device not revoked or quarantined.

Ranking is deterministic for an identical snapshot:

```text
eligibility filter
→ verification tier
→ effective price
→ reproducibility score
→ accepted-result rate
→ recent availability
→ stable offer ID tie-break
```

The existing paid-market matcher already uses deterministic exact matching and can supply the selector pattern, although it does not currently claim execution jobs. `tinyassets/paid_market/match.py:1-21`, `tinyassets/paid_market/match.py:61-159`

### 9.3 Settlement

Funds are escrowed when a market assignment is created.

Settlement key:

```text
job_id : lease_fence : accepted_result_sha256
```

Payment occurs only when:

1. B2 completion CAS accepts the current lease and fence;
2. the result passes the required verification tier;
3. the accepted result hash is durably recorded;
4. no blocking policy or dispute state exists.

Stale, superseded, malformed, policy-rejected, or unverifiable results receive no settlement. Escrow is refunded or enters dispute according to market policy.

The existing market ledger’s pure append/apply model is a suitable base for fenced settlement. `tinyassets/paid_market/ledger.py:1-28`, `tinyassets/paid_market/ledger.py:75-105`

### 9.4 Untrusted-host verification

Self-reported sandbox attestation is not proof of honest execution. A device signature proves attribution only.

Initial B3 verification requires one of:

- owner-daemon replay from the exact capsule and source;
- independent verifier-host replay selected separately from the executor; or
- deterministic patch application plus isolated verification on a trusted owner host.

Verification compares:

- capsule and source hashes;
- resulting repository tree;
- required check outcomes;
- policy and image identities;
- bounded output hashes.

Market policy MAY randomly duplicate jobs across independent hosts. Agreement, disagreement, stale results, policy violations, and disputes feed reputation.

Hardware remote attestation may be added later, but a self-declared TEE, container, WSL, seccomp, or rootless flag never counts as proof.

### 9.5 Private-repository delivery

For a private repository:

1. Owner-side source courier fetches the exact commit using owner-held credentials.
2. It removes remotes, hooks, credentials, ignored secrets, and host-local metadata.
3. It creates and signs a credential-free source manifest and bundle.
4. It encrypts the bundle to the selected host’s registered X25519 key.
5. Ciphertext travels by owner-controlled CAS or direct transfer.
6. Capsule binds both plaintext and transport hashes plus the recipient key ID.
7. Market host decrypts only after winning the current fenced claim.
8. GitHub credentials never leave the owner/effect boundary.

Encryption in transit does not protect source from the selected host operator after decryption. Therefore:

- initial B3 SHOULD launch with public repositories;
- private jobs on an untrusted market host require explicit `host_visible_private` consent;
- confidential private jobs require BYO, an organizationally trusted host, or a future independently verified confidential-compute tier.

### 9.6 Reputation

Reputation is calculated from platform-observed events:

- accepted versus rejected fenced results;
- replay agreement;
- stale completion attempts;
- capsule or artifact mismatch;
- cleanup and availability failures;
- dispute outcomes;
- verification success;
- job cancellation behavior.

Host self-reported performance or attestation does not directly increase reputation.

### 9.7 No shared-capacity fallback

If no BYO or market host is eligible:

```text
job.status = pending
job.blocked_reason = no_eligible_external_daemon
```

The platform MUST NOT start a hidden worker, founder worker, emergency worker, serverless job, or shared cloud executor.

## 10. PLAN.md and compose reconciliation

### 10.1 Invariant text to add to PLAN.md

```markdown
### Compute ownership invariant

TinyAssets production services are control-plane only. Every executable
job lease is fulfilled by either an owner-authorized BYO daemon or a
resource-market host selected through the same daemon claim, lease,
heartbeat, and fenced-result protocol.

TinyAssets and its founder own no shared coding-worker fleet and provide
no platform-capacity fallback. The founder is an ordinary user under the
same identity, capability, daemon-registration, claim, and review rules.

When no eligible BYO or market daemon is online, jobs remain pending.
“Zero hosts online” uptime applies to authoring, browsing, collaboration,
routing, universe/job state, review, and market state; it does not imply
that executable jobs progress without external compute.

B2 and B3 are dependency-ordered validation slices of this one end-state
architecture: B2 proves the protocol with an owner daemon; B3 places
market matching in front of the unchanged protocol.
```

### 10.2 PLAN statements requiring removal or rewrite

| Location | Contradiction | Required change |
|---|---|---|
| `PLAN.md:69` | Browser users are served by “host the daemon for them,” which can imply a platform-owned daemon | Rewrite as market-rented or user/organization-managed external daemon. Browser users retain the same control-plane UX. |
| `PLAN.md:71` | “Cloud-mediated equivalents” is ambiguous about cloud execution | Define cloud mediation as control-plane routing to BYO/market hosts, not platform compute. |
| `PLAN.md:248` | Claims are described across “cloud + host executors” | Replace with claims across BYO and market daemons. |
| `PLAN.md:258` | A baseline fleet of two Codex and two Claude workers can be read as platform fleet capacity | Reclassify as an optional per-user or market-host configuration example, never platform baseline. |
| `PLAN.md:261` | Explicitly pairs cloud-side `cloud_worker` with host tray workers over one file lock | Remove. Replace with API-mediated offers, fenced leases, and external daemons. |
| `PLAN.md:449` | Says complete-system/node execution remains available with zero hosts | Qualify: control-plane state and UX remain available; executable jobs remain pending. |
| `PLAN.md:535` | Repeats full uptime with zero hosts online | Apply the same control-plane/job-progress distinction. |
| `PLAN.md:562` | DigitalOcean self-hosting bridge is ambiguous about execution | State that the deployment hosts only control-plane services. |
| `PLAN.md:539` | Rejects phased target architectures | Clarify that B2-first and B3-second are verification order, not different target architectures or a migration. |

Compatible text should be retained:

- `tinyassets/runtime/` owns scheduling and executors. `PLAN.md:197`
- One shared execution lifecycle should serve all surfaces. `PLAN.md:233`
- Execution is opt-in while authoring remains available without a daemon. `PLAN.md:256`
- The platform is a cloud control plane. `PLAN.md:553`

### 10.3 Compose statements requiring removal

The entire platform `worker` fleet block in `deploy/compose.yml:171-256` must be removed, not renamed.

Specific contradictions:

| Location | Existing behavior | Required disposition |
|---|---|---|
| `deploy/compose.yml:171-174` | Declares a cloud-side node-executor fleet for the host universe | Delete |
| `deploy/compose.yml:176-179` | Gives platform workers shared Codex and Claude authentication homes | Delete; platform services must not mount provider auth homes |
| `deploy/compose.yml:181-183` | Claims file-locked concurrency across workers | Delete; B2 uses API CAS/fencing |
| `deploy/compose.yml:184-227` | Defines the base `cloud_worker` service | Delete |
| `deploy/compose.yml:189` | Uses `seccomp=unconfined` | Delete; prohibited for any future runner |
| `deploy/compose.yml:190` | Uses `apparmor=unconfined` | Delete |
| `deploy/compose.yml:191` | Launches `tinyassets.cloud_worker` | Delete |
| `deploy/compose.yml:194-208` | Mounts platform data and provider auth into the worker | Delete |
| `deploy/compose.yml:229-256` | Defines three additional shared workers | Delete |

`tinyassets/cloud_worker.py` itself describes a platform worker that closes host-offline execution and consumes the shared filesystem queue. `tinyassets/cloud_worker.py:1-24`. It also resolves local universe paths and inherits platform process environment. `tinyassets/cloud_worker.py:125-161`, `tinyassets/cloud_worker.py:192-208`. It must be retired from production execution, with any reusable pure queue logic moved behind the B2 server-side store adapter.

## 11. Security invariants

1. **No platform compute:** only owner BYO or selected market daemons execute jobs.
2. **No founder bypass:** founder identity and daemons use normal enrollment and authorization.
3. **No ambient execution:** `LEGACY_UNBOUND` is permanently ineligible for `repo` and `source_exec`.
4. **Stable scope only:** capsules contain universe capability IDs, never resolved paths.
5. **Exact source:** every job binds source manifest, base commit, base tree, branch version, and node version.
6. **Immutable capsule:** any lease/fence change creates a new signed capsule.
7. **Audience binding:** a capsule is valid only for its claimed daemon.
8. **Fenced effects:** stale or superseded leases cannot complete, settle, push, or merge.
9. **Independent heartbeat:** lease health is independent of node/model progress.
10. **No raw credentials in the child:** provider, GitHub, vault, MCP, SSH-agent, and platform admin credentials are absent.
11. **Model broker only:** model use is job-, route-, lease-, budget-, and fence-bound.
12. **Separate executor classes:** `repo` health never authorizes `source_exec`.
13. **Child-only OS attestation:** the isolation environment flag is not a global readiness switch.
14. **Fixed launcher:** callers cannot choose mounts, images, environment, network, devices, or sandbox flags.
15. **No native fallback:** missing Linux/WSL2/Podman isolation means fail closed.
16. **No ambient egress:** launch policy is `none` or `model_broker_only`.
17. **Artifact separation:** the 4 MB request envelope is not source, patch, or log transport.
18. **Typed extraction:** unstructured host paths or arbitrary files are never accepted as results.
19. **Fresh-base revalidation:** candidate patches are reapplied against an exact clean base outside the job child.
20. **Cleanup before success:** destruction must be confirmed before successful completion.
21. **Result/effect separation:** a sandbox result does not itself authorize GitHub operations.
22. **Market attestation skepticism:** self-reported isolation is attribution, not proof.
23. **Private-host clarity:** encryption does not hide source from a host that must execute it.
24. **Server-side queue paths:** daemons never see platform filesystem layout.
25. **No hidden fallback:** absence of eligible capacity leaves the job pending.

## 12. Build slices

`[B2-LIVE]` marks prerequisites for the first live test, defined as a public TinyAssets repository job initiated through a real chatbot connector and executed on an owner-enrolled Windows daemon using WSL2/Podman.

Every slice has a dual-family gate:

- **Family A:** implementer supplies focused tests and evidence.
- **Family B:** opposite model family reviews the current diff, attacks the named invariant, and independently reruns or reproduces the required evidence.
- A slice does not merge until both verdicts are recorded.

| Slice | Files | Contract and acceptance | Dual-family attack gate |
|---|---|---|---|
| **S0 `[B2-LIVE]` Control-plane invariant** | `PLAN.md`; `deploy/compose.yml`; `tinyassets/cloud_worker.py`; relevant compose tests | Add compute invariant; remove platform worker services/auth mounts; retire production `cloud_worker` entrypoint. Control plane starts with zero execution workers. | Opposite family searches all compose/deploy/runtime entrypoints for remaining platform coding executors or provider-auth mounts. |
| **S1 `[B2-LIVE]` Capsule and scope contracts** | `tinyassets/runtime/execution_capsule.py`; `tinyassets/sandbox_policy.py`; `tinyassets/graph_compiler.py`; `tinyassets/runs.py`; capsule tests | Implement JCS/hash/signature validation; bind exact request/source/version/lease; permanently reject `LEGACY_UNBOUND` for sandbox classes; no path fields. | Mutate every signed field, inject paths/unknown keys, replay to a second daemon, and verify fail-closed behavior. |
| **S2 `[B2-LIVE]` Fenced filesystem store** | `tinyassets/branch_tasks.py`; `tinyassets/runtime/lease_store.py`; store tests; concurrency tests | Add lease ID, monotonic fence, expiry, capsule/result refs, and CAS. Exactly one of concurrent claimers wins. | Crash/reclaim tests prove old heartbeat, result, and completion cannot mutate the new lease. |
| **S3 `[B2-LIVE]` Device identity and revocation** | `tinyassets/host_pool/registration.py`; `tinyassets/host_pool/client.py`; `tinyassets/runtime/daemon_auth.py`; auth API module; auth tests | Device-key enrollment, five-minute bound credentials, nonce replay defense, epoch revocation. Remove Supabase service-role use from daemons. | Attempt replay, key substitution, owner crossover, revoked-token use, and service-role discovery. |
| **S4 `[B2-LIVE]` B2 polling/claim/heartbeat API** | `tinyassets/api/execution_jobs.py`; `tinyassets/runtime/lease_store.py`; `tinyassets/host_pool/client.py`; API tests; load tests | Outbound long poll; atomic claim; 30-second independent heartbeat; 120-second lease; standard error/idempotency semantics. | Run duplicate/parallel claims, delayed heartbeats, API restarts, and 1,000 simulated long-polling daemons without double ownership. |
| **S5 `[B2-LIVE]` Blob and typed-result protocol** | `tinyassets/runtime/blob_refs.py`; `tinyassets/runtime/execution_result.py`; `tinyassets/api/execution_jobs.py`; blob/result tests | CAS upload, hash/size commit, typed candidate result, fenced completion CAS. Private refs remain owner-controlled. | Upload truncation, hash mismatch, oversized artifacts, duplicate commits, cross-job references, and stale completion. |
| **S6 `[B2-LIVE]` Linux narrow launcher** | `tinyassets/runner/launcher.py`; `tinyassets/runner/backends/linux.py`; `tinyassets/providers/base.py`; `tinyassets/sandbox_policy.py`; runner tests | Fixed bwrap/rootless-OCI policy, namespaces/cgroups/seccomp, no egress, no arbitrary options, child-only OS attestation. | Escape suite covers host mounts, proc/sys/dev access, network, privilege escalation, fork bombs, and forged attestation. |
| **S7 `[B2-LIVE]` Model broker** | `tinyassets/runner/model_broker.py`; `tinyassets/runner/driver.py`; `tinyassets/runtime/execution_capsule.py`; broker tests | UDS-only child capability; job/fence/model/budget enforcement; no raw provider key in child environment or filesystem. | Child attempts token extraction, alternate models, budget overflow, post-expiry calls, socket forwarding, and cross-job reuse. |
| **S8 `[B2-LIVE]` Staging, extraction, revalidation, destruction** | `tinyassets/runner/staging.py`; `tinyassets/runner/result_extractor.py`; `tinyassets/runner/revalidate.py`; `tinyassets/runner/cleanup.py`; integration tests | Credential-free exact-base staging; typed patch extraction; fresh-base apply; isolated verification; confirmed cleanup. | Malicious archive, path traversal, symlink, submodule, hook/filter, mode, oversized patch, cleanup-failure, and TOCTOU cases. |
| **S9 `[B2-LIVE]` Windows backend** | `tinyassets/runner/backends/windows_wsl2.py`; `tinyassets/runner/launcher.py`; Windows readiness tests; Windows escape tests | WSL2/Podman fixed-policy child; no broad Windows mounts; no native fallback; diagnostic installation state. | Opposite family verifies host-drive/network isolation, missing-WSL fail closure, Podman policy, and child-only attestation on Windows. |
| **S10 `[B2-LIVE]` Engine routing integration** | `tinyassets/engine_binding.py`; `tinyassets/api/universe.py`; `tinyassets/sandbox_policy.py`; `tinyassets/host_pool/client.py`; routing tests | `host_daemon` becomes externally dispatchable when an eligible B2 daemon exists. Platform never resolves a local executor. `market_rented` remains declare-only until B3. | Verify no engine choice, environment flag, legacy path, or API process can dispatch locally. |
| **S11 `[B2-LIVE]` First end-to-end live test** | `output/user_sim_session.md`; B2 live-test script; connector fixture; load/acceptance artifact | Real chatbot prompt creates a public-repo job; Windows BYO daemon claims, executes, revalidates, uploads, and submits; separate authorized effect opens a reviewable PR. Demonstrate stale-result rejection and zero platform workers. | Fable-5 repeats the rendered chatbot path, inspects the capsule/result/lease evidence, and verifies post-fix clean-use evidence or leaves a watch item. |
| **S12 Source-exec implementation** | `tinyassets/runner/source_exec.py`; `tinyassets/sandbox_policy.py`; `tinyassets/graph_compiler.py`; source-exec tests | Distinct image, policy, readiness, input, and typed output. No repo capability or patch result. | Attempt executor-class confusion, repo mounts, inherited credentials, and repo-patch output. |
| **S13 B3 selector and eligibility** | `tinyassets/runtime/execution_selector.py`; `tinyassets/paid_market/match.py`; `tinyassets/api/execution_jobs.py`; selector tests | Deterministic BYO-or-market selector before unchanged B2 offer/claim. No platform fallback branch. | Exhaustive selector cases prove no ineligible or platform-owned host becomes eligible. |
| **S14 B3 fenced settlement and reputation** | `tinyassets/paid_market/ledger.py`; `tinyassets/paid_market/reputation.py`; `tinyassets/runtime/result_verification.py`; settlement tests | Escrow and payout bind to current fence plus accepted result hash; verification/replay drives reputation. | Submit stale, duplicated, colluding, mismatched, disputed, and unverifiable results; prove no premature payout. |
| **S15 Private source delivery** | `tinyassets/runtime/source_delivery.py`; `tinyassets/runner/staging.py`; `tinyassets/host_pool/client.py`; private-delivery tests | Owner courier, credential stripping, X25519 transfer, recipient binding, owner-controlled CAS, explicit confidentiality tier. | Search bundle/child/logs for credentials; attempt recipient substitution, ciphertext replay, manifest mismatch, and unauthorized private matching. |
| **S16 B3 live test** | `output/user_sim_session.md`; market acceptance script; settlement evidence; reproducibility evidence | A non-founder user selects a market host through the chatbot; the host uses unchanged B2; independent verification accepts the fenced result; settlement completes. A no-host case stays pending. | Opposite family repeats both successful and no-capacity paths and confirms no hidden platform execution. |

## 13. First B2 live-test acceptance criteria

The first live test is complete only when all are true:

1. `S0–S10` have passed both family gates.
2. A non-special user enrolls an owner daemon using device keys.
3. The platform stores no daemon service-role credential.
4. A real chatbot connector creates the job.
5. The API returns a signed capsule through atomic claim.
6. The daemon heartbeats independently while the node is blocked or running.
7. The Windows daemon uses WSL2/Podman; no native process runs the job.
8. The child has no raw provider, GitHub, vault, or platform credential.
9. Source matches the signed exact base.
10. The result is content-addressed and typed.
11. The patch is reapplied against a fresh exact-base checkout.
12. A deliberately expired/reclaimed lease’s result is rejected.
13. Workspace destruction is confirmed before success.
14. The sandbox result does not itself push or merge.
15. A separately authorized effect creates a reviewable PR.
16. Platform compose contains no shared coding workers or provider-auth mounts.
17. With the owner daemon offline, the control plane remains usable and the job stays pending.
18. Concurrency/load proof covers at least 1,000 long-polling daemons, 10,000 queued jobs, duplicate claims, lease expiry, and stale completion.
19. The final user-surface proof is captured as a rendered chatbot conversation.
20. Post-fix real-user clean-use evidence is recorded; if none exists yet, the system remains under an explicit watch item rather than being declared fully proven.

## 14. B3 acceptance criteria

B3 is complete only when:

1. Market matching runs solely as a selector before B2.
2. Market and BYO hosts use identical claim, heartbeat, result, and completion endpoints.
3. No platform-owned host is present in selector input or fallback logic.
4. Settlement requires current fenced completion and accepted-result verification.
5. Self-reported attestation alone cannot unlock settlement or confidential work.
6. Independent replay detects a deliberately dishonest or corrupted result.
7. Reputation is derived from platform-observed outcomes.
8. Public-source market execution passes a live chatbot test.
9. Private-source execution uses recipient-bound credential-free encrypted delivery.
10. The UI clearly discloses when private source will be visible to a market host.
11. A no-eligible-host test leaves the job pending without starting platform compute.

## 15. Open risks and unresolved decisions

| Risk | Consequence | Required disposition |
|---|---|---|
| Windows WSL2/Podman host integration | Windows mounts or networking may weaken the intended Linux boundary | Block B2 Windows launch until escape tests pass on the actual supported Windows build. |
| Bubblewrap policy complexity | Bubblewrap primitives are not themselves a complete policy | Keep launcher fixed and review every namespace, mount, fd, capability, and seccomp decision. |
| Model prompt exfiltration | Untrusted source can intentionally include private repository data in model prompts | Broker policy, logging disclosure, optional redaction, and user-visible data-flow consent are required; raw credentials remain prohibited. |
| Private market host visibility | A host that executes plaintext can inspect it | Public-first B3; explicit host-visible consent or trusted/attested tier for private work. |
| Market-host dishonesty | Signed receipts can be fabricated by the host | Independent replay, deterministic artifact comparison, duplicate sampling, and reputation. |
| Non-deterministic models/tests | Honest replays may differ | Verify exact patch/tree and required checks; record nondeterminism policy rather than demanding identical transcripts. |
| Device compromise | A stolen daemon key can claim owner jobs | OS key storage, short credentials, revocation epoch, owner-visible device inventory, and capsule audience binding. |
| Platform signing-key rotation | Old or offline daemons may reject legitimate capsules or accept retired keys | Publish overlapping signed key sets with activation/retirement timestamps and revocation support. |
| Clock skew and network partition | Healthy work can lose its lease | Short skew allowance, independent heartbeat, fail-safe cancellation, and idempotent reclaim. Never accept stale completion. |
| Filesystem MVP scalability | Single-writer storage limits control-plane replication | Keep one authoritative writer through B2; move to transactional storage before multi-writer production. |
| Filesystem lock assumptions | OS file locks do not provide arbitrary cross-host consensus | Never mount the MVP store into worker hosts or describe it as a distributed lock. |
| Image/driver supply chain | A compromised runner image defeats isolation | Immutable digests, signed policy/image manifests, reproducible build evidence, and rollback/revocation. |
| Dependency fetching | Package managers may execute install scripts or reach arbitrary hosts | Keep disabled at first; introduce only through a separate lockfile/hash-bound fetch policy. |
| Git object format | SHA-1 and SHA-256 repositories have different object identifiers | Capsule explicitly carries `object_format`; never infer or normalize commit IDs. |
| Private artifact storage | PLAN currently prohibits platform-held private content | Use owner CAS/direct transfer unless the lead approves a PLAN amendment. |
| Source-exec ambiguity | Treating arbitrary source as repository work can silently broaden authority | Preserve distinct executor class and postpone activation until S12 passes. |
| Effect authorization | A valid patch may still target the wrong repository or stale head | Separate effect CAS against accepted hash, exact target, expected head, owner grant, and review state. |
| Reputation manipulation/collusion | Hosts may coordinate to approve each other’s bad results | Independent selector domains, random owner replay, anomaly detection, and delayed settlement for weak-verification tiers. |

## 16. Reviewer attack checklist

The design should be rejected or amended if a reviewer finds any path where:

- the platform starts coding/model execution itself;
- a founder-only identity, daemon, credential, or worker exists;
- a daemon receives a platform filesystem path;
- `LEGACY_UNBOUND` reaches `repo` or `source_exec`;
- a capsule can be edited without changing its hash/signature;
- a capsule can be replayed to another daemon;
- a stale lease can complete, settle, push, or merge;
- a heartbeat depends on model or graph-node progress;
- a job child can read raw provider/GitHub/vault credentials;
- a caller can choose launcher mounts, image, network, or sandbox flags;
- Windows falls back to native process execution;
- `repo` readiness authorizes `source_exec`;
- a result bypasses fresh-base revalidation;
- cleanup failure can still produce success;
- artifacts travel through the 4 MB request envelope;
- market self-attestation is treated as proof;
- private source is silently exposed to a market host;
- a sandbox result directly performs a GitHub effect;
- the filesystem MVP is treated as a cross-host distributed lock;
- no-capacity state starts an implicit platform worker.
## 17. Binding review amendments (Fable-5 opposite-family review, 2026-07-18)

Both families validated this spec at the design level (Codex authored it from its
architecture judgment; Fable-5 reviewed and confirmed the three-boundary model, the
B2 fencing protocol, the trust model, and the §10 reconciliation claims are sound).
The items below are spec-completeness amendments to FOLD INTO the named slice's
definition BEFORE that slice is built. S0 is unaffected and may start immediately.
Each slice build prompt MUST carry its amendment; the slice's dual-family gate MUST
verify it.

- **[S5] Result canonicalization (§7).** `ExecutionResultV1` MUST be canonicalized
  and hashed exactly like the capsule: RFC 8785 JCS + domain-separation prefix
  `UTF8("tinyassets.execution-result.v1\0") || SHA256(canonical_result)`. Otherwise
  two implementations disagree on `result_sha256` -> spurious 409s and
  verification-tier comparisons over different bytes.
- **[S4] Heartbeat response + cancellation channel (§8.5).** Define the heartbeat
  RESPONSE schema, minimally `{ lease_extended_to: Timestamp, directive: "continue"
  | "cancel" }`, so the platform delivers owner cancellation / wind-down over the
  lease channel (today only the request + 409 are specified; nothing delivers the
  cancellation the broker enforces in §6.3).
- **[S5] Blob quota + retention (§5.3/§8.6).** Bound each enrolled daemon's
  `blobs:init` volume with per-owner/per-daemon storage quotas + an unreferenced /
  failed-job blob TTL + GC, so a buggy/malicious enrolled device cannot disk-fill
  the single-writer MVP control plane.
- **[S9] Windows model-broker transport (§6.3/§9).** On `windows-wsl2-podman` the
  daemon-side broker and the child are separated by the WSL2 VM boundary — a host
  UDS cannot be inherited into the VM child. Name the bridge (WSL-side broker
  component / vsock / authenticated localhost forward); it MUST preserve `network:
  model_broker_only` and job/lease/fence binding. This is the one intentional hole
  in the network boundary and needs its own named requirement.
- **[S10] Legacy local tray disposition (§10.2).** The existing `fantasy_daemon`
  filesystem claim loop is a legacy LOCAL dispatch path with no enrollment / capsule
  / lease / fence. RESOLUTION (option a, per Hard Rule 11 single-clean-route + §1):
  the owner's local tray ENROLLS like any daemon and claims via the B2 protocol even
  locally — ONE protocol, no dual path. The pre-B2 filesystem claim loop is retired
  from executable coding/repo/source dispatch. S10's attack gate ("no legacy path
  can dispatch locally") MUST cover the tray.
- **[S7] Model-broker protocol sub-spec REQUIRED before S7 (§6.3 + new §15 risk).**
  The broker is the largest attack surface and its §6.3 contract is the thinnest
  relative to exposure. S7 MUST begin with its own broker protocol spec covering:
  child->broker channel authentication INSIDE the sandbox (prevent a second in-child
  process reusing the socket after job exit — lease revocation bounds time, not
  concurrent multiplexing); per-call fence-check; and the B3 case where an
  owner-controlled remote broker runs prompts authored by untrusted
  market-host-visible source under the OWNER's provider account (budget the cost AND
  the ToS/abuse exposure). Dual-family review of that sub-spec gates S7.
- **[S4/infra] Postgres timing (§15).** §13.18's 1,000 long-polling daemons against
  the single-writer filesystem MVP is aggressive for one droplet (1,000 held
  connections x 30s waits); expect it to force the Postgres decision earlier than
  §15's "before multi-writer production." Planning heads-up, not a contract change.
- **Citation fixes (§4/§8.6).** §4 private-work-content prohibition is at PLAN.md:57
  (fixed). §8.6 owner-CAS "proof of possession" (challenge over declared sha256
  ranges) is unspecified — needed by S15 at the latest; may defer past B2.

## 18. Binding host-approved delivery rebase (2026-07-20)

This section is the durable anti-loss amendment for the host-approved un-bundling decision.
It changes delivery order, not destination or scope. Sections 1–17 remain preserved as the
original reviewed program and contract history. Where they conflict, this section controls
only:

- authority derivation;
- runnable vertical-slice order;
- the timing of the dual-family gate; and
- the deferred-work inventory and status vocabulary.

The complete S0–S16 program remains required. A later slice is not optional merely because an
earlier runnable slice can ship without it. No row in §18.5 may disappear merely because a
slice ships; it leaves this plan only when implementation and its named proof land, or when a
host-approved superseding decision records the replacement and carries the source link
forward. `PLAN.md` is deliberately unchanged by this document; the amendment package remains
host-gated backlog.

### 18.1 Unified authority derivation: three mechanisms, one principle

Binding principle:

> Positive authority is re-derived from an unforgeable fact at the decision point. Mutable
> rows, events, projections, caches, requests, and receipts may reject, narrow, rate-limit,
> deduplicate, or record a decision; they never create or expand authority.

The mechanisms are deliberately not collapsed into one constructor:

| Mechanism | Unforgeable fact and verifier | Surfaces |
|---|---|---|
| **M1 — platform signature** | Verify canonical, domain-separated, purpose-specific platform-signed bytes against a release-pinned trust root through one M1 `RecordVerifier`. | Execution capsules and lease grants; signed terminal completion attestations; owner enrollment approval/device credential/access grants; market claim ownership and other platform-decided grants. |
| **M2 — content addressing** | Re-hash or re-resolve the exact content at the authority sink; the digest identifies the bytes. No platform signature is added merely to restate a hash. | Blob bytes and result references; capsule/result digests; exact Git commit/tree/head and patch identities. |
| **M3 — external re-confirmation** | Freshly verify through the external authority's cryptography or protected transaction/API at the decision point. | WorkOS JWT/JWKS human identity; GitHub repository/review/protected-mutation state; externally authoritative payment facts where applicable. |

All three return the same sealed `Verified[T]` evidence shape so authority sinks have one
calling convention. M1 alone is unified behind `RecordVerifier`; M2 and M3 retain
mechanism-specific verifiers and receive a verifier-neutral, package-private way to mint the
same `Verified[T]` only after successful verification. A Python wrapper is conspicuous, not a
security boundary by itself.

**Verify-key custody is the structural lever.** Authority consumers hold neither raw M1 verify
keys nor signing keys. The platform trust/composition root resolves purpose-separated public
keys from a signed, release-pinned manifest and constructs the only M1 verifiers. Production
private keys stay outside the control-plane/user-code process behind schema-specific,
non-exporting signer capabilities. Trust-root and custody work therefore precedes route
activation; otherwise signatures are theater.

**Mutation probes are the enforcement gate.** Every authority sink has a real decision-level
probe that preserves or forges mutable state while removing, corrupting, widening, or
contradicting the M1/M2/M3 fact. Acceptance must fail or remain no broader. A schema/type/unit
test that does not invoke the real decision is supporting evidence only. Reset, duplicate,
cross-owner, cross-generation, key-rotation, stale-content, and external-unavailability cases
belong in the same registry.

The adopted shape is from `output/s2-gate/design-authority-fable.md`, reconciled with the
broader surface inventory in `output/s2-gate/design-authority-codex.md`. The Fable scoping is
binding where they diverge: one principle and one return type, but three honest verification
mechanisms. WorkOS verification remains M3 and is not replaced or platform-re-signed.

### 18.2 New runnable vertical-slice order

Each slice must produce a runnable system and a concrete proof. The first slice may be narrow,
but it uses final-shaped seams: no throwaway authority constructor, alternate worker protocol,
or row-authoritative compatibility path may be introduced just to make it run.

| Order | Runnable vertical slice | Program coverage | What running it proves |
|---:|---|---|---|
| **V1 — wiring now** | **Authenticated signed-completion spine.** Persist one job; authenticate the daemon claim; mint a capsule-bound signed grant; execute through the narrow execution seam; accept a device-signed candidate plus content-addressed blobs; fenced-complete with a signed terminal attestation; replay from that attestation. | Minimum final-shaped path through S1, S2, S3 auth substrate, S4, S5, and S10a; trust-root/composition-root prerequisite. | One real job can traverse `job -> authenticated claim + signed grant -> execute -> signed candidate + blobs -> completion + signed terminal attestation`; forged/stale rows or events cannot create success, and restart replay re-derives the same terminal fact. |
| **V2** | **Confined owner-daemon execution.** Externalize signing/KEK authority, remove platform/user-code co-location, add the per-job runner, model broker, exact-source staging, revalidation, destruction, Linux and Windows backends, daemon coordinator, and the single B2 routing cutover. | S0, S6, S7, S8, S9, S10. | Hostile job code cannot read platform secrets or escape its fixed policy; the platform never supplies hidden compute; lease loss/cancel tears down safely; the owner tray uses the same B2 protocol rather than a local fallback. |
| **V3** | **Exactly-once reviewable GitHub PR effect.** Consume the accepted result through M1, re-derive patch/base/head through M2, re-confirm repository/credential facts through M3, and open one PR. It does not approve or merge. | S10.5 and its S0/S5/S8/S10a dependencies. | One accepted result causes exactly one result-bound branch and reviewable PR across retries/crashes, with no ambient token, caller-selected repository, stale-head write, approval, or merge authority. |
| **V4** | **First live B2 user path plus operational proof.** Stage live enrollment signing through the bounded window, run the real connector conversation, stale-result choreography, scale/load cases, authority CI, and post-fix watch. | S11 plus S3 live rollout, CI/mutation coverage, and §14 proof. | A non-special user can enroll, create, and observe a public-repo job through the rendered chatbot path; the Windows owner daemon completes it; zero platform workers remain; 1,000 pollers/10,000 jobs and stale completion do not split ownership. |
| **V5** | **Execution breadth and private delivery.** Add the separate `source_exec` class and owner-controlled, recipient-bound private-source transfer without broadening repo authority. | S12 and S15. | Executor-class confusion fails closed; source execution has distinct policy/result types; private bytes and credentials never enter platform storage or the wrong host, and explicit host-visibility consent is enforced. |
| **V6** | **Public-source market execution.** Put deterministic market selection before the unchanged B2 protocol; add fenced escrow, verification/replay, settlement, and reputation. | S13 and S14; staged M1 market ownership. | A selected external market daemon uses the same claim/lease/result path as BYO; stale or unverifiable results cannot pay; no eligible capacity leaves the job pending with no platform fallback. |
| **V7** | **B3 live path and private-market policy.** Run a non-founder market job through the rendered connector, independent verification, settlement, no-capacity behavior, and explicit host-visible-private consent where enabled. | S16 and the market-facing portion of S15. | The full market path works for a real user and settles only the current verified result; the no-host path remains usable but pending; private visibility is disclosed and enforced. |
| **V8** | **Protected GitHub merge and adjacent authority closure.** Redesign merge so only GitHub's protected, SHA-bound transaction plus fresh confirmation can produce `merged`; close the registered systemic authority sites with their correct M1/M2/M3 mechanism. | Post-S10.5 merge effect and systemic authority follow-through discovered by the S2 gate. | Mutable projections/outboxes/receipts cannot merge or confirm; all manual/auto/recovery routes use one gateway; every registered positive-authority sink has a mutation probe and fresh external/content proof where required. |

### 18.3 Complete S0–S16 preservation map

This map updates the original program to the approved authority design while preserving every
stage. “Later” means reordered, never removed.

| Program stage | Owning vertical slice | Preserved end-state obligation under the unified design |
|---|---|---|
| **S0** | V2, with trust-root work pulled forward into V1 | Zero platform workers; no in-process user-code path beside platform signing/KEKs; release-pinned trust root; purpose-separated external signer custody. Live universe-engine remediation remains host-gated. |
| **S1** | V1 | Exact, path-free, audience/job/lease/fence/source/policy-bound capsule; M1 signature verified from the pinned capsule key. |
| **S2** | V1, hardening in V4 | Atomic claim/fence/expiry/CAS; M1 grant and terminal attestation; generation monotonicity; event/table integrity; replay derives from the signed terminal fact, never mutable terminal state. |
| **S3** | V1 substrate, V4 live staging | WorkOS remains M3; platform-decided intent/approval/enrollment/credential/access/revocation facts use M1; device signature proves possession; exact-request authenticated principal crosses into acceptance. |
| **S4** | V1 | One trust-root-built composition root mounts poll/claim/heartbeat/candidate/completion; no caller-injected issuer/key/runtime; failure isolates execution routes without taking down authoring/browsing. |
| **S5** | V1, M2 hardening in V4 | Device-signed canonical result; decision-point M2 blob proof; typed `Verified[BlobRef]`; fenced completion consumes fresh proofs; owner-CAS proof remains explicit. |
| **S6** | V2 | Fixed, reviewed Linux isolation backend and policy; caller cannot choose mounts/image/network/devices/flags; child-only attestation. |
| **S7** | V2 | Job/lease/fence-bound broker capability with no raw provider key, scoped budget/cost authority, cancellation, process/session binding, and no generic broker credential. |
| **S8** | V2 | Exact accepted source closure, malicious-input-safe staging/extraction, fresh-base M2 revalidation in a second child, and confirmed destruction. |
| **S9** | V2 | Fixed Windows WSL2/Podman path, authenticated broker bridge, no native fallback or broad Windows mount, real escape/readiness proof. |
| **S10** | V2 | All owner-daemon execution routes use B2; retire JSON/filesystem/local/cloud-worker coding execution and any environment-flag bypass. |
| **S11** | V4 | Rendered public-repo chatbot proof, non-special enrollment, stale-result rejection, zero-worker proof, load/concurrency evidence, and post-fix clean-use/watch. |
| **S12** | V5 | Separate source-exec image/policy/readiness/input/output; never inherits repo capability or returns repo patches. |
| **S13** | V6 | Deterministic BYO-or-market selector before unchanged B2 eligibility/claim; verified capability/identity facts only; no platform fallback branch. |
| **S14** | V6 | Escrow/settlement bound to current fence plus M2 accepted-result identity, M1 claim ownership, verified actor/payment facts, and independent result verification; platform-observed reputation. |
| **S15** | V5 and V7 | Owner courier, credential stripping, recipient-bound encryption, owner-controlled storage/proof, explicit confidentiality tier, and no false claim that encryption hides plaintext from the executing host. |
| **S16** | V7 | Real non-founder market run over unchanged B2, independent verification, fenced settlement, no-host pending behavior, rendered user proof, and clean-use/watch evidence. |

### 18.4 Status vocabulary for the deferred inventory

- **confirmed-unfixed:** a reviewed finding still needs a failing regression and implementation.
- **build-ready-not-built:** an actionable design/spec exists; implementation evidence is absent.
- **specified-not-built:** the preserved contract exists, but the implementation brief may still
  need composition details.
- **redesign-required:** a prior premise is invalid; do not build the old shape.
- **host-gated:** work may be prepared, but the named live/design boundary cannot be crossed
  without explicit host go/no-go.
- **binding-no-change:** a protected boundary to preserve, not an implementation task.
- **UNVERIFIED:** the cited artifact or this sweep does not establish the stronger claim.

### 18.5 Complete deferred backlog (anti-loss ledger)

| ID | Deferred work | Owning vertical slice | Source artifact(s) | Status / exit condition |
|---|---|---|---|---|
| **B01** | Add a durable monotonic generation floor: a restored superseded generation must fail closed; use the append-only `lease_events` maximum fence as the rejection floor. | V1 | `output/s2-gate/s2-leasestore-report.md`; `output/s2-gate/fable-fix4-commit-review.md` | **confirmed-unfixed per host directive. Artifact linkage UNVERIFIED:** the cited artifacts establish current fence/reclaim/re-completion semantics, but this sweep did not locate the new high-water finding verbatim. Must begin with a failing restore-old-generation regression. |
| **B02** | Block `INSERT OR REPLACE`/`REPLACE` against `lease_completion_attestations` with an exactly validated `BEFORE INSERT` duplicate-PK/task guard independent of `recursive_triggers`. | V1 | `output/s2-gate/codex-attestation-schema-review.md`; `output/s2-gate/codex-attestation-table-validation.md`; `output/s2-gate/ultra-lens-attestation-append-only.md` | **confirmed-unfixed.** Exit when ordinary duplicate insert, `INSERT OR REPLACE`, `REPLACE`, and UPSERT mutation probes fail closed on supported SQLite. |
| **B03** | Apply the same `INSERT OR REPLACE` protection to the append-only `lease_events` evidence ledger; do not rely on non-persistable connection-local `recursive_triggers`. | V1 | `output/s2-gate/gate-verdict-fable-fix5.md`; `output/s2-gate/codex-attestation-table-validation.md` | **confirmed-unfixed per host directive.** Source pairing establishes insertability plus the SQLite replacement bypass pattern; exact current-table repro is **UNVERIFIED** until the required failing test lands. |
| **B04** | Replace attestation `len != 1` veto semantics with verify-first, content-deduplicated replay: ignore unverifiable rows, collapse byte/content-identical valid attestations, and reject only conflicting distinct valid payloads. | V1 | `output/s2-gate/codex-attestation-schema-review.md`; `output/s2-gate/fable-s10a-final-review.md` | **confirmed-unfixed.** Exit with junk/invalid-row availability, identical-copy dedup, and two-distinct-valid conflict regressions. |
| **B05** | Remove caller-neutralizable `unbound_fields`; domain separator selects an immutable per-domain field contract with JSON-type-strict bindings and fail-closed unknown domains. | V1 | `output/s2-gate/codex-domain-contract-spec.md`; `output/s2-gate/codex-unbound-fields-policy.md`; `output/s2-gate/gate-m1h-codex.md` | **build-ready-not-built.** Every authority-relevant field must be bound or specialized-validated by the registered domain contract. |
| **B06** | Cross-check signed `owner_user_id` against the exact-request authenticated daemon principal on candidate acceptance, completion, and replay; no grant-owner fallback. | V1 | `output/s2-gate/codex-owner-authority-fix.md`; `output/s2-gate/gate-m1h-codex.md` | **build-ready-not-built; current exploitability UNVERIFIED.** Exit with the coherently re-signed owner-mutation probe described by the source. |
| **B07** | Eliminate blob/SQLite lock-order inversion by enforcing one order (physical blob-root coordinator, then SQLite transaction) on candidate and completion paths. | V1 | `output/s2-gate/gate-m1h-codex.md`; `output/s2-gate/codex-blob-lock-redesign.md` | **confirmed-unfixed.** Exit with both scheduler orders completing without `database is locked`, deadlock, or split result. |
| **B08** | Replace path-string blob-root locks with physical directory identity so Windows `\\?\` paths, junctions/symlinks, case, separators, and tested UNC/drive aliases cannot bypass serialization. | V1 | `output/s2-gate/gate-m1h-codex.md`; `output/s2-gate/codex-blob-lock-redesign.md` | **confirmed-unfixed; UNC equivalence UNVERIFIED.** Fail closed when physical identity cannot be obtained. |
| **B09** | Remove stale per-instance blob `_index`; reload/validate/mutate an operation-local index under the shared physical-root lock and persist that explicit value atomically. | V1 | `output/s2-gate/gate-m1h-codex.md`; `output/s2-gate/codex-blob-lock-redesign.md` | **confirmed-unfixed.** Exit when cross-instance writers preserve both updates and stale instances cannot resurrect collected bindings. |
| **B10** | Validate the full completion-attestation table contract, not only `PRAGMA table_info`: exact main-table SQL, conflict policies, `table_xinfo`, FK, index, trigger, namespace, and temp-shadow state. | V1 | `output/s2-gate/codex-attestation-table-validation.md`; `output/s2-gate/gate-m1h-codex.md` | **confirmed-unfixed.** Never auto-repair or recreate evidence on mismatch; raise stored-state corruption. |
| **B11** | Implement the S3 authority map: M3 WorkOS owner plus M1 intent, approval, possession-backed enrollment, credential state, access grant, revocation, and verified-request chain. | V1 substrate; V4 live flip | `output/s2-gate/codex-s3-authority-map.md` | **build-ready-not-built; route activation UNVERIFIED.** No mutable row supplies owner/key/epoch/token authority. |
| **B12** | Bind bearer-token and device-key resolution to the signed enrollment/credential chain; chosen token rows, row-key substitution, epoch rollback, and revocation clearing must fail. | V1 substrate; V4 live flip | `output/s2-gate/codex-s3-bearer-token-design.md` | **build-ready-not-built.** Use a closed, no-downgrade legacy window only if live population is proven. |
| **B13** | Build the sole S4 execution-authority composition root and mount poll/claim/heartbeat/candidate/completion only from its complete runtime. | V1 | `output/s2-gate/codex-s4-wiring-gate-spec.md` | **build-ready-not-built; production custody UNVERIFIED.** No partial runtime, caller-supplied binder/key, or unsigned fallback. |
| **B14** | Build the release-pinned trust root and purpose-separated external signer custody for capsule, grant, and completion authority (and approved later purposes). | V1 prerequisite | `output/s2-gate/codex-trust-root-custody-design.md`; `output/s2-gate/codex-s4-wiring-gate-spec.md` | **build-ready-not-built.** Private keys stay outside control-plane/user-code memory; returned signatures are locally reverified before commit. |
| **B15** | Convert blob acceptance to M2 decision-point re-derivation returning `Verified[BlobRef]`; JSON bindings are veto/consistency only; owner CAS needs fresh proof. | V1 then V4 hardening | `output/s2-gate/codex-s5-blob-m2-audit.md`; `output/s2-gate/codex-m2m3-tightening-spec.md` | **build-ready-not-built; filesystem/owner-CAS threat remains UNVERIFIED.** No blob signing key. |
| **B16** | Build S10a `run_graph` -> persisted run/outbox/job -> authenticated claim/grant -> accepted-result checkpoint resume, including crash, cancellation, duplicate, healing, and lock-order cases. | V1 | `output/s2-gate/codex-s10a-final-spec.md`; `output/s2-gate/codex-build-order-graph.md` | **build-ready-not-built.** Exactly-once checkpoint resume derives from the verified terminal attestation, not a job row. |
| **B17** | Build S10.5: one M1-authorized, M2-exact, M3-reconfirmed reviewable GitHub PR per accepted result; retire ambient/caller-target legacy effect routes. | V3 | `output/s2-gate/codex-s10-5-final-spec.md` | **build-ready-not-built.** Scope ends at PR open; it neither approves nor merges. |
| **B18** | Land the shared verifier-neutral `Verified[T]` mint seam and M2/M3 tightening without routing hashes or external facts through `RecordVerifier`. | V1 foundation; V3/V8 consumers | `output/s2-gate/codex-m2m3-tightening-spec.md`; `output/s2-gate/design-authority-fable.md` | **build-ready-not-built.** M1 custody remains exclusive; M2/M3 verifiers can mint only after real verification. |
| **B19** | Deliver the per-job sandbox runner and use it to confine every user-code route while externalizing the platform key/KEK trust domain. | V2 | `output/s2-gate/codex-sandbox-runner-design.md`; `output/s2-gate/codex-s0-sandbox-remediation-spec.md` | **specified-not-built; live-path host gate applies.** The runner must be final-shaped and preserve the live universe engine through staged cutover. |
| **B20** | Add blocking CI authority gates: site/effect/probe set equality, semantic mutation suite, real CPython 3.11 shard, exact plugin-mirror regeneration, and stable aggregate branch-protection context. | V4 | `output/s2-gate/codex-ci-authority-gates.md` | **build-ready-not-built; workflow execution UNVERIFIED.** Keep heuristic suspicious-read scanning advisory only. |
| **B21** | Close mutation-probe coverage gaps across S3 auth, universe ACL/home, executable branch content, market ownership, GitHub, completed-run consumers, daemon control/schedules/memory, blob index, and queue cancellation. | V4 and V8 by owning surface | `output/s2-gate/codex-mutation-probe-gap-audit.md`; `output/s2-gate/codex-systemic-reaudit-2.md` | **confirmed coverage gap.** Each registered sink gets a genuine positive control and a committed raw-DML/storage mutation against the real decision. |
| **B22** | Apply the reconciled exec-plan/PLAN amendment package only after host approval; retain held S7/B3 hunks and resolve overlaps by exact source text, not stale line numbers. | Governance prerequisite across V2–V8 | `output/s2-gate/codex-plan-package-final.md`; `output/s2-gate/fable-consolidate-plan-amendments.md` | **host-gated.** `PLAN.md` remains untouched here. Exec-plan source is build-ready; the six PLAN edits remain separately approval-controlled. |
| **B23** | Redesign GitHub merge authority: the current manual merge worker is not authoritative because protection checks are incomplete and a mutable receipt can skip GitHub reads. | V8 | `output/s2-gate/codex-github-mergeworker-audit.md`; `output/s2-gate/codex-m3-github-redesign.md` | **redesign-required.** Do not rely on “projection as cache because worker re-confirms.” Only fresh protected SHA-bound GitHub mutation plus exact post-read can mint `Verified[GitHubMergeConfirmation]`. |
| **B24** | Stage live S3 enrollment/credential signing with new-record dual-write/shadow verification, a bounded closed legacy population, fresh owner/device re-enrollment, and a separately approved enforcement flip. | V4 | `output/s2-gate/design-authority-fable.md`; `output/s2-gate/codex-s3-authority-map.md` | **host-gated.** Never bulk-sign mutable legacy rows or select fallback through a mutable flag. |
| **B25** | Stage live market claim-ownership signing and legacy-position reconciliation before removing row authority or enforcing no-artifact/no-settlement. | V6 | `output/s2-gate/design-authority-fable.md`; `output/s2-gate/design-authority-codex.md` | **host-gated; market liveness UNVERIFIED in source.** Keep ledger conservation; signer failure leaves money pending. |
| **B26** | Preserve WorkOS JWT/JWKS verification as M3; add only provenance typing/shadow comparison where needed. Do not platform-re-sign or replace the live auth mechanism. | V1/V4 boundary | `output/s2-gate/design-authority-fable.md`; `output/s2-gate/codex-s3-authority-map.md` | **binding-no-change.** Any WorkOS enforcement or shadow deploy remains an explicit live-surface host decision. |
| **B27** | Remediate S0’s live universe-engine execution path: dark-cut parent-process user code only through staged host go/no-go; preserve uptime while moving execution and keys to separate trust domains. | V2 | `output/s2-gate/codex-s0-sandbox-remediation-spec.md`; `output/s2-gate/codex-s0-staging-live-safe.md` | **host-gated.** No autonomous dark cut of the live engine path. |
| **B28** | Implement S6 fixed Linux launcher/backend and its escape/readiness suite under the selected reviewed policy. | V2 | `output/s2-gate/codex-sandbox-runner-design.md`; `output/s2-gate/codex-s6-amendment-final.md` | **specified-not-built.** No caller-selected launcher parameters or unsupported fallback. |
| **B29** | Implement S7 model broker: connection/session binding, scoped credential, per-call fence, cost/budget ledger, cancellation, framing, and explicit B3/remote-broker posture. | V2 | `output/s2-gate/s7-subspec-reconciled.md`; `output/s2-gate/fable-s7-opens-crossfamily.md` | **specified-not-built.** Use the latest cross-family resolutions; superseded crypto/transport drafts are not authority. |
| **B30** | Implement S8 exact-source staging, extraction, fresh isolated revalidation, cancellation phase map, and destruction proof. | V2 | `output/s2-gate/codex-s8-amendment-v2.md`; `output/s2-gate/gate-verdict-fable-s8-amendment.md` | **dual-family design-approved; implementation UNVERIFIED.** Do not claim “credential-free” until verified source closure proves it. |
| **B31** | Implement S9 Windows WSL2/Podman launcher and the decided authenticated cross-VM broker bridge; run real Windows escape/readiness tests. | V2 | `output/s2-gate/fable-s9-final-resolution.md`; `output/s2-gate/fable-s9-bridge-fix.md` | **specified-not-built; runtime UNVERIFIED.** No native Windows fallback or broad host-drive mount. |
| **B32** | Implement S10 single-protocol routing cutover: tray enrolls/polls/claims through B2; remove legacy JSON/filesystem/local/cloud-worker coding paths. | V2 | `output/s2-gate/codex-build-order-graph.md`; `output/s2-gate/execplan-runner.md` | **specified-not-built.** Required between S10a and S11; absence from a narrower build prompt never removes it. |
| **B33** | Build S11 load/acceptance harness and exact B2 live fixture: target repository/task/prompt, test identity, stale-result choreography, evidence manifest, thresholds, and storage-fallback decision. | V4 | `output/s2-gate/codex-load-architecture.md`; `output/s2-gate/codex-remaining-path-audit.md` | **specified/not-fully-specified, not built.** Fixture defaults and evidence schema remain **UNVERIFIED** until frozen. |
| **B34** | Implement S12 source-exec with distinct image, policy, readiness, input/output, and class-confusion tests. | V5 | `output/s2-gate/execplan-runner.md`; `output/s2-gate/codex-remaining-path-audit.md` | **specified-not-built.** It never gains repo mounts or repo-patch authority. |
| **B35** | Implement S13 deterministic BYO/market selector over unchanged B2 eligibility and claims. | V6 | `output/s2-gate/codex-b3-foldback.md`; `output/s2-gate/execplan-runner.md` | **specified-not-built.** No separate market worker protocol or platform-owned candidate. |
| **B36** | Implement S14 fenced escrow/settlement, independent verification/replay, disputes, and platform-observed reputation. | V6 | `output/s2-gate/codex-market-settlement-deepdive.md`; `output/s2-gate/codex-b3-foldback.md` | **specified-not-built; production money behavior UNVERIFIED.** Stale/unverifiable/colluding results cannot pay. |
| **B37** | Implement S15 private-source courier, credential stripping, owner-CAS possession proof, recipient-bound encryption, confidentiality consent, and challenge/retention rules. | V5/V7 | `output/s2-gate/execplan-runner.md`; `output/s2-gate/codex-remaining-path-audit.md` | **specified-not-built.** Platform-hosted private ciphertext still requires a separately approved PLAN change. |
| **B38** | Run S16 non-founder B3 live test: selected market host, unchanged B2 protocol, independent verification, settlement, no-host pending case, rendered conversation, and clean-use/watch evidence. | V7 | `output/s2-gate/codex-b3-foldback.md`; `output/s2-gate/execplan-runner.md` | **specified-not-built.** Requires all V6 gates and live host approval. |
| **B39** | Close adjacent positive-authority surfaces discovered by the systemic sweep: universe ACL/home, daemon control, schedules/subscriptions, branch ownership/publication/version execution, completed-run consumers, rollback snapshots, daemon-memory promotion, and task cancellation. | V8, split by owning module | `output/s2-gate/codex-systemic-reaudit-2.md`; `output/s2-gate/design-authority-codex.md` | **confirmed static findings; exploitability/production reach varies and is marked UNVERIFIED in source.** Assign M1/M2/M3 honestly and require registered mutation probes before activation. |
| **B40** | Specify and build authenticated distribution, rotation, revocation, and atomic activation of the daemon-side platform-capsule trust set. | V2 | `output/s2-gate/codex-remaining-path-audit.md`; `output/s2-gate/codex-trust-root-custody-design.md` | **not-fully-specified.** A daemon must distinguish platform capsules without accepting caller-provided keys or mutable active state. |
| **B41** | Finish the non-special-user enrollment journey across tray, browser/chatbot approval, inventory, revoke, re-enroll, and diagnostics. | V4 | `output/s2-gate/codex-remaining-path-audit.md`; `output/s2-gate/codex-s3-authority-map.md` | **not-fully-specified.** HTTP primitives alone do not satisfy the runnable user journey. |
| **B42** | Define and enforce the platform-issued daemon capability ceiling and signed eligibility/policy/image registry; daemon self-declaration may narrow but never expand it. | V1/V2 | `output/s2-gate/codex-remaining-path-audit.md`; `output/s2-gate/codex-s3-authority-map.md` | **specified-not-built.** Current self-created capability authority is not the end state. |
| **B43** | Own public-source snapshot production: resolve exact public repo/base, create canonical bundle/manifest, sign producer attribution, and commit it to CAS before claim. | V1/V2 | `output/s2-gate/codex-remaining-path-audit.md`; `output/s2-gate/codex-s10a-final-spec.md` | **not-fully-specified.** V1 may use the narrowest fixed fixture, but the production owner/component cannot be lost. |
| **B44** | Define and build the durable owner-daemon coordinator state machine from poll through claim, capsule verify, heartbeat, source, broker, launch, revalidate, upload, complete, teardown, and crash-spool recovery. | V2 | `output/s2-gate/codex-remaining-path-audit.md`; `output/s2-gate/codex-build-order-graph.md` | **not-fully-specified.** Lower-level APIs do not by themselves own the end-to-end daemon lifecycle. |

Backlog row count: **44**. Rows B01–B27 capture the host-enumerated security,
design, invalidation, and host-gate set; B28–B44 preserve the S0–S16 implementation and
integration work that moves behind V1 so un-bundling cannot erase it.

### 18.6 Amended process rules (host-approved 2026-07-20)

These rules supersede §12's “every slice has a dual-family gate” merge requirement and §17's
per-slice phrasing. The underlying independent-review requirement still applies before live
deployment.

1. **Deliver runnable vertical slices.** A slice ends in a running path and a user/system
   behavior it proves, not a horizontal pile of schemas, types, or review papers. Interfaces
   remain final-shaped and later scope stays in §18.5.
2. **Dual-family approval is a pre-deploy gate, not a per-slice build gate.** Focused tests and
   normal independent review still gate each change. Before any affected live deployment,
   route activation, enforcement flip, money movement, or rendered acceptance test, both model
   families review the integrated deploy candidate and evidence. This allows narrow slices to
   iterate without lowering the live-surface bar.
3. **Confirmed findings become failing regression tests.** The next artifact for B01–B10 and
   other confirmed findings is the smallest real-sink test that fails for the demonstrated
   reason. Review documents remain provenance; they are not substitutes for executable gates.
4. **Structural rebuild only when a test proves the shape wrong.** A review concern alone may
   request a probe or mark a claim UNVERIFIED; it does not force architecture churn. When the
   reproducing/mutation test proves the current shape cannot satisfy the invariant, stop the
   patch loop and rebuild the smallest implicated boundary.

Process-analysis provenance: `output/s2-gate/fable-process-changes-text.md`. The host-approved
2026-07-20 rules above are authoritative where they differ from that artifact's recommendations.

### 18.7 Anti-loss closeout rule

A vertical slice may claim its runnable proof while later rows remain open. Its closeout must:

1. list the backlog IDs it closes;
2. leave every other owned/later ID in this ledger with its next proof;
3. add new confirmed gaps as new rows rather than burying them in a verdict;
4. retain or supersede source artifact paths explicitly; and
5. never describe “not needed for this slice” as “not needed for the program.”

That is the binding meaning of the host decision: delivery is un-bundled; the vision is not.
