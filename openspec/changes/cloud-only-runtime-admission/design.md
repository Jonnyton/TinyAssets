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
| **A — Storage shape** | `automation_executor_class` CHECK still admits `'tray'`; runtime metadata carries a self-asserted string | This repo | **Yes**, narrowly: registration binds attested instance id + boot epoch. |

Layer C is *necessary and insufficient*: a copied tunnel token would let any
machine register a connector for the same tunnel and receive public requests.
That is exactly why Layer B must refuse at the **origin**, independent of how the
request arrived.

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
   route/listener. It is absent-by-default, not attested.
2. **Deploy-recorded expected instance — second factor.** The droplet id CI
   reads from the DO API is recorded into the release state the deploy already
   writes (`release-state.json`, `deploy-prod.yml:391-393`;
   `_load_release_state` / `scripts/deployed_sha.py`). The resolver requires the
   metadata id to **equal** the recorded expected id.
3. **Build identity** — existing `/mcp/pulse` `git_sha` gate. Proves which
   build, never which host. Supporting only.

**Decision:** attestation = (1) reachable **and** (2) matching. The desktop fails
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
as the reason for a refusal. The requirement reads *not attested ⇒ refuse*, so
the desktop is refused for being unattested, which is what makes it hold for a
renamed or aliased machine too.

## Enforcement sites (the smallest set that covers the audited boundaries)

```
resolve_platform_runtime_provenance()   <- one resolver, fail-closed
   |
   +-- (A) claim CAS        _transaction_allows_assigned_consumer / authority_claim
   |                        (branch_tasks_v2.py:462-511)  <-- INSIDE the txn
   +-- (B) registration     ensure_daemon_runtime (daemon_registry.py:489-530)
   +-- (C) startup/exec     serving boot assert; foreground + served provider
   |                        execution (agent_runtime_provider_execution.py:1225,
   |                        background_served_provider.py:1336,1547,
   |                        foreground_run_provider.py)
   +-- (D) origin ingress   platform request admission at the origin
   +-- (E) recovery         watchdog / release-reconcile / stale-runtime retirement
```

- **(A)** must be in-transaction because `_consumer_skip_reason` is
  process-local and pre-CAS. The negative test drives `claim_assigned` directly,
  bypassing the consumer loop entirely — a consumer-loop-only test passes against
  the unfixed tree and proves nothing.
- **(B)** additionally defeats **replay**: the runtime row binds the attested
  instance id and a boot epoch, and readers re-validate. An existing row is not
  permission.
- **(C)** has no degraded mode. Unattested serving startup exits non-zero; it
  does not serve locally.
- **(D)** is at the origin by necessity: we cannot stop a copied token from
  dialling Cloudflare, so the origin must refuse to answer platform traffic when
  unattested.
- **(E)** closes the fallback hole the directive names explicitly: a retirement
  or recovery plan that finds no attested successor leaves work **pending**. It
  never re-homes to an unattested runtime, and "temporarily" is not an exception.

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
| Public hostname really terminates at the tunnel, not a residential IP | Cloudflare API, `CLOUDFLARE_ZONE_ID` | `GET /client/v4/zones/{zone_id}/dns_records?name=tinyassets.io` — [CF DNS API](https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/list/) |
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
| 1 | **Negative direct claim** — unattested, valid ready assignment, pending `cloud` task, `claim_assigned` called **directly** | zero claims; refusal reason recorded |
| 2 | **Negative registration** — unattested `ensure_daemon_runtime` | refuses; no `runtime_registration: cloud_worker` row written |
| 3 | **Negative startup/foreground** — unattested serving boot and an unattested foreground/served provider turn | boot exits non-zero; turn refuses, no provider process spawned |
| 4 | **Replayed stale registration** — a row attested for instance X + boot epoch N, then read by an unattested process (and by a different boot epoch) | authority refused on read; row existence confers nothing |
| 5 | **Local spoofed labels** — set every env var the container sets (incl. `TINYASSETS_ALLOW_CLAUDE_SERVING`, `TINYASSETS_DATA_DIR=/data`), hostname aliased to `mcp.tinyassets.io`, compose labels matched | still refused at all four sites |
| 6 | **Recovery/fallback** — stale-cloud-worker retirement and watchdog with no attested successor | work stays pending; nothing re-homed to an unattested runtime, not even momentarily |
| 7 | **Ingress** — tunnel-forwarded platform request arriving at an unattested origin | origin refuses before any universe work |
| 8 | **Cloud positive** — attested process claims a `cloud` task | claim succeeds, audience records the resolved CLOUD class, run proceeds |
| 9 | **Free-only first answer** — brand-new user, free/zero-setup provider only, no borrowed subscription and no automatic change to any existing user workflow | first answer served entirely on cloud, attested end to end |

Tests 5 and 1 are the load-bearing pair: without them the change is a rename.
Test 9 is the acceptance the directive names (`new-user free-provider
onboarding`) and must not be satisfied by any founder-held subscription.

Every new test must be run against the **unfixed** tree and be required to fail
there, and the suite must run on the Linux oracle before push (the resolver
touches process/network syscalls a Windows run will skip).

## Rollout

Resolver + ledger land in **record-only** mode; confirm on the droplet that it
attests and that the expected id matches; then flip (A)–(E) to refuse in one
change. A resolver that cannot attest on the real droplet must never be flipped —
that is how a cloud-only guard takes the platform down.
