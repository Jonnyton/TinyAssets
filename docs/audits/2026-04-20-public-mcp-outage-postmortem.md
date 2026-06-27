# Public MCP Outage Postmortem — 2026-04-19

**Incident date:** 2026-04-19 (afternoon–evening, Pacific).
**Author:** navigator.
**Severity:** P0 — public MCP connector unreachable from Claude.ai for all users for an unknown window.
**Duration:** lower bound ~90 min (first commit in suspect window to first confirmed detection); upper bound undetermined (no sub-daily monitoring existed).
**Status:** dev remediation in flight as of writing; canary design shipping concurrently (see `docs/design-notes/2026-04-19-uptime-canary-layered.md`).

**Post-incident correction (2026-04-19 evening):** dev browser-probe of Cloudflare Zero Trust revealed the tunnel's Published Application Route is `mcp.tinyassets.io` (path `*` → `http://localhost:8001`), NOT `api.tinyassets.io`. `api.` was never created; NXDOMAIN has always been the state. The real root cause is a **URL mismatch**: the Claude.ai connector was configured for `https://tinyassets.io/mcp` (apex+path) while the tunnel serves `mcp.tinyassets.io` (subdomain+catch-all). Fix = update the connector URL in Claude.ai, not reconfigure Cloudflare. This postmortem's §1 timeline + §2.1 diagnosis references to `api.tinyassets.io` reflect the hypothesis at incident time; leaving the narrative unedited for audit-history integrity. At the time, the team treated `mcp.tinyassets.io/mcp` as the production URL; `api.` remains reserved as a future alias.

**Superseding endpoint note (2026-04-20):** the canonical user-facing MCP URL is now `https://tinyassets.io/mcp`. `mcp.tinyassets.io` remains the Access-gated tunnel origin only and should not be used in user-facing connector setup or public canary commands.

---

## 1. Timeline (Pacific time, 2026-04-19)

| Time | Event | Source |
|---|---|---|
| 15:15 | `bf2b634` — `scripts: browser_lock + lead_browser — shared CDP tab` lands. | git log |
| 15:56 | `269bc79` — `landing: tinyassets.io root serves minimal HTML index`. Adds `@mcp.custom_route("/", methods=["GET"])` inside `tinyassets/universe_server.py` to serve static HTML at the server root. | git log + commit msg |
| ~16:00–17:00 (estimated) | GoDaddy + Cloudflare dash automation session — `7407bc1` (godaddy-ops skill creation) + `1d498ff` (Cloudflare-dash automation gotchas 15-min lessons). The gotchas memo itself is direct evidence of in-session live-editing of Cloudflare DNS records. | git log + skill content |
| 16:30 (est) | Cloudflare tunnel or DNS reconfig changes the `api.tinyassets.io` route. Per godaddy-ops skill §"Cloudflare DNS dashboard — automation gotchas": *"Moving a Tunnel public-hostname from apex → subdomain deletes the apex CNAME."* This exact class of atomic-delete likely nuked the `api.tinyassets.io` CNAME. | godaddy-ops skill line 122 |
| 17:05 | Host live-chat on Claude.ai receives MCP connector errors. First confirmed public detection. | lead report |
| 17:05–now | `tinyassets.io/mcp` = HTTP 404 (GoDaddy W+M landing serving root, passing through `/mcp` as an unknown path); `api.tinyassets.io` = NXDOMAIN. Local `localhost:8001` remains healthy. | lead diagnosis |
| 17:20 | Dev dispatched to restore route. Navigator dispatched to design canary + write this postmortem in parallel. | lead message |

**Lower-bound outage window:** 15:56 (earliest possibly-contributing commit) → 17:05 (first confirmed detection) ≈ **69 min of potential silent outage**. Actual break likely landed mid-window during the Cloudflare reconfig, so true outage ≈ 30–60 min before detection.

---

## 2. Root-cause reconstruction

Three candidate causes; evidence scores them.

### 2.1 Primary: Cloudflare tunnel reconfig dropped the `api.tinyassets.io` CNAME

**Evidence:**
- NXDOMAIN on `api.tinyassets.io` ≠ 404. NXDOMAIN = DNS record doesn't exist. A code-level routing bug inside FastMCP cannot produce NXDOMAIN. A CNAME deletion can.
- godaddy-ops skill was authored in-session specifically to document a Cloudflare-dash automation run whose lessons include "Moving a Tunnel public-hostname from apex → subdomain deletes the apex CNAME" — direct testimony that tunnel-edit-side-effects were encountered and learned about this same day.
- The `tinyassets.io/mcp` → GoDaddy 404 is consistent: the Websites + Marketing origin correctly serves root but returns 404 for `/mcp` (which it doesn't know about). This is the expected state when `api.tinyassets.io` (the cloudflared tunnel hostname) vanishes and only the W+M-backed apex remains.

**Verdict: load-bearing cause.** The DNS-layer deletion of `api.tinyassets.io` is what made the MCP unreachable.

### 2.2 Secondary (contributing, not causal): `269bc79` landing handler

**Evidence:**
- The commit adds a `@mcp.custom_route("/", methods=["GET"])` handler. Inspection of `tinyassets/universe_server.py:162-174` shows it correctly returns a static HTMLResponse and does NOT intercept `/mcp` — FastMCP routes are registered by path; `/` does not shadow `/mcp`.
- Commit's own test suite includes a regression guard (`tests/test_landing_index.py`) specifically asserting the handler does NOT invoke the dispatcher.
- Localhost:8001 MCP remained healthy throughout; if 269bc79 had clobbered MCP routing, localhost would have 404'd too.

**Verdict: probably innocent in isolation.** The lead's initial hypothesis — "landing-page fix clobbered /mcp routing" — is likely a red herring driven by temporal coincidence with the real DNS failure. Recommend dev NOT revert 269bc79 as part of the fix unless code-level inspection confirms otherwise; reverting healthy code masks the real DNS-layer fix.

### 2.3 Candidate dismissed: cloudflared process crash

**Evidence against:** lead's diagnosis reports `cloudflared processes running`. Live tunnel with no crash rules this out.

---

## 3. Why existing monitoring missed it

`SUCCESSION.md` §165:

> **Monitoring:** a weekly cron pings `tinyassets.io` and checks WHOIS expiry date; if <60 days, alerts `ops@tinyassets.io`.

Three gaps exposed:

1. **Weekly cadence is far too coarse.** A 69-minute outage lives entirely inside a weekly-probe's blind spot with ~99.3% probability.
2. **`tinyassets.io` root check doesn't probe the MCP path.** Even if the weekly ping had fired mid-outage, it would have hit the GoDaddy W+M landing (200 OK) and reported green. The apex landing stayed up while the MCP path was dead — the monitor was watching the wrong surface. Incident-time notes below still mention `api.tinyassets.io`; that was the pre-correction hypothesis, not the current endpoint.
3. **No connector-layer probe.** Even a frequent curl of `/mcp` would not catch Claude.ai-specific failure modes (auth-session TTL, connector authentication handshake regressions, prompt-directive breakage). No surface exists that exercises what real users experience.

Pre-commit hooks exercised: mirror-parity, mojibake, ruff, mock-banner. None of them probe the public routing surface. There was no reason to expect them to; routing is not a commit-local invariant. But the absence of any cross-cutting liveness signal is the gap.

---

## 4. The code/DNS interaction that likely broke routing

Reconstruction:

1. 269bc79's landing handler was added with the *intention* of making `tinyassets.io/` return something human-readable via the MCP process's own root. That requires the apex DNS to resolve to the cloudflared tunnel (not to the GoDaddy W+M origin).
2. In the Cloudflare-dash session that followed, the host/lead adjusted tunnel public-hostname records to set up the apex → cloudflared route.
3. **Per the documented gotcha**, moving a tunnel public-hostname from apex → subdomain (or vice versa) can atomically delete the previous apex CNAME managed by Cloudflare Tunnel.
4. Net effect: `api.tinyassets.io` CNAME got deleted as a side-effect of an apex-route change that didn't plan for the co-managed `api.*` record.
5. No post-change verification ran (no canary existed); outage persisted silently until host visited Claude.ai.

**This is a "learned the gotcha the hard way" outage.** The memo that now exists (`.agents/skills/godaddy-ops/SKILL.md` lines 112–122) is the postmortem-as-skill — future automation reading that skill will know to "plan the replacement apex record BEFORE making the tunnel change or DNS goes dark."

---

## 5. Prevention

### Proposal A (recommended): pre-commit hook is the wrong layer

A pre-commit hook cannot catch this class of outage because **no commit touched the broken surface**. The outage was purely in Cloudflare dashboard state, not in any file in the repo. A pre-commit hook on "landing-page edits to tinyassets.io" would have passed green on 269bc79 and caught nothing.

The right shape is the Layer-1 canary (see `docs/design-notes/2026-04-19-uptime-canary-layered.md`) — continuous out-of-band probing of the public surface, independent of any commit.

### Proposal B: add a Hard Rule to AGENTS.md

Add under `## Hard Rules`:

> 10. **Public surface changes verify post-change.** After any edit to DNS records, tunnel config, Cloudflare settings, GoDaddy W+M config, or any surface that affects `tinyassets.io/mcp`, run `python scripts/uptime_canary.py --once` before considering the change complete. DNS changes that pass locally but break the public surface are P0 incidents.

The hook can't enforce this (it's a dashboard, not a commit), but the rule is crisp and enforceable by the lead + by the canary itself (red alarm within 4 min means the change broke something).

### Proposal C: extend the canary's scope to all four trust-surfaces

Per the forever rule (§1 of AGENTS.md: "complete-system 24/7 uptime is top priority"), the canary should cover every public surface. Current design covers Layer 1 (curl /mcp) + Layer 2 (Claude.ai connector). Expand to:

- `tinyassets.io/` root (catches the opposite failure: W+M landing gone + tunnel-only works).
- `tinyassets.io/mcp` initialize/tools-list (canonical MCP path).
- GitHub Actions independent-vantage probe (catches failures invisible to host-machine DNS resolver).

Recommend all three as incremental ~0.25 dev-day additions to the canary's first-draft commit.

---

## 6. Other unmonitored surfaces with silent-outage potential

Inventoried per the four uptime surfaces from the AGENTS.md Forever Rule:

| Surface | Current monitoring | Silent-outage risk | Recommendation |
|---|---|---|---|
| **tier-1 chatbot MCP** (`tinyassets.io/mcp`) | NONE (until canary lands) | Materialized today. | Layer-1 + Layer-2 canary (in flight). |
| **tier-3 OSS `git clone`** | NONE | HIGH — a dirty-tree commit breaking `pip install -e .` or `pytest` on fresh clone would go undetected until a contributor tries. | Add a GitHub Action that runs nightly on a fresh runner: `git clone` → `python -m venv` → `pip install -e .` → `pytest tests/smoke/` — fail loudly on regression. ~0.5 dev-day. |
| **tier-2 tray one-click install** | NONE | HIGH — packaging mirror drift, entry-point regression, cloudflared missing, singleton-lock bug. Host notices only when trying to install on a fresh machine. | Manual quarterly fresh-install rehearsal (documented as runbook) + canary that probes `localhost:8001/mcp` on the primary host (out of scope for this postmortem but belongs on the list). |
| **Node discovery / remix / converge** (`discover_nodes` MCP action) | NONE | MEDIUM — feature isn't live yet, but the moment it ships it joins this list. | Add a canary probe calling `discover_nodes` once it's live. Track-H-first-draft follow-up. |
| **Paid-market inbox + bid matching** | NONE | HIGH (once shipped) — daemon-economy first-draft's entire product thesis depends on this end-to-end. | Canary probe per §3 of `docs/exec-plans/active/2026-04-19-daemon-economy-first-draft.md` done-line — once-hourly end-to-end test transaction in test-mode. |
| **Moderation + abuse response** | NONE | LOW at current scale (manual host-admin). | Skip until community-flag primitive ships. |
| **Landing page root (`tinyassets.io/`)** | SUCCESSION.md §165 weekly cron | LOW-MEDIUM — "is the domain reachable" signal only; does not probe routing. | Add to Layer-1 canary. ~5 LOC. |
| **GitHub Actions / CI** | GitHub-native | LOW — they email on failure. | No action. |
| **Supabase Postgres** | Supabase-native uptime + backup alerts | LOW — paid plan monitoring. | No action. |

**Highest-priority post-canary addition:** tier-3 OSS clone nightly probe. That surface is just as public as the MCP connector and has zero monitoring today — the project is one bad commit away from "fresh contributors silently bounce because `pip install -e .` fails."

---

## 7. STATUS.md Concerns draft (host-managed — I am NOT editing)

To surface to host async per my standing rule. One line, ≤150 chars:

```
[2026-04-19 17:05] P0 public MCP outage — api.tinyassets.io NXDOMAIN during Cloudflare-tunnel reshuffle. Root-cause + canary: docs/audits/2026-04-20-public-mcp-outage-postmortem.md.
```

---

## 8. Follow-up work to queue

1. **Canary implementation** — see `docs/design-notes/2026-04-19-uptime-canary-layered.md`. ~0.5–1 dev-day for Layer 1 + alarm. Layer 2 incremental ~0.5 dev-day.
2. **AGENTS.md Hard Rule 10** (Proposal B §5) — one-line addition. Requires host ratification.
3. **tier-3 OSS clone nightly GitHub Action** — ~0.5 dev-day. Highest-priority post-canary addition.
4. **Tier-2 fresh-install rehearsal runbook** — ~1 dev-day. Host does the rehearsal quarterly; script captures observations.
5. **Paid-market end-to-end canary probe** — queued behind daemon-economy first-draft. Part of Track E's ship-gate.

---

## 9. What this postmortem does NOT decide

- Whether to auto-revert code commits on canary alarm. Recommend no — too many failure modes are DNS/infra, not code. Manual investigation.
- Whether to page a human at night. At current scale (solo host, MVP) best-effort Task-Scheduler writes to STATUS.md is enough. Add paging when scale demands.
- Cloudflared config-as-code. A future improvement would store tunnel public-hostname mappings in-repo (e.g., a `cloudflare/tunnels.yml` that a deployment script reconciles). Defer — single-host project doesn't yet justify the config-management overhead.
- The 5 other unmonitored surfaces from §6 — queued as follow-up work, not first-draft.

---

## 10. Lessons filed into existing skills

The `godaddy-ops` skill's Cloudflare-dash section (lines 112–122) IS the practical lesson of this outage in skill form. Specifically line 122:

> **Moving a Tunnel public-hostname from apex → subdomain deletes the apex CNAME.** Cloudflare auto-managed the record; when the Tunnel's "Published application route" changes hostname, the DNS is updated atomically. Plan the replacement apex record BEFORE making the tunnel change or DNS goes dark.

This memo existing in-repo is the strongest remediation against a repeat: the next automation run against Cloudflare dash will read this skill and know the gotcha before hitting it. No code change needed for that lesson to hold.

**Action:** no further skill edit. The lesson is already captured. Verify that any future Cloudflare-automation task includes a Layer-1 canary probe post-change as an explicit step — add that line to the `godaddy-ops` skill's "Cloudflare DNS dashboard" section when the canary ships.
