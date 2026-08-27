# Codex opposite-provider review — ClawHosters architecture implications

Date: 2026-08-10  
Initial provider: Claude Code (Fable 5)  
Reviewer: Codex  
Source note: `docs/design-notes/2026-08-10-arch-research-clawhosters.md`  
TinyAssets baseline: `origin/main@7b451b2c98abb9b411d35b32def96a319d721594`  
Verdict: **ADAPT**

## Executive judgment

The note found useful patterns, especially explicit first-use model capacity,
pre-provisioned compute, and lifecycle-aware capacity management. It does not
support its two strongest architectural conclusions as written:

1. ClawHosters proves tenant isolation for an OpenClaw *instance*. It does not
   prove TinyAssets's per-job Engine OS containment, exact workspace projection,
   no-raw-credential guarantee, or execution-admission evidence. A VPS boundary
   complements those controls; it does not dissolve their P0/P1 class.
2. ClawHosters advertises zero-downtime updates, but its published
   `docker commit` implementation only preserves a container writable layer
   before restart/redeploy. It does not show old and new serving concurrently,
   an exclusive-writer handoff, or a consistent data migration.

The note also compares against a stale TinyAssets checkout. Current
`origin/main` already performs a volume-less, network-less candidate-image load
probe before quiescence and has an immutable previous-image rollback path. The
stop-writer fence protects the shared `tinyassets-data` volume from rogue or
concurrent writers; it is not an anti-pattern to remove.

## Source freshness and evidence standard

External facts were re-checked on 2026-08-10 against the ClawHosters founder's
technical posts and product/docs pages. Those are primary *vendor* evidence,
not independent verification of a closed platform. Koi's ClawHub scan is
independent security research. The source note's `[E]` label is too broad
because it combines vendor assertions, published implementation excerpts, and
independent observation.

Primary URLs:

- https://clawhosters.com/blog/posts/how-i-built-60-second-vps-provisioning
- https://clawhosters.com/blog/posts/building-managed-hosting-platform-tech-deep-dive
- https://clawhosters.com/docs/security-overview
- https://clawhosters.com/docs/claude-setup-token
- https://clawhosters.com/pricing
- https://clawhosters.com/roadmap
- https://clawhosters.com/faq
- https://clawhosters.com/
- https://www.koi.ai/blog/clawhavoc-341-malicious-clawedbot-skills-found-by-the-bot-they-were-targeting

## Fact verdicts

| Claim | Verdict | Evidence vs inference / correction |
|---|---|---|
| Dedicated Hetzner VPS + one Docker container | **ADAPT** | Vendor docs support one dedicated VPS per **instance**, not per customer. The primary OpenClaw workload is containerized, but the architecture also uses nginx/ZeroTier sidecars, and the FAQ says one instance may run multiple agents. `customer = VPS = container = agent` is false precision. |
| Snapshot + pre-warmed claim-don't-create pool | **APPROVE** | The founder publishes the claim service, DB claim, metadata rename, SSH check, snapshot contents, and async replenishment. Timing is misassembled: snapshot creation is 30–60 s; the published pre-warmed user path is about 15–20 s total, not 15–20 s claim plus another 20–30 s. Pool size/seasonal policy remains operator assertion. |
| Five-layer routing | **APPROVE** | The technical post documents Cloudflare, front nginx, Traefik/Redis, VPS nginx, and the OpenClaw container. Hetzner firewall is a security boundary around that route, not a sixth routing layer. |
| Rails monolith control plane | **APPROVE** | The founder explicitly describes one Rails app/control server with PostgreSQL, Sidekiq, Clockwork, Redis/Traefik, and Hetzner APIs. Closed-platform vendor evidence only. |
| `docker commit` zero-downtime updates | **REJECT** | The code excerpt proves writable-layer preservation before restart/redeploy. The roadmap/homepage separately claim zero downtime. No published path proves parallel old/new service, health-before-cutover, writer fencing, or state convergence. `docker commit` also does not capture named-volume data. |
| Self-heal ladder | **APPROVE** | The deep dive supports four consecutive failures -> pattern-based config repair, five -> Telegram/email admin alert, plus stuck-deploy reconciliation. This is operator-published behavior, not an external availability test. |
| AES-256-GCM Rails vault for setup tokens | **ADAPT** | The setup-token page says AES-256; the security page says BYOK secrets use AES-256-GCM via Rails encrypted credentials. With no source or key-management description, this is a vendor storage claim. The statement that ClawHosters “never accesses or reads” the token is architecturally false or at least misleading because the control plane must decrypt or deliver it to the instance. |
| €19–59 infra fee unbundled from model cost | **ADAPT** | Prices and free BYOK/no-markup are supported. Calling the whole fee “infra” is inference: plans include managed service and free loaner-model usage, with managed packs/overages alongside BYOK. The note's estimated €4–8 COGS is not established by ClawHosters evidence. |
| Backups exclude chat history | **ADAPT** | Free config backups exclude history/files/packages. But current vendor pages conflict: pricing says full backup service is “Coming Soon,” while the homepage and FAQ claim daily/full snapshots including conversations. “No restore path today” is not settled without an authenticated product check. |
| 39 running vs 1186+ customers | **APPROVE facts / REJECT inference** | Both counters are present on the vendor homepage. They do not prove signups, paid conversion, churn, or pause-on-zero attrition; “Happy Customers” may be cumulative or marketing-defined. |
| ClawHub 824 / 10,700+ = ~7.7% | **APPROVE historical** | Koi's Feb. 16 update reports these counts. It is a historical incident ratio, not a current marketplace “base rate”; ClawHub has since added scanning/audit controls and later studies report materially different rates depending on classifier. |

## TinyAssets implication verdicts

### 1. Per-universe hard isolation via snapshot + pool — **ADAPT**

Approve dedicated execution capacity as an optional isolation and noisy-neighbor
boundary. Reject the claim that it dissolves the Engine OS and credential-bleed
concerns. Current `engine-os-sandbox` requires per-execution kernel separation,
exact default-deny projection/egress, resource bounds, absence of platform
secrets, cleanup, and request-bound evidence. A root-capable agent on its own VPS
can still read that universe's raw credentials and violate all but the
cross-tenant boundary.

TinyAssets-native direction: keep the multi-tenant control plane; provision
ephemeral per-job sandbox backends from an immutable pool; offer a dedicated
per-universe worker/VPS tier only for long-running or higher-risk workloads.
Snapshots/pools are backend capacity mechanics, not the security contract.
Credential isolation remains fail-closed environment/custody work.

The 1.9 GiB production host cannot carry a meaningful warm full-VPS or duplicate
fleet pool. External capacity needs a measured cost/concurrency model and must
preserve the PLAN invariant that authoring works with zero daemon runtime.

### 2. Never-empty deploys — **ADAPT**

Approve the outcome: a failed deploy must not take the public surface to zero.
Reject ClawHosters/`docker commit` as proof and reject dual old/new writers on
the current shared volume.

Current `origin/main` already moves in the right direction: candidate import is
tested in a `--network=none`, volume-less container while the live fleet stays
up; the workflow records an immutable previous image and can restore it after a
failed forward path. The remaining target is **never-empty ingress plus
single-writer cutover**, not generic start-new-before-stop-old.

Per-universe isolation changes the calculus only when each runtime has exclusive
authority over its own state and cutover is epoch-fenced. Snapshotting while the
old runtime keeps accepting writes creates divergent state. A safe handoff still
needs: prove candidate without the authoritative volume; quiesce/fence the old
writer; take a consistent checkpoint/apply deltas; start exactly one new writer;
canary; then release or exclusively restart the old immutable image on rollback.
With the current 1.9 GiB host, a stable lightweight ingress/control plane plus a
short exclusive writer cutover is more credible than two full fleets.

### 3. Day-0 loaner model — **ADAPT**

Approve the onboarding goal. The TinyAssets shape is a temporary, explicit,
provenance-labelled platform binding with strict per-user/per-universe budget,
rate, provider, privacy/jurisdiction, abuse, expiry, and receipt fields. It must
never be ambient host inheritance and must not silently enter fallback chains.
It should bridge to requester-owned compute or BYOK, not become an unbounded
subsidy or weaken provider authority.

### 4. Hibernation lifecycle — **ADAPT**

Hibernate a **runtime activation/executor**, not the universe. A universe is
durable state, identity, authoring, collaboration, schedules, and receipts; PLAN
already requires authoring with zero daemons. The control plane must stay awake,
own schedules/ingress, and wake execution on admitted demand. V1 should stop
compute without deleting data, preserve SQLite/OKF checkpoint consistency, and
prove bounded wake latency and no missed scheduled effects. Automated deletion
is a separate retention/custody decision and should not ship in V1.

### 5. Unvetted commons warning — **ADAPT**

The incident is relevant, but evaluator/provenance gates alone are insufficient.
A shared executable-artifact surface also needs immutable versions and hashes,
publisher identity, least-privilege capability declarations, static and dynamic
scanning, quarantine, revocation/kill propagation, dependency/SBOM evidence,
and install-time revalidation. Provenance tells us who supplied malware; it does
not prevent execution.

## Module-table corrections

1. The table is not actually the PLAN module map. It omits Harness &
   Coordination and Constraints, while adding sandbox, credential vault,
   conversation ingress, observability, billing, and identity as standalone
   rows. Call it a 14-surface comparison, not module-by-module against PLAN.
2. Daemon Platform is not “one daemon process” today. Current production shape
   is a daemon plus provider-shaped worker containers sharing one
   `tinyassets-data` volume; per-universe runtime allocation remains incomplete.
3. Sandbox status is stale and understated. Current main tracks graph/provider
   code that can falsely attest or execute in-process, and the active
   `engine-os-sandbox` contract is per-job trusted admission with closed
   projections and evidence—not the note's older WebFetch/cwd shorthand.
4. Credential vault is materially overstated. The canonical current spec says
   `.credential-vault.json` is unencrypted recoverable JSON protected only by
   best-effort file modes; the layered cipher/store design is future design.
5. Providers are not simply “subscription-only default.” Host-local API-key
   variables are opt-in, while universe vaults can bind subscriptions or BYO
   keys; ambient/no-universe authority and legacy provider ceilings remain open
   concerns.
6. Uptime/deploy is stale. The three Aug. 7 zero-container incidents are
   historical evidence, but current main has a pre-quiescence candidate-load
   guard, safe previous-image capture, rollback, and explicit fence recovery.
   The fence itself is a data-integrity boundary around exact shared-volume
   consumers.
7. “Full outcome ladder” and some Brain/runtime language blend PLAN target state
   with shipped product state. The comparison should label target, dark seam,
   shipped code, and live-deployed proof separately.

## Material items the note missed

- **Three isolation scopes:** tenant/universe isolation, untrusted-workload
  containment, and credential/authority isolation are different controls. A
  VPS proves only the first unless additional mechanisms are present.
- **Isolation unit mismatch:** ClawHosters provisions per instance, not per user;
  one customer may own multiple instances, and one instance may run multiple
  agents. TinyAssets must separately bind universe, daemon identity, runtime,
  executor, and job.
- **`docker commit` is the wrong state primitive:** it creates mutable
  snowflake images, may capture secrets/transient state, excludes volume data,
  weakens reproducibility/SBOM/signature provenance, and does not solve SQLite
  schema/data rollback.
- **Control-plane shared fate:** dedicated customer VPSs do not remove the Rails,
  Postgres, Redis/Traefik, DNS, or operator control plane as common failure and
  compromise domains.
- **Vendor custody contradiction:** security docs say chats are not accessible
  to ClawHosters, while the homepage advertises live conversation/API-event
  monitoring and full searchable detail. That may be dashboard proxying rather
  than storage, but it requires an explicit access-path threat model.
- **Backup-secret risk:** free config backups include API keys/bot tokens. The
  note does not ask how backup encryption keys, access, rotation, deletion, and
  restore authorization work.
- **Pool hygiene and economics:** atomic claim, post-release wipe/reimage,
  snapshot secret scrubbing, host-key/cloud-init identity regeneration, image
  patch drift, idle-pool COGS, and regional capacity are all unproven. Retail
  price and a solo operator do not prove TinyAssets unit economics.
- **Hibernation/pool tension:** hibernation saves idle compute while a warm pool
  deliberately pays for idle compute. The design needs an arrival-rate and
  latency-SLO model before choosing pool size.
- **IP-auth proxy fragility:** source-IP authentication becomes awkward under
  hibernation, IP reuse, NAT, and migration. TinyAssets should bind actor,
  universe, attempt, budget, and expiry cryptographically rather than inherit
  this pattern.
- **State partition is prerequisite:** moving from one shared SQLite volume to
  per-universe machines requires separating platform-transactional state,
  universe-private state, indexes, schedules, receipts, and cross-universe
  queues. Provisioning cannot substitute for that data-plane design.

## Fold-back

This review does not authorize direct implementation from the source note.
Future OpenSpec work may reuse the adapted directions above, but must start
from current `origin/main` and preserve the existing `engine-os-sandbox`,
single-writer fence, provider-authority, and zero-daemon-authoring contracts.
No STATUS row was added from this stale, heavily shared checkout; a builder
should claim a narrow current-main lane rather than paste the source note's
combined four-implication row.

CLAWHOSTERS_VERDICT: ADAPT
