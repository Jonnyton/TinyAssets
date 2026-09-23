# Design — cloud-only runtime admission

**Candidate verification correction,2026-09-22:** root reproduced four failures
in builder5345d4ad before correcting them: a socket inactivity timeout was not a
whole startup-observation deadline; inherited process evidence was not cleared
after a PID change; a stat/read race could exceed the expected-state read bound;
and boolean true was accepted as schema version1. The candidate now bounds the
caller's wait with one daemon reader, rejects its late result, reads state with a
byte ceiling, validates the version's integer type, and invalidates inherited
cache/mutex state on PID change (PID is not cloud proof). One late metadata reader
may still finish in the background; this is a startup-wait bound, not a claim
that an arbitrary blocked transport thread was forcibly terminated. Independent
review must assess that explicit lifetime tradeoff before release.

Expected-state installation now stages in the same validated volume and uses an
atomic rename so readers never see an in-place partial write. Preparation failure
preserves prior state and does not falsely report it missing. Focused Windows
cohort175passed; workflow actionlint passed, plugin mirror rebuilt. Local Linux
oracle was attempted and reports no Docker engine; it was not started. Linux
and deployed redeploy/restart/rollback evidence remain required and unclaimed.

## Threat model, stated precisely

The founder requirement is that the personal desktop never serves or executes
platform work, **even momentarily**, and that the boundary hold by enforcement
rather than by a naming convention. The adversary that matters is therefore
*accident with authority*: a developer checkout, a stale registration row, a
recovery path looking for any available worker, a copied env file, a second
`cloudflared` connector started "just to test". Every one of those has a local
process that already holds legitimate developer credentials.

It is **not** a model of a motivated attacker with root on the founder's own
machine. That distinction is load-bearing: nothing available in this deployment
is hardware attestation, so a root-level local operator can eventually forge any
software-visible fact. The design goal is *absent-by-default off cloud, and
refused when absent* — not unforgeable.

Two claims this design explicitly does **not** make:

- A droplet-injected secret or a copied tunnel token is **not** non-copyable and
  **not** sufficient physical proof. Possession travels with a file.
- A dev-local claim against a cloned DB is **not** a production breach. It is
  evidence the guard is missing, nothing more.

## Layering: application enforcement vs cloud custody

These are different control families with different owners, and conflating them
is how "cloud-only" became a label.

| Layer | Controls | Owner | Enforced by this change? |
|---|---|---|---|
| **C — Network/credential custody** | Cloudflare tunnel credential scope, Cloudflare Access on the internal origin, DO firewall, GitHub Actions secret custody (`DO_API_TOKEN`, `DO_DROPLET_HOST`, `DO_SSH_KEY`, `DO_SSH_USER`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID`), deploy-only SSH path | Cloud control planes; founder as account holder | **No.** Stated as invariants + verified read-only. Code cannot enforce them. |
| **B — Application admission** | Provenance resolver + refusals at claim CAS, registration, startup/foreground/served execution, origin ingress, recovery | This repo | **Yes.** |
| **A — Storage shape** | `automation_executor_class` CHECK still admits `'tray'`; runtime metadata carries a self-asserted string | This repo | **Yes**, narrowly: registration binds admitted instance id + boot epoch. |

Layer C is *necessary and insufficient*: a copied tunnel token lets any machine
register a connector for the same tunnel and **receive public requests** — and a
connector that receives and refuses has still taken that traffic out of service.
So Layer B refuses at the **origin** as a backstop, and the repo separately
**deletes its own ability to enroll a connector** (see § Off-cloud public
routing). Production authority still rests on Layer C custody, which code
cannot enforce.

## Evidence primitive — decided from deployed infrastructure

The deployment is a single DigitalOcean droplet reached over SSH by
`deploy-prod.yml` (`runs-on: ubuntu-latest`, secrets at
`.github/workflows/deploy-prod.yml:67-71,148-160`), with Cloudflare in front.
No founder decision is needed to pick the primitive; the deployed infrastructure
determines it. Ranked by what a copied checkout does *not* carry:

1. **DO droplet metadata service — primary.**
   `http://169.254.169.254/metadata/v1/id` and `/metadata/v1/region`
   ([DigitalOcean metadata API docs](https://docs.digitalocean.com/reference/api/metadata/droplet-properties/)).
   Link-local; the provider supplies this service inside its droplets. A checkout,
   env file, hostname or compose label does not carry it. No desktop endpoint
   observation is claimed here; absence or mismatch must refuse.
   **Honest strength:** unauthenticated and unsigned — readable by any
   process inside the droplet, and forgeable by a local root operator who adds a
   route/listener. It is absent-by-default, not attestation: unsigned metadata plus a copied expected id is an accidental-start guard, nothing stronger.
2. **Deploy-recorded expected instance — correlation, not a security factor.** The droplet id CI
   reads from the DO API is prepared before startup in the dedicated typed
   `platform-expected-instance.json` in the canonical data volume, separate from
   the post-health `release-state.json` receipt. The resolver requires the
   metadata id to **equal** that expected id. See state placement below.
3. **Build receipt** — existing `/mcp/pulse` `git_sha` gate. Reports the mutable
   deployment receipt, not proof of the running binary or host. Supporting only.

**Decision:** origin correlation = (1) reachable **and** (2) matching. An ordinary
off-cloud start without matching evidence resolves not-cloud; a different droplet
can have reachable metadata but a mismatching id. No actual desktop metadata
probe is claimed. Deliberate local forgery is outside this unsigned primitive's
guarantee; cloud credential/routing custody remains necessary for exclusion.
Missing expected state resolves not-cloud rather than defaulting to cloud.

**Implementation constraint discovered while reading the tree:** the outbound
SSRF driver deliberately classifies `169.254.169.254` as a blocked link-local
target (`tests/test_outbound_ssrf_driver.py:254-255,280`). The metadata probe
must therefore be a dedicated internal client with a hard-coded literal address,
no redirects, a sub-second timeout and no user-supplied input — never routed
through the HTTP-connection/effect surface, and never reachable as a user
capability. Adding it must not relax that classification.

**Process lifetime and deployment ordering (lead + Opus84478, 2026-09-22).**
Resolve the bounded metadata observation and expected-id match once for each new
serving/worker process, before any write transaction. Retain that immutable result
for the process lifetime; claims and provider admission read it without network
I/O. A refused process never silently upgrades its cached evidence: an explicitly
restarted process performs a fresh bounded resolution. This is a startup-origin
backstop, not continuing cloud attestation or a replacement for live lease and
per-universe authority checks. Those checks continue unchanged on each operation.
No per-request metadata poll or retry storm is introduced. Runtime implementation
review must verify that every entry point uses the same process-owned result.

`deploy-prod.yml:317-375` starts and checks the service before its receipt write
at376-395. Merely adding an expected ID to that success receipt would make first
enforcement depend on a field that does not yet exist. Task4 must prepare and
verify the expected-id state before starting the candidate, preserve it across
receipt replacement, and preserve compatible state on rollback. Do not publish a
successful build receipt before health checks to solve this ordering problem.
Record-only acceptance must cover a real redeploy/restart and rollback-state
compatibility, not only one metadata read. Final storage placement is an
implementation-review question; the mutable successful-release receipt is not
itself an unforgeable trust anchor.

`DESKTOP-KCPMGP3` appears in the design only as a loud tripwire log line, never
as the reason for a refusal. The requirement reads *not admitted ⇒ refuse*, so
the desktop is refused for being unadmitted, which is what makes it hold for a
renamed or aliased machine too.

## Enforcement sites (the smallest set that covers the audited boundaries)

```
resolve_platform_runtime_provenance()   <- one resolver, fail-closed
   |
   +-- (A) claim CAS        _transaction_allows_assigned_consumer /
   |                        _assigned_consumer_refusal_reason
   |                        (branch_tasks_v2.py:1170)  <-- non-optional path
   +-- (B) registration     ensure_daemon_runtime (daemon_registry.py:489-530)
   +-- (C) startup/exec     serving boot assert; last provider-authority
   |                        boundary (foreground_run_provider.py:484,595,
   |                        background_served_provider.py:1336,1547)
   +-- (D) origin ingress   platform request admission at the origin
   +-- (E) recovery         watchdog / release-reconcile / stale-runtime retirement
```

- **(A)** must be in-transaction because `_consumer_skip_reason` is
  process-local and pre-CAS. It must bind to the **non-optional** predicate:
  `transaction_check` returns the existing predicate result when
  `authority_claim is None` (`branch_tasks_v2.py:489`), so a mandatory gate
  living only in that callback is opt-out by construction. **Ordering
  constraint:** bounded metadata resolution happens *before* the write
  transaction opens; the CAS evaluates only the resulting trusted,
  process-owned evidence value. No HTTP or socket I/O may run while the SQLite
  write lock is held — that converts a metadata timeout into a database stall.
  The negative test drives `claim_assigned` directly with **no**
  `authority_claim` callback, bypassing the consumer loop entirely — a
  consumer-loop-only test, or one that supplies the callback, passes against the
  unfixed tree and proves nothing.
- **(B)** does **not** rest on `boot_id`. That value is `uuid.uuid4().hex`
  (`assigned_queue_consumer.py:209`): a process incarnation / liveness marker,
  unordered, unauthenticated and carrying no cloud provenance. It is not an
  epoch, not an identity and not a replay defence, and no independent
  anti-replay property is claimed from it. Staleness continues to be handled by
  the **existing** descriptor expiry; legitimate restarts and simultaneous cloud
  workers must keep working, and neither may be refused as "replay". No new
  storage schema or registry is introduced to encode the UUID. What (B) does
  assert is narrower and sufficient: an existing registration row is not
  permission, so authority is re-resolved on read rather than inherited from the
  row.
- **(C)** carries the whole foreground/served surface, because those paths never
  call `claim_assigned` and stamp the class as a literal
  (`foreground_run_provider.py:484,595`,
  `background_served_provider.py:1336,1547`). Queue and registration checks
  cannot cover them; only startup admission plus the last provider-authority
  boundary can. There is no degraded mode: unadmitted serving startup exits
  non-zero rather than serving locally. Per-universe, user-bound authority is
  unchanged — platform provenance is an added condition on the same check, never
  a relocation of authority away from the universe's owner.
- **(D)** is at the origin as a *backstop*, not as the prevention. A refusing
  off-cloud connector has already absorbed public traffic (see § Off-cloud
  public routing). Prevention is removing the in-repo enrollment path plus
  token custody; the origin refusal covers what custody cannot.
- **(E)** closes the fallback hole the directive names explicitly: a retirement
  or recovery plan that finds no admitted successor leaves work **pending**. It
  never re-homes to an unadmitted runtime, and "temporarily" is not an exception.

Storage (Layer A) stays descriptive in this change: the `'tray'` CHECK value is
not removed here, because removing a degenerate enum value kills every branch
that tested for it and that belongs in its own lane.

## Verification facts that must come from cloud APIs

Read-only, on the trusted hosted runner class `deploy-prod.yml` already uses
(`ubuntu-latest`), in a dedicated workflow with no write scopes. No new MCP tool,
no new provider account, no new privileged agent. Keys are never printed: the job
compares inside itself and emits only ids and booleans; `::add-mask::` any
derived value; never `set -x`.

| Fact | Source | Call |
|---|---|---|
| Expected droplet id, region, public IPv4 set | DO API, `DO_API_TOKEN` | `GET https://api.digitalocean.com/v2/droplets` (Bearer) — [DO API ref](https://docs.digitalocean.com/reference/api/digitalocean/#tag/Droplets) |
| Which connectors serve the public tunnel | Cloudflare API, `CLOUDFLARE_API_TOKEN` | `GET /client/v4/accounts/{account_id}/cfd_tunnel/{tunnel_id}/connections` — assert every active connector origin IP ∈ the droplet IP set (no second connector anywhere) — [CF tunnel API](https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/) |
| Internal origin resolves to the selected tunnel | Cloudflare API, `CLOUDFLARE_ZONE_ID` | `GET /client/v4/zones/{zone_id}/dns_records?name=mcp.tinyassets.io`; compare selected tunnel target, not merely record type — [CF DNS API](https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/list/) |
| Canonical MCP paths select the expected Worker | Cloudflare API, `CLOUDFLARE_ZONE_ID` | `GET /client/v4/zones/{zone_id}/workers/routes`; require continuous coverage and reject or mark unknown competing overrides. This checks configured routing, not deployed Worker source or credential custody. |
| Which build is actually running | in-repo, existing | `python scripts/deployed_sha.py --assert-contains <sha>` (bearer `/mcp/pulse`) |

Provider documentation above establishes contract shape, not deployment.
Hosted run35694437735 at06:21UTC2026-09-22 observed reachable container metadata,
resolved expected droplet and identity_match=true, plus three canonical Worker
paths bound correctly. Tunnel/DNS facts remain unknown for missing account/tunnel
IDs; custody unknown and SSH trust TOFU-unverified. No raw identities or secrets
were retrieved locally. Overall unknown, enforcement none, boundary not closed.

## Exact remaining external facts (not assumed, not blocking the other lanes)

1. **Cloudflare account id and the public tunnel id.** Neither appears in the
   inventoried secret names (only `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID`).
   Obtainable read-only via `GET /client/v4/accounts` **if** the existing token
   carries account-list + `Cloudflare Tunnel: Read` scope; the token's scope was
   never read. Otherwise a non-secret repo **variable** (not a secret) is needed.
   Blocks only the connector-set verification, not the resolver.
2. **Container metadata reachability:** observed reachable and matching the
   expected droplet in hosted run35694437735. This resolves the builder gate,
   not custody. No copied host metadata fallback is required or authorized.
3. **The droplet's id** (we hold `DO_DROPLET_HOST`, a hostname/IP, not an id).
   Derivable read-only in CI from fact 1's DO call; recorded nowhere in-repo yet.
4. **Whether any non-droplet connector is registered today.** Answerable only by
   the connector call above, i.e. gated on fact 1.

No founder decision is requested for any of these: 1–4 are cloud-API reads on
infrastructure the platform already owns.

## Test matrix (all required; the negatives are the point)

| # | Test | Asserts |
|---|---|---|
| 1 | **Negative direct claim** — unadmitted, valid ready assignment, pending `cloud` task, `claim_assigned` called **directly** | zero claims; refusal reason recorded |
| 2 | **Negative registration** — unadmitted `ensure_daemon_runtime` | refuses; no `runtime_registration: cloud_worker` row written |
| 3 | **Negative startup/foreground** — unadmitted serving boot and an unadmitted foreground/served provider turn | boot exits non-zero; turn refuses, no provider process spawned |
| 4 | **Replayed stale registration** — a row admitted for instance X + boot epoch N, then read by an unadmitted process (and by a different boot epoch) | authority refused on read; row existence confers nothing |
| 5 | **Local spoofed labels** — set every env var the container sets (incl. `TINYASSETS_ALLOW_CLAUDE_SERVING`, `TINYASSETS_DATA_DIR=/data`), hostname aliased to `mcp.tinyassets.io`, compose labels matched | still refused at all four sites |
| 6 | **Recovery/fallback** — stale-cloud-worker retirement and watchdog with no admitted successor | work stays pending; nothing re-homed to an unadmitted runtime, not even momentarily |
| 7 | **Ingress** — tunnel-forwarded platform request arriving at an unadmitted origin | origin refuses before any universe work |
| 8 | **Cloud positive** — admitted process claims a `cloud` task | claim succeeds, audience records the resolved CLOUD class, run proceeds |
| 9 | **Free-only first answer** — new user completes their own OpenRouter OAuth callback and eligible free-model approval, no copied key or borrowed subscription | actual tool-capable answer served entirely on admitted cloud runtime |

Tests 5 and 1 are the load-bearing pair: without them the change is a rename.
Test 9 is the acceptance the directive names (`new-user free-provider
onboarding`) and must not be satisfied by any founder-held subscription.

New negative regressions must demonstrate the defect against the unfixed tree;
preserved-behavior positives may already pass there. Run the relevant suite on
the Linux oracle before push; do not substitute Windows-only evidence for Linux
process/network behavior.

## Colliding as-built specs (named, not edited here)

The directive says it supersedes earlier host/tray-bridge, host-fleet and
local-fallback language. Two as-built capabilities still assert that shape, so a
reviewer must see the collision rather than discover it at sync time:

- **`openspec/specs/desktop-host-runtime/spec.md`** — `:8` has the tray
  launching provider-pinned daemon subprocesses, *the local MCP server*, and a
  local Cloudflare tunnel gated only on `TINYASSETS_TRAY_ENABLE_TUNNEL` plus
  token availability; `:24,:45` have it starting daemons against a local data
  root; `:59` has it restarting a local MCP server and tunnel after process
  death with backoff. That is a local serving/ingress path enabled by an env var
  and token possession — precisely what this change refuses. It is also the
  clearest route by which the founder's desktop could serve "momentarily".
- **`openspec/specs/daemon-identity-and-host-pool/spec.md:76,97`** — a host-pool
  client that registers host rows and returns a `host_id`. Related fleet
  language is already marked deleted in `daemon-runtime-and-dispatch:82`
  ("the host-run worker fleet this originally coordinated is deleted"), so this
  is likely stale spec text rather than live behaviour — but it is unverified
  here and must not be assumed dead.

Resolution belongs to task 12 (sync), after review: the local tray may keep
**developer and client** functions, and must lose any requirement that lets it
serve platform traffic or publish an ingress. A developer tool is not promoted
into a platform service by having a token. This change does not edit those specs.

## Naming the guarantee honestly (review finding 1)

The evidence primitive is an **unsigned, unauthenticated link-local read plus a
comparison against an id the deploy copied into a file.** Both halves are
software-visible and copyable. It is therefore:

- **Is:** an accidental-start guard. It makes "cloud" *absent by default* on any
  machine that is not the droplet, so a developer checkout, a stale row, a
  recovery path or a second connector started "just to test" refuses instead of
  proceeding. That is the failure mode that actually threatens this deployment.
- **Is not:** attestation. Nothing here is signed, nothing is rooted in hardware,
  and a local root operator can add a route or listener on `169.254.169.254` and
  drop the expected id into the release file. No document in this change may
  describe it as attestation, proof of physical provenance, or a boundary a
  motivated local operator cannot cross. Where earlier drafts said "attested",
  read **admitted** — the resolver's verdict, not a proof.

**Where production authority actually rests:** Layer C custody (table above) —
who holds `CLOUDFLARE_TUNNEL_TOKEN`, the Access service token, `DO_SSH_KEY`, and
the GitHub Actions secret store. Layer B refusals reduce blast radius and make
accidents loud; they do not substitute for custody. Any claim that the founder
boundary is closed must cite both layers. Layer C requires verified cloud access
and custody controls; Python refusal checks alone cannot establish it.
Unsigned metadata is the **backstop only**: the boundary is not closed until
actual cloud routing, credential custody and data custody close it too.

**Live milestone and what it does not settle (2026-09-22).** PR #3913, sha
`dfa22598c35aabad7be27aacbff75d300e17b584`, removed daemon/tray/plugin tunnel
startup; hosted build `35689968798` and deploy `35690255704` passed public
handles and the protected-SHA gate at 05:20 UTC. Ordinary primary-app retest 8
completed 22:28 PDT: five controls pass, sequential 37.3s, parallel 158.4s,
intermittents still open. None of that is cloud-boundary or free-user proof —
the cloud-side tunnel remains and custody is open. The bounded preflight is
PR #3914, mergedfdb6ff15; actual hosted observation35694437735 is recorded above.
Do not upgrade its limited passing facts into an overall cloud-boundary claim.

## Off-cloud public routing: prevention, not detection (review finding 2)

The review is correct and the earlier draft was wrong. `deploy/cloudflare-worker/
worker.js:43,90` forwards every public request to the **tunnel hostname**
`https://mcp.tinyassets.io`, so Cloudflare's edge picks whichever connector is
registered for that tunnel. Cloudflare load-balances across a tunnel's active
connectors; a second connector that receives a request and refuses it has still
**absorbed that request's share of public availability** — the user sees an
error, not a failover. Auditing apex DNS (the earlier plan) never sees this
route at all, because the apex record is unchanged when a rogue connector
joins. Origin refusal plus a periodic audit is therefore detection *after* the
availability damage, not prevention.

Enumerating the prevention levers actually available in this topology:

| Lever | Prevents off-cloud enrollment? | Where it lives |
|---|---|---|
| Remove the in-repo code path that can enroll a connector | **Yes, for that accidental-start path only** | This repo (Layer B) |
| Tunnel-token custody: only authorized cloud systems can obtain connector credentials | Prevents unauthorized enrollment only to the extent custody/access policy is actually enforced | Cloud infrastructure (Layer C) |
| Origin refusal when unadmitted | No — refuses *after* receiving | Layer B |
| Periodic connector audit | No — detects afterwards | CI |

The verified Cloudflare contract says tunnel-token possession permits running
a connector. That supports protecting the token; it does not establish that no
additional provider-side restriction exists. Do not assert a universal absence
of Cloudflare controls without evidence. Prevention here requires removing the
repo's local enrollment path plus independently verified cloud credential/access
policy; a periodic connector inventory only detects the currently visible set.

Credential exposure requires both invalidating future enrollment with the old
credential and evicting established unauthorized connections. Rotation alone is
insufficient. The provider's tunnel-token documentation describes connection
cleanup as well as rotation; replacing the whole tunnel is not assumed to be the
only eviction mechanism. Determine the supported targeted cleanup and availability
sequence before any mutation. No rotation, eviction or tunnel replacement is
authorized by an observation report. Repository secret names read at05:43UTC
2026-09-22 include no `CLOUDFLARE_TUNNEL_TOKEN`; this is not proof of absence from
environment/organization secrets, cloud files, backups or prior copies. Secret
values were not read. Data-root and session-key custody remain separately open.

**The in-repo path is concrete and was found by inspection**, not assumed:
`fantasy_daemon/__main__.py:3294` defines `_start_tunnel(port, tunnel_name)`,
which execs `cloudflared tunnel run <tunnel_name>` when a name is given and
`cloudflared tunnel --url http://localhost:<port>` (a public quick tunnel) when
it is not. It is called at `:3542`, `:3755` and `:3844`, and re-exported from
`tinyassets/__main__.py:48,63` and the plugin runtime mirror
(`packaging/claude-plugin/.../tinyassets/__main__.py:48,63`). Given local
`cloudflared` credentials and the production tunnel's name, that function
enrolls the founder's desktop as a connector for the production tunnel and it
then receives public traffic. The quick-tunnel branch publishes a
`trycloudflare.com` URL straight off the desktop. `openspec/specs/
desktop-host-runtime/spec.md:8,59` is the as-built spec for exactly this,
gated only on `TINYASSETS_TRAY_ENABLE_TUNNEL` plus token availability.

**Specified prevention:** the platform daemon/tray SHALL have no code path that
enrolls a Cloudflare connector or publishes a public ingress — the named-tunnel
branch and the quick-tunnel branch both go, along with the env gate that arms
them. This is a **deletion**, not a new guard: a capability that does not exist
cannot be started by accident, and it does not depend on the resolver working.
A developer tool is not promoted into a platform service by holding a token.
Removal of the capability is in the delivery tasks; token custody is stated as a
Layer C invariant and verified read-only, because code cannot enforce it.

## Bounded hosted preflight (review finding 3)

The preflight was designed to observe three previously unknown facts:
(a) whether `169.254.169.254` answers from inside the deployed daemon container,
(b) the droplet id the resolver must match, and
(c) whether any connector outside the droplet serves the public tunnel today.

`scripts/cloud_only_preflight.py` (hosted run35694437735) resolves
them read-only from hosted CI. Its bounds are part of the design, not
implementation detail:

- **Read-only only.** No POST/PUT/PATCH/DELETE to any provider, no SSH mutation,
  no infrastructure change of any kind. The DO/Cloudflare calls used are `GET`.
- **Not a remote command runner.** The container metadata probe is one fixed,
  hard-coded SSH command on the configured deployment host
  (`docker exec <service> python -c <fixed literal>` reading the
  literal metadata URL); there is no user-supplied shell, no argument
  interpolation into a shell, and no arbitrary `exec` of caller-supplied Python.
- **Sanitized output only.** It emits typed verdicts (`pass` / `refuse` /
  `unknown`) plus booleans and counts. The expected instance match is a boolean;
  no enumerable droplet-id digest is emitted.
  It never prints raw API bodies, tokens, IP addresses, hostnames, connector
  ids, user data or private connection state. Connector location is reported as
  a count of in-set vs out-of-set connectors — never the addresses.
- **Missing permission is `unknown`, never `pass`.** A token that lacks scope, a
  missing secret, an unreachable API and a non-200 all produce a typed
  `unknown`/`refuse` with a reason code. There is no path on which absent
  evidence reads as a passing proof.
- **Runs on hosted CI only**, with the existing credential *names*
  (`DO_API_TOKEN`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID`, the deploy SSH
  secrets). No new secret, no new provider account, no new MCP tool. It must not
  be run on the founder's PC with production credentials.

**Workflow placement (merged and executed in run35694437735):** a
new `.github/workflows/cloud-only-preflight.yml`, `runs-on: ubuntu-latest`,
`permissions: contents: read` only, default-branch `workflow_dispatch` only,
**never** on `pull_request` (a fork PR must not reach these secrets). It is a
separate workflow from `deploy-prod.yml` so it never gains deploy scopes, and it
is *not* wired as a required check in this change. The first-step branch check
is an ordinary dispatch guard, not a secret-access policy: the workflow can be
edited. A protected cloud access policy and credential lifecycle still require
separate verification. A successful deployed SHA proves code placement, never
exclusive credential possession. No production credential is used locally.

**This is explicitly incomplete.** A record-only preflight and a record-only
resolver observe; they do not enforce. Until tasks 7–10 flip the refusals and a
deployed sha proves them live, the cloud-only boundary is **not closed**, and no
document in this change may report otherwise.

## Free-user acceptance is a real authorization, not an invented provider

Earlier wording ("no credential deposited", "zero-setup provider") implied a
capability that neither exists nor is required. Corrected: the free path is the
**user's own OpenRouter account**, authorized by that user. The acceptance is:

1. A brand-new user completes **OpenRouter's OAuth PKCE** authorization in their
   own browser, against their own account
   (`https://openrouter.ai/docs/use-cases/oauth-pkce` — *cited from the
   documented contract shape; see § Source citations and their limits*).
2. The automatic callback returns to the platform and the grant is exchanged.
3. The user approves an **eligible free model** for their universe.
4. The user's **first actual tool-capable response** is served, end to end, on an
   admitted cloud runtime.

No key copying, no borrowed or founder subscription, no account-specific patch,
and no automatic change to any existing user's workflow. An answer produced from
any credential the user did not themselves authorize does **not** satisfy this.

## Local isolated tests vs production authority (review finding 5)

These are different things and the change must keep saying so:

- **Local isolated developer tests** — a temp data root, a fixture DB, a
  monkeypatched resolver — acquire **no production authority**. They cannot
  claim a live task, register a live runtime, serve public traffic or reach the
  production DB. Running them off-cloud is correct and stays possible after this
  change — local development, test and browser use are permitted without
  production authority; the resolver is injected in tests, never satisfied by an
  env var (a tests-only env var in production code is reachable from `env_file`).
  A fixture DB passing these self-consistency checks is **not** demonstrated
  access to production data, and a successful diagnostic run establishes no
  custody or policy. Custody is never established by a code label, a variable
  name or a green check.
- **Production authority** is exactly: claiming a live assigned task, holding a
  live runtime registration, serving traffic that arrived through the public
  tunnel, or relaying a model turn for a real universe. Those are what the
  resolver gates, and they are what the desktop must never acquire.

**Red-before scope:** the **new negative regressions** (test matrix 1–7) SHALL
be run against the unfixed tree and SHALL fail there — without that they may be
vacuous. The **positive** cases (8 cloud success, 9 free-provider acceptance)
assert preserved behaviour and MAY pass at baseline; requiring them to fail
first would be theatre.

## Source citations and their limits

Every provider URL in this document is the official public documentation for the
contract shape being relied on:

- DigitalOcean droplet metadata — `https://docs.digitalocean.com/products/droplets/how-to/access-metadata/`
  (reference: `https://docs.digitalocean.com/reference/api/metadata/droplet-properties/`).
  **Limit:** the service is unauthenticated and unsigned; DO documents it as a
  convenience, not an identity proof.
- DigitalOcean API, droplet list — `https://docs.digitalocean.com/reference/api/reference/droplets/`.
  **Limit:** requires a token with droplet read; a read-scoped token is enough.
- Cloudflare Tunnel connections — `https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/subresources/connections/methods/get/`.
  **Limit:** requires the account id and tunnel id plus `Cloudflare Tunnel: Read`;
  neither id is in the inventoried secret names.
- Cloudflare DNS records list — `https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/list/`.
- OpenRouter OAuth PKCE — `https://openrouter.ai/docs/guides/overview/auth/oauth`.

**Lead verification, 2026-09-22 UTC:** the official pages above were read through
the web research tool; moved metadata and OAuth URLs are corrected here. The
metadata ID is an integer returned over link-local HTTP, not signed attestation.
Tunnel connections expose nested `conns[].origin_ip`; incomplete pagination and
absent observations must remain unknown. These public contracts do not establish
the actual deployed account, routing, metadata reachability or credential custody.

Two additional custody contracts were read, not exercised:
`https://developers.cloudflare.com/tunnel/reference/tunnel-tokens/` says token
rotation prevents new connections using the old token but existing connectors
remain until restarted; rotation alone therefore does not establish exclusion.
`https://developers.cloudflare.com/fundamentals/api/how-to/restrict-tokens/`
describes API-token IP/TTL restrictions (Verify Token is exempt from IP filtering),
not an IP restriction on connector tokens. No token rotation or access change was
performed. These constraints require cross-family review before implementation.

## Expected-instance state placement (task 4 implementation decision, 2026-09-21)

The ordering constraint above asked for the expected identity to be prepared
before the candidate starts and preserved across receipt replacement and a
compatible rollback. A field in the existing success receipt was considered first
and rejected on three counts, all readable in `deploy-prod.yml`:

1. **Wrong time.** `Publish release-state receipt` runs after the fail-safe
   deploy and the public canary (steps at `:317`, `:347`, `:376`). A candidate
   that resolves provenance at startup would read a field that does not exist
   yet on its first boot, so first enforcement would depend on absence.
2. **Rewritten whole.** The receipt is generated by `cat > release-state.json`
   and installed over the previous file. Any rewrite that does not know about the
   field erases it; that includes rollback and reconcile paths that publish their
   own receipt.
3. **Wrong role.** The mutable success receipt is already documented above as not
   a trust anchor, and it carries *build* identity. Expected *machine* identity
   has a different lifetime — it survives image rollback because the droplet does
   not change — so co-locating them makes each rewrite a chance to lose it.

**Decision:** one minimal dedicated typed file in the existing data root —
`platform-expected-instance.json`, resolved through `tinyassets.storage.data_dir()`
with no path logic of its own, so a container deploy with
`TINYASSETS_DATA_DIR=/data` writes and reads inside the same bind-mount. Shape:
`{"schema": "platform_expected_instance", "version": 1,
"expected_instance_id": "<bare digits>", "recorded_at": …, "enforced": false}`.
No storage schema, no table, no migration, no MCP surface, no new credential —
`DO_API_TOKEN` already exists for the preflight and is read only on hosted CI.

The identity comes from the DigitalOcean inventory read matched exactly against
`DO_DROPLET_HOST` (`scripts/prepare_expected_instance_state.py` reusing
`cloud_only_preflight.resolve_expected_droplet`), never from the droplet's own
metadata answer — recording what the box claims and then comparing it to the same
claim would be circular. The raw id stays in an underscore-prefixed internal fact
field, which the preflight's output sanitizer already strips, and neither CI logs
nor the runtime verdict object ever carries it.

**Record-only consequences, stated plainly.** The preparation step is
`continue-on-error: true` in this slice: an observation must not be able to take a
deploy down. If it does not run, the resolver observes `expected_identity_missing`
and records not-cloud, which is the fail-closed direction and changes no admission
behaviour. The enforcement flip (tasks 6–8) must make that step required, because
at that point a missing expectation stops being an observation and starts being a
refusal. What is built here is the candidate only: one resolver, one immutable
per-process observation, one sanitized startup log line, zero refusal sites.
Task 5's live halves — that it resolves CLOUD on the real droplet, that the
expected id survives a real redeploy, restart and rollback — are **not** proved by
any of this and remain open.

## Reading the main process's cached observation back (task 4/5 slice, 2026-09-22)

The record-only candidate above resolves its verdict at startup and **only logs
it**. That closes nothing for task 5, which has to confirm the verdict the real
droplet's serving process actually holds. Two routes were considered and one
rejected on evidence:

* **The hosted preflight's own metadata read is not this evidence.** It is a
  separate short-lived CI-driven child reaching a metadata service; it says
  nothing about what the long-lived main serving process resolved and cached at
  its own startup. Same fact class, different process, different lifetime.
* **Raw or shared log scraping is rejected** (Opus57466 architecture review,
  2026-09-22, accepted). A fluentd/log-driver stanza in compose is configuration,
  not a runtime observation: a dual local cache may or may not still make
  `docker logs` answer, and nothing in this change has *observed* that. We do
  not claim the log route is available and we do not build on it.

**Decision: read it back over the existing authenticated `/mcp/pulse`.** That
route already exists, already sits behind the same bearer boundary as the rest of
`/mcp`, already has the operational probe principal bound to it, and already has
a caller (`scripts/deployed_sha.py`) that fetches it once inside the hosted
post-receipt step. No new route, workflow, secret, credential, permission or
principal is introduced, and no auth rule is widened.

**Two review overclaims about `/mcp/pulse`, corrected (lead, 2026-09-22).** The
architecture review justified this route partly by calling `git_sha` a binary
identity and `uptime_seconds` a process-birth marker. Neither is true here:

1. `git_sha` is read from the **mutable release receipt** the deploy writes to
   the host volume (`_load_release_state`), exactly the limit
   `scripts/deployed_sha.py` already documents (`proves: "receipt"`). It is not
   derived from the running binary. Binary freshness SHALL NOT be inferred from
   it, and this slice does not.
2. `uptime_seconds` is measured from `_pulse_started`, a monotonic stamp taken
   when `create_streamable_http_app()` **constructs the app**, not at strict
   process birth and not at container start. It is an app-construction elapsed
   time and nothing more.

So the readback establishes exactly one fact: *the process that answered this
request holds a cached startup verdict of X*. It SHALL NOT be read as binary
freshness, as the current container incarnation, as a statement about all
workers (one response samples one responding worker), as attestation, or as
credential/data custody. Those remain open for the enforcement flip to prove
separately, each on its own evidence.

**Non-mutating peek.** The endpoint is a health `GET`. It must never become a
place where a fresh metadata resolve is triggered, so the readback uses a peek
that never calls the resolver, never initializes the cache, and holds no lock
that a resolving caller needs. Its states are exactly three: *observed cloud*,
*observed not-cloud with a reason*, and **explicit unknown** — unobserved,
failed, or inherited across a PID change. Unknown is a first-class value, never
smoothed into `CLOUD` and never a trigger to go and find out.

**Sanitized, canary-only, fixed schema.** The field is `platform_runtime_provenance`
and is emitted **only** when the request's already-resolved identity is the
operational probe principal (`current_identity_or_none()`, the existing request
identity API). Every other authenticated caller gets the pulse fields it gets
today, byte-identical; unauthenticated callers stay rejected by the middleware
before the endpoint runs. The payload is the sanitized observation shape the
module already defines — verdict, snake_case reason token, booleans, `observed`,
and `mode` — with no instance id, no expected id, no hash, no address, no path
and no secret. The field is **optional in the response schema**: a consumer that
does not see it SHALL treat provenance as unknown rather than inferring anything,
because an older build simply does not carry it.

**Reporter stays a diagnostic.** `scripts/deployed_sha.py --report-provenance`
projects an allowlist out of the **same already-fetched** pulse response — no
second request, no raw server dict echoed into output. A missing, malformed or
unexpected value prints as unknown.

The allowlist is of **known protocol values, not token shapes**. A snake_case
shape check was tried first and was wrong three ways at once, each of them the
leak the sanitizer exists to stop: `reason="instance_<id>"` is a well-formed
token that carries a droplet id into a CI log; `mode="enforcement_enabled"`
prints a fake enforcement claim out of a record-only diagnostic; and Python's
`$` matches *before* a trailing newline, so `"instance_match\n"` satisfies a
`^...$` check and injects a line break. Matching is exact membership with no
`strip()` and no normalization — a value that needs cleaning up before it
matches is not the protocol value, and cleaning it is precisely how the newline
gets through. A reason the reporter has not learned yet prints as unknown; a
test harvests the module's own reason-construction sites so the allowlist
cannot silently fall behind the thing it reports on. It SHALL NOT change the
existing gate's exit semantics: `--assert-contains` still passes or fails purely
on the receipt comparison, and an unknown provenance is **not** a pass of cloud
acceptance — it is the absence of an observation. The hosted post-receipt
`Verify protected receipt contains target revision` step gains the flag only, so
the evidence lands in a run log that already exists.

## Rollout

### Residual authority repair after deployed PR3919

PR3919 deployed the initial guards as042cdce8; PR3920 synced their bounded
as-built contract as16e6f0bf. The subsequent source audit identified a remaining
provider-service class literal, worker-descriptor renewal based only on stored
identity, and the legacy cloud-activation claim/resume predicate. These are
concrete missing application checks, not demonstrated access from a local clone
to production state or a proved production execution bypass.

This repair uses the same process observation: provider-work authority derives
its class through the cache-only helper inside its existing transaction;
descriptor publication and renewal require admission before reading/writing the
slot; cloud-class legacy claims and resumption resolve before the store call and
check only cached admission inside their mandatory lifecycle predicate. No
network observation may occur under a database transaction. Existing owner,
lease, grant and model-binding checks remain independent and unchanged.

Descriptor clearing remains a capacity-removing operation, with existing exact
worker checks intact; it is not publication or renewal. Existing generic and
non-cloud activation semantics are not silently redefined by the cloud-class
repair. This does not grant them platform-serving/provider-execution authority.
The test seam stays an explicitly injected observation, including independently
in spawned test children, never a production environment bypass.

New negatives must fail on the unchanged runtime before the guards and pass
afterward; existing admitted-path checks retain their assertions. The local
Linux engine remains unavailable and must not be started on the personal PC;
hosted Linux evidence is required, not replaced by Windows results. Exact-head
independent review, verified deployment, public canary and ordinary rendered app
acceptance still gate release claims. Custody, maintenance-authority coverage,
the broader recovery matrix and clean free-user onboarding remain open.

The runtime builder's actual-metadata gate is satisfied by hosted
run35694437735, not by prediction. Runtime code may now be built for the
record-only slice; enforcement still requires its own live positive observation
and reviewed refusal sites. Unknown custody facts remain open independently.

Resolver + sanitized startup record/readback land in **record-only** mode; confirm on the droplet that
the observed instance matches the expected id; then flip (A)–(E) to refuse in one
change. A resolver that cannot resolve on the real droplet must never be flipped —
that is how a cloud-only guard takes the platform down. Record-only is
**observation, not enforcement, and not guaranteed risk-free**: it still adds a
metadata read and a startup log record on a live path, so it is staged and watched
rather than assumed inert.
