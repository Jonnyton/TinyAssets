# Design: target architecture

## Context

**What production looks like today** (`origin/main` `55a526ff`, read 2026-10-02):

- **One droplet** in DigitalOcean sfo3: `s-4vcpu-8gb`, Debian 12, kernel 6.1. It reports `/dev/kvm`, `kvm_intel` with `nested=Y`, and the `vmx` flag.
- **One daemon container** serves everything: the MCP and app API, the scheduler, the provider jails and the tool jails.
- **All state is SQLite plus files** on one Docker volume under `/data`.
  - Each universe is a host directory, `/data/<universe>/`.
  - The agent's files and the platform's hidden per-universe state live side by side in it: `.credential-vault.json`, `.runs.db`, the consent, usage and attention databases, lock files.
- **Isolation is per-call bubblewrap** on the shared kernel:
  - `universe_tools.py` runs the four tools;
  - `provider_jail.py` runs provider CLIs, with the universe bound read-write;
  - #4245 adds a shared seccomp denylist.
- **Network:**
  - the tool jail has an empty network namespace plus the checking egress proxy (`universe_egress.py`);
  - the provider jail moves behind the egress floor in #4245.
- **Concurrency limits are global:** 4 runs per host (`runs.py:5597`, `TINYASSETS_RUN_MAX_CONCURRENT`) and 4 tool slots (`universe_tools.py:173`).
- **Daemon-side reads of universe files** go through `universe_files.py` (O_NOFOLLOW per component, bounded). #4247 widens its ratchet to the remaining ~350 sites.

**Approved direction:**

- The founder approved the sealed box (2026-10-01): "every command center is a sealed box that owns its files and disk; the daemon never reads box contents via host paths, only via the box API; tool calls and provider CLIs run inside it".
- He then asked for the target shape now (2026-10-02): "move towards the architecture and dependencies we want later sooner rather than later… do things correct the first time".

**What this design is.** It fixes the final interfaces and where every piece of data lives. Capacity is the only thing that scales later.

## Goals / Non-Goals

**Goals:**

1. **One shape for every account and every stage.** Stages change capacity behind fixed interfaces, never code paths ("all accounts, one code path"; PLAN "Phased rollout — explicitly rejected").
2. **The cross-user floor is held by construction, not by audit:**
   - a separate kernel per command center;
   - its own disk;
   - no daemon access to its files through host paths;
   - no platform state inside it;
   - no cross-tenant host uid.
3. **Cost scales with work, not with registered users.** Boxes are suspended unless acting. The loop holds a waiting turn in about a megabyte. Idle users cost storage only.
4. **Uptime:**
   - no deploy gaps;
   - continuous off-region durability;
   - a standby that can take over with fencing;
   - a recovery drill that actually runs.
5. **Least-privilege secrets per process.**

**Non-Goals:**

- Building more than one cell, or more than one box host, now. The seams exist; the second instance waits for its capacity trigger.
- Choosing the Postgres vendor. Postgres is decided (2026-07-25); self-hosted versus managed is a spend decision in S10.
- Changing the MCP tool surface. The seven canonical handles are unchanged.
- Settling private-content custody (PLAN carve-out 2). Boxes hold what universes hold today.
- Running a Claude **subscription** server-side for anyone but its owner. The TOS gate is the founder's decision (D6).
- Picking the usage-limit numbers. The founder picks them (D9).

## Architecture

```
                    tinyassets.io  (Cloudflare: DNS, Worker router, tunnel)
                               |
                 signed cell claim -> cell c0 (only cell today)
                               |
 +------------------------- CELL (control plane, always on) --------------------------+
 |  blue | green daemon (one active; leadership lease for singleton duties)           |
 |    MCP + app API, auth (WorkOS JWKS)                                               |
 |    thin agent loop (asyncio; HTTP model protocols; turn -> bound BoxHandle)        |
 |    scheduler / triggers / inbox / notifications (the only timers)                  |
 |    platform state: per-account SQLite under <data>/platform/  --Litestream--> R2/B2 |
 |    outbox -> Postgres (catalog, ledger, inbox, market)        (off-region backups)  |
 |  egress proxy (own process, own secret: vault key; placeholder -> credential)       |
 +------------------------------|-----------------------------------------------------+
                                | BoxProvider RPC (UDS today; mTLS when the host is remote)
 +---------------------- BOX HOST (boxhostd; same machine today) ----------------------+
 |  per command center: one sealed box                                                 |
 |    Firecracker microVM via jailer (distinct uid)  | fallback: gVisor runsc          |
 |    fixed-size disk image (allocated from the account quota), no NIC                 |
 |    boxd (in-box agent) over vsock: exec / read / write / list / export              |
 |    awake only while acting; snapshot + suspend after <=60 s idle                    |
 |  box images + snapshots --restic (dedup chunks)--> off-region                       |
 +-------------------------------------------------------------------------------------+
 standby cell + standby box host in a second region: cloudflared stopped, restoring
 continuously; promoted only after fencing the primary.
```

## Decisions

### D1. The unit of isolation is one sealed box per command center

- **Every command center gets exactly one box:**
  - its own guest kernel (microVM), or its own user-space kernel (gVisor);
  - its own disk;
  - no network interface.
- **The box holds the command center's files:**
  - the workspace;
  - brain, wiki, notes, skills and prompts (today's `AGENT_BRAIN_FILES`);
  - the agent-owned harness files;
  - workflows and their checkouts;
  - file-based CLI credentials for command adapters (D6).
- **Inside the box run** every tool call (the four tools) and every command-adapter CLI. A second agent of the same command center shares the box. The cross-user floor is per user, not per agent (memory `the-floor-is-cross-user-only`).
- **Driver selection.**
  - **Firecracker with snapshot/restore is primary.** It gives a hardware VM boundary, and its lazy restore means a woken box pays only for the memory it touches (Evidence E3).
  - **gVisor (rootful runsc, systrap) is the fallback** behind the same interface. It needs no KVM, starts in ~50 ms, and returns freed memory within 5 s. It cannot restore rootless, and its restore is eager (+420 MiB) (E4).
  - **The driver is a box-host configuration, not a code path.** Slice S0 decides which driver production starts with. The `BoxProvider` contract tests (S4) run against both drivers in CI.
- **Rejected:**
  - *OpenShell as the runtime:* no snapshot, the VM driver is experimental with gateway-wide sizing, and its credential placeholders do not fit subscription CLIs (spike §3).
  - *Rootless Podman:* shared kernel, and limits fail open without cgroup delegation (spike §4.3).
  - *Per-call bwrap:* isolation rank 5 (box-cost research §4).

### D2. `BoxProvider`: the only way the platform touches a box

```python
class BoxProvider(Protocol):            # tinyassets/boxes/provider.py
    def ensure_awake(self, cc: CommandCenterId, *, reason: WakeReason) -> BoxHandle
    def exec(self, h: BoxHandle, argv: Sequence[str], *, stdin: bytes = b"",
             env: Mapping[str, str] = {}, cwd: str = "/cc", limits: ExecLimits) -> ExecResult
    def read(self, h, path: str, *, offset: int = 0, max_bytes: int) -> FileRead      # bytes + generation
    def write(self, h, path: str, data: bytes, *, mode: WriteMode,                    # create | replace | cas
              expect_generation: int | None = None) -> FileWrite
    def list(self, h, path: str, *, max_entries: int) -> list[DirEntry]
    def stat(self, h, path: str) -> FileStat | None
    def remove(self, h, path: str) -> None
    def export(self, h, *, manifest: ExportManifest) -> Iterator[bytes]                # D11 bundle stream
    def import_bundle(self, cc, chunks: Iterable[bytes]) -> ImportReport
    def usage(self, h) -> BoxUsage                       # bytes used, disk allocation, change generation
    def suspend(self, h) -> None                         # snapshot + stop; idempotent
    def destroy(self, cc: CommandCenterId) -> DestroyReceipt   # disk, snapshots, backups (D12)
```

- **`BoxHandle`** is bound to `(command_center_id, account_id, box generation)`.
  - It is minted by `ensure_awake` and carried on the turn object from turn start.
  - It is never looked up by name per call, so a loop bug cannot route user A's tool call into user B's box (memory `verify-the-binding-in-the-destructive-step`).
  - A handle whose generation is stale, because the box was destroyed or re-imported, is refused.
- **Paths are box paths** (`/cc/...`). The provider resolves them inside the box, so a link the agent planted can only resolve inside the box's own filesystem.
- **Transport.**
  - `boxhostd` holds the drivers.
  - The control plane talks to it over a Unix socket today, and over mTLS when the box host is remote. It is the same RPC either way.
  - `boxhostd` talks to `boxd` inside each box over vsock (Firecracker) or a host-uds socket (gVisor).
  - Framing: length-prefixed JSON headers plus raw byte frames, no shell interpolation. `exec` takes argv, never a command string.
- **The daemon process has no filesystem access to box images or snapshots.** They live under `<boxes>/`, owned by the `boxhostd` uid with mode 0700. The daemon runs as a different uid. This is the by-construction close of #4244. A lint plus a ratchet test refuses any `open()` of a box-host path from `tinyassets/` outside the local driver.
- **Rejected:** a shared filesystem between daemon and box (virtio-fs or 9p bind of a host directory). It reopens the host-path trust class and is not supported by Firecracker.

### D3. Disk: one fixed-size image per box, allocated from the account's storage quota

- **The image.**
  - Each box has one ext4 image, created as a fresh sparse file. Holes read as zero, so there is zero-on-allocate by construction (the Cloudflare cross-tenant storage lesson, box-cost research §4).
  - Its size is the box's **disk allocation**.
- **The account quota stays one pool per account** (`account-storage-quota`; founder 2026-09-30). The invariant is: *the sum of an account's box allocations ≤ the account's storage quota*. The cell's allocator is the single writer of allocations, and it holds this invariant transactionally.
  - **A new command center** starts with a small allocation (default 1 GiB, or the remaining pool if smaller).
  - **Growth.** When `boxd` reports free space below a threshold (default 20% or 256 MiB) and the pool has headroom, `boxhostd` grows the backing file and the box resizes online. Firecracker gets a drive rescan, then `resize2fs` runs in the guest. gVisor's fallback uses an XFS project quota per box directory set to the allocation.
  - **Shrinking** happens only through an offline compaction (export, then import into a smaller image). It runs when the owner deletes data or asks, never automatically under a running box.
- **What a box sees at the quota:** `ENOSPC` from its own filesystem. Nothing else on the host is affected.
- **The user-facing quota refusal** (visible, with an inline "Upgrade" link) happens at the API and loop layer when a grow request is denied. That is the current `account-storage-quota` behaviour, re-homed.
- **Host disk.** Images are sparse, so the host can overcommit allocations. `boxhostd` refuses a grow when host free space would fall below its floor, and pages.
- **Measured costs (E3):** a box image starts from the shared read-only base rootfs (1.1 GB, copy-on-write per box) plus the command center's data image.
- **Rejected:**
  - a single per-account image shared by several boxes (ext4 cannot be mounted read-write twice);
  - an even split of the quota per command center (it breaks "one pool").

### D4. Lifecycle: awake only while acting

```
 absent --create--> cold (image only)
 cold --ensure_awake--> booting --(boxd ready)--> awake
 suspended (snapshot) --ensure_awake--> restoring --> awake
 awake --(no exec/API in flight for idle_s <= 60)--> suspending --> suspended
 awake|suspended --destroy--> absent      (any state --host restart--> suspended or cold)
```

**Idle and timers:**
- `idle_s` defaults to 30 s and can be configured up to 60 s. It is never a vendor default of 10–15 min.
- A box has no timers and no cron. In-box background processes freeze with the snapshot and continue on the next wake.
- Anything that must happen on a schedule is a control-plane trigger (D7).

**Restore path:**
- Firecracker restores from the full snapshot plus the latest diff snapshot. Measured: restore and resume 31–51 ms; guest observed running at 52–166 ms; host RSS 15–22 MiB right after restore (E3).
- Diff snapshots (2–8 MiB, 20 ms) are taken at suspend, so a crash loses at most the in-memory state since the last suspend. Files persist on the disk image regardless.

**Memory:**
- The box memory ceiling is 1 GiB (512 MiB default for tools-only boxes). It is a **ceiling, not a reservation**: the balloon and free-page reporting return memory (E3, E5).

**Seats and capacity (D9):**
- A **seat** is one concurrently running agent turn of the account (unchanged semantics).
- Box awake time is metered for compute-hours.
- At host capacity, a wake **waits** in the box host's admission queue and is never refused (founder 2026-09-30). The waiting state is visible on the turn and in the activity line.

### D5. Network and credentials

- **No network interface in any box.**
  - Egress is a single socket to the cell's egress proxy: vsock for Firecracker, host-uds for gVisor. Measured working through gVisor with our proxy: Anthropic 401 through the proxy, 403 for metadata and private addresses, no direct path (spike §8.3).
  - The egress floor is unchanged: globally routable only, SMTP ports refused, a per-box connection cap.
- **Credential placement.** The egress proxy is its own process. It is the only holder of the vault decryption key.
  - **Header-auth credentials** (API keys, OAuth bearer tokens the platform refreshes) are injected by the proxy, for the endpoint the connection profile names. The loop and the box see only a placeholder. Measured pattern: OpenShell's supervisor swapped a placeholder for the real value only at the approved host (spike §3).
  - **File-based CLI credentials** that a CLI refreshes itself (Codex `auth.json`) live **inside that user's box**, on its disk image, encrypted at rest with a per-box key held by `boxhostd`. They never live on a shared host path.
  - **A Claude subscription** is never used server-side for anyone but its owner, and only behind the founder's TOS decision (D6). Default: off.
- **TLS interception** is needed for placeholder substitution inside HTTPS. It uses a per-cell CA installed only in box images and in the loop's own HTTP client trust store. It is never used for a connection without a placeholder; those are tunnelled byte-for-byte.

### D6. A thin vendor-neutral agent loop in the control plane; CLI-in-box only where a credential needs it

**The loop:**
- It runs as asyncio tasks in the cell's daemon.
- It speaks the standard model protocols through the generic connector: OpenAI chat and responses, Anthropic messages, and the OpenAI-compatible API (`api_key_http_provider.py` encoders).
- It holds a waiting turn as a coroutine plus one HTTP stream plus its context buffer. That is estimated at ~1 MB and measured in S7.
- It never executes model output. It parses tool-call JSON and forwards each call over the turn's bound `BoxHandle`.

**Effects:**
- Box memory per awake agent drops from 338–525 MiB (CLI in box) to the tools-only footprint, estimated at 80–130 MiB.
- The model credential never enters the box (box-cost research §E.2b).

**Precedent:** Anthropic's Managed Agents made the same split and measured p50 TTFT −60% and p95 −90% (staged-architecture §7.5).

**CLI-in-box stays** for:
- **command adapters**, meaning any binary a user connects;
- **file-OAuth CLIs**, such as Codex via its own login;
- **a Claude subscription CLI.** That path is gated by `claude_subscription_serving`, an **owner-scoped** setting. Today only the founder's own command center can turn it on, under his TOS decision (memory `anthropic-forbids-third-party-subscription-oauth`). For everyone else the sanctioned subscription path is the user's own device (desktop app).
- One CLI process never serves two users.

**The turn journal is unchanged** (`agent_turns`, per round). After a failover, an interrupted turn *reconciles* into held states (`agent_turn_reconcile.py`). It does not replay.

### D7. The control plane is the only always-on layer

- **Inside the cell, under one leadership lease:** the scheduler, the trigger table, the inbox, notifications, the outbox pump, quota and metering.
- **Coalescing:** one pending run per trigger. Proactive cadence decays with engagement:
  - 4 runs/day while the user engages;
  - 1/day after a week without engagement;
  - weekly after a month;
  - back to normal on the next interaction.

  That puts the dormant-user duty floor at ~0.1% (box-cost research §D.1).
- **Waking a box** is always the control plane calling `ensure_awake`. A box cannot schedule itself.
- **The platform-visible record per command center lives outside the box** (D8): schedule, routing, unread and notification metadata, quota counters, activity line. Listing, scheduling and notifying therefore never wake a box.

### D8. Data placement: where everything lives

| Data | Home | Store | Replication / backup |
|---|---|---|---|
| Command center files (workspace, brain/wiki, skills, prompts, notes, workflows, agent-owned harness files) | **inside the box**, on its disk image | files | restic (content-defined chunks) to off-region object storage, at suspend when dirty and at least hourly. Restore = rebuild the image |
| Box memory state | box host | Firecracker snapshot (full + diffs) | not backed up (rebuildable by a cold boot) |
| File-OAuth CLI credentials | inside the box, encrypted with a per-box key | file | with the box disk |
| Header-auth credentials (vault) | cell, `<data>/platform/<account>/vault` | encrypted file + key held only by the egress proxy | Litestream/restic, encrypted |
| Per-command-center platform state: runs, consent, usage, attention, conversation and session journals, rules, auto-review results, activity records, pending effects, proposals, import quarantine, browser profile, locks/stamps | cell, `<data>/platform/<account>/<command_center>/` (never mounted in any box) | per-account SQLite + files | **Litestream v0.5** continuous to off-region (RPO ~1 s); restic for files |
| Cross-user transactional domains: catalog, ledger, inbox, market | shared | **Postgres** (founder-approved 2026-07-25) | managed point-in-time recovery or pgBackRest to off-region |
| Commons (OKF bundle) | shared | files (canonical), with a SQLite/FTS index rebuilt from them | restic off-region |
| Identity map (WorkOS subject → user → home cell) | shared, read-mostly | Postgres (with the catalog) | as Postgres |
| Release state, health | per cell | file | — |

**Rules:**
- Nothing the platform trusts is ever read from inside a box. The platform reads box content only through `BoxProvider`, and treats it as untrusted input (memory `daemon-reads-universe-files-as-untrusted`).
- Per-account SQLite stays the store for anything owned by one account. Postgres holds only what is genuinely cross-user. This follows the measured counter-example: 37signals moved per-tenant SQLite to MySQL for cross-tenant features and DR (staged-architecture §7.1).
- **SQLite ≥3.51.3** in every image (prod links 3.46.1; Tailscale WAL-reset race), pinned before Litestream is turned on.

**Hot-path cache.**
- The daemon caches the box reads it needs on every turn: persona grounding (soul, founder files), the skills index, and harness prompts.
- The cache is keyed by `(command_center, box change generation)`. `boxd` keeps a monotonic change generation, bumped by any write, and returns it on every RPC. A cached entry is valid while the generation matches, so a turn that finds a warm cache never wakes the box.
- The activity status line is platform state (D7), not a box read.

**The #4247 safe-reader ratchet maps onto this directly.**
- `universe_files.py` becomes the **local driver** behind `BoxProvider.read/list/stat`.
- Its ratchet test, "no raw read of a universe file outside this module", becomes "no daemon read of command-center content outside `BoxProvider`".
- The ~350 sites move once (S3). Switching the driver to a box (S11) then changes nothing at the call sites.

### D9. Usage limits: storage, seats, priority compute-hours, spare lane

These are three numbers per account and one code path (box-cost research §F.3):
- **Storage GiB** is enforced as box disk allocation (D3). New user-driven writes are refused visibly at the quota.
- **Seats**, meaning concurrent running agent turns: extra turns **wait**.
- **Priority compute-hours per month** are metered per second from the box lifecycle. One compute-hour is one awake hour of a box with a ≤512 MiB ceiling; larger ceilings scale linearly.
  - Past the budget, work moves to the **spare-capacity lane**. It is admitted only while the host has headroom: lower priority, never dropped.
  - A trigger that fires while its previous run is still waiting is coalesced.
- **Host-capacity admission replaces the global 4-run pool and the 4 tool slots.** One user's fan-out is bounded by their seats, so it can never block another user's admission.
- **The numbers are the founder's to pick.** Proposed: free 200 compute-hours, 2 seats, 2 GiB; paid 2,000, 8, 20 GiB. Per memory `usage-limits-are-storage-and-seats`, no compute-hour limit code ships until he picks. S9 ships metering and the lane first.

### D10. Cells: user-to-cell routing from day one, one cell now

- **A cell** is one control plane plus its box host capacity, serving a shard of users. All of a user's command centers live in the user's cell.
- **The routing seam:**
  - **`home_cell`** on the account record. A signed `cell` claim is minted at sign-in. The edge Worker routes by the claim, and falls back to a small global lookup on a cold start. Today every claim says `c0` and the Worker has one target.
  - **Ownership generation** (I11): moving a user bumps it, and requests carrying an older generation are refused, not served stale.
  - **Ingress dedup and event cursors** (I10): every externally triggered request carries an idempotency key that the cell deduplicates.
  - **Transactional outbox** (I12): a cell's effects on the shared Postgres domains are written to a local outbox in the same transaction as the cause, then pumped. They are never written directly.
  - **Consistent export** (I13): `BoxProvider.export` plus the platform-state snapshot, at one change generation, is the user-migration unit between cells and the D11 export bundle.
- **Moving a user between cells** = export, import, flip `home_cell`, bump the generation. Nothing in the code checks how many cells exist.

### D11. Uptime topology

**Zero-downtime deploys (blue-green behind the tunnel):**
- `cloudflared` points at a local switch on the cell host. The switch fronts a `blue` and a `green` daemon.
- **A deploy:**
  1. starts the idle colour;
  2. waits for its health check;
  3. moves new requests to it;
  4. puts the old colour into **drain**: no new admissions, scheduler leadership released, in-flight turns and SSE streams finished, up to the drain bound;
  5. stops the old colour.

  A turn still running at the bound is journaled and reconciles on the new colour.
- **Singleton duties (D7) run only under the leadership lease.** It is fenced by a lease generation, so the two colours never both schedule.
- **Box hosts are unaffected by control-plane deploys.**
- **Target:** zero origin-down seconds per deploy, measured by a 5-second restart-gap probe. Today: 3.7 min/day.

**Warm standby, second region:**
- A smaller standby cell host and box host in another region or provider.
  - Its `cloudflared` connector is installed and **stopped**, because tunnel replicas take traffic from the nearest edge (staged-architecture §7.4).
  - It restores Litestream continuously.
  - It restores box disks lazily, from restic, on the first wake after promotion.
- **Promotion:**
  - The detector is a Cloudflare Load Balancer health check, or two red canaries.
  - The primary is **fenced first**: powered off through the provider API with a scoped token held only by CI, and blocked from auto-restart.
  - Then the standby's daemon and connector start.
  - If fencing cannot be confirmed, promotion stops and pages a human.
  - Failback is manual.
- **RPO:**
  - platform state ~1 s (Litestream);
  - box files ≤ the backup interval (default 1 h, plus at suspend when dirty);
  - box memory is lost, so the box cold-boots.
- **RTO:** ≤5 min after detection.

**DR drill:**
- **Scheduled weekly**, restoring **from the off-region copies** into a fresh VM.
- It asserts the canary goes green, and that N sampled boxes restore with matching content checksums.
- It pages when the drill itself fails.
- As built, the drill is dispatch-only and last ran 2026-07-24; S1 fixes this.

### D12. Account deletion, export, and migration

**Account deletion:**
- `BoxProvider.destroy` for each of the account's command centers removes the disk image, the snapshots, and the box's restic snapshot set, and then prunes it.
- The platform-state directories and Postgres rows go through the existing schema-derived deletion set (memory `deletion-set-derived-from-schema`).
- It produces one `DestroyReceipt` per box, and deletion completes only when every receipt exists.

**Export (harness D11 / §4.17):**
- `BoxProvider.export` streams the command center's files, scrubbed by the D11 manifest, from inside the box, plus the platform-owned records the manifest selects.
- The result is the same bundle used for sharing, import and moving between cells (D10). Credentials are never exported.

**Migration from shared `/data/<universe>` (S11):**
- It is **clean cutover, no compatibility layer** (memory `clean-cutover-no-compat-while-early`): one locked, idempotent, resumable migration run in the `command-center-cutover` freeze window if that has not shipped yet, otherwise in its own window.
- **The run:**
  1. Inventory each universe directory, derived and never hand-listed. Agent-owned regular files go to the box; platform files go to `<data>/platform/` (already done by S2); everything else is reported.
  2. Build each box image by copying regular files only, refusing links and special files.
  3. Verify file counts and content hashes inside the box through `BoxProvider`.
  4. Flip each command center's `box_generation`.
  5. Keep the source directory read-only until the drill passes.
- **Backup:** a pre-run volume snapshot plus a restic snapshot off-region.
- **Rollback:**
  - before the flip, the old image keeps running unchanged;
  - after the flip, deploy the previous image plus the pre-run snapshot. The layout guard from rename C4a refuses a mixed state.

## Interfaces fixed by this change

| # | Interface | Module (target) | Local implementation now | Scaled implementation |
|---|---|---|---|---|
| I1 | `BoxProvider` (D2) | `tinyassets/boxes/provider.py` | `boxhostd` on the same host (UDS) | remote box hosts (mTLS), N per cell |
| I2 | `PlatformStatePaths` (D8) | `tinyassets/platform_state.py` | `<data>/platform/<account>/<cc>/` | same, per cell |
| I3 | Thin turn loop (D6) | `tinyassets/agent_loop/` | in-process asyncio | same in every cell |
| I4 | Placement `home_cell` (D10) | `tinyassets/cells.py` | constant `c0` | edge-routed cells |
| I5 | `store_for(account)` | storage factories | per-account SQLite files | same, per cell |
| I6 | Bundle export/import (D12) | `tinyassets/export_bundle/` | from box | user moves between cells |
| I7 | `TransactionalStore` (catalog, ledger, inbox, market) | `tinyassets/txstore/` | one Postgres | Postgres HA |
| I8 | Scheduler/trigger table under lease (D7) | `tinyassets/scheduler/` | in the active colour | per cell |
| I9 | Release state + health per origin | `scripts/deployed_sha.py`, `/data/release-state.json` | per colour | per cell |
| I10 | Ingress dedup + cursors | request-idempotency store | local SQLite | per cell |
| I11 | Ownership generation | account record | generation 1 | bumped on move |
| I12 | Outbox to `TransactionalStore` | per-cell SQLite outbox | pump in-process | same |
| I13 | Consistent export | I6 + platform-state snapshot | — | cell moves |
| I14 | `EgressProxy` placeholder contract (D5) | `tinyassets/egress/` | own process on the cell host | per cell |

## Slice plan

Every slice below is opened as its own delivery change: one owner, one branch, one PR, ≤12 tasks, proposal and design first where it touches storage, authority, migration or money.

**Founder spend** marks slices that need a paid resource approved first.

**Order:** S0, S1, S2 and S8 can start now in parallel. S10 can start any time.

```
S0 ─┐                 S1 (independent)      S8 (independent)     S10 (independent)
    ├──> S5 ──┐
S2 ─> S3 ─> S4 ─┬─> S6 ─> S7 ──┐
                └─> S9 <─ S5   ├──> S11 (cutover)
                               │
            S2,S3,S5,S6,S7 ────┘
```

### S0. DigitalOcean nested-KVM validation (decides the box host) — **founder spend**

- **Goal:** decide whether Firecracker runs acceptably under DigitalOcean's nested KVM. DO calls nested virtualization unsupported, even though production reports `nested=Y`.
- **Owner brief:**
  - Production stays untouched. Run on a **short-lived staging droplet** of the production size (`s-4vcpu-8gb`, sfo3, 2 h ≈ $0.14), created from `deploy/hetzner-bootstrap.sh` and destroyed after.
  - Fallback if the founder prefers: a gated quiet-window micro-benchmark on production, which needs explicit founder approval.
  - The scripts already exist from the 2026-10-01 spike: `fc_snap.py`, `gv_ckpt.py` and `sysprobe.py`. They move into `scripts/box_bench/` in this slice.
- **Tasks:**
  1. Create the staging droplet.
  2. Run Firecracker + jailer as a dedicated uid.
  3. Measure cold boot and restore p50/p95, `exec` RPC p50/p95, and snapshot create and size.
  4. Measure idle CPU per awake box and steal time under 10 and 30 concurrent awake boxes.
  5. Measure the gVisor equivalents on the same droplet.
  6. Record the results.
  7. Destroy the droplet.
  8. Write the decision.
- **Decision rule:**
  - **Firecracker on DO** if restore p95 ≤ 500 ms, exec p95 ≤ 50 ms, awake-idle CPU ≤ 5% of a core per box, and 30 awake boxes keep the host responsive (canary p95 unchanged).
  - **Otherwise a bare-metal box host:** OVH RISE-S Hillsboro, 64 GB, native KVM, $77/mo with setup waived on a 12-month term; **founder spend**. The control plane stays on DO.
  - **gVisor on the droplet** serves until the box host exists.
- **Acceptance:** numbers recorded in the slice's design.md with commands; the decision written into this design (D1) and PLAN.

### S1. Durability foundations and the warm standby — **founder spend**

**Spend:**
- off-region object storage (R2 or B2), ~$0–5/mo;
- the standby droplet (2–4 GiB), $12–24/mo;
- a Cloudflare Load Balancer, ~$5/mo.

**Tasks:**
1. Pin SQLite ≥3.51.3 in the image, and assert it at startup.
2. Run a Litestream v0.5 sidecar for every SQLite store, to the off-region bucket.
3. Change `BACKUP_DEST` to the off-region bucket. The GitHub copy keeps the brain tier only.
4. Restore test from Litestream: point in time.
5. Give `dr-drill.yml` a weekly `schedule:` and restore from the off-region copy.
6. Provision the standby through the bootstrap script, with `cloudflared` installed and stopped.
7. Continuous Litestream restore on the standby.
8. A fence-then-promote workflow, using a scoped DO token held only by GitHub Actions.
9. A Cloudflare LB health check as the detector.
10. A promotion drill.
11. The runbook.
12. Spec sync to `uptime-and-alarms` and `platform-state-placement`.

**Acceptance:**
- the drill restores from off-region and goes green;
- a promotion drill reaches green ≤5 min after detection;
- RPO is measured.

### S2. Platform state out of the universe directory (§4.16, concern #4258)

**Brief:** the full-blast fix #4258 asked for. It can ship before boxes exist, and it is a hard prerequisite for them.

**Tasks:**
1. Add a `PlatformStatePaths` resolver (I2) as the only way to name a platform file.
2. Move to `<data>/platform/<account>/<cc>/`, through it:
   - the vault;
   - the run, consent, usage, attention, conversation and session stores;
   - rules, auto-review, activity, pending effects, proposals, import quarantine, the browser profile;
   - locks and stamps.
3. Add a startup migration: locked, idempotent and verified, with a backup.
4. Refuse to open a platform store found inside a universe directory. That closes #4258 attack 3, the pre-created consent database.
5. Prove no jail mounts the platform root: a test plus the Linux oracle.
6. Fold in `.universe-sidecars`.
7. Update the account-deletion set.
8. Spec sync.

**Acceptance:** the #4258 reproductions (rename re-exposure, hard-link capture, forged consent DB) fail in the Linux oracle.

### S3. One accessor for command-center content, plus the hot-path cache

**Brief:** this builds on #4247's ratchet.

**Tasks:**
1. Define the `BoxProvider` read/list/stat/write signatures with a **local driver** wrapping `universe_files.py`.
2. Migrate the ~350 daemon sites, in batches by module.
3. Make the ratchet count *any* universe-path open outside the provider, with a target of zero.
4. Add the change-generation hot-path cache: persona grounding, skills index, prompts.
5. Measure turn latency before and after.
6. Spec sync.

**Acceptance:** the ratchet holds at 0; turn latency does not regress.

### S4. `BoxProvider` complete, plus `boxd` and the gVisor driver

**Tasks:**
1. `boxhostd`: its own uid, a Unix-socket RPC, and the framing.
2. `boxd` in the base image: exec, files, change generation, usage.
3. The gVisor driver, rootful runsc with systrap. Each box runs as a distinct host uid/user namespace, with `--network=none` and the proxy socket over host-uds.
4. Contract tests that every driver must pass, covering:
   - path escape;
   - links resolving inside the box only;
   - a stale handle being refused;
   - a cross-box handle being refused;
   - `ENOSPC` at the allocation.
5. Re-point `universe_tools.RUNNER` and `provider_jail.confine_launch` at `BoxProvider`.
6. The box-host admission queue: wait, never refuse.
7. Spec sync.

**Acceptance:** the contract suite is green on gVisor in CI; a tool loop runs end to end through a box on staging.

### S5. Firecracker driver, disk allocator and host build — **founder spend if S0 picks bare metal**

**Tasks:**
1. Firecracker + jailer, one uid per VMM, with a pinned version.
2. The base rootfs plus the per-box data image. The image is a fresh sparse file.
3. Full and diff snapshots at suspend, and restore on `ensure_awake`.
4. The idle timer (≤60 s).
5. Balloon and free-page reporting.
6. vsock `boxd`.
7. The grow-only disk allocator, holding the account invariant (D3).
8. Rebuild the box host on Debian 13: the droplet, or the bare-metal host S0 picked.
9. restic backup of the box images, off-region.
10. The contract suite on Firecracker.
11. Spec sync.

**Acceptance:**
- the contract suite is green on both drivers;
- restore p95 on the production box host meets S0's rule.

### S6. Egress proxy as credential injector, and per-process secret scope

This slice coordinates with the secret-scope lane.

**Tasks:**
1. The proxy as its own process, the only holder of the vault key.
2. The placeholder contract (I14) for header-auth credentials.
3. A per-cell CA in box images and the loop's trust store. Connections without a placeholder are tunnelled verbatim.
4. File-OAuth CLI credentials encrypted inside the box.
5. The owner-scoped `claude_subscription_serving` gate, default off.
6. Remove `DO_API_TOKEN`, `STRIPE_SECRET_KEY`, `WORKOS_API_KEY` and `CLOUDFLARE_TUNNEL_TOKEN` from every process that handles tenant input, so each lives only in its one consumer.
7. A test that reads `/proc/<pid>/environ` names per process.
8. Spec sync to `credential-vault`.

**Acceptance:**
- a box process and the loop process each hold no real credential (asserted);
- the CLI reaches its API through a placeholder.

### S7. The thin agent loop

**Tasks:**
1. An asyncio loop over the generic connector's HTTP protocols.
2. Bind a `BoxHandle` at turn start.
3. Forward tool calls through it.
4. The per-round journal (unchanged schema).
5. Streaming to SSE.
6. CLI-in-box as the path for command adapters and file-OAuth CLIs.
7. Measure memory per waiting turn: 500 concurrent turns against a mock SSE server.
8. A real subscription-free turn, live through `ui-test`.
9. Retire the per-turn provider jail for HTTP connections.
10. Spec sync.

**Acceptance:**
- a live rendered conversation works;
- the waiting-turn memory is measured;
- cancellation and reconcile work.

### S8. Always-on control plane, leadership lease, and blue-green deploys

**Tasks:**
1. A leadership lease with a fenced generation.
2. The scheduler, triggers, outbox pump and metering run under it.
3. Trigger coalescing.
4. Engagement-decayed cadence.
5. Remove or forbid in-box timers: a box has no cron, asserted.
6. The blue/green compose services plus the local switch.
7. Drain mode.
8. `deploy-prod.yml` switches colours.
9. A 5-second restart-gap probe.
10. A replay-safety check: only idempotent requests are retried at the edge.
11. Spec sync.

**Acceptance:** a scripted deploy loop shows 0 s of origin-down time and no duplicate effects.

### S9. Usage limits on the box lifecycle — **founder decision on the numbers**

**Tasks:**
1. Meter box awake time per second, weighted by memory ceiling.
2. Seat admission plus host-capacity admission replace `TINYASSETS_RUN_MAX_CONCURRENT` and `_HOST_SLOTS`.
3. The spare-capacity lane.
4. The visible waiting message with its reset time and the inline Upgrade link.
5. Storage refusal at a denied grow (D3).
6. Ship the limit numbers only after the founder picks them.
7. Spec sync to `account-compute-budget`.

**Acceptance:** one account's fan-out never delays another account's admission (measured).

### S10. Postgres domains and the cell seam — **founder spend if managed Postgres**

**Spend:** self-hosted on the cell host is $0; DO managed is $15.15/mo, or $30.30 with HA.

**Tasks:**
1. Inventory which of catalog, ledger, inbox and market exist on SQLite today.
2. Define `TransactionalStore` (I7) and stand up Postgres.
3. Migrate the existing domains in a locked, verified run.
4. The outbox (I12).
5. The identity map in Postgres.
6. `home_cell` + the signed cell claim + the Worker route (one target).
7. The ownership generation (I11).
8. Ingress dedup (I10).
9. Postgres backups off-region.
10. Spec sync to `cell-routing` and `platform-state-placement`.

**Acceptance:** a simulated user move between two local cells passes the generation and dedup tests.

### S11. Cutover: shared `/data/<universe>` becomes sealed boxes

**Depends on:** S2, S3, S5 (or S4 with gVisor), S6, S7.

**Tasks:**
1. The derived inventory.
2. The migration run, inside the `command-center-cutover` freeze window if it is still open (D12).
3. Per-box verification through `BoxProvider`.
4. The flip.
5. Rollback rehearsal on staging.
6. Export from the box (harness D11) and deletion through `destroy`.
7. Retire the bwrap tool/provider jails, `.universe-sidecars` and the host-path local driver.
8. Live proof: a rendered conversation using every tool, plus the public canary with `--assert-handles`.
9. `deployed_sha.py --assert-contains`.
10. Spec sync and archive.

**Acceptance:**
- every command center serves from its box;
- the old paths are gone;
- the DR drill restores boxes.

## What this supersedes, and the interim hardening

| Interim item | Status |
|---|---|
| #4245 shared seccomp denylist for the bwrap jails | **Keep until S11.** Add the measured delta (mount APIs, `memfd_create` after a compatibility check, `process_vm_*`, pidfd, `execveat(AT_EMPTY_PATH)`, `seccomp(SET_MODE_FILTER)`, non-route netlink) only if S11 is more than ~4 weeks out. Retired by S11 |
| #4247 safe-reader ratchet | **Becomes S3.** Its module becomes the local driver of `BoxProvider` |
| #4252/#4253 mask of hidden root files | **Retired by S2:** platform state is no longer there |
| `openat2` universe-path helper (spike §9) | Folded into S3's local driver; unnecessary after S11 |
| Per-universe project quota (spike §9) | **Not built.** Replaced by box disk allocation (D3) |
| `TINYASSETS_RUN_MAX_CONCURRENT` / `_HOST_SLOTS` | Replaced by S9 admission |
| `.universe-sidecars/` | Folded into S2's platform root |
| PLAN "Backend stack (target): Supabase" | Postgres stays; the vendor is open (S10) |

## Risks / Trade-offs

- **DO nested virtualization is officially unsupported.** S0 measures it, and the design survives either answer. The driver is box-host configuration, and gVisor is the fallback behind the same contract.
- **Firecracker host-side CVEs** (CVE-2026-5747 VMM OOB write, CVE-2026-1386 jailer symlink). Mitigation: a pinned VMM version, jailer, seccomp on the VMM, a distinct uid per VMM, and patch cadence in the host runbook.
- **The TLS-interception CA is new attack surface.** It is scoped to placeholder-bearing connections only, and the CA private key is held by the proxy process alone.
- **The shared loop holds many users' turns in one process.** Mitigations:
  - credentials are never in it (D5);
  - the turn object binds the box handle (D2);
  - model output is never executed;
  - the loop's own code is the reviewed surface.
- **Snapshot restore pins to the CPU model.** Firecracker snapshots are not portable across CPU families. On failover to the standby, boxes cold-boot from disk (D11). The memory state loss is accepted.
- **Box-file RPO is the backup interval** (≤1 h, plus at suspend), weaker than platform state (~1 s). This is accepted and stated in the uptime spec.
- **Operations labour.** `boxhostd` is our orchestrator. The E2B postmortem says the orchestrator is where outages come from, so it stays one process with no external scheduler (no Nomad or Consul).
- **The migration touches every user's data.** It is a clean cutover in one locked run, with backup, verify, rollback and a rehearsal on staging (S11 task 5).

## Open questions (founder)

1. S0 spend: a staging droplet (~$0.14), or approve a quiet-window benchmark on production instead.
2. S1 spend: off-region bucket provider (R2 or B2), the standby droplet ($12–24/mo), and the Cloudflare Load Balancer (~$5/mo).
3. S5 spend, if S0 fails on DO: OVH RISE-S Hillsboro ($77/mo, 12-month term).
4. S9: the compute-hour numbers.
5. S10: self-hosted Postgres ($0) or DO managed ($15.15/mo, or $30.30 with HA).
6. D6: the Claude subscription TOS gate stays owner-only (founder's own command center) until he decides otherwise.

## Evidence (measured 2026-10-01/02; the full reports were session artifacts and are summarised here)

- **E1. Today's production** (read-only, 2026-10-02):
  - memory and CPU: 1,086 MiB used of 7,940 MiB; CPU 97–99% idle;
  - restarts: 81 in 4 days, p50 8 s, max 191 s, 14.8 min origin-down;
  - backups: same region; the full tier is 4.0 GB and fails GitHub's 2 GiB limit;
  - DR drill last ran 2026-07-24;
  - SQLite 3.46.1;
  - the daemon environment holds `DO_API_TOKEN`, `STRIPE_SECRET_KEY` (live), `CLOUDFLARE_TUNNEL_TOKEN` and `WORKOS_API_KEY` (names only);
  - bill $57.72 (September).
- **E2. Syscall surface** (#4245 head `30b0249b`, 34 syscalls, real jails versus an unfiltered baseline):
  - #4245 filters mknod, io_uring, bpf, perf_event_open, keyring, setns, ptrace and userfaultfd. The tool jail also filters symlink, userns and clone3.
  - Still reaching the kernel in both jails: mount, umount2, open_tree, fsconfig, memfd_create, process_vm_readv/writev, the pidfd family, execveat(AT_EMPTY_PATH), seccomp(SET_MODE_FILTER), non-route netlink.
  - In the provider jail, after an in-jail `unshare -r --mount`, the mount calls are reachable with namespace capabilities.
- **E3. Firecracker v1.17.0** (512 MiB guest, warm workspace of 54 MB files plus a 200 MiB incompressible heap, nested KVM on WSL2):
  - cold boot to warm: 6.3–6.7 s; running warm RSS 416–419 MiB;
  - full snapshot: 0.56–0.69 s; 512 MiB (295 MiB zstd); diff snapshot 20 ms, 2–8 MiB;
  - restore: 31–51 ms; running at 52–166 ms; RSS 15–22 MiB after restore, 29–49 MiB after 5 s;
  - balloon: 192 MiB inflation took RSS from 417 to 319 MiB in 0.2 s.
- **E4. gVisor release-20260928.0** (systrap, no KVM):
  - start: 42–59 ms; exec 16 ms median; idle box 16 MiB PSS, ~0 CPU;
  - checkpoint: 0.32–0.51 s, 265 MiB (241 zstd);
  - restore: rootful 0.46 s, eager (+420 MiB); **rootless restore unsupported**;
  - frees 476 → 75 MiB within 5 s;
  - writing small files through the gofer is slow: 19–32 s for a workspace Firecracker built in 6.5 s;
  - runs in a production-shaped unprivileged container without `/dev/kvm`.
- **E5. OpenShell v0.1.2:**
  - microVM boots at 64 MiB; ~80 MiB idle; 3.4% of a core per idle VM; 5.7 s restart;
  - libkrun free-page reporting returned 126 of 136 MiB in 15 s;
  - no memory snapshot;
  - placeholder credentials proven for header auth;
  - the codex profile does not drive codex-cli 0.160.
- **E6. Costs and research** (staged-architecture and box-cost research, 2026-10-01/02):
  - box tier: OVH RISE-S Hillsboro $77/mo for 64 GB, native KVM;
  - storage: R2 $0.015/GB-mo with no egress; B2 $6.95/TB-mo;
  - Litestream v0.5 with point-in-time restore; LiteFS is unsupported;
  - Cloudflare tunnel replicas route to the nearest replica;
  - cost per user (est.): ~$6–8 at 10 users, $1–3 at 30–100, $0.15–0.35 at 1k, $0.05–0.14 at 10k. Thin loop plus cadence decay are the biggest levers.
- **E7. Capacity on today's droplet** (4 vCPU / 7.9 GB, illustrative):
  - active seats: CLI in gVisor ~19, CLI in Firecracker ~16;
  - a thin-loop tools-only box (est. 80–130 MiB) roughly triples that;
  - idle users cost disk only, ~0.3 GB each, ≈ $0.005/mo on R2.
