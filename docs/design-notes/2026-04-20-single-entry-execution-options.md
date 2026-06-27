---
title: Single canonical public entry point — execution options
date: 2026-04-20
author: navigator
status: active
status_detail: AWAITING LEAD RATIFICATION — do not execute until one option is selected
related:
  - docs/ops/dns-tunnel-single-entry-cutover.md (runbook — DRAFT, blocked on this doc)
  - deploy/cloudflare-worker/worker.js
  - PLAN.md § System Shape — "Single canonical public entry point"
---

# Single Canonical Entry Point — Execution Options

## The constraint

`deploy/cloudflare-worker/worker.js:31`:

```js
const TUNNEL_ORIGIN = 'https://mcp.tinyassets.io';
```

The Worker routes `tinyassets.io/mcp*` → tunnel by making a subrequest with
`Host: mcp.tinyassets.io`. Cloudflare's edge resolves that subrequest via the
DNS CNAME `mcp.tinyassets.io` → tunnel UUID. **Deleting the CNAME breaks the
Worker's ability to reach the tunnel. Canonical URL goes red. P0 recurs.**

The CNAME is not a second public entry point in practice — it's tunnel plumbing.
But it IS publicly resolvable: anyone who discovers `mcp.tinyassets.io` can send
requests directly to the tunnel, bypassing the Worker. The host's security concern
is valid; the naive "delete the CNAME" fix is not.

## The goal

One URL that users connect to (`tinyassets.io/mcp`). Zero alternative publicly
reachable surfaces for the tunnel. `mcp.tinyassets.io` continues to exist as
internal routing plumbing but is unreachable from the public internet.

---

## Option 1 — Cloudflare Access service-token gate on `mcp.tinyassets.io`

**What it does.**
Add a Cloudflare Access application protecting `mcp.tinyassets.io/*`. The Worker
is issued a service token (client_id + client_secret as env vars). Every subrequest
from the Worker carries `CF-Access-Client-Id` + `CF-Access-Client-Secret` headers.
Cloudflare Access validates the token at the edge before routing to the tunnel.
Direct requests from anywhere else get a Cloudflare Access 401/redirect page.

**Worker change:** add two lines:

```js
forwardedHeaders.set('CF-Access-Client-Id', env.CF_ACCESS_CLIENT_ID);
forwardedHeaders.set('CF-Access-Client-Secret', env.CF_ACCESS_CLIENT_SECRET);
```

Worker env vars `CF_ACCESS_CLIENT_ID` + `CF_ACCESS_CLIENT_SECRET` set as secrets
via Wrangler or the Workers dashboard.

**Security win:** High. Direct hits to `mcp.tinyassets.io` get a 401. The CNAME
resolves publicly, but nothing unauthorized can reach the tunnel. Matches the
spirit of the host directive.

**Ops complexity / cost:** Low. Cloudflare Access is included in the free tier for
up to 50 users. Service tokens (non-human auth) don't count against seat limits.
Dashboard: Zero Trust → Access → Applications → Add. Workers secrets: one
`wrangler secret put` per var. Total: ~30 minutes, no new vendors.

**Reversibility:** High. Deleting the Access application restores full public
access to `mcp.tinyassets.io`. No DNS or tunnel config changes required.

**Host-executable without our help:** Yes. Dashboard-only for Access setup;
`wrangler secret put` or Workers dashboard for the secrets. README-level steps.

**Tradeoff / risk:** The CNAME remains publicly resolvable (DNS returns an IP).
An attacker who knows `mcp.tinyassets.io` still knows it exists — they just can't
talk to it. If the security concern is "no evidence of a second surface" (security-
through-obscurity) this doesn't fully satisfy. If the concern is "no one can reach
it" (functional block), this satisfies it. The token secret must be rotated on any
Worker compromise.

---

## Option 2 — Cloudflare Tunnel private hostname (Zero Trust / WARP Connector)

**What it does.**
Instead of a public DNS CNAME, the tunnel uses a private hostname routed only
through Cloudflare's Zero Trust network. The Worker references an internal
hostname (e.g., `tinyassets-daemon.internal`). Only Zero Trust-enrolled clients
(the Worker via service token, or the host via WARP) can resolve and reach it.
The hostname is never in public DNS.

**Security win:** Highest. `mcp.tinyassets.io` ceases to exist in any DNS
anywhere. No publicly resolvable record. The attack surface is eliminated, not
gated.

**Ops complexity / cost:** High. Requires:
- Cloudflare Zero Trust account (free tier covers this, but enrollment is a
  different product surface from regular Cloudflare).
- WARP Connector installed on the host machine OR the daemon host enrolls in the
  Zero Trust org.
- Worker updated to reference the private hostname.
- Tunnel re-configured for private network routing (`private_network` mode).
- Non-trivial debugging surface: errors in the Zero Trust routing path are harder
  to diagnose than DNS/CNAME errors.

**Reversibility:** Moderate. Unwinding Zero Trust enrollment and private routing
requires multiple dashboard changes. More steps = more failure modes on rollback.

**Host-executable without our help:** Marginal. Zero Trust enrollment has a
learning curve and some steps require CLI (`cloudflared tunnel route`). Doable
with good runbook, but not dashboard-only.

**Tradeoff / risk:** Most correct architecturally, but highest ops burden.
Appropriate if the threat model is "we want zero public DNS evidence of this
surface." Overengineered if the threat model is "we don't want direct connections
bypassing the Worker."

---

## Option 3 — Move landing page off GoDaddy to Cloudflare Pages

**What it does.**
Migrate `tinyassets.io` apex from GoDaddy Website Builder to Cloudflare Pages.
Once Cloudflare owns the apex, configure the tunnel's ingress directly on
`tinyassets.io/mcp` with no Worker needed. The CNAME for `mcp.` is deleted;
the tunnel serves the path directly.

**Security win:** Highest for long-term architecture. Eliminates the Worker
(one less hop), the `mcp.` subdomain entirely, and the GoDaddy apex routing
constraint that created this entire problem.

**Ops complexity / cost:** Highest. Requires:
- Rebuilding the landing page on Cloudflare Pages (or migrating GoDaddy
  Website Builder content manually).
- Cloudflare tunnel reconfiguration for path-based routing at the apex
  (`tinyassets.io/mcp` ingress rule directly, not via subdomain).
- DNS cutover from GoDaddy-managed apex to Cloudflare Pages.
- Risk: landing page content loss or GoDaddy-specific features that don't
  translate to Pages.

**Reversibility:** Low. GoDaddy Website Builder content may not be portable.
Once the apex migrates, rolling back is a multi-hour DNS + content restoration
exercise.

**Host-executable without our help:** No. Requires significant dev + host
coordination for both content migration and tunnel reconfiguration. Days, not hours.

**Tradeoff / risk:** Correct end-state for a production platform (single provider,
no GoDaddy dependency). But "correct end-state" is not the same as "right now."
This is a multi-day project that should not be on the Task #7 critical path.

---

## Option 4 — Cloudflare WAF rule limiting `mcp.tinyassets.io` to CF-originated requests

**What it does.**
Add a Cloudflare WAF rule on `mcp.tinyassets.io`: block any request that does not
carry a specific custom header (`X-CF-Worker-Request: 1`) or does not originate
from Cloudflare's own egress IP ranges. The Worker adds the header to every
subrequest.

**Security win:** Weak. Cloudflare's egress IPs are public knowledge. The custom
header value can be guessed or discovered if it's static. This is security-through-
obscurity at the header layer.

**Ops complexity / cost:** Low. WAF rule creation is dashboard-only, ~10 minutes.

**Reversibility:** High. Deleting the WAF rule removes the protection.

**Host-executable without our help:** Yes.

**Tradeoff / risk:** Not recommended as a standalone solution. The attack surface
is "publicly resolvable AND reachable by anyone who reads Cloudflare's IP list
and knows the header." Suitable only as a defense-in-depth layer on top of
Option 1, not as the primary solution.

---

## Ranking

| | Security win | Ops complexity | $ cost | Reversibility | Host-solo? |
|---|---|---|---|---|---|
| **Option 1 (Access token)** | High | Low | Free | High | Yes |
| **Option 2 (private hostname)** | Highest | High | Free | Moderate | Marginal |
| **Option 3 (Cloudflare Pages)** | Highest | Highest | Free | Low | No |
| **Option 4 (WAF header)** | Weak | Low | Free | High | Yes |

**Navigator recommendation: Option 1 (Cloudflare Access service-token).**

Rationale: satisfies the host's functional requirement (no one can reach the
tunnel directly except the Worker), is host-executable in ~30 minutes, is fully
reversible, and costs nothing. The residual gap (CNAME is still DNS-resolvable)
is accepted as a known tradeoff — the same way `localhost` is "resolvable" but
not reachable from outside. If the threat model ever escalates to "zero DNS
evidence," Option 2 is the upgrade path, not a precondition.

Option 2 is the right long-term answer if this becomes a security-hardened
production service with a formal threat model. Not the right answer for the
current sprint.

Option 3 is the right long-term answer for the overall platform architecture
(eliminate GoDaddy, consolidate on Cloudflare). The correct time to do it is
when the landing page needs a redesign anyway — not as part of Task #7.

Option 4 is noise. Don't use it alone.

---

## Proposed implementation steps (Option 1)

**Host-side (Cloudflare dashboard):**

1. Zero Trust → Access → Service Auth → Service Tokens → **Create Service Token**.
   Name: `tinyassets-mcp-worker`. Copy the generated `client_id` + `client_secret`
   (client_secret shown once only).

2. Zero Trust → Access → Applications → **Add application** → Self-hosted.
   - Application name: `tinyassets-daemon-tunnel`
   - Application domain: `mcp.tinyassets.io` (subdomain: `mcp`, domain: `tinyassets.io`)
   - Session duration: 24 hours (service token sessions renew automatically; this
     is a session timeout for human fallback access if ever needed)
   - Policy: Create a policy `worker-only` — Action: Service Auth, Include:
     Service Token = `tinyassets-mcp-worker`.
   - Save.

3. Workers & Pages → `tinyassets-mcp-router` → Settings → Variables and Secrets:
   - Add secret: `CF_ACCESS_CLIENT_ID` = value from step 1.
   - Add secret: `CF_ACCESS_CLIENT_SECRET` = value from step 1.

**Dev-side (code change to `worker.js`):**

In `proxyToTunnel`, after building `forwardedHeaders`, add:

```js
// Cloudflare Access service token — authenticates this Worker to the
// Access-protected mcp.tinyassets.io application. Without these headers,
// any direct request to mcp.tinyassets.io gets Cloudflare Access 401.
if (env.CF_ACCESS_CLIENT_ID) {
    forwardedHeaders.set('CF-Access-Client-Id', env.CF_ACCESS_CLIENT_ID);
    forwardedHeaders.set('CF-Access-Client-Secret', env.CF_ACCESS_CLIENT_SECRET);
}
```

Note: `env` is passed to the Worker's `fetch` handler as the second argument
(`export default { async fetch(request, env) { ... } }`). Worker currently
only takes `request`; this requires adding `env` to the handler signature.

**Verification after deploy:**

- `tinyassets.io/mcp` → green (canonical probe passes).
- `mcp.tinyassets.io/mcp` directly → 302 redirect to Cloudflare Access login
  page (or 401 JSON if client does not follow redirects). NOT a 200.

---

## Host-call questions (if any option is selected)

These are host-judgment calls, not architecture questions:

1. **Is "DNS-resolvable but functionally unreachable" (Option 1) sufficient**, or
   does the threat model require zero DNS evidence (Option 2)?
2. **Is the GoDaddy landing page content portable?** If yes, Option 3 becomes
   much more attractive as a near-term project. If not (GoDaddy-specific widgets,
   builder-only templates), Option 3 is a future-redesign project, not now.
3. **Who holds the Cloudflare Zero Trust admin credentials?** If host-only, the
   implementation is host-executed with our runbook. If we have delegated
   dashboard access, dev can execute step 1 directly.
