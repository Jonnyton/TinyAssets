---
status: active
---

# Daemon-Host Tray Changes — Track D

**Date:** 2026-04-18
**Author:** dev (task #30 pre-draft; unblocks track D when dispatched)
**Status:** Pre-draft spec. No code yet. Executable on dispatch without design re-research.
**Source of truth:**
- `docs/design-notes/2026-04-18-full-platform-architecture.md` — §5 daemon hosting (especially §5.1.1 Tray UX, §5.2 cascade, §5.3 multi-daemon spawn, §5.4 host pool, §5.6 self-only), §13.2 tier-2 onboarding, §14.5 host-directory heartbeats.
- `docs/specs/2026-04-18-full-platform-schema-sketch.md` — `host_pool`, `capabilities`, `wallets`, `provider_plan_tiers`.
- `docs/specs/2026-04-18-mcp-gateway-skeleton.md` — OAuth flow + structured error envelope.
- `docs/specs/2026-04-18-paid-market-crypto-settlement.md` — §5 daemon earnings, §6.1 wallet registration.
- Memory: `project_user_tiers.md`, `project_daemon_default_behavior.md`, `project_monetization_crypto_1pct.md`, `project_cold_start_and_fulfill_paths.md`.
- Existing code: `universe_tray.py` (in-flight rebrand via task #7; file-rename via task #8 → will become `tinyassets_tray.py`), `tinyassets/singleton_lock.py` (task #6 landed).

The tray is tier-2's primary surface. Install-to-productive-daemon budget is <5 minutes per the "main is always downloadable" forever-rule. This spec makes the transition from today's single-box tray (MCP + tunnel + daemon) to the full-platform tray (register host with control plane; opt into paid market; earn) executable without re-research.

---

## 1. UX surface — post-full-platform tray

The tray is repositioned: no longer a self-contained MCP endpoint, now a **host-registered worker** that shows up in the control plane's `host_pool` and cascades through `request_inbox`.

### 1.1 Layout (menu sections, top to bottom)

```
┌─ TinyAssets Tray ─────────────────────────┐
│ Status: Online | Live at platform        │
│ Account: @alice-gh  ·  Tier: T2          │
├──────────────────────────────────────────┤
│ ▸ Daemons (3 running)                    │
│    ☑ local        ollama-local    active │
│    ☑ claude       claude-sonnet   active │
│    ☐ codex        —                      │
│    ☐ gemini       —                      │
│    [+ Launch daemon...]                  │
├──────────────────────────────────────────┤
│ ▸ Capabilities (5 declared)              │
│    goal_planner × claude-sonnet    paid  │
│    scene_drafter × ollama-local    self  │
│    …                                      │
│    [+ Add capability...]                 │
├──────────────────────────────────────────┤
│ ▸ Earnings                               │
│    Balance: 12.4 WF  (≈ testnet)         │
│    This week: 1.7 WF                     │
│    [Request payout] [Settlement history] │
├──────────────────────────────────────────┤
│ ▸ My chatbot requests (2 running)        │
│    scene_drafter  sporemarch  45%        │
│    goal_planner   echoes       queued    │
├──────────────────────────────────────────┤
│ ▸ Active-mode cascade (last action)      │
│    14:32  Claimed paid request #a8b4c3    │
│    14:31  Host queue empty — scanning    │
│           paid pool…                     │
├──────────────────────────────────────────┤
│ ▸ Settings                               │
│    Wallet: 0xABC…F21 (primary)           │
│    Auto-mode: ON                         │
│    Network allowlist (3 users)            │
│    Local-first pin: ollama-local (conf'l)│
│    Open Logs · Help · Sign out · Quit    │
└──────────────────────────────────────────┘
```

### 1.2 Surfaces (maps to §5.1.1 + spec cross-refs)

| Surface | Purpose | Cross-ref |
|---|---|---|
| **Daemons (provider-grouped)** | One row per provider (`local`, `claude`, `codex`, `gemini`, ...). Shows current count. "Launch daemon" opens provider picker. ~~2nd+ same-provider gates on confirmation popup (§4 below).~~ **Retracted 2026-04-24: no payment-tier gate. Host spawns daemons freely. §4 multi-daemon spawn UI is retired.** | §5.1.1 |
| **Capabilities** | List of `(node_type, llm_model)` pairs declared in `host_pool`. Each row has a visibility toggle (self / network / paid) + optional `price_floor` slider for paid. "Add capability" pulls from `capabilities` reference table (ref §1.5b of schema spec). | §5.1.1 |
| **Earnings** | Read `daemon_earnings` view from schema-spec + crypto-spec §5.2. Shows balance, weekly accrual. "Request payout" triggers on-demand `request_payout` RPC from crypto-spec §5.3; "Settlement history" reads `ledger` + `settlement_batches` rows. | paid-market §5 |
| **My chatbot requests** | User's own `request_inbox` rows where `requester_user_id = owner_user_id`. Closes the consumption loop per §5.1.1. RLS policy `req_own_requests` from schema spec §2.4 makes this a direct read. | §5.1.1 |
| **Active-mode cascade log** | Tail of recent cascade decisions (§5.2 steps 1-4). Shows what the daemon is reasoning about without exposing full logs. | §5.2 |
| **Settings** | Wallet registration (register / switch primary / disconnect); auto-mode toggle; network allowlist editor; local-first pin per universe; log access; sign-out; quit. | §5.6 + crypto §5.1 |

### 1.3 Explicit non-goals

- **No chat UX.** Chat stays in Claude.ai. Tray is hosting-and-earnings only.
- **No universe authoring.** Editing nodes/goals/branches happens in the web app or Claude.ai, not the tray.
- **No tunnel management.** Post-full-platform, the tray does NOT run cloudflared; the daemon connects directly to Supabase Realtime. Drop the `TUNNEL_TOKEN` + `start_tunnel()` code paths from today's `universe_tray.py`.
- **No per-universe local MCP port.** Today's tray runs an MCP server on :8001 for local-only testing. Post-full-platform, Claude.ai talks to the remote gateway at `tinyassets.io/mcp` (canonical; routed via a Cloudflare Worker to the tunnel-internal origin at `mcp.tinyassets.io`); the local MCP server becomes optional (kept as a dev-debug tool via an env flag, not a default).

---

## 2. First-run + install flow

**Goal: <5min from download to productive daemon.** Fail-fast on network issues; queue registration for retry on intermittent connectivity.

### 2.1 Install artifact (per §8)

User downloads `TinyAssets-Setup.{exe,dmg,deb,AppImage}` from `tinyassets.io/host`. Install:

1. Extracts to standard OS location (`Program Files/TinyAssets`, `/Applications/TinyAssets.app`, `/usr/local/bin/tinyassets`).
2. Registers autostart (Windows Task Scheduler, macOS LaunchAgent, Linux systemd user unit).
3. Creates desktop shortcut pointing at the tray launcher.
4. First-run marker file absent → triggers onboarding on launch.

### 2.2 First-run flow

```
Step 1/5  Welcome
   [Continue]

Step 2/5  Sign in
   [Sign in with GitHub]  (OAuth via browser to tinyassets.io/authorize — canonical; Worker-routed to the same tunnel-internal origin as /mcp)
   ↳ Gateway returns bearer JWT stored in OS keychain (macOS Keychain / Windows Credential Locker / Linux libsecret).
   [Skip for now]  (offline install; retried on next launch)

Step 3/5  Pick capabilities  (optional — can skip + add later)
   [ ] goal_planner × claude-sonnet         $ price floor: ___ (paid)
   [ ] scene_drafter × ollama-local                              (self)
   [ ] entity_extractor × claude-haiku      $ price floor: ___ (paid)
   […]
   [Skip for now]
   [Continue]

Step 4/5  Register payout wallet  (only if any capability = paid)
   [Connect wallet]  → WalletConnect URI / QR / deep link per crypto-spec §4.1
   [Skip for now]  (earnings accrue; payout blocked until wallet registered)
   [Continue]

Step 5/5  Ready
   "You're hosting. The daemon starts automatically when you sign in."
   [Finish]
```

**Friction budget per step:**
- Step 1: ~3s.
- Step 2 (GitHub OAuth roundtrip + bearer save): ~30s if already signed in to GitHub in a browser, ~2min if first-time.
- Step 3 (pick 1 capability): ~30s.
- Step 4 (wallet connect): ~60s if user already has a wallet app; skippable.
- Step 5: ~3s.

**Total: ~2-4 min when GitHub + wallet are already set up; ~5 min cold.** Meets forever-rule.

### 2.3 Offline install behavior

If step 2 fails (no network):
- Store "pending registration" state in local config.
- On every tray launch, silently retry registration until success.
- Tray UI shows "Offline — signing in on next connection" in status line.
- Daemons CANNOT launch without bearer (they need it to write `request_inbox` claims). Tray surface clear: "Sign in required to host daemons."

### 2.4 Re-install / multi-machine behavior

Same user installs on a second machine:
- GitHub OAuth → same `user_id` → new `host_pool` row with distinct `host_id`.
- Primary wallet applies across both (one wallet per user, per crypto-spec §6.1).
- Both hosts show up in `host_pool`; `discover_nodes`-style visibility respects the `owner_user_id` match.

---

## 3. Daemon-host ↔ control-plane handshake

### 3.1 Connect → register → cascade

```
TRAY boot                                CONTROL PLANE
  │
  ├─ load bearer from keychain          ↓
  ├─ IF pending_registration:
  │    retry step 2
  ├─ connect to Supabase Realtime with bearer
  │    ├─────────────────────────────────→ auth.authorize
  │    ←────────────────────────────────── ws session opened
  │
  ├─ upsert host_pool rows (one per capability declared)
  │    ├─ INSERT INTO host_pool (owner_user_id, provider, capability_id, visibility, ...)
  │    │    ON CONFLICT (owner_user_id, capability_id) DO UPDATE
  │    └────────────────────────────────→ Postgres
  │
  ├─ join Presence channel 'host_pool:online' with payload {host_id, capabilities[]}
  │    └────────────────────────────────→ Supabase Presence (no DB write)
  │
  ├─ subscribe to 'bids:<capability_id>' channel for each declared capability
  │    └────────────────────────────────→ Realtime
  │
  └─ enter cascade loop (§5 below)
```

**No `last_heartbeat` column write** (§14.5). Presence server-side maintains a TTL-scoped record. Dispatch queries join `host_pool` against Presence's live-set at query time:

```sql
-- Control-plane query to find online paid-tier hosts for capability X
SELECT hp.*
FROM public.host_pool hp
WHERE hp.capability_id = $1
  AND hp.visibility = 'paid'
  AND hp.host_id IN (
    SELECT host_id
    FROM public.host_pool_online_view   -- Postgres function, reads Presence state
  );
```

**Presence TTL:** 90s default (Supabase). Tray emits Presence ping every 30s via the Realtime client. Abrupt tray exit = Presence expires after 90s; graceful-quit sends explicit `leave()` first.

### 3.2 Graceful shutdown

On Quit / OS shutdown:

```
TRAY                                     CONTROL PLANE
  ├─ mark running daemons as             ↓
  │   non-claiming (stop polling bids)
  ├─ wait up to 30s for in-flight claims
  │   to complete OR transition to
  │   'failed' with refund
  ├─ send Presence leave() on each
  │   subscribed channel
  │    └───────────────────────────────→ Presence removes host_id
  ├─ close Realtime connection
  │    └───────────────────────────────→ WS close
  └─ exit
```

If the tray crashes: Presence TTL expires after 90s; control plane routes around the missing host. In-flight `claimed` rows timeout based on `capabilities.max_run_seconds`; rows flip to `failed`, refund fires.

### 3.3 Reconnect semantics

Tray connection drops (network blip, laptop sleep):

- Realtime client auto-reconnects with exponential backoff.
- On reconnect, re-send Presence join + channel subscribes.
- In-flight claimed rows survive — they're Postgres state, not connection state.
- If disconnect > `claim_stale_after` (capability-configured, default 10 min), control plane auto-flips the claim to `failed` so another host can pick up. Host returning from sleep sees "stale claim reverted" in the cascade log.

---

## 4. Multi-daemon spawn UI

> **Retracted 2026-04-24.** Host confirmed normal state is 1 always-on daemon; multi-daemon is ad-hoc test sessions driven via host's own chatbot. The "1/provider free, 2nd+ confirmation popup" framing was wrong. Host spawns without confirmation friction. The payment-tier popup UX below is **retired** — do not implement. The §4.2 payment-tier estimate table and §4.3 same-provider policies are also retired.

~~Per §5.3 + memory `project_daemon_default_behavior.md`: 1 daemon per provider is free; 2nd+ same-provider fires confirmation popup.~~

### 4.1 Launch flow

```
User clicks "+ Launch daemon..." in tray menu.
    ↓
Provider picker opens:
   ( ) local (0 running)
   ( ) claude (1 running ⚠)
   ( ) codex (0 running)
   ( ) gemini (0 running)
    ↓
User selects "claude" (already 1 running).
    ↓
Confirmation popup opens:
   ⚠ Launching a 2nd Claude daemon

   Expected impact:
   • Rate limits: a 2nd Claude daemon in always-active mode will hit
     concurrent-request limits on the Anthropic API. Work will queue or fail.
   • Suggested plan: Claude Team / Max  (≈ $200/mo)
       Source: provider_plan_tiers table, updated 2026-04-10

   Do you have headroom on your Anthropic plan?

   [Cancel]  [Launch anyway]
    ↓
"Launch anyway" → spawn daemon process → tray updates count to "claude (2 running)".
```

### 4.2 Payment-tier estimate lookup

Popup text is built at open-time from `provider_plan_tiers` table (schema §1.8). Tray fetches via gateway RPC `get_provider_plan_estimate(provider, current_count)` which returns `{plan_name, monthly_cost_usd, notes, last_updated}`. Offline fallback: cached last-known values + "(cached)" label. No hardcoded strings.

### 4.3 Same-provider policies

- **1st daemon on a provider**: single click, no popup.
- **2nd+ on same provider**: popup fires. User can proceed.
- **No cap on total daemon count.** 10 Claude daemons is the user's call — popup fires for each launch past #1 until user sets "don't ask again for claude" (optional stored preference).

---

## 5. Active-mode cascade UI

Per §5.2 + memory `project_daemon_default_behavior.md`. Make the cascade's reasoning visible so the host trusts the daemon is alive.

### 5.1 Live log

Bottom panel of tray. Tails the daemon's cascade-decision log (separate from heavy node-execution logs — see §5.2 for filter). Example entries:

```
14:32:41  Completed scene_drafter request #a8b4c3 (4m 12s). Payout pending.
14:32:41  Cascade: checking host queue…
14:32:42  Cascade: host queue empty.
14:32:42  Cascade: scanning paid pool for matching capabilities…
14:32:43  Cascade: 3 paid requests match; ranking by value-vs-effort…
14:32:44  Cascade: claimed paid request #b2e5f1 (scene_drafter, 0.5 WF bid).
14:32:44  Running scene_drafter on universe=sporemarch…
```

### 5.2 Filter: cascade vs execution

Two log streams:

- **Cascade log** (UI-visible): step-1-to-4 decisions, claim events, payout events. Low volume, high interpretability.
- **Execution log** (file-only, `logs/daemon.<provider>.log`): full LangGraph trace, node-level events. High volume; not tailed into UI by default. "Open Logs" in tray menu opens the folder.

This prevents the UI from thrashing during active execution.

### 5.3 Active-mode toggle

Per §5.2 end-note: host can switch from active-mode (full cascade) to passive-mode (host-queue only, then sleep) via the Settings → Auto-mode toggle. Default per capability per §5.2: `visibility=paid` → on; `visibility=self` → off. Host override persists.

---

## 6. Singleton enforcement

Builds on task #6's landed `tinyassets/singleton_lock.py` (committed earlier this session as part of the tray-singleton fix).

- **Lock path**: `logs/.tray.lock` (same as today). Post-rename, the lock file is unchanged — singleton_lock module lives in `tinyassets/`, which isn't part of #8's tray-file rename.
- **Behavior unchanged**: double-click shortcut 2nd time → silent exit with "already running" message.
- **Scope unchanged**: one tray per host computer. Multi-daemon spawns are all children of the one tray process.

No new code for track D here. Module is already production-ready.

---

## 7. Tier-migration paths

Per §2.5 (tier migration is a first-class feature). The tray is both the gateway to tier-2 and a signpost to tier-3.

### 7.1 T1 → T2 (chatbot user → daemon host)

Entry points:
- Web app banner "Host a daemon" when user is signed in.
- Chatbot-suggested path: when a tier-1 user hits "no daemon available for capability X" (per memory `project_cold_start_and_fulfill_paths.md` path 4 — "user self-hosts"), chatbot surfaces download link.
- Direct URL `tinyassets.io/host`.

Flow:
1. User clicks download on any of the above surfaces.
2. Installer runs; first-run wizard triggers (§2.2).
3. Step 2 GitHub OAuth = same account as their tier-1 web app login. `host_pool.owner_user_id = auth.uid()`. **No account stitching.**
4. User's existing goals/branches/nodes untouched; now they additionally host a daemon.

Tier transition is permissionless — no admin approval, no separate T2 plan. Tier is a capability-level descriptor, not a paywall.

### 7.2 T2 → T3 (daemon host → OSS contributor)

Tray Help menu link: **"Contribute to TinyAssets →"** → opens `github.com/<org>/TinyAssets/blob/main/CONTRIBUTING.md`.

No in-tray build tooling. Contributor work happens in a normal dev checkout; the tray's job is discovery, not gatekeeping.

### 7.3 Downgrade

User uninstalls tray:
- OS uninstall removes binary + autostart + desktop shortcut.
- `host_pool` rows for this host go `status='offline'` after Presence TTL expires; soft-delete after 30 days.
- User's GitHub-OAuth account retains all tier-1 state (goals / branches / nodes / chat history / wallet registration).
- Reinstalling later re-creates `host_pool` rows; earnings history preserved.

---

## 8. Install artifact plan

**Windows**: `.exe` via Inno Setup or Wix. Code-signed with an EV cert (avoids SmartScreen warnings). Auto-update via Squirrel.Windows or Velopack.

**macOS**: `.dmg` with notarized app bundle (Developer ID + Apple notarization). Auto-update via Sparkle.

**Linux**: `.deb` for Debian/Ubuntu, `.AppImage` for everything else. `apt` repo for `.deb`, direct-download for `.AppImage`. Auto-update via the `.deb` package manager; `.AppImage` self-updates via `appimageupdate`.

**Code signing**:
- Windows EV cert: ~$300/yr through Sectigo/DigiCert.
- macOS Developer ID: $99/yr Apple Developer Program.
- Linux: GPG-sign `.deb` packages with a project key.

**Auto-update channels**: `stable` (default, monthly releases), `beta` (weekly, opt-in). Force-update for critical security patches only.

**"Main is always downloadable" contract**: CI builds all 4 artifacts on every merge to `main`. Release-Notes auto-generated from commit messages. Download URLs point at the latest stable per-platform.

**OPEN:** code-signing cert procurement is a host task, not a dev task. Track D can ship unsigned for initial smoke; signing is a CI wiring add post-cert-in-hand. Flag in §11 Q1.

---

## 9. Telemetry + error handling

Per privacy memory (`project_privacy_per_piece_chatbot_judged.md` spirit — concept-only, training-excluded by default):

### 9.1 Phones home

- **Crash reports** (opt-in, OFF by default). On crash, tray offers to send stack + OS version + TinyAssets version + redacted config. No universe content, no canon, no chat.
- **Daemon-completion metrics** (opt-in, ON by default for paid hosts, OFF for self/network). `request_inbox` row state transitions are already in Postgres; tray reports nothing in addition.
- **Earnings accrual events**: zero net-new telemetry — all derived from `ledger` rows server-side.
- **Heartbeat**: Presence pings only (§3.1). Not telemetry; it's the keepalive.

### 9.2 Does NOT phone home

- Universe content, nodes, goals, canon, chat messages (live in owner's local + Supabase-with-RLS; tray never copies).
- Host hardware identifiers (no fingerprinting).
- User's filesystem layout (paths stay on the host per `add_canon_from_path` design).
- Any data marked `training_excluded=true` (crypto-spec §6.2 + schema spec §17.4 structural enforcement).

### 9.3 Error handling

| Error class | Tray behavior |
|---|---|
| Bearer expired | Auto-refresh via gateway OAuth refresh path (crypto-spec §5.1). If refresh fails, surface "Sign in required" banner; daemons pause. |
| Gateway unreachable | Presence drops on its own; UI shows "Offline — reconnecting" with exponential backoff. Daemons continue local host-queue work. |
| Supabase Postgres unreachable | Same as above; writes queue locally until reconnect. |
| Claim race lost | Logged silently in cascade log ("claim #X lost to other host"); cascade continues. |
| Provider rate-limit (e.g. Anthropic 429) | Back off per §4.1 recommendation; log in cascade; pause that specific daemon until window clears. |
| Crash loop on a provider | After N crashes in M minutes, tray disables auto-launch for that provider + surfaces error in UI. Host manually re-enables. |

---

## 10. Honest dev-day estimate

Navigator's §10 estimate: **2 dev-days** for track D.

My build-out:

| Work item | Estimate |
|---|---|
| Rip out cloudflared + local-MCP-port logic (tunnel no longer needed post-full-platform) | 0.15 d |
| OS keychain integration (macOS Keychain / Win Credential Locker / Linux libsecret) for bearer storage | 0.25 d |
| First-run wizard — 5-step flow + offline-queue logic | 0.5 d |
| Capability-picker UI — fetches from `capabilities` table; per-row visibility + price-floor controls | 0.3 d |
| Provider-launch popup — reads `provider_plan_tiers`, renders warning copy | 0.2 d |
| Cascade live-log panel — tails daemon cascade decisions; filter cascade vs execution | 0.3 d |
| Earnings panel + `request_payout` RPC wiring | 0.3 d |
| Consumption panel — "my chatbot requests" list (reads user's `request_inbox` rows) | 0.2 d |
| Supabase Realtime client integration — Presence join, channel subscribes, graceful-shutdown | 0.5 d |
| Daemon subprocess management — launch/kill/supervise, per-provider crash-loop detection | 0.4 d |
| Tier-migration surfaces — "Contribute" link, upgrade banners | 0.1 d |
| Cross-platform install-artifact build (Win/macOS/Linux) + auto-update wiring | 0.5 d |
| CI — artifact build + sign + upload on merge (EV-cert-pending skippable) | 0.25 d |
| Telemetry opt-in UI + config persistence | 0.15 d |
| Integration smoke: full user flow on 1 platform (Windows default, macOS as fast-follow) | 0.3 d |
| Docs (install runbook, tray user guide) | 0.15 d |
| **Total** | **~4.45 d** |

**Revision: 2 d → ~4.5 d.** Navigator's 2d materially under-scoped — the under-count is in (a) cross-platform install-artifact build (~0.5 d, the forever-rule compliance work), (b) Supabase Realtime integration inside a desktop tray runtime (~0.5 d; more than a websocket ping), (c) first-run wizard (~0.5 d, 5 steps with OS-level keychain + OAuth roundtrip), (d) daemon subprocess management + crash-loop detection (~0.4 d).

**Defer paths** to hit closer to navigator's 2 d:
- **Ship Windows-only at launch** (drop macOS + Linux artifacts for fast-follow): saves ~0.4 d. Breaks "main is always downloadable" for non-Windows users. Not recommended.
- **Defer telemetry + crash-report UI**: saves ~0.15 d. Ship blind; add on 2.0.
- **Defer auto-update**: saves ~0.2 d. Users must manually re-download. Works for launch, annoying at scale.
- **Defer consumption panel** ("my chatbot requests"): saves ~0.2 d. Closes the feedback loop later. Low-severity defer.
- **Reuse existing `universe_tray.py` as scaffold vs full rewrite**: saves ~0.5 d if it's a fork, loses ~0.5 d in migration tech-debt over time. Recommend fork for launch; clean up post-MVP.

**Recommend full ~4.5 d.** Same pattern as prior specs: navigator's estimate is lean, track D has more surfaces than "wire up a tray" implies. Pushes §10 dev-day delta to **+6 dev-days total across my 5 specs** (25:+0, 26:+2, 27:+1, 29:+3, 30:+2.5). Running §10 total: ~14-18 dev-days with 2 devs. Still weeks-not-months, still worth honestly surfacing to host before Q1 lock-in.

---

## 11. OPEN flags

| # | Question |
|---|---|
| Q1 | Code-signing cert procurement — Windows EV (~$300/yr) + macOS Developer ID ($99/yr). Host task, not dev. Who / when / budget? |
| Q2 | Auto-update mechanism per platform — Squirrel/Velopack/Sparkle — committed library pick before track D starts? Affects ~0.2 d. |
| Q3 | Offline cold-start posture — if step 2 (sign-in) fails, should the tray still let the user pick capabilities (for later)? Or lock the UI until online? Recommend allow-pick-later so first-run isn't blocked. |
| Q4 | Cascade-log retention — UI panel tails last N entries. N=100? Persist across tray restarts or ephemeral? Recommend persist 7-day rolling in `logs/cascade.log`. |
| Q5 | Tray crash-report channel — Sentry OSS self-host on the control plane, or third-party (Sentry SaaS / Bugsnag)? Third-party is cheapest dev-time; self-host is cheapest long-term. Recommend SaaS at launch, revisit at 1k DAU. |
| Q6 | Multi-user on one machine — shared desktop PC with multiple accounts. Does each OS account run its own tray + `host_pool` row? Recommend yes (keychain is per-OS-account; Presence is per-connection). |
| Q7 | Headless daemon mode — for users who want a daemon on a server box with no tray UI (SSH-only hosts). Config-driven launch, no GUI. Defer to v2? Flagged per forever-rule (install-ready covers this eventually). |
| Q8 | Package manager ingestion — `brew install workflow`, `winget install workflow`, `apt install workflow`. Which ecosystems at launch? Recommend Homebrew + winget post-initial-launch. Not blocking tier-2 MVP. |
| Q9 | Local-first pin visibility — when user pins `ollama-local` for a universe, does the tray surface this as a lock-icon in the universe list? Recommend yes; pair with confidentiality-tier badge per §5.6. |
| Q10 | Tray-as-standalone vs MCPB bundle — per §13.2 "MCPB bundle via Claude Desktop's distribution, or direct installer." Which is primary? MCPB leverages Claude Desktop's existing install flow. Direct installer is fully-self-contained. Recommend direct installer as primary; MCPB as co-distribution channel. |

---

## 12. Acceptance criteria

Track D is done when, on a clean install:

1. User downloads the installer from `tinyassets.io/host`, runs it, completes the 5-step first-run in <5 min.
2. Post-onboarding, daemon appears in `host_pool` with `status='online'` visible on the web app's admin view.
3. User's own chatbot request is served by their own daemon (tests the self-visibility cascade step 1).
4. User toggles a capability to `paid`, another user places a matching paid bid, the daemon claims + completes, earnings show in tray, payout settles per crypto-spec cadence.
5. User closes tray gracefully; `host_pool.status` flips `offline` after Presence TTL (<120 s).
6. User re-opens tray; `host_pool` re-registers; earnings history preserved.
7. Auto-update mechanism tested end-to-end on at least one platform (a new build replaces the running one without user action).
8. Singleton enforcement holds per task #6 tests — double-click shortcut → silent exit on 2nd instance.
9. Cross-platform artifact build green in CI for Windows + macOS + Linux. At least Windows signed.
10. All 10 OPEN flags in §11 resolved or explicitly deferred.

If any of the above fails, track D is not shippable; tier-2 user onboarding breaks. Forever-rule "main is always downloadable" depends on this.

---

## 13. Confidential-tier observability (task #79 amendment, 2026-04-19)

**Source directive:** Devin persona CHAT-2 (navigator intelligence report §S-3). Tier-2 hosts who handle sensitive work (Devin's D&D campaign notes = identifiable minor-player PII buried in session logs) need to SEE where their daemon is routing before trusting it, and have a hard-stop fail-local option. Without this, Devin's quote: "I'd tell my group not to install it."

Cross-refs: `project_privacy_per_piece_chatbot_judged.md` (per-piece visibility enforcement), `project_user_tiers.md` (T2 = daemon host, one-click install, privacy-aware), privacy catalog `docs/catalogs/privacy-principles-and-data-leak-taxonomy.md` §7 system-point taxonomy.

### 13.1 Tray surface: current LLM binding

Every daemon row in the Daemons section already shows `provider + model` (§1.1). Amendment: add an explicit **route badge** that is load-bearing in the visual hierarchy (not just a label):

```
┌─ Daemons (3 running) ────────────────────────┐
│ ☑ local      ollama-local          ● local   │ ← green dot
│ ☑ claude     claude-sonnet-4-6     ○ cloud   │ ← amber dot
│ ☑ codex      codex-mini            ○ cloud   │ ← amber dot
└──────────────────────────────────────────────┘
```

**Color semantics:**
- **Green `●` = on-host execution.** Node ran inside the daemon process, prompt + output never crossed host boundary.
- **Amber `○` = cloud route.** Provider API received the prompt (Anthropic / OpenAI / Google / DeepSeek / etc.).
- **Red `✕` = rejected.** Daemon tried to cloud-route a locked universe/capability; rejection is user-visible (see §13.3).

Tooltip on each badge shows the last N routing decisions (timestamp + destination + justification). One-click opens the full audit tab (§13.4).

### 13.2 Per-universe "lock local" switch

New per-universe setting surfaced in the web app AND tray Settings:

```
┌─ Per-universe routing ───────────────────────┐
│ D&D-campaign        [lock to local only ☑]   │
│ fantasy-novel       [any provider ☐]          │
│ maya-payables       [lock to local only ☑]   │
└──────────────────────────────────────────────┘
```

Written to new schema-spec field `universes.sensitivity_tier` (values: `open` | `confidential` | `regulated`). `confidential` tier = local-only; `regulated` tier adds audit-log retention requirements. MVP ships `open` + `confidential`; `regulated` post-MVP.

Enforcement is server-side at request-dispatch (spec #25 `submit_request` RPC + spec #27 gateway). Tray surfaces the status and triggers the switch via existing MCP tool; tray itself doesn't enforce. This matters: even if the tray is compromised, the server-side RLS + dispatch gate still blocks cloud providers on a confidential-tier universe's requests.

Wire format: `submit_request` adds `routing_constraint: 'local_only' | 'any'` derived from the universe's `sensitivity_tier`. Gateway rejects any bid matching a non-local provider with MCP error envelope code `routing_violation`.

### 13.3 Visible rejection on local-lock violation

When the gateway rejects a cloud bid for a confidential-tier request:

1. Bid source (the attempting daemon's tray) surfaces a **red toast** with the rejection reason.
2. Requesting user's chatbot narrates: "I tried to route this to [provider] but your D&D-campaign universe is locked to local-only. Falling back to a local daemon in the queue." No silent fallback — narration always fires.
3. Audit log row captures the attempt regardless of success (§13.4).

Silent fallback is the exact failure mode Devin named; the `routing_violation` envelope exists specifically so user-facing surfaces can narrate without ambiguity.

### 13.4 Audit log tab in tray

New tab / dashboard (post-MVP can reuse Active-mode cascade log surface):

```
┌─ Routing audit ──────────────────────────────┐
│ Filter: [all ▼] [today ▼] [universe: * ▼]     │
├──────────────────────────────────────────────┤
│ 14:32:10 goal_planner  → ollama-local        │
│   u=D&D-campaign   confidential  ● local     │
│   justification: capability=self-pinned       │
├──────────────────────────────────────────────┤
│ 14:31:04 scene_drafter → REJECTED (cloud)    │
│   u=D&D-campaign   confidential  ✕ blocked   │
│   attempt: claude-sonnet via paid-market     │
│   reason: routing_violation (local_only)      │
│   fallback: queued to local daemon pool      │
├──────────────────────────────────────────────┤
│ 14:28:45 scene_drafter → claude-sonnet       │
│   u=fantasy-novel  open           ○ cloud    │
│   justification: user-approved paid bid       │
└──────────────────────────────────────────────┘
```

**Data source:** `daemon_routing_events` table (new in schema spec #25). Schema:

```sql
CREATE TABLE public.daemon_routing_events (
  event_id bigserial PRIMARY KEY,
  owner_user_id uuid NOT NULL REFERENCES auth.users(id),
  daemon_id uuid NOT NULL REFERENCES public.host_pool(daemon_id),
  universe_id uuid NULL,
  sensitivity_tier text NULL,
  request_id uuid NULL REFERENCES public.request_inbox(request_id),
  capability_id text NOT NULL,
  routed_to text NOT NULL,         -- provider:model OR 'rejected'
  decision text NOT NULL
    CHECK (decision IN ('local', 'cloud', 'rejected', 'fallback')),
  justification text NOT NULL,     -- short tag: capability=self|user-approved|routing_violation
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX daemon_routing_events_owner_time
  ON public.daemon_routing_events (owner_user_id, created_at DESC);

ALTER TABLE public.daemon_routing_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY routing_events_owner_only
  ON public.daemon_routing_events FOR SELECT USING (owner_user_id = auth.uid());
```

Retention: 30 days for `open`-tier universes, 90 days for `confidential`, 1 year for `regulated`. Reaper job runs daily.

### 13.5 Confidential-tier request flow

End-to-end for a `confidential` universe:

1. User marks `D&D-campaign` as confidential in tray (§13.2) → writes `universes.sensitivity_tier='confidential'`.
2. Chatbot submits a request referencing this universe.
3. Gateway at `submit_request` looks up universe tier → injects `routing_constraint='local_only'` into the `request_inbox` row.
4. Realtime bid channel broadcasts request with constraint; cloud-provider daemons see the constraint and skip bidding.
5. Only local-provider daemons bid. If none online, request queues indefinitely with "waiting for local daemon" status narrated to chatbot.
6. On any daemon attempting to fulfill in violation (race condition, cache staleness, etc.), `complete_request` RPC validates the daemon's provider against `routing_constraint` → rejects with `routing_violation` → re-queues → writes `daemon_routing_events` row with `decision='rejected'`.
7. Tray of the attempting daemon shows red toast; user-facing chatbot narrates per §13.3.

### 13.6 Dev-day impact

Per navigator ~0.25d. Honest revision:

| Component | Dev-days |
|---|---|
| `universes.sensitivity_tier` column + migration | 0.05 |
| `daemon_routing_events` table + RLS + reaper | 0.10 |
| `submit_request` routing_constraint injection | 0.10 |
| Gateway/complete_request rejection + envelope | 0.15 |
| Bid channel constraint propagation | 0.10 |
| Tray: route badge + color dot | 0.20 |
| Tray: per-universe lock switch (UI) | 0.15 |
| Tray: audit log tab | 0.25 |
| Chatbot narration of rejection + fallback | 0.10 |
| Tests (integration: confidential flow end-to-end; unit: rejection envelope) | 0.20 |
| **MVP subtotal** | **~1.4** |

Revision rationale: navigator's 0.25d was for "tray display" only. Actual scope includes schema + dispatch gate + rejection envelope + end-to-end narration — all load-bearing for the privacy guarantee to be enforceable, not just visible. Cutting any component leaves a gap Devin's D&D group would find.

**Deferral lever:** ship §13.1 badge + §13.2 switch + §13.3 rejection + basic §13.4 (using existing cascade-log surface, no new tab) — ~1.0d. Dedicated audit tab + 90-day retention policy post-MVP — saves ~0.4d.

### 13.7 Acceptance criteria

Amendment to §12:
- 11. Marking `D&D-campaign` as confidential → chatbot asked to use a cloud-only capability → chatbot narrates "tried to route to X but locked local; falling back" → daemon_routing_events row has `decision='rejected'`.
- 12. Tray's Daemon row shows `● local` / `○ cloud` badge matching the last recorded event for that daemon.
- 13. Devin-persona smoke: user-sim persona files a GitHub Issue about confidentiality → tries to route → observes green dot + audit log showing local-only → confirms trust.

### 13.8 Cross-refs

- §30 tray spec (this file) §1.1 existing route display.
- Spec #25 `submit_request` + schema — adds `routing_constraint` + `universes.sensitivity_tier` + `daemon_routing_events`.
- Spec #27 MCP gateway — rejection envelope for `routing_violation` code.
- Privacy catalog §7 system-point taxonomy — daemon execution system-point has an explicit entry naming this rejection path.
- Memory `project_privacy_per_piece_chatbot_judged.md` — visibility is per-piece; this amendment extends to per-universe routing.
- Navigator intelligence report §S-3 Devin CHAT-2 — source directive.
