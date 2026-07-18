# GitHub-native review/merge prior art (S4 redesign basis)

> Durable copy of the Codex-authored, Claude-verified, host-approved prior-art
> research that redirects S4 to a GitHub-authoritative design (host decision
> 2026-07-16). Sections 1-2 are copied verbatim from the research report; the
> report's section-3 tail was corrupted draft noise and is replaced here with
> the clean section-3 rerun. See the companion decision record
> `docs/design-notes/2026-07-16-s4-github-native-redirect.md`.

# Research report: standard answers for patch-loop review, sandboxing, and secrets

All web sources were accessed 2026-07-16. Repository findings refer to `origin/feat/patch-loop-s4` at `3beb9f2224d0877683eb91cb121b136e62b3c280` and the 2026-07-15 reference design.

## 1. GitHub-native review and merge primitives vs. the S4 queue

### Current state

S4 makes TinyAssets authoritative for approval and merge state. `review_queue.py` maintains local item states, head-bound approval tokens, policy generations, merge claims, timer state, and per-branch policy bindings; `github_merge.py` separately reconstructs required-check status from classic branch-protection APIs.

That is why reviews keep finding races: TinyAssets is implementing a second, partially synchronized PR transaction system beside GitHub’s. GitHub already owns the PR head, reviews, rulesets, checks, mergeability, and atomic merge operation.

### The standard answer: GitHub is authoritative; TinyAssets is a chat projection and workflow coordinator

The owner does not need to visit GitHub. Chat can submit a real GitHub PR review using the owner’s GitHub App user access token, then display the resulting GitHub state. GitHub documents that user access token actions are attributed to the user, while installation-token actions are attributed to the App. The PR-review API supports GitHub App user tokens and fine-grained PATs with `Pull requests: write`. ([GitHub App authentication](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/about-authentication-with-a-github-app), [PR reviews API](https://docs.github.com/en/rest/pulls/reviews))

The patch PR should therefore be authored by the TinyAssets GitHub App, not by the owner. GitHub does not allow an author to approve their own PR. A repository-wide `CODEOWNERS` entry such as `* @owner`, protected from modification, plus a required-code-owner-review ruleset makes the owner’s API-submitted review the native gate. ([required reviews](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/approving-a-pull-request-with-required-reviews), [CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners))

GitHub rulesets can require pull requests, approval counts, code-owner review, dismissal of stale approvals, approval of the latest reviewable push, named status checks, deployment success, and merge queue use. Multiple active rulesets aggregate and the most restrictive applicable rules win. Availability is plan-dependent for private repositories. ([ruleset rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets), [about rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets))

### S4 feature mapping

| S4 feature | GitHub-native equivalent | Assessment |
|---|---|---|
| Review-required gate | Ruleset/branch protection requiring PR approval and code-owner review | Native. Configure `* @owner`, protect `CODEOWNERS`, dismiss stale approvals, and require latest-push approval. |
| Owner approval from chat | `POST /pulls/{n}/reviews` with `event=APPROVE` and `commit_id=head_sha`, authenticated with owner’s GitHub App user token | Native state with chat UX. TinyAssets authenticates the chat user, calls GitHub, and mirrors the returned review. |
| Manual merge | Owner approval followed by an explicit chat `merge` action calling the merge API with expected `sha` | Native. GitHub atomically rechecks rules and head SHA. |
| Automatic merge | GraphQL `enablePullRequestAutoMerge`; GitHub merges once required reviews/checks are satisfied | Native. GitHub disables auto-merge in some untrusted-push/base-change cases. ([auto-merge](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/automatically-merging-a-pull-request), [GraphQL pull mutations](https://docs.github.com/en/graphql/reference/mutations#enablepullrequestautomerge)) |
| Timer merge | No simple PR-level “merge after T” primitive | Genuine gap. Keep one durable `not_before` scheduled effect, then enable auto-merge or request merge. |
| Timer via deployment environment | Environment wait timer plus required reviewer, then a ruleset requiring deployment success | Technically native, but too heavy for the default: it requires Actions/deployment wiring, is plan-limited for private repos, and represents deployment approval rather than PR review. ([environment protection](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments), [environments API](https://docs.github.com/en/rest/deployments/environments)) |
| Approval invalidated by changed head | Review submitted against `commit_id`; stale-review dismissal/latest-push approval rules | Native if repository rules are configured correctly. |
| Approval after policy tightening | GitHub re-evaluates current rulesets/protection at merge | Partial. GitHub-native tightening is enforced; TinyAssets-only changes such as `auto → manual`, a fresh-OAuth requirement, or a timer change are not. |
| Required-status-check verification | Ruleset-required checks plus GitHub auto-merge, merge queue, or merge endpoint enforcement | Native authority. TinyAssets may display checks, but should not reimplement the gate. |
| Merge serialization | GitHub merge transaction; merge queue for busy eligible repositories | Native. Merge queue additionally tests against latest base and earlier queued PRs. |
| Reshape | Submit `REQUEST_CHANGES` review and enqueue Workflow’s `draft_patch` resume | Hybrid. GitHub owns review state; TinyAssets owns workflow continuation and notes. |
| Reject | Request changes/close PR plus terminal Workflow outcome | Hybrid. GitHub has no irreversible “reject forever” state because a PR can be reopened. |
| Hold/release | Disable/enable auto-merge; cancel/recreate local timer if applicable | Mostly native. |
| Chat browse queue | Query open App-authored/labeled PRs; retain a local cache/projection for latency and Workflow linkage | GitHub should be authoritative; SQLite need not be a competing state machine. |

GitHub merge queue is useful for organization-owned, high-concurrency repositories, but it is not a universal baseline: GitHub documents it for public organization repositories and private organization repositories on Enterprise Cloud, not ordinary personal repositories. ([merge queue](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/merging-a-pull-request-with-a-merge-queue))

### Permission design

| Operation | Minimum documented repository permission |
|---|---|
| Read PRs/reviews | `Pull requests: read`, or `Contents: read` for some PR reads |
| Create PR / submit owner review | `Pull requests: write` |
| Create branch, commit content, merge PR | `Contents: write` |
| Modify workflow files | `Workflows: write`, only if patching workflows is allowed |
| Display check runs / commit statuses | `Checks: read`; `Commit statuses: read` |
| Read classic branch protection | `Administration: read` |
| Read active rulesets | `Metadata: read` |
| Configure rulesets/branch protection/environments | `Administration: write` |
| Approve pending environment deployment | `Deployments: write` |

Sources: [pull-request API permissions](https://docs.github.com/en/rest/pulls/pulls), [branch-protection API](https://docs.github.com/en/rest/branches/branch-protection), [repository-rules API](https://docs.github.com/en/rest/repos/rules), [check runs](https://docs.github.com/en/rest/checks/runs), [commit statuses](https://docs.github.com/en/rest/commits/statuses).

Do not grant the steady-state App `Administration: write` merely to make setup convenient. Use an owner-guided one-time ruleset setup or an explicitly optional setup grant, then operate with `Contents` and `Pull requests` permissions. GitHub’s GraphQL documentation does not publish a reliable per-mutation permission table for auto-merge/queue mutations, so the App manifest should be integration-tested rather than assuming that REST permission descriptions transfer exactly. ([choosing GitHub App permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app))

### Verdict: hybrid, decisively GitHub-authoritative

Keep TinyAssets authoritative only for:

- Chat identity/session authorization.
- Job-to-PR/universe/run linkage.
- `reshape` durable resume/outbox state.
- Product preference: manual, automatic, or `not_before`.
- A tiny timer scheduler and reconciliation cache.
- Workflow terminal outcomes and explanatory notes.

Delete or substantially simplify:

- `merge_approvals`, approval-token expiry/consumption, policy-generation signatures, and head-bound token minting.
- Local `approved → merging → merged` authority, merge-claim leases, stale-claim recovery, and their CAS races.
- `_github_required_checks_passed`. It only reads classic branch protection and manually combines status/check-run names, so it cannot faithfully represent aggregate rulesets, required deployments, or merge-queue merge-group semantics.
- Most of `review_queue` as a state machine. Replace it with a minimal PR binding/projection or derive the queue from App-authored/labeled GitHub PRs.
- Security-sensitive interpretation of `merge_policy_bindings`; retain only the off-GitHub product preference.
- Local handling of head-change approval invalidation where GitHub’s stale-review/latest-push rules provide it.

Risks:

- Repository rules must be installed and verified. Without a required-review rule, an API caller with `Contents: write` may merge.
- `CODEOWNERS` must cover every path and itself be protected.
- The App must not be configured as a ruleset bypass actor.
- GitHub UI changes become legitimate state changes; TinyAssets must consume webhooks or reread immediately before reporting success.
- GitHub does not expire an otherwise-valid approval because 24 hours elapsed. If freshness is a real product requirement, retain that one explicit constraint rather than the general token machinery.
- Tightening a TinyAssets-only policy must disable auto-merge and, if renewed consent is required, dismiss or supersede the prior review.

---

## 2. Off-the-shelf sandboxing for the Phase-2 per-job runner

### Current state

The repository’s current sandbox seam is Linux `bubblewrap`; `probe_sandbox_available()` explicitly reports it unavailable on Windows. More seriously, `CodexProvider` currently falls back to `--dangerously-bypass-approvals-and-sandbox` when `bwrap` is missing. That is incompatible with a Phase-2 credential-grade runner.

`node_sandbox.py`, CLI tool policies, and subprocess environment filtering are useful inner controls, but they are not an isolation boundary against model-driven repository code.

### 2026 option survey

| Option | Windows-first fit | Hard-$0 | MVP judgment |
|---|---|---:|---|
| Windows Sandbox | Disposable Hyper-V environment; `.wsb` can disable networking/clipboard and control mapped folders | Yes on supported Pro/Enterprise/Education editions | Real VM isolation, but GUI-oriented and weakly orchestrated for a 24/7 headless daemon. Useful later for Windows-only test lanes. ([configuration](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-configure-using-wsb-file), [edition/policies](https://learn.microsoft.com/en-us/windows/client-management/mdm/policy-csp-windowssandbox)) |
| WSL2 alone | VM-like Linux environment available on Windows 11 | Yes | Substrate, not per-job isolation. Default Windows-drive mounts and Windows interop must not be treated as safe. ([WSL FAQ](https://learn.microsoft.com/en-us/windows/wsl/faq), [WSL configuration](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)) |
| Rootless Podman machine | Windows client controls a WSL2-backed Linux VM; each job is an OCI container; Podman machine is rootless | Yes | Shortest credible local path. ([Podman installation](https://podman.io/docs/installation), [podman machine](https://docs.podman.io/en/stable/markdown/podman-machine-init.1.html), [rootless model](https://docs.podman.io/en/latest/markdown/podman.1.html)) |
| Docker rootless/Desktop | Similar container workflow | Conditional | Technically viable, but Desktop is only free for personal use, education, noncommercial OSS, and qualifying small businesses. Podman avoids making licensing part of the MVP contract. ([rootless Docker](https://docs.docker.com/engine/security/rootless/), [Desktop licensing](https://docs.docker.com/subscription/desktop-license/)) |
| Claude Code sandbox | `bubblewrap` on Linux/WSL2; tool and network restrictions; native Windows unsupported | Yes with existing subscription | Good defense in depth, not the outer boundary. Anthropic explicitly documents limitations including inherited credentials, domain-fronting risk, and Docker-socket escape. Set `failIfUnavailable=true`; never permit unsandboxed fallback. ([Claude Code sandboxing](https://code.claude.com/docs/en/sandboxing), [CLI controls](https://code.claude.com/docs/en/cli-reference)) |
| Codex CLI sandbox | Native OS sandbox; Windows native enforcement or WSL2/Linux isolation; `read-only`, `workspace-write`, and `danger-full-access` modes | Yes with existing subscription | Good inner boundary. Use `workspace-write`, no network, approval `never`; never `danger-full-access`. ([Codex security and approvals](https://learn.chatgpt.com/docs/agent-approvals-security), [Codex sandboxing](https://learn.chatgpt.com/docs/sandboxing)) |
| gVisor | OCI-compatible userspace kernel on Linux | Yes | Stronger future Linux worker runtime; compatibility/performance cost and not a native Windows answer. ([overview](https://gvisor.dev/docs/), [requirements](https://gvisor.dev/docs/user_guide/faq/)) |
| Firecracker | KVM microVMs with jailer on Linux | Yes, but operationally expensive | Excellent later multi-tenant boundary; wrong MVP because Windows cannot run it natively and TinyAssets would inherit kernel/rootfs/jailer orchestration. ([Firecracker](https://github.com/firecracker-microvm/firecracker), [getting started](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md)) |
| E2B | Hosted Firecracker agent sandboxes | No durable guarantee | Excellent future adapter; free tier/credits do not make recurring execution hard-$0. ([pricing](https://e2b.dev/pricing)) |
| Modal Sandboxes | Hosted gVisor sandboxes with network blocking | No | Usage-billed; future hosted adapter. ([resources/pricing behavior](https://modal.com/docs/guide/sandbox-resources), [networking](https://modal.com/docs/guide/sandbox-networking)) |
| Daytona | Hosted container/Linux VM/Windows VM sandboxes | No durable guarantee | Useful future provider, particularly for Windows VM jobs, but tier limits/top-ups and vendor dependency violate the baseline. ([sandboxes](https://www.daytona.io/docs/en/sandboxes/), [limits](https://www.daytona.io/docs/en/limits/)) |

### Shortest credible live path

Use rootless Podman on a dedicated WSL2 Podman machine and create one disposable OCI container per patch job.

The job profile should be conventional:

- Non-root UID and rootless runtime.
- `--network=none` for untrusted editing/testing.
- Read-only image/root filesystem.
- Writable temporary workspace and one narrow output mount.
- `--cap-drop=all`, `no-new-privileges`, no devices.
- CPU, memory, process-count, disk-output, and wall-clock limits.
- No Windows-drive mount, daemon database, user profile, SSH agent, Git config with credentials, Credential Manager access, or Podman/Docker socket.
- Destroy container and writable layer after every terminal result.
- Export only a bounded patch, structured test receipt, logs, and hashes.
- Validate patch paths/size outside the sandbox and apply it to a fresh clean worktree before the GitHub effector acts.

Repository acquisition and dependency/image preparation should happen in a controlled preparation phase. The model-driven edit/test phase should run offline wherever possible.

Remote model execution creates one unavoidable distinction: a coding CLI needs a model credential or subscription session. “No ambient credentials” should mean no GitHub, vault, host, cross-universe, or unrelated provider credentials. There are two credible patterns:

1. MVP: give the job only its dedicated model-provider capability, with GitHub and all other host secrets absent; then run tests in a second completely credential-free, networkless container.
2. Stronger design: keep model authentication in a daemon-side broker and expose only a narrow model RPC to the container. The provider secret never enters the job.

Do not mount the existing per-universe `CODEX_HOME`, Claude configuration directory, or `.credential-vault.json` into arbitrary test processes. A whole authentication home is a capability bundle, not a single scoped secret.

The first live acceptance test should deliberately attempt to read a known host canary secret, access `C:\`, reach the internet, contact the container runtime socket, exceed resource limits, and smuggle an out-of-workspace patch. Every attempt must fail while a real patch still reaches a PR end-to-end.

### Verdict: Podman/WSL2 outer boundary, vendor sandboxes only as inner controls

This deletes or avoids:

- A custom Windows process sandbox.
- Custom filesystem virtualization or overlay implementation.
- A home-grown syscall policy engine.
- Custom microVM lifecycle, kernels, images, jailers, and attestation.
- Treating CLI allow/deny lists as the security boundary.
- The present unsafe Codex bypass fallback.
- An MVP dependency on paid E2B/Modal/Daytona infrastructure.

Risks:

- Rootless containers are materially better than subprocesses, but not the final hostile multi-tenant boundary.
- WSL interop, `/mnt/c`, and runtime-socket exposure can collapse isolation if mounted.
- Offline execution requires dependency-prefetched images or controlled setup.
- Model-provider credentials remain valuable; isolate them from test subprocesses or broker them.
- A generated patch can itself be malicious even when its execution was contained; host-side path validation and owner review remain mandatory.
- Windows-native test suites need a later Windows Sandbox/VM lane.
- If untrusted public workloads or multiple hostile tenants become real, graduate the Linux worker to gVisor, Firecracker, or a hosted sandbox rather than extending the Podman policy indefinitely.

---

## 3. Phase-2 vault/KMS for per-universe BYO credentials

_Clean rerun (the research report's section-3 tail was corrupted). Original title: "Phase‑2 per-universe BYO credential storage — Windows 11"._

**Freshness:** 2026‑07‑16. All linked sources were accessed 2026‑07‑16. Local baseline: [`credential_vault.py` at branch tip](https://github.com/Jonnyton/TinyAssets/blob/21ee0177ec4327ffe2cd8e3b14f79ab7a61792f1/tinyassets/credential_vault.py).

## Executive judgment

Use a small, Windows-only credential broker backed directly by **current-user DPAPI**. Store each DPAPI ciphertext in the daemon identity’s private `%LOCALAPPDATA%\TinyAssets\credential-store\v1\` directory, outside every universe/repository/shared artifact. Universe state contains only an opaque random reference plus non-secret provider/scope metadata.

Do not make Python `keyring`, age/SOPS, libsodium, 1Password, or cloud KMS the mandatory Phase‑2 backend. `keyring` is acceptable for short tokens, but not as the uniform store because GitHub App PEM keys have no safe contractual fit within Windows Credential Manager’s size limit. DPAPI is built into Windows, costs $0, accepts byte blobs, manages its own encryption key, provides integrity protection, and normally limits decryption to the same Windows identity and machine. Never set `CRYPTPROTECT_LOCAL_MACHINE`, because that permits any account on the machine to decrypt. [`CryptProtectData`](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)

This protects copied disks/files/backups and prevents secrets entering shared artifacts. It does **not** protect against compromise of the daemon account or code already running as that account; such code can invoke DPAPI too.

## Options surveyed

| Option | 2026 finding | Verdict |
|---|---|---|
| Direct DPAPI | User-scoped, same-machine protection; no application master key; built-in MAC; unattended mode can use `CRYPTPROTECT_UI_FORBIDDEN`. | **Standard backend.** |
| Python `keyring` / Credential Manager | `keyring`’s preferred Windows backend is `WinVaultKeyring`, using generic Windows Credential Manager entries and UTF‑16 password text. [`Windows.py`](https://github.com/jaraco/keyring/blob/main/keyring/backends/Windows.py) Generic credentials have a 2,560-byte blob ceiling. [`CREDENTIALW`](https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw) Thus the effective text ceiling is roughly 1,280 UTF‑16 code units. GitHub supplies a PKCS#1 RSA PEM whose size is not promised to fit. [`GitHub private keys`](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/managing-private-keys-for-github-apps) | Optional for small tokens only; reject as the uniform backend. |
| `age` / SOPS | Sound authenticated file encryption, but SOPS’ Windows age backend expects a long-lived identity such as `%AppData%\sops\age\keys.txt`; custody merely moves to that key. [`SOPS`](https://github.com/getsops/sops), [`age format`](https://age-encryption.org/v1) | Good for Git-managed encrypted configuration, unnecessary for a local runtime broker. |
| libsodium sealed boxes | Encrypts to a recipient public key, but TinyAssets must still protect the recipient private key; sealed boxes also do not authenticate the sender. [`libsodium`](https://doc.libsodium.org/public-key_cryptography/sealed_boxes) | Crypto primitive, not a credential store. |
| 1Password CLI | Good optional operator backend; `op` supports opaque references and least-privilege service accounts. Unattended use bootstraps through `OP_SERVICE_ACCOUNT_TOKEN`, itself a secret, and requires a 1Password account. [`CLI service accounts`](https://www.1password.dev/service-accounts/use-with-1password-cli), [`pricing`](https://1password.com/pricing/password-manager) | Keep for repo/operator secrets; optional adapter/import source, not hard-$0 default. |
| Cloud KMS/Vault | Strong centralized custody and sign-only keys. | Excluded by the stated hard-$0/local requirement. |

Python’s present `chmod(0o600)` is not a Windows security boundary: Windows `os.chmod` only controls the read-only flag; other permission bits are ignored. [`os.chmod`](https://docs.python.org/3/library/os.html#os.chmod)

## Minimal interface and record shape

```python
class SecretStore(Protocol):
    def put(self, scope: SecretScope, value: bytes) -> SecretRef: ...
    def get(self, ref: SecretRef, expected: SecretScope) -> SecretBytes: ...
    def delete(self, ref: SecretRef, expected: SecretScope) -> None: ...
```

- `SecretRef` is an unguessable 128-bit-or-larger identifier such as `secret:v1:<random>`; it encodes no path, token, username, or provider account.
- `SecretScope` binds `founder_id`, stable `universe_id`, credential kind, provider, destination, and purpose. Authorization is checked before DPAPI decryption and rechecked against the protected envelope afterward.
- The protected plaintext envelope contains schema version, ref, scope, creation/version metadata, and raw secret bytes. DPAPI’s MAC detects ciphertext tampering; envelope checks detect cross-universe/ref swapping.
- One immutable DPAPI blob per ref; no mutable vault index. Write encrypted bytes to a unique same-directory temporary file, flush, then `os.replace`.
- Rotation is `put(new) → atomically change the non-secret binding → delete(old)`. Provider revocation remains mandatory; deleting a local file is neither provider revocation nor guaranteed SSD/backup erasure.
- On startup, run a write/read/delete probe under the daemon’s final Windows identity. Missing DPAPI support, wrong account, corrupt/missing blob, scope mismatch, or ACL failure raises a typed `CredentialUnavailable`; never return `""`, `None`, or fall back to ambient/global credentials.
- Restrict the store directory’s DACL to the daemon/current-user SID and SYSTEM. Use user-scoped DPAPI under exactly the identity that runs the tray/service; an identity change requires re-deposit.
- Logs, receipts, MCP responses, exceptions, metrics, and shared state may contain only ref, kind, scope summary, timestamps, and success/error class—never secret values or reversible fingerprints.

## GitHub custody

Prefer a GitHub App over PATs for durable automation. GitHub explicitly directs long-lived integrations toward Apps and recommends fine-grained PATs over classic PATs when a PAT is unavoidable. [`PAT guidance`](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)

For an App:

1. Store only the BYO App’s non-expiring PKCS#1 private key under DPAPI. It is the crown-jewel credential and must be manually rotated/revoked; GitHub supports overlapping keys for rotation. Never distribute a platform-owned App private key into per-universe stores.
2. At job start, sign an RS256 App JWT with expiration no more than ten minutes. [`JWT rules`](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app)
3. Mint an installation token restricted again to the required repository IDs and permissions. It expires after one hour; cache only in process memory and never persist it. [`Installation tokens`](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app)
4. Treat token text as opaque. GitHub began rolling out the `ghs_APPID_JWT` installation-token format on 2026‑04‑27, so length or “40-character token” assumptions are already invalid.
5. Use a user access token only when the action must be attributed to the founder. Expiration is enabled by default unless opted out: access token 8 hours, refresh token 6 months. Refresh returns a new pair and immediately invalidates the old refresh token and access token, so serialize refresh per ref and commit the replacement atomically. [`Refresh lifecycle`](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/refreshing-user-access-tokens)
6. PAT fallback: accept only a fine-grained, selected-repository, minimum-permission token with an expiry; clearly mark it as a long-lived bearer credential.

## What replaces/deletes the Phase‑1 scheme

- Delete secret-valued `token`, `access_token`, `*_b64`, OAuth bundle, and PEM fields from `.credential-vault.json`.
- Delete base64 decoding as “vault” behavior; base64 is transport encoding, not encryption.
- Delete POSIX `chmod` as the Windows protection mechanism.
- Delete plaintext `.credentials/` materialization and fixed-name plaintext temporary files.
- Delete whole-JSON read/modify/write, process-local “atomicity” locks, and shared `.tmp` names.
- Delete silent missing-vault-as-empty behavior and every fallback to host/global auth.
- Delete persistence of minted GitHub installation/access tokens; retain only the root credential needed to mint them.
- Keep only non-secret credential bindings and the existing provider/destination/purpose policy model; secret storage and authorization remain separate.

Migration must be an explicit local command: read one legacy record, DPAPI-store it, verify retrieval, atomically replace the artifact with its ref, then remove plaintext remnants. Any secret ever committed, synchronized, logged, or backed up in the old format must be revoked or rotated at its provider.

## Classic hand-rolled-vault failures to prevent

- Treating base64, hidden filenames, private repositories, or `chmod` as encryption.
- Storing an AES/age/libsodium master key beside the ciphertext—or in an inherited environment variable—so one compromise obtains both.
- Reusing nonces, omitting integrity/authenticated scope, or inventing cryptographic formats instead of using DPAPI.
- Authorizing possession of a ref rather than checking founder, universe, provider, destination, and purpose.
- Failing open to an ambient PAT, subscription login, or process-global token when lookup/decryption fails.
- Leaking through logs, exception representations, test fixtures, argv, environment dumps, fixed temporary files, crash reports, or secret-bearing summaries.
- Racing JSON rewrites or one-time OAuth refreshes, losing the newest credential, and silently resurrecting an older one.
- Confusing local deletion with remote revocation, secure erasure, or completed rotation.
- Assuming at-rest encryption protects a live compromised daemon account.

## Required Phase‑2 proof

Test exact-byte round trips including a real generated GitHub-format RSA PEM; wrong Windows user/machine; missing backend; corrupt, truncated, swapped, and missing blobs; concurrent put/get/delete/rotation; crash injection around replacement; legacy migration; and canary-secret scans across universe artifacts, Git history, logs, argv, child environments, temporary directories, and status/MCP responses. No clean failure may cause ambient-credential fallback.
