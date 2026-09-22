# Design — cloud-only runtime admission

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
   ([DigitalOcean metadata API docs](https://docs.digitalocean.com/reference/api/metadata-api/)).
   Link-local; answered only from inside a droplet. A checkout, env file,
   hostname or compose label does not carry it, and on the founder's desktop
   nothing answers that address, so the resolver's natural failure there is
   refusal. **Honest strength:** unauthenticated and unsigned — readable by any
   process inside the droplet, and forgeable by a local root operator who adds a
   route/listener. It is absent-by-default, not attestation: unsigned metadata plus a copied expected id is an accidental-start guard, nothing stronger.
2. **Deploy-recorded expected instance — second factor.** The droplet id CI
   reads from the DO API is recorded into the release state the deploy already
   writes (`release-state.json`, `deploy-prod.yml:391-393`;
   `_load_release_state` / `scripts/deployed_sha.py`). The resolver requires the
   metadata id to **equal** the recorded expected id.
3. **Build identity** — existing `/mcp/pulse` `git_sha` gate. Proves which
   build, never which host. Supporting only.

**Decision:** cloud-origin evidence = (1) reachable **and** (2) matching. The desktop fails
(1); a stolen env file or a rebuilt container on another machine fails (1) and
(2); a droplet whose deploy state was never written fails closed rather than
defaulting to cloud.

**Implementation constraint discovered while reading the tree:** the outbound
SSRF driver deliberately classifies `169.254.169.254` as a blocked link-local
target (`tests/test_outbound_ssrf_driver.py:254-255,280`). The metadata probe
must therefore be a dedicated internal client with a hard-coded literal address,
no redirects, a sub-second timeout and no user-supplied input — never routed
through the HTTP-connection/effect surface, and never reachable as a user
capability. Adding it must not relax that classification.

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

Provider documentation above is official public documentation, cited as the
contract shape. It is **not** observed deployment: nothing in this change ran any
of these calls, and none of these values has been read.

## Exact remaining external facts (not assumed, not blocking the other lanes)

1. **Cloudflare account id and the public tunnel id.** Neither appears in the
   inventoried secret names (only `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID`).
   Obtainable read-only via `GET /client/v4/accounts` **if** the existing token
   carries account-list + `Cloudflare Tunnel: Read` scope; the token's scope was
   never read. Otherwise a non-secret repo **variable** (not a secret) is needed.
   Blocks only the connector-set verification, not the resolver.
2. **Is `169.254.169.254` reachable from inside the daemon container as
   deployed?** Normally yes on a DO droplet's default bridge, but this droplet's
   egress policy was not tested. Must be probed once on the droplet before the
   resolver's primary evidence is committed to. Fallback if unreachable: read the
   metadata id on the host during deploy and inject it — which is copyable, so
   the resolver would then need a second non-copyable factor, and the honest
   claim would weaken. This is the single fact that could change the design.
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
boundary is closed must cite both layers, and Layer C is verified, never coded.
Unsigned metadata is the **backstop only**: the boundary is not closed until
actual cloud routing, credential custody and data custody close it too.

**Live milestone and what it does not settle (2026-09-22).** PR #3913, sha
`dfa22598c35aabad7be27aacbff75d300e17b584`, removed daemon/tray/plugin tunnel
startup; hosted build `35689968798` and deploy `35690255704` passed public
handles and the protected-SHA gate at 05:20 UTC. Ordinary primary-app retest 8
completed 22:28 PDT: five controls pass, sequential 37.3s, parallel 158.4s,
intermittents still open. None of that is cloud-boundary or free-user proof —
the cloud-side tunnel remains and custody is open. The bounded preflight is
PR #3914, **pending CI with no live observation yet**; no cloud fact may be
asserted from it until it has actually run.

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
| Remove the in-repo code path that can enroll a connector | **Yes, for accidents** — the only class in scope | This repo (Layer B) |
| Tunnel-token custody: token exists only in the droplet's env, rotated on any exposure | **Yes, for the credential** | Layer C, founder/CI |
| Origin refusal when unadmitted | No — refuses *after* receiving | Layer B |
| Periodic connector audit | No — detects afterwards | CI |

The verified Cloudflare contract says tunnel-token possession permits running
a connector. That supports protecting the token; it does not establish that no
additional provider-side restriction exists. Do not assert a universal absence
of Cloudflare controls without evidence. Prevention here requires removing the
repo's local enrollment path plus independently verified cloud credential/access
policy; a periodic connector inventory only detects the currently visible set.

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

Three facts the design depends on have never been observed:
(a) whether `169.254.169.254` answers from inside the deployed daemon container,
(b) the droplet id the resolver must match, and
(c) whether any connector outside the droplet serves the public tunnel today.

`scripts/cloud_only_preflight.py` (added in this change, **not run**) resolves
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

**Workflow placement (candidate added, not deployed or executed):** a
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

## Rollout

The runtime builder is gated on an **actual metadata diagnostic**, not on a
predicted one: PR #3914's preflight must have run and reported a real
observation first. No cloud fact is invented ahead of it, and nothing here
depends on a result that does not yet exist.

Resolver + ledger then land in **record-only** mode; confirm on the droplet that
the observed instance matches the expected id; then flip (A)–(E) to refuse in one
change. A resolver that cannot resolve on the real droplet must never be flipped —
that is how a cloud-only guard takes the platform down. Record-only is
**observation, not enforcement, and not guaranteed risk-free**: it still adds a
metadata read and a ledger write on a live path, so it is staged and watched
rather than assumed inert.
