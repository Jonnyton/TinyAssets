# Design: target architecture

*Revision 2, 2026-10-02.* This revision folds in the cross-family refute (gpt-6-astra, round 1: **ADAPT**, Appendix R). It also adds the on-disk layout agreed with `command-center-cutover` (D8a). Raw measurements are in `evidence.md`.

## Context

**What production looks like today** (`origin/main` `55a526ff`, read 2026-10-02):

- **Host.** One droplet in DigitalOcean sfo3: `s-4vcpu-8gb`, Debian 12, kernel 6.1. It reports `/dev/kvm`, `kvm_intel nested=Y` and `vmx`.
- **One daemon container serves everything:** the MCP and app API, the scheduler, the agent turns, the provider jails and the tool jails.
- **One process writes `agent_turns`.** `storage/agent_turn_boot.py:28` pins this invariant, and `tests/test_orphaned_turn_reconcile.py` holds it. Startup reconciliation (`universe_server.py:4369`, `agent_turn_reconcile.py:100`) settles any turn this boot did not create.
- **State is SQLite plus files** on one volume under `/data`. Each universe is a host directory, `/data/<universe>/`, and it mixes the agent's files with hidden platform state: the vault, the run, consent, usage and attention databases, and locks.
- **Isolation is per-call bubblewrap** on the shared kernel: `universe_tools.py` for the four tools, `provider_jail.py` for CLIs. #4245 adds a shared seccomp denylist.
- **Credentials.** HTTP model calls already run credential-blind. The generic connector calls an owned broker process bound to the exact owner, connection and grant (`providers/api_key_http_provider.py:354-362`). CLI launches materialise a per-launch credential snapshot.
- **Concurrency limits are global:** 4 runs per host (`runs.py:5597`) and 4 tool slots (`universe_tools.py:173`).
- **Daemon reads of universe files** go through `universe_files.py`, with O_NOFOLLOW per component and a size bound. #4247 widens its ratchet to the ~350 remaining sites.

**Approved direction.**

- Founder, 2026-10-01, on the sealed box: "approved, go with the sealed box design".
- Founder, 2026-10-02, on the target shape now: "move towards the architecture and dependencies we want later sooner rather than later… do things correct the first time".

**What this design is.** It fixes the final interfaces and where every piece of data lives. Capacity is what scales later.

## Goals / Non-Goals

**Goals:**

1. **One shape for every account and every stage.** Stages change capacity behind fixed interfaces, never code paths ("all accounts, one code path"; PLAN "Phased rollout — explicitly rejected").
2. **The cross-user floor is held by construction:**
   - a separate kernel per command center;
   - a per-box hard disk bound;
   - no daemon access to box contents through host paths;
   - no platform state inside a box;
   - no cross-tenant host uid;
   - every box operation authenticated to its owning account.
3. **Cost scales with work, not with registered users.** Boxes are suspended unless acting; idle users cost storage only.
4. **Uptime:**
   - deploys without request failures;
   - continuous off-region durability for platform state;
   - a fenced standby;
   - a recovery drill that actually runs.
5. **Least-privilege secrets per process.**

**Non-Goals:**

- **More than one cell or box host now.** The seams exist. A second cell (and the cell-move protocol, D10) is built when its capacity trigger fires; that is capacity work, not an interface change.
- **The Postgres vendor.** Self-hosted versus managed is S10's spend decision.
- **MCP tool surface changes.** The seven canonical handles are unchanged.
- **Private-content custody** (PLAN carve-out 2).
- **Serving a Claude subscription server-side** for anyone but its owner (D6).
- **A compute-hour budget.** Today's founder rule is storage + seats. D9 adds metering only, and the budget is a founder decision.

## Architecture

```
               tinyassets.io (Cloudflare: DNS, Worker router, tunnel)
                          | signed cell claim -> cell c0 (only cell today)
+----------------------------- CELL (always on) ------------------------------------+
| FRONTEND  blue | green   MCP + app API, auth; stateless; replaceable per deploy      |
|     |  (local RPC; queues while the owner hands over)                               |
| EXECUTION OWNER (exactly one, under a generation-fenced lease)                      |
|     thin agent loop, agent_turns writer + reconcile, scheduler/triggers/inbox/      |
|     notifications, outbox pump, metering, storage allocator                        |
| CREDENTIAL BROKER (own process; only holder of the vault key; owner/connection/     |
|     grant-bound requests; OAuth refresh)                                            |
| platform state: .platform/ (D8a)  --Litestream--> off-region                        |
+------------------------------|------------------------------------------------------+
                               | BoxProvider RPC (UDS now; mTLS when remote), per-op
                               | auth: cell credential + account + cc + op id + epoch
+------------------- BOX HOST (boxhostd; same machine today) -------------------------+
| one sealed box per command center: Firecracker via jailer (distinct uid) | gVisor    |
| per-box hard disk bound; no NIC; boxd over vsock; awake only while acting           |
| checkpoint manifests bind memory snapshot to disk state; reservation ledger         |
| box backups from quiesced/suspended images --restic, per-account key--> off-region   |
+-------------------------------------------------------------------------------------+
standby cell + standby box host in a second region: connectors stopped, restoring;
promoted only after BOTH primary hosts are fenced.
```

## Decisions

### D1. One sealed box per command center; Firecracker primary, gVisor fallback

- **What a box is.** Every command center gets exactly one box with its own kernel boundary, a hard disk bound and no network interface.
- **What runs in it.** The box holds the command center's user content (D8a). Every tool call and every CLI run on its behalf executes inside it.
- **Agents.** Several agents of one command center share its box. The floor is cross-user, not per agent (memory `the-floor-is-cross-user-only`).
- **Drivers.**
  - **Firecracker with snapshot/restore is primary.** It gives a hardware VM boundary, and its lazy restore means a woken box pays only for the memory it touches (E3).
  - **gVisor (rootful runsc, systrap) is the fallback** behind the same contract. It needs no KVM, starts in ~50 ms, and frees memory in 5 s. Its restore is eager and cannot run rootless (E4).
  - **The driver is box-host configuration, not a code path.** S0 decides which driver production starts with. The contract suite (S4) runs against both drivers.
- **Rejected:**
  - *OpenShell as runtime:* no snapshot, the VM driver is experimental with gateway-wide sizing, and its placeholder model does not fit subscription CLIs (E5).
  - *Rootless Podman:* shared kernel, and limits fail open without delegation.
  - *Per-call bwrap:* isolation rank 5.

### D2. `BoxProvider`: the only way the platform touches a box

```python
class BoxProvider(Protocol):                       # tinyassets/boxes/provider.py
    # binding is separate from waking: bind never contacts the box
    def bind(self, cc: CommandCenterId, *, account: AccountId, turn: TurnId | None) -> BoxHandle
    def committed_generation(self, h: BoxHandle) -> int     # from boxhostd metadata; works while suspended
    def ensure_awake(self, h: BoxHandle, *, reason: WakeReason) -> None
    # execution lifecycle (idempotent by op_id; a lost reply is resolved by status, never by re-running)
    def start_exec(self, h, op_id: OpId, argv: Sequence[str], *, stdin: StreamIn | None = None,
                   env: Mapping[str, str] = {}, cwd: str = "/cc", limits: ExecLimits) -> ExecId
    def stream(self, h, exec_id: ExecId, *, from_offset: int = 0) -> Iterator[ExecEvent]   # stdout/stderr/exit
    def cancel(self, h, exec_id: ExecId) -> None        # kills the process tree in the box
    def exec_status(self, h, op_id: OpId) -> ExecStatus  # running | exited(code) | unknown_after_restore
    # files (paths are box paths; resolved inside the box)
    def read(self, h, path: str, *, offset: int = 0, max_bytes: int) -> FileRead       # bytes + generation
    def read_many(self, h, paths: Sequence[str], *, max_total: int) -> Snapshot        # one generation
    def write(self, h, op_id: OpId, path: str, data: StreamIn, *, max_bytes: int,
              mode: WriteMode, expect_generation: int | None = None) -> FileWrite  # temp + rename in box
    def download(self, h, path: str) -> Iterator[bytes]                                # bounded streaming
    def list(self, h, path: str, *, cursor: str | None = None, limit: int) -> DirPage  # paginated
    def stat(self, h, path: str) -> FileStat | None
    def remove(self, h, op_id: OpId, path: str) -> None
    # whole-box
    def export(self, h, *, profile: ExportProfile) -> Iterator[bytes]   # 'share' (scrubbed) | 'migration' (complete)
    def import_bundle(self, cc, chunks: Iterable[bytes], *, profile: ExportProfile) -> ImportReport
    def usage(self, h) -> BoxUsage          # used bytes, hard bound, generation
    def suspend(self, h) -> None            # checkpoint + stop; idempotent
    def destroy(self, cc, op_id: OpId) -> DestroyReceipt
```

**Authentication of every operation.**
- `boxhostd` authenticates each call with:
  - the cell's credential;
  - the handle's account and command center;
  - the turn, when there is one;
  - the operation id;
  - the box's **placement epoch**.
- It refuses an operation when:
  - the account does not own the command center;
  - the epoch is stale (the box moved or was re-imported);
  - the handle was minted for another command center.
- **A valid handle passed to the wrong turn still fails at the execution boundary.**
- A turn binds its handle at turn start and never looks a box up by name per call.

**Lost replies.**
- `boxd` records each operation's outcome by `op_id` for a retention window.
- A retry with the same `op_id` returns the recorded outcome and never re-runs it.
- An operation in flight across a host crash reports `unknown_after_restore`, and the turn holds instead of re-issuing it. This is the same rule as the turn journal.

**Cache validity without waking** (fixes refute 1).
- `boxd` keeps a monotonic **change generation**. It is bumped by any write through the API, and by inotify watches on the cache-relevant paths (persona files, `skills/`, `prompts/`), whoever wrote them: a CLI, `bash`, or the API.
- At suspend, `boxhostd` persists the last generation. That makes `committed_generation` answerable while the box sleeps.
- A turn with a warm cache at the committed generation calls `bind`, never `ensure_awake`, so it does not wake the box.

**Transport.**
- Control plane to `boxhostd`: a Unix socket today, mTLS when the host is remote. It is the same RPC.
- `boxhostd` to `boxd`: vsock (Firecracker) or host-uds (gVisor). It reconnects after every restore, because vsock connections close on restore (Firecracker snapshot docs).
- Framing: length-prefixed JSON headers plus raw byte frames. `exec` takes argv, never a command string.

**No host-path access.**
- Box images, snapshots and the reservation ledger live under `<boxes>/`, owned by the `boxhostd` uid with mode 0700.
- The daemon runs as a different uid, so it cannot open them.
- A ratchet test fails any daemon-side open of command-center content outside `BoxProvider`. This is the by-construction close of #4244.

### D3. Disk: per-box hard bound for the floor; logical account quota; physical reservation for the host

The original "sum of allocations = quota" design was wrong in two ways (refute 2). Sparse holes could exhaust the host without a grow request ever being made, and empty reservations consumed the quota. The replacement separates three concerns.

**1. Per-box hard bound (the cross-user floor, by construction).**
- Each box's filesystem has a hard size: on Firecracker, the ext4 image size; on gVisor, an XFS project quota.
- A full box sees `ENOSPC` inside itself and affects nothing else.
- Images are fresh sparse files, which gives zero-on-allocate (the Cloudflare cross-tenant storage lesson).
- The bound starts at `used + headroom`, where headroom is the smaller of 1 GiB and the account's remaining quota.
- It grows online through the documented Firecracker sequence: grow the backing file, `PATCH /drives` rescan, then `resize2fs` in the guest. S5 validates this against the pinned version.
- Shrinking happens only through offline compaction (export, then import).

**2. Logical account quota (the `account-storage-quota` semantics, unchanged).**
- Account usage = the **used bytes** of each box (from `boxd` statfs, not its bound) + the user-attributable platform bytes that change already counts (run records, checkpoints, upload custody). Platform runtime stays excluded.
- At the quota, new user-driven writes are refused visibly with the inline Upgrade link, and box bounds stop growing.
- **Accepted overshoot.** Several awake boxes of one account can together overshoot by at most `headroom × (awake boxes − 1)`. That error is per account, never cross-user, and it is corrected at the next grow or wake. The quota is a usage limit, not a floor invariant.

**3. Physical host reservation (no overcommit of guaranteed space).**
- `boxhostd` keeps a durable reservation ledger: the sum over boxes of their bounds, plus snapshot space, plus the writable rootfs layer, plus a floor.
- That sum must fit the host's free space.
- A grow is **reserve, then resize, then confirm**, and is idempotent by `op_id`. On startup, `boxhostd` reconciles the ledger against the actual image sizes.
- A grow that would breach the floor is denied (the box hits its own `ENOSPC`) and pages.
- Because bounds track usage plus headroom, the reservation tracks real usage, not quotas.

**Fencing.** A box host acts on a box only while it holds that box's current placement epoch, which the cell issues. After reassignment, an old host refuses to start or write the box.

### D4. Lifecycle and checkpoints

```
 absent --create--> cold --ensure_awake--> booting --> awake
 suspended --ensure_awake--> restoring --> awake
 awake --(no op in flight for idle_s)--> checkpointing --> suspended
 any --destroy--> absent
 host crash while awake  --> cold   (disk is newer than any memory checkpoint)
```

**Idle and timers.**
- `idle_s` defaults to 30 s and can be configured up to 60 s.
- A box has no timers or cron. In-box background processes freeze at checkpoint and continue on the next restore.

**Checkpoints** (refute 3).
1. At suspend, `boxhostd` pauses the VM, asks `boxd` to `sync` and freeze the filesystem, then takes the memory snapshot.
2. It **merges the diff into the base** using the release's `rebase-snap`, so a restore always loads one memory file.
3. It writes a **checkpoint manifest** binding that memory file to the disk image's content hash and generation.
4. On resume, the image is marked **dirty**. A restore is allowed only from a manifest whose disk hash still matches.
5. A dirty image (the host crashed while awake) **cold-boots** from disk. Memory state is lost and the turn reconciles.

**Restore numbers (E3):** 31–51 ms to resume; running at 52–166 ms; RSS 15–22 MiB after restore.

**Memory ceiling:** 1 GiB, 512 MiB for tools-only boxes. It is a ceiling, not a reservation: the balloon and free-page reporting return memory.

**Admission.** A **seat** is one concurrently running agent turn of the account, as today. At host capacity, a wake **waits** in the box host's FIFO admission queue and is never refused (founder 2026-09-30). The waiting state is visible.

### D5. Network and credentials: the existing broker, extended; no TLS interception

**No NIC in any box.** Egress goes to one socket: vsock (Firecracker) or host-uds (gVisor). The cell's egress floor applies unchanged:
- globally routable destinations only;
- no metadata, private or loopback addresses;
- SMTP ports refused;
- a per-box connection cap.

**The credential broker is the one privileged process.** It holds the vault decryption key. It builds on today's broker (`api_key_http_provider.py:354-362`), which already binds every request to the exact owner, connection and grant, and owns:
- **Requests for the loop.** The loop sends owner-, connection- and grant-bound requests. The broker performs the HTTPS call to the connection's endpoint itself (its own TLS, with upstream certificate validation), streams the response back, and propagates cancellation.
- **OAuth refresh and rotation.** These follow the existing single-flight refresh requirement (`credential-vault` "One Shared Single-Flight Credential Refresh"): serialised refresh, re-read under locks, atomic write-back. Revocation and refresh failure report as sign-in failures.
- **A credential-management interface** for deposit, rotate and revoke, called only by owner-authorised platform actions.

**API-key CLIs in a box.** The CLI's base URL points at a **broker endpoint exposed inside the box** over the egress socket. Examples: `ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL`.
- The endpoint is plain HTTP inside the box's private channel.
- The broker authenticates the box by its socket, and the connection by the CLI's configured connection id.
- The broker adds the key and makes the upstream TLS call.
- So **no per-cell CA and no TLS interception** are needed (refute 4). Pinned-certificate CLIs are unaffected, because they talk to the broker, not the upstream.

**File-OAuth CLIs (e.g. Codex login).**
- These must hold and refresh their own token file. It is stored in `.platform/cc-<ulid>/.credentials/` (D8a).
- It is materialised into **that** box for the launch, and copied back through the broker after the run.
- This is the one sanctioned case of a real credential inside a box process, scoped to its owner's box and its run.

**Streaming and WebSockets.** v1 supports request/response and streamed responses (SSE/chunked) with backpressure and cancellation. An upgrade (WebSocket) is supported only for connection protocols that declare it. Redirects are followed only within the connection's declared hosts.

### D6. A thin vendor-neutral loop; CLI in a box only where the credential needs it

**The loop:**
- It runs in the **execution owner** (D11), as asyncio tasks.
- It speaks the standard model protocols through the broker (D5).
- It holds a waiting turn as a coroutine plus a stream plus its context buffer, estimated at ~1 MB; S7 measures it.
- It never executes model output. It forwards each tool call over the turn's bound handle with an `op_id`.

**Effects.** Box memory per awake agent drops from 338–525 MiB (CLI in box) to the tools-only footprint, estimated at 80–130 MiB, and no model credential is in the box (Anthropic's Managed Agents split: p50 TTFT −60%).

**CLI in a box stays for:**
- command adapters (any binary);
- file-OAuth CLIs;
- the Claude subscription CLI, behind the **owner-scoped** `claude_subscription_serving` setting. It defaults off, only the owner's own command center may turn it on, and that is the founder's TOS decision (memory `anthropic-forbids-third-party-subscription-oauth`).

One CLI process never serves two accounts.

**The turn journal keeps its single-writer invariant.** Only the execution owner writes `agent_turns`, and reconciliation runs only after it acquires the lease (D11). After a failover or host crash, an interrupted turn reconciles into a held state. Its unknown-outcome operations stay unknown (D2), and nothing replays.

### D7. The control plane is the only always-on layer

- **Under the execution owner's lease:** the scheduler, the trigger table, the inbox, notifications, the outbox pump, metering and the storage allocator.
- **Coalescing:** one pending run per trigger.
- **Engagement-decayed proactive cadence:** 4/day while engaged, 1/day after a week, weekly after a month, reset on the next interaction. That puts the dormant duty floor at ~0.1%.
- A box is woken only by the control plane.
- The platform-visible record per command center lives in `.platform/`: schedule, routing, unread and notification metadata, quota counters and the activity line. Listing, scheduling and notifying never wake a box.

### D8. Data placement

| Data | Home | Store | Backup |
|---|---|---|---|
| Command center user content | **inside the box** (D8a dir 1 becomes the disk image) | files | restic from quiesced/suspended images only (D11), **per-account encryption key**, off-region |
| Box memory state | box host | Firecracker checkpoint (merged) + manifest | not backed up; cold boot rebuilds |
| Vault + file-OAuth CLI credentials | `.platform/cc-<ulid>/` | encrypted; key only in the broker | Litestream/restic, encrypted, per-account key |
| Per-command-center platform state (D8a dir 2) | `.platform/cc-<ulid>/` | SQLite + files | **Litestream v0.5** off-region (RPO ~1 s); restic for files |
| Per-account platform state (D8a dir 3) | `.platform/accounts/<id>/` | SQLite | Litestream |
| Catalog, ledger, inbox, market | shared | **Postgres** (PLAN 2026-07-25) | managed PITR or pgBackRest, off-region |
| Commons (OKF bundle) | shared | files (canonical) + rebuildable index | restic |
| Identity map (subject → user → home cell, ownership generation) | shared | Postgres | as Postgres |
| Root databases (`.tinyassets.db`, `.runs.db`, …) | cell root | SQLite (renamed by the cutover) | Litestream |

**Rules.**
- **The platform never trusts box content.** It reads it only through `BoxProvider`, as untrusted input (memory `daemon-reads-universe-files-as-untrusted`).
- **SQLite ≥3.51.3 in every image**, pinned before Litestream is turned on.
- **Each outbox sits beside its cause** (refute 5). An effect bound for Postgres is written to an `outbox` table **in the same SQLite database, and the same transaction, as its cause**. The pump delivers at least once. The Postgres consumer applies idempotently, deduplicating on `(origin store, outbox id)` with a unique constraint. "Exactly once" is not claimed across an asynchronous failover: an effect whose acknowledgement was lost reconciles into an unknown/held state.

**Hot-path cache.**
- Persona grounding, the skills index and prompts are read with `read_many` at one generation and cached by `(cc, generation)`.
- A turn compares the cache with `committed_generation`, which needs no wake (D2).
- The activity line is platform state.

**The #4247 ratchet maps directly.** `universe_files.py` becomes the **local driver** of `BoxProvider.read/read_many/list/stat`. Its ratchet becomes "no daemon read of command-center content outside `BoxProvider`". The ~350 call sites move once (S3), and switching the driver to a box (S11) changes nothing at those sites.

### D8a. Target on-disk layout (agreed with `command-center-cutover`, 2026-10-02)

*This section is shared with `openspec/changes/command-center-cutover` (PR #4262, rename-cc). Both changes cite it. The cutover moves data straight into this layout, so the storage migration runs **once**. After the cutover, S11 turns directory 1 into a disk image. That is an image build, not a second layout migration.*

**Rule:** anything the daemon **trusts** goes in the platform directories: authority, identity, owner settings, records. Anything the person or their agent may write is **user content**, and the daemon treats it as untrusted.

```
data_dir()/
  cc-<ulid>/                      1. USER CONTENT = the future box volume (box path /cc)
  .platform/
    cc-<ulid>/                    2. per-command-center platform state (daemon-only)
    accounts/<account_id>/        3. per-account platform state (daemon-only)
  .tinyassets.db, .runs.db, ...   4. root databases (unchanged location, renamed schema)
```

| # | Directory | Holds | Never holds |
|---|---|---|---|
| 1 | `cc-<ulid>/` | The agent-owned brain files (`identity.md`, `founder.md`, `origin.md`, `body.md`, `orgchart.md`, `projects.md`, `goals.md`, `index.md`, `log.md`, `voice.md`, `AGENTS.md`). The harness dirs (`skills/`, `prompts/`, `extensions/`, `workflows/`, `bin/`, `notes/`, `wiki/`). Upload **bytes**, verbatim (Hard Rule 9). Files a run or the agent wrote into the folder. Permanent workspace generations. Anything else the agent creates | anything the daemon trusts |
| 2 | `.platform/cc-<ulid>/` | Credentials: the vault, file-OAuth CLI credentials (`.credentials/`). Per-home databases: runs, consent, usage, attention, conversation custody and session journals, checkpoints. Records: rules, auto-review, activity, pending effects, proposals, import quarantine, the browser profile. Identity and coordination: the id marker (`.command_center_id`), lease/seat/slot/lock/stamp state, the egress socket (formerly `.universe-sidecars/<id>/`). Upload **custody** records. **Owner-door files the agent must not write: `soul.md`, `config.yaml`** | agent-writable content |
| 3 | `.platform/accounts/<account_id>/` | The storage ledger (D3), the compute meter (D9), seat state | — |
| 4 | root DBs | Unchanged except for the rename. S10 moves catalog, ledger, inbox and market to Postgres. Per-account rows move behind `store_for(account)` in their own slice | — |

**What the agent may read but must not write** (`soul.md`, `config.yaml`, conversation history) reaches the box as a **read-only projection**, refreshed at wake. The daemon never reads the projection back.

**Resolvers:** one module owns all three paths: `command_center_dir(id)`, `platform_dir(id)` (`PlatformStatePaths`, I2) and `account_platform_dir(account_id)`. A test fails on any hand-built path.

### D9. Usage limits: storage + seats (unchanged); compute metering; budget is the founder's call

- **The founder rule stands:** account limits are storage GiB and concurrent seats, and work waits and is never refused (memory `usage-limits-are-storage-and-seats`).
- **This change ships metering only.** Box awake seconds, weighted by memory ceiling, give an operational measurement of cost per account.
- **Not built until the founder decides:** a monthly priority compute-hour budget with a spare-capacity lane. Box-cost research §F.3 proposes it, and it would change the two-dimension rule.
- **Admission fairness, stated measurably** (refute 7). Host-capacity admission is **FIFO across accounts**. One account can occupy at most its seats' worth of concurrently awake boxes. A run within its seats is admitted no later than any later-arriving run from another account. Admission bounds concurrency, not the CPU or I/O a running box consumes. Per-box CPU and IO weights (cgroup `cpu.weight`/`io.weight` on the VMM, or gVisor's equivalents) bound noisy neighbours, measured in S5's co-tenancy test.
- **Host admission replaces** `TINYASSETS_RUN_MAX_CONCURRENT` and `_HOST_SLOTS`.

### D10. Cells: the seam now, one cell, the move protocol specified

- **A cell** is one control plane plus its box host capacity. All of a user's command centers live in the user's `home_cell`.
- **The seam, built now in S10:**
  - `home_cell` on the account, and a signed cell claim minted at sign-in;
  - the edge routes by the claim, with one target today;
  - an **ownership generation** in the identity map, so a request or claim with an older generation is refused;
  - **ingress dedup** by idempotency key;
  - the beside-the-cause outbox (D8).
- **Export profiles (refute 5).**
  - `share`: harness §4.17. Scrubbed, credentials excluded, owner-selected memory.
  - `migration`: complete private state, re-encrypted credential custody, pending work, dedup history and ownership metadata.
  - They are one container format with distinct profiles. Only `share` is user-facing.
- **The move protocol (I13).** It is specified now and built when the second cell's trigger fires:
  1. close the account's admission;
  2. drain and fence its turns;
  3. suspend its boxes (consistent checkpoints);
  4. snapshot its SQLite stores with the backup API, at one admission-closed point;
  5. transfer in the `migration` profile and import;
  6. **flip `home_cell` and bump the generation atomically** in the identity map;
  7. reopen.

  Writes cannot land between the snapshot and the flip, because admission is closed.

### D11. Uptime: one execution owner behind replaceable frontends

Refute 6 is the blocker this section fixes. Two daemons writing `agent_turns` breaks `agent_turn_boot.py`'s invariant: green's startup would settle blue's live turns before traffic switched.

**The control plane splits into two roles:**
- **Frontend** (MCP and app API, auth, streaming to clients). It holds no turn ownership, and its deploy is blue-green.
- **Execution owner** (the loop, the `agent_turns` writer and reconciliation, the scheduler, triggers, the outbox pump, metering, the allocator). There is exactly one at a time, under a **lease fenced by generation**.
- Frontends forward turn starts and cancellations to the current owner over local RPC. While the owner hands over, frontends **queue** requests. They wait and are never refused.

**Owner handover:**
1. The new owner starts in standby.
2. The old owner drains: it stops admitting turns, finishes in-flight turns up to the drain bound, journals the rest, cancels outstanding box executions with `cancel` and records their `op_id`s, then releases the lease.
3. The new owner acquires the lease at generation+1, runs reconciliation (now safe, because the old owner is gone), and serves the queue.
4. Every owner-side mutation checks the lease generation, so a stalled old owner cannot write after losing it.

**Measured target:** zero failed requests per deploy; queueing visible as latency. The restart-gap probe (5-second resolution) is evidence, not proof; request-level errors are the metric.

**Schema-changing cutovers are a declared maintenance exception.** Rename D7/C4b needs an exclusive migration, and so does S11. These run in announced freeze windows under the cutover's exclusion protocol. That protocol now covers both frontend colours, the owner, `boxhostd`, Litestream and the backup workers.

**Warm standby, second region:**
- A standby cell host and box host. Their connectors are stopped. They restore Litestream continuously, and restore box disks from restic on first wake.
- **Promotion fences every primary execution host:** the cell host **and** the box host, if separate. They are powered off through the provider API with CI-held credentials and blocked from auto-restart.
- If fencing cannot be confirmed, promotion stops and pages. Failback is manual.
- **Promotion also restores:** the broker's vault key (from the founder-held key escrow; S1 defines it) and Postgres (PITR to the standby region).

**Recovery points:**
- platform state ~1 s;
- box files: the last box backup (default ≤1 h, plus at suspend when dirty);
- box memory is lost, so boxes cold-boot.

**Recovery times, stated separately (refute 3):**
- **API availability** ≤5 min after detection;
- **a given command center usable**, meaning its image is restored on first wake. That time is size-dependent and is measured in S5, not promised here.

**Consistent box backups.** Backups are taken only from **suspended** images, or for a box awake longer than the interval, from a brief `boxd` filesystem freeze plus a reflink copy (the box-host filesystem is XFS with reflink). restic reads the immutable copy.

**DR drill.**
- It is **weekly and scheduled**, and restores into a fresh host **from off-region copies only**.
- It uses a fresh template environment with the pinned image. It never copies the primary host's environment or secrets (existing `uptime-and-alarms` requirement).
- It asserts the canary goes green and that sampled boxes match their content checksums. A failure pages.

### D12. Deletion, export, migration

**Account deletion keeps today's semantics** (`account_deletion.py:199`, refute 5).
- The schema-derived deletion set decides what goes.
- Command centers the person owned that **survive** them keep their box, with the opaque-fingerprint owner. Only command centers the deletion set deletes are `destroy`ed.
- Destroying removes the image, the checkpoints and the backup set.
- **Backups are crypto-shredded.** Each account's backup data is encrypted under a per-account key, and deletion destroys that key. Platform replicas (Litestream, standby copies) receive the deletion through normal replication.
- A **tombstone list** of deleted accounts is checked by every restore, so an old backup cannot resurrect them.
- Deletion completes when every destroy receipt and the key destruction are recorded.

**Export (harness D11 / §4.17).** `BoxProvider.export(profile="share")` plus the manifest-selected platform records.

**Migration from shared `/data/<universe>`** runs in one window (D8a):
- **The `command-center-cutover` (#4262)** moves data straight into the D8a layout, so platform state lands in `.platform/` and user content in `cc-<ulid>/`. That delivers S2's moves.
- **S11 then builds each box image from `cc-<ulid>/`.** It copies regular files only, refusing links and special files, verifies counts and hashes through `BoxProvider`, and flips `box_epoch`. The source stays read-only until the drill passes.
- **Backup:** a pre-run volume snapshot plus restic off-region.
- **Rollback:** before the flip, nothing changed. After the flip, redeploy the previous image with the snapshot; the C4a layout guard refuses mixed state.

## Interfaces fixed by this change

| # | Interface | Module (target) | Local implementation now | Scaled implementation |
|---|---|---|---|---|
| I1 | `BoxProvider` (D2) | `tinyassets/boxes/provider.py` | `boxhostd` on the same host (UDS) | remote box hosts (mTLS) |
| I2 | `PlatformStatePaths` + `command_center_dir` + `account_platform_dir` (D8a) | `tinyassets/platform_state.py` | `.platform/…`, `cc-<ulid>/` | same, per cell |
| I3 | Thin loop in the execution owner (D6, D11) | `tinyassets/agent_loop/` | one owner process | one per cell |
| I4 | `home_cell` + signed claim (D10) | `tinyassets/cells.py` | constant `c0` | edge-routed cells |
| I5 | `store_for(account)` | storage factories | per-account SQLite | same, per cell |
| I6 | Export profiles `share` / `migration` (D10, D12) | `tinyassets/export_bundle/` | share from box | migration for cell moves |
| I7 | `TransactionalStore` | `tinyassets/txstore/` | one Postgres | Postgres HA |
| I8 | Owner lease + scheduler/triggers (D7, D11) | `tinyassets/scheduler/` | one owner | per cell |
| I9 | Release state + health per role/origin | `scripts/deployed_sha.py` | per colour + owner | per cell |
| I10 | Ingress dedup + cursors | request-idempotency store | local SQLite | per cell |
| I11 | Ownership generation | identity map (Postgres) | generation 1 | bumped on move |
| I12 | Beside-the-cause outbox + idempotent consumer | each SQLite store + Postgres | in-process pump | same |
| I13 | Cell move protocol (D10) | `tinyassets/cells.py` | specified, not built | built at the second-cell trigger |
| I14 | Credential broker (D5) | `tinyassets/broker/` (extends today's owned broker) | own process | per cell |
| I15 | Box placement epoch + reservation ledger (D3) | `boxhostd` | one host | N hosts |

## Spec reconciliation owed (existing requirements the slices modify)

The umbrella's delta specs sync only when this change archives, after S11. Each slice that changes as-built behaviour MODIFIES or REMOVES the existing requirement **in its own change**, so the main specs never contradict as-built:

| Existing requirement | Owner slice | Change |
|---|---|---|
| `uptime-and-alarms` "Nightly Two-Tier Backup And Manual Fresh-Host Data-Restore Drill" | S1 (platform state), S5 (boxes) | MODIFIED: scheduled drill from off-region copies, Litestream tier, box sample. The no-secret-transfer and archive-validation clauses are kept |
| `credential-vault` "Per-Universe Provider Auth Env Overlay Without Cross-Universe Leakage" | S6, S11 | MODIFIED: API-key CLIs get a broker base URL instead of the key; file-OAuth materialisation moves into the box. REMOVED at S11 for the bwrap path |
| `credential-vault` "One Shared Single-Flight Credential Refresh" | S6 | kept; the broker becomes its sole caller |
| `credential-vault` "As-Built Storage Protection Is Filesystem Permissions Only" | S6 | MODIFIED: vault key in the broker only |
| `account-deletion` (main spec) | S11 | MODIFIED: destroy receipts, crypto-shred, tombstones |
| `account-storage-quota` (change in flight) | S4/S5 | adds the per-box bound and physical reservation (D3) beside its logical quota |
| `universe-seats` / `two-dimension-usage-limits` | S9 | host admission replaces the global pool; FIFO fairness |

## Slice plan

**How slices ship.** Each slice is delivered as one or more delivery changes. Each change has ≤12 tasks, one owner and one PR, with proposal and design first where it touches storage, authority, migration or money. A slice's checkbox in `tasks.md` ticks when **all** of its changes have landed, deployed, been live-verified and archived. Slices marked **(multi)** are expected to need more than one change.

```
S0 ──────────────────────────┐
S1 (platform durability) ────┼─────────────────────────────┐
cutover #4262 / S2 ──> S3 ──> S4 ──┬──> S5 ──┐              │
                                   ├──> S6 ──┼──> S7 ──┐    │
S8 (owner/frontend split) ─────────┼─────────┘         ├──> S11
                                   └──> S9 <── S5      │    │
S10 (Postgres + seam) ─────────────────────────────────┘    │
S0 ──> S5;  S1 + S5 ──> box-inclusive drill;  S9 ──> S11 ───┘
```

### S0. DigitalOcean nested-KVM validation — **founder spend** (staging droplet ~$0.14)

- **Goal:** decide Firecracker on DigitalOcean nested KVM versus a bare-metal box host. Production is not touched.
- **Setup:** a short-lived `s-4vcpu-8gb` droplet in sfo3 for ~2 h, built by `deploy/hetzner-bootstrap.sh` and destroyed after. A quiet-window production benchmark is the alternative, and needs explicit founder approval.
- **Tasks:**
  1. Move the spike scripts into `scripts/box_bench/` with their versions pinned (`evidence.md`).
  2. Run Firecracker + jailer as its own uid.
  3. Measure cold boot and restore p50/p95, exec RPC p50/p95, and checkpoint time and size.
  4. Measure idle CPU and steal for 10 and 30 awake boxes, plus a 30-box restore storm.
  5. Run the same set on gVisor.
  6. Record the raw results.
  7. Destroy the droplet.
  8. Write the decision.
- **Decision rule:**
  - **Firecracker on DO** if restore p95 ≤ 500 ms, exec p95 ≤ 50 ms, awake-idle CPU ≤ 5% of a core per box, and canary p95 is unchanged with 30 awake boxes.
  - **Otherwise a bare-metal box host:** OVH RISE-S Hillsboro, $77/mo, **founder spend**. gVisor on the droplet serves until it exists.

### S1. Platform-state durability and the warm standby — **founder spend** (bucket ~$0–5/mo, standby $12–24/mo, Cloudflare LB ~$5/mo) — (multi)

- **S1a durability:**
  1. Pin SQLite ≥3.51.3 and assert it at startup.
  2. Run Litestream v0.5 for every SQLite store, to off-region.
  3. Move `BACKUP_DEST` off-region. The GitHub copy keeps the brain tier only.
  4. Restore test, including point in time.
  5. Schedule `dr-drill.yml` weekly, restoring from the off-region copy (MODIFIED requirement, see reconciliation).
  6. Alarms for replication and backup lag.
  7. Define the vault-key escrow.
- **S1b standby:**
  1. Provision the standby through bootstrap, with connectors stopped.
  2. Continuous restore on the standby.
  3. Fence-every-primary-host promotion, using a scoped DO token in CI.
  4. A Cloudflare LB health-check detector.
  5. A promotion drill.
  6. The runbook.
- **Acceptance:** the drill is green from off-region; promotion reaches API-green ≤5 min after detection; RPO is measured.
- The box-inclusive drill lands in S5.

### S2. Platform state out of the universe directory (§4.16, #4258)

- **If the cutover lands first, it delivers S2's moves.** The cutover (#4262) moves data straight into D8a. S2 then shrinks to tasks 4, 5 and 7.
- **Tasks:**
  1. The `PlatformStatePaths` resolver.
  2. Move the D8a dir-2 items through it.
  3. A locked, verified startup migration with backup.
  4. Refuse to open a platform store found inside user content (#4258 attack 3).
  5. Prove no jail mounts `.platform/`, in the Linux oracle.
  6. Fold in `.universe-sidecars`.
  7. Update the deletion set.
  8. Spec sync.
- **Acceptance:** the three #4258 reproductions fail in the oracle.

### S3. One accessor for command-center content, plus the hot-path cache — (multi, one change per module batch)

- **Tasks:**
  1. The `BoxProvider` read-side signatures (`read`, `read_many`, `list` with cursor, `stat`) as a local driver over `universe_files.py`.
  2. Module-batched migrations of the ~350 sites, each its own change.
  3. Ratchet the count to zero.
  4. The generation cache.
  5. A latency check.
- **Acceptance:** the ratchet holds at 0; no turn-latency regression.

### S4. `BoxProvider` complete, `boxd`, gVisor driver, allocator and admission — (multi)

- **Tasks:**
  1. `boxhostd` (own uid, RPC, per-operation authentication, placement epochs, op-id outcome log).
  2. `boxd` (execution lifecycle, files, inotify generation, usage).
  3. The gVisor driver: rootful runsc, a distinct uid/userns per box, `--network=none`, the egress socket over host-uds, and an XFS-project-quota hard bound.
  4. The driver-agnostic reservation ledger and the grow protocol (D3).
  5. FIFO host admission (D9).
  6. The contract suite. It covers path escape, links resolving in-box only, a stale or foreign handle being refused, a lost-reply retry not re-running, cancel killing the tree, and `ENOSPC` at the bound with no effect on a neighbour.
  7. Re-point `universe_tools.RUNNER` and `provider_jail.confine_launch` at `BoxProvider`.
  8. Spec sync.
- **Acceptance:** the contract suite is green on gVisor in CI; a tool loop runs through a box on staging.

### S5. Firecracker driver, host build, box backups, box-host operations — **founder spend if S0 picks bare metal** — (multi)

- **Tasks:**
  1. Firecracker + jailer at a pinned version, one uid per VMM, cgroup CPU/IO weights.
  2. The base rootfs plus a per-box image; images are fresh sparse files.
  3. Checkpoint with merge plus a manifest; restore only on a manifest match, otherwise cold boot.
  4. Idle suspend.
  5. Balloon and free-page reporting.
  6. vsock `boxd` with reconnect.
  7. The online grow sequence, validated.
  8. The box host on Debian 13 with XFS reflink.
  9. Consistent restic backups with a per-account key.
  10. The box-inclusive DR drill.
  11. Box-host operations:
      - metrics: awake boxes, admission wait, reservation headroom, restore p95;
      - a partition and reconnect path;
      - a compromised-host quarantine runbook (fence, rotate the cell credential, re-image);
      - checkpoint compatibility across VMM upgrades: cold boot when versions differ.
  12. A co-tenancy test: one box saturating CPU, memory, disk and egress while a neighbour completes a turn.
  13. Spec sync.
- **Acceptance:** the contract suite is green on both drivers; restore p95 meets S0's rule; the co-tenancy test passes.

### S6. Credential broker extension and per-process secret scope

- Coordinated with the secret-scope lane.
- **Tasks:**
  1. The broker as its own process, the only holder of the vault key, with escrow (S1).
  2. In-box broker endpoints for API-key CLIs (base-URL mode).
  3. File-OAuth materialise and copy-back.
  4. The owner-scoped `claude_subscription_serving` gate, default off.
  5. Credential rotation: per-cell broker credentials, box-socket identities, revoke.
  6. Keep `DO_API_TOKEN`, `STRIPE_SECRET_KEY`, `WORKOS_API_KEY` and `CLOUDFLARE_TUNNEL_TOKEN` out of every process handling tenant input; the broker's exception is narrow and stated.
  7. A `/proc/<pid>/environ` names test per process.
  8. MODIFIED vault requirements (see reconciliation).
- **Acceptance:** no real credential in the loop or in any box process, **except** a file-OAuth CLI's own token inside its owner's box during its run (asserted). API-key CLIs reach their API through the broker endpoint.

### S7. The thin loop

- **Depends on:** S4, S6, S8.
- **Tasks:**
  1. An asyncio loop through the broker in the execution owner.
  2. Bind the handle at turn start, then forward tool calls by `op_id` over `start_exec`/`stream`/`cancel`.
  3. The per-round journal (single writer kept).
  4. Streaming to clients via the frontend.
  5. CLI-in-box for command adapters and file-OAuth CLIs.
  6. Memory per waiting turn: 500 concurrent against a mock SSE server.
  7. A live rendered conversation (`ui-test`).
  8. Retire the per-turn provider jail for HTTP connections.
  9. Spec sync.
- **Acceptance:** live proof; memory measured; cancellation and reconcile work.

### S8. Execution owner + frontends, the lease, the always-on duties, deploys — (multi)

- **This must land before any second writer exists.** It replaces the "independent blue-green" plan that refute 6 broke.
- **Tasks:**
  1. The owner lease with generation fencing, checked by every owner-side mutation.
  2. Reconciliation runs only after the lease is acquired; `test_orphaned_turn_reconcile.py` is extended.
  3. Frontend/owner RPC, with queueing during handover.
  4. The scheduler, triggers, outbox pump and metering under the lease.
  5. Coalescing and cadence decay.
  6. No in-box timers (asserted).
  7. Blue/green frontends behind the local switch.
  8. `deploy-prod.yml`: frontends blue-green, owner handover.
  9. The maintenance-exception protocol for schema cutovers.
  10. A request-level error probe during scripted deploys.
  11. Spec sync.
- **Acceptance:** a scripted deploy loop shows 0 failed requests, no duplicate effects and no live turn settled.

### S9. Admission and metering

- **Founder decision** before any compute budget exists.
- **Tasks:**
  1. Meter box awake seconds weighted by memory ceiling.
  2. Seat and FIFO host admission replacing `TINYASSETS_RUN_MAX_CONCURRENT` and `_HOST_SLOTS`.
  3. A visible waiting state.
  4. Storage refusal when a grow is denied (D3).
  5. Spec sync.
- **Only if the founder adopts it:** a compute-hour budget and spare-capacity lane, as its own change.
- **Acceptance:** FIFO fairness holds under a 20-agent fan-out (measured).

### S10. Postgres domains and the cell seam — **founder spend if managed Postgres** ($15.15–30.30/mo; self-hosted $0)

- **Tasks:**
  1. Inventory which of the four domains exist today.
  2. `TransactionalStore` and Postgres.
  3. A locked, verified migration of the existing domains.
  4. Beside-the-cause outboxes plus the idempotent consumer.
  5. The identity map with the ownership generation.
  6. `home_cell` plus the signed claim plus the Worker route (one target).
  7. Ingress dedup.
  8. Off-region Postgres backups.
  9. Spec sync.
- **Acceptance:**
  - a stale-generation request and a duplicate webhook are refused or deduplicated;
  - a lost-ack outbox delivery applies once.
  - (The cell move itself is I13, built at the second-cell trigger.)

### S11. Cutover: user content into sealed boxes

- **Depends on:** the cutover (#4262) or S2, plus S1, S3, S4/S5 (per S0's decision), S6, S7, S8 and S9.
- **Tasks:**
  1. The derived inventory of `cc-<ulid>/`.
  2. Build the images in a declared freeze window, under the extended exclusion protocol (D11).
  3. Verify each box through `BoxProvider`.
  4. The `box_epoch` flip.
  5. A rollback rehearsal on staging.
  6. Export (`share`) and deletion through `destroy` + crypto-shred + tombstones.
  7. Retire the bwrap jails and the host-path local driver.
  8. Live proof: a rendered conversation using every tool, plus `mcp_public_canary.py --assert-handles`.
  9. `deployed_sha.py --assert-contains`.
  10. Sync the umbrella specs, then archive.
- **Acceptance:** every command center serves from its box; the old paths are gone; the DR drill restores boxes.

## What this supersedes, and the interim hardening

| Interim item | Status |
|---|---|
| #4245 seccomp denylist for the bwrap jails | Kept until S11. Add the measured delta (`evidence.md` E2) only if S11 is more than ~4 weeks out |
| #4247 safe-reader ratchet | Becomes S3; its module becomes the local `BoxProvider` driver |
| #4252/#4253 hidden-file masks | Retired by the cutover/S2 |
| `openat2` helper, per-universe project quota (spike §9) | Not built; D3 and S3 replace them |
| `TINYASSETS_RUN_MAX_CONCURRENT` / `_HOST_SLOTS` | Replaced by S9 |
| `.universe-sidecars/` | Folded into `.platform/cc-<ulid>/` |
| PLAN "Backend stack (target): Supabase" | Postgres stays; the vendor is open (S10) |

## Risks / Trade-offs

- **DO nested virtualization is unsupported.** S0 measures it; gVisor is the fallback behind the same contract.
- **Firecracker host CVEs** (2026-5747, 2026-1386). Mitigations: a pinned version, jailer, seccomp, a uid per VMM, patch cadence, and S5's quarantine runbook.
- **The broker is a high-value process.** It handles requests on tenants' behalf and holds the vault key. Its surface is narrow: owner/connection/grant-bound requests, the box-socket identity, and no execution of content.
- **Checkpoints are CPU-model-bound.** On failover or a VMM upgrade, boxes cold-boot. Memory loss is accepted, and turns reconcile.
- **Box-file RPO is the backup interval.** It is weaker than platform state, and stated.
- **Account quota can overshoot** by bounded headroom (D3). This is per account, never cross-user.
- **Operations labour:** `boxhostd` is our orchestrator. E2B's outage was its orchestrator, so ours stays one process with no external scheduler.
- **The migration touches every user's data.** It runs once (D8a), with backup, verify, rollback and rehearsal.

## Open questions (founder)

1. **S0:** a staging droplet (~$0.14), or a quiet-window production benchmark.
2. **S1:** bucket provider (R2/B2), standby droplet ($12–24/mo), Cloudflare LB (~$5/mo), and the vault-key escrow holder.
3. **S5, if S0 fails on DO:** OVH RISE-S Hillsboro ($77/mo, 12-month term).
4. **S9:** whether to add a compute-hour budget and spare lane to storage + seats.
5. **S10:** self-hosted Postgres ($0) or DO managed ($15.15/$30.30 HA).
6. **D6:** the Claude subscription stays owner-only (founder's command center) unless he decides otherwise.

## Appendix R. Cross-family refute, round 1 (gpt-6-astra, 2026-10-02): **ADAPT**

The disposition of each point is above. In summary:

| # | Finding | Disposition |
|---|---|---|
| 1 | BoxProvider lacks the execution lifecycle, pagination, streaming transfers, bulk reads and cache validation; caching contradicted waking; the handle bound the destination, not the principal | **Accepted.** D2 rewritten: `bind` separate from `ensure_awake`, `committed_generation`, op-id lifecycle, `read_many`, cursors, streaming, per-operation authentication with epochs |
| 2 | Overcommit made the host guarantee false; the allocator was not crash-safe; the quota semantics changed | **Accepted.** D3 rewritten into three concerns: per-box bound, logical quota, physical reservation ledger plus epochs |
| 3 | Diff chain, vsock reconnect, memory/disk mismatch after a crash, inconsistent backups, RTO meaning, box-host fencing | **Accepted.** D4 checkpoint manifest and merge; D11 consistent backups, split RTO, fence every host |
| 4 | Selective TLS interception is unworkable; the existing broker binding was ignored; OAuth refresh had no owner; S6 acceptance contradicted file OAuth | **Accepted.** D5 now builds on the existing broker; base-URL mode for CLIs; no CA; refresh in the broker; S6 acceptance carries the explicit exception |
| 5 | The outbox transaction boundary; export versus migration; consistent moves; deletion semantics; backup resurrection | **Accepted.** Beside-the-cause outbox; `share`/`migration` profiles; the move protocol; today's deletion semantics kept, plus crypto-shred and tombstones |
| 6 | Blue-green breaks the `agent_turns` single writer (`agent_turn_boot.py:28`) | **Accepted, blocker.** D11 adds one execution owner behind replaceable frontends; reconciliation only after the lease; schema cutovers are a maintenance exception |
| 7 | Dependencies (S8, S10, S11, S1/S5, gVisor allocator); D9 broke storage + seats; the fairness claim; oversized slices; missing operations work | **Accepted.** Graph fixed; D9 is metering only, budget a founder decision; FIFO fairness stated; multi-change slices; operations work in S1/S5/S6 |
| 8 | ADDED-only deltas contradict existing specs; drill secret transfer; vault overlay; the broker exception; the gVisor representation; the compute example; exactly-once | **Accepted.** Reconciliation table (owner slices MODIFY in their own changes); PLAN drill wording fixed; specs reworded (driver-neutral bound, broker exception, at-least-once + idempotent apply, metering example) |
| — | Evidence summarised without reproducible reports | **Accepted.** `evidence.md` added with versions, commands and raw results; S0 commits the scripts |
