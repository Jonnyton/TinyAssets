# Minimal-onboarding Android app — scope + reuse map + slice-3 prune inventory

Date: 2026-08-10. Status: **planning artifact only** (read-only investigation, no
backend code touched). Author lane: parallel design while Codex builds
`byo-llm-connect-flow` slice 1.

Founder goal (memory `minimal-onboarding-android-app`): a very thin Android app
whose entire purpose is minimal-friction onboarding to your cloud agent.
`open → WorkOS login → connect subscription (one default button; everything else
behind "Other") → straight into chat with a preset seed-universe agent + a
proactive heartbeat`. Returning users land straight in the chat; the ongoing
conversation lives in the phone's notification tab.

## Grounding caveat (read this first)

- The local checkout HEAD is `3124e2d8`, which is **689 commits behind
  `origin/main`** (`git rev-list --left-right --count HEAD...origin/main` = `1  689`).
- The in-flight `byo-llm-connect-flow/design.md` is grounded on `origin/main`
  `7b451b2c`. Newer symbols it references (`ProviderAuthorityHeldError`,
  `ProviderRequestCapability`, `api/interlocutor.py`, `provider_serving_binding.py`)
  **do not exist in the local tree** — they are on `origin/main`.
- Therefore **every file:line citation below is taken from `origin/main`**
  (`git show origin/main:<path>` / `git grep origin/main`), not the local
  checkout. The builder must re-confirm against the live `origin/main` head
  before deleting anything (per memory `stale-checkout-as-audit-oracle`).

---

## 1. Adjacent-lane reuse map (reuse, do not restart)

### (a) Phone / mobile chatbot surface — **does not exist; must be built**

No native mobile, Android, APNs, or FCM code exists anywhere in `tinyassets/`.
The only "android" hits are `esbuild`/`oxc` npm build binaries in
`WebSite/design-system/package-lock.json` (irrelevant tooling).

What the memory's "phone-chatbot" reference (`wf-cloud-drain-live-activation-20260803`
`_PURPOSE.md`, bullet "add phone-chatbot inspect/control/evolution") actually is:

| Artifact (branch `codex/cloud-drain-live-activation-20260803`) | What it is | Reuse value |
|---|---|---|
| `scripts/pushover_page.py`, `tests/test_pushover_page.py`, `.github/workflows/pushover-test.yml` | Pushover push-notification sender (ops alerting) | A working **push channel v0** for the "notification tab" requirement — reusable as the outbound push before native APNs/FCM |
| `WebSite/design-source/ui_kits/tinyassets-web/PhoneTeamCommand.jsx`, `.../workflow-web/PhoneTeamCommand.jsx` | React UI-kit **mockup** of a phone command surface | Visual reference only; ops-control framing (inspect/control the cloud drain), **not** consumer onboarding |

Conclusion: the "phone-chatbot" lane is an **ops-control + Pushover-alert** concept,
a different intent from consumer onboarding. Reuse the Pushover path as an early
push channel; treat `PhoneTeamCommand.jsx` as a design cue, not a codebase to fold in.

The **reusable conversational substrate** (this is what the app rides on):

| Surface | File (origin/main) | Role for the app |
|---|---|---|
| MCP `converse` handle | `tinyassets/universe_server.py:1417` (`def converse`) | The single "talk to your agent" primitive. No `graph_id` → resolves/creates the founder home. |
| App-event ingress | `tinyassets/app_ingress.py:84` (`deliver_app_event`) | Generic "route, recognise, answer, post one external chat event" seam. Today `provider="slack"` only — the pattern a `provider="app"`/mobile transport extends. |
| Outbound app client | `tinyassets/effectors/app_ingress_client.py` | Existing outbound posting client (Slack today) — the shape a mobile push transport mirrors. |
| Chat surface / routing | `tinyassets/api/chat_surface.py`, `tinyassets/app_channel_routing.py` | Resolves which serving binding answers a channel. |
| Durable conversation memory | `tinyassets/conversation_store.py`, `tinyassets/conversation_memory.py` | Per-universe session-anchored history (memory `agent-needs-cross-turn-memory`, merged base #2400). Session ids like `slack:<channel>` / `converse:<uid>:<actor>` — the app adds `app:<device|session>`. Gives cross-turn continuity for free. |

### (b) Proactive heartbeat — **substrate exists; the outreach loop must be built**

No built "agent proactively reaches out" feature. The word "heartbeat" in the
tree is either host-liveness (`tinyassets/host_pool/heartbeat.py`) or task-lease
liveness (`branch_tasks.py:heartbeat_at`) — neither is agent-initiated outreach.

The real substrate a proactive heartbeat composes from:

| Piece | File (origin/main) | Role |
|---|---|---|
| Cloud automations w/ cadence | `tinyassets/api/cloud_automations.py:88` (`cadence_seconds`), `:564`, `:642` | A universe already models a typed automation with a cadence — the scheduler primitive for "reach out every N". |
| Delivery path | `tinyassets/app_ingress.py:84` `deliver_app_event` | Where a scheduled turn's output is routed + posted back to the user. |
| Continuity | `conversation_store.py` | So a proactive message and the user's reply are one thread. |

Known blocker (memory `autonomy-needs-foundation-not-a-gate`): "heartbeat can't
run: fantasy fallback, orphaned automations/stale binding, P0 deploy." The
heartbeat is gated on the **same** thing the app is — a real serving provider
(byo-llm-connect-flow slice 1). Build the heartbeat as a small scheduled
automation that calls `converse` and pushes the reply; do **not** build a new
engine.

### (c) Default seed universe on signup — **exists, directly reusable**

`tinyassets/api/first_contact.py:31` `ensure_founder_home(base, founder)` —
"Resolve or atomically create the authenticated founder's home universe."
Auto-invoked by `converse` when `graph_id` is omitted
(`universe_server.py:1437` imports `ensure_founder_home`; `:1427` "On first
contact it creates and binds a blank seed universe, then loads its persona").

- Create scope is checked (`require_action_scope("universe","create_universe")`)
  and concurrent callers converge on one binding + one ledgered creation
  (`claim_founder_home`, `daemon_server.py:4594`).
- Completion marker: `home_is_complete` = `soul.md` present
  (`first_contact.py:24`). `get_status` surfaces a `first_contact` block when no
  complete home is bound (`api/status.py:978`).
- **The seed home is created empty of an LLM provider.** Until a provider is
  connected it fail-closes with "Connect your provider" — so (c) works but the
  agent cannot *reply* without byo-llm-connect-flow slice 1/2. This is the app's
  central dependency (see §2).

### (d) WorkOS login — **exists, identity only**

- `tinyassets/auth/workos_provider.py`, `auth/middleware.py`, `auth/provider.py`,
  `auth/wellknown.py` — the AuthKit/WorkOS OAuth identity layer.
- Founder↔home binding: `daemon_server.py:4594` `claim_founder_home` (D10),
  `:4630` `get_founder_home`.
- Reference: `docs/reference/workos-authkit-integration.md`,
  `docs/research/multi_tenant_hosted_runtime.md`.
- **WorkOS grants identity/login only, never LLM entitlement** (proposal §1;
  memory `no-host-writer-ever-prune-all-fleets`). The LLM grant is each
  provider's own OAuth (Anthropic/OpenAI), captured by byo-llm-connect-flow slice 2.

### Adjacent OpenSpec/worktree lanes to coordinate with (not restart)

| Lane / change | State | Relevance |
|---|---|---|
| `byo-llm-connect-flow` (slices 1–3) | **in-flight, Codex building slice 1** | The entire "connect subscription → agent can reply" backend. The app is its client. |
| `wf-cloud-drain-live-activation-20260803` | cloud GitHub-drain activation | Owns Pushover push + PhoneTeamCommand mock; ops-control, not onboarding. |
| `wf-custom-agent-app-ingress-foldback-20260803`, `wf-custom-agent-app-conversation-handoff-20260803` | coordination/audit foldbacks (merged PRs #2246/#2238/#2235) | The authenticated Slack app-event → reply path (`deliver_app_event`, app-principal mapping, custody, governed reply) the mobile transport generalizes. Note: "Slack is an interaction surface, never authority or canonical storage; do not add an eighth public handle." |
| `engine-os-sandbox` / `distributed-execution` | spec-refine lanes | The OS-level sandbox for the serving turn (STATUS P1: converse is in-process-confined only). Orthogonal to onboarding but gates safe multi-user serving. |

---

## 2. Android app — OpenSpec-style scope

### Design law

Minimize user actions/time to "talking to your cloud agent." Everything not on
the critical path defers behind **"Other"** or happens automatically (the seed
universe is pre-set-up; the heartbeat runs itself).

### Onboarding flow

```
Open app
  ├─ already logged in?  ──yes──▶  straight into Chat (returning user)
  └─ no
       ▼
  WorkOS login (identity)                    [(d) exists]
       ▼
  Connect your subscription                  [byo slice 2 — MUST BUILD]
   ├─ [ Connect Claude ]  (default)   ← provider-OAuth (Anthropic)
   ├─ [ Connect ChatGPT ] (default)   ← provider-OAuth (OpenAI)
   └─ [ Other ▸ ] self-host · API key · routed · market   (hidden until they graduate)
       ▼   (on success: mint + wire serving binding + set_serving — byo slice 1)
  Seed universe already running              [(c) exists: ensure_founder_home]
   → Chat with the agent (first-person relay via converse)
   → Proactive heartbeat active              [(b) build small]
       ▼
  Ongoing conversation ⇄ phone notification tab   [push — MUST BUILD]
```

### Screens (deliberately few)

| # | Screen | Shown when | Backend it needs |
|---|---|---|---|
| S0 | Splash / session check | every open | session/token validity (WorkOS) |
| S1 | WorkOS login (WebView/AuthKit) | no valid session | `auth/workos_provider.py` **(exists)** |
| S2 | Connect subscription (one default + "Other") | logged in, no serving provider | provider-OAuth connect + vault capture — **byo slice 2** |
| S3 | Chat (the home; first-person agent) | serving provider present | `converse` **(exists)**; serving binding — **byo slice 1** |
| S4 | (OS) Notification tab thread | background / proactive | push transport + `deliver_app_event` — **build push; ingress exists** |

Returning-user path is S0 → S3 directly. S2 is shown once (and re-shown only if
the provider is revoked/disconnected). There is intentionally **no** universe
picker, no workflow builder, no settings gauntlet in v1 — "Other" is a single
deferred bucket.

### Per-screen backend/MCP mapping

| Screen | Surface | Exists? | byo-llm-connect-flow dependency |
|---|---|---|---|
| S1 login | WorkOS AuthKit (`auth/*`) | ✅ exists | none (identity only) |
| S2 connect | `write_graph target=agent_binding operation=bind_serving_provider` + `set_serving` (design.md Decisions 2 & 5); provider-OAuth federation + vault deposit | ❌ build | **slice 2** (OAuth UX + vault capture, `connections` row) **and** **slice 1** (mint chat/completion binding, `set_serving`) |
| S3 chat | `converse` (`universe_server.py:1417`); seed home via `ensure_founder_home` | ✅ converse+seed exist | **slice 1** — without a minted serving binding, `converse` fail-closes "Connect your provider" |
| S3 continuity | `conversation_store.py` (session id `app:<session>`) | ✅ exists | none |
| S4 proactive | scheduled automation (`cloud_automations.py cadence_seconds`) → `converse` → `deliver_app_event` → push | ⚠️ substrate exists, **loop + push build** | **slice 1** (agent must be able to reply) |
| S4 push | native APNs/FCM (or Pushover v0 reuse) outbound | ❌ build | none, but pointless until slice 1 |

### Exists vs must-build

**Exists (reuse):** WorkOS identity + founder-home binding; `converse` + seed-home
auto-creation (`ensure_founder_home`); durable conversation memory; the
`deliver_app_event` ingress seam; a working Pushover push path (v0); automation
cadence primitive.

**Must build:**
1. The Android client itself (S0–S4; thin).
2. **byo-llm-connect-flow slice 2** connect UX reachable from mobile (the native
   app *can* host the provider-OAuth WebView — an advantage over the MCP
   connector, which "CANNOT do OAuth login itself", memory
   `no-host-writer-ever-prune-all-fleets`).
3. **byo-llm-connect-flow slice 1** serving binding + `set_serving` (Codex, in flight).
4. A **mobile-facing transport for `converse`** — see the endpoint gap below.
5. Push transport (APNs/FCM; Pushover as v0) + the proactive heartbeat loop.

### Endpoint gap (decide early)

`converse` is exposed over **MCP only** at `/mcp` — there is no REST route for it
(`git grep` for `add_route`/`@app.post`/`/converse` in `daemon_server.py` on
origin/main returns nothing). Two options for the app:

- **A. App speaks MCP** to `https://tinyassets.io/mcp` with the WorkOS bearer
  token — reuses the exact live connector surface (canonical handles
  `read_graph`/`write_graph`/`run_graph`/`read_page`/`write_page`/`converse`,
  per `openspec/specs/live-mcp-connector-surface/spec.md`). No new server
  surface; the app is "just another MCP client." **Preferred for v1.**
- **B. A thin mobile BFF** (REST → converse) — more app-friendly, but adds a new
  public surface subject to Hard Rule #11 canaries and the eighth-handle
  prohibition. Avoid for v1.

### Smallest shippable v1

**One vertical path, MCP-client-based, owner/founder only:**

1. Android app: S0 session check → S1 WorkOS login (WebView) → S3 chat via **MCP
   `converse`** against `https://tinyassets.io/mcp` with the WorkOS token.
2. S2 connect: host the **provider-OAuth WebView** for one provider (start with
   whichever byo slice 2 lands first) → vault deposit → `bind_serving_provider`
   + `set_serving`. Until slice 1/2 land, S2 shows a "coming soon / connect on
   web" stub and the app degrades to read-only.
3. Seed home is automatic (`ensure_founder_home` via `converse`).
4. Continuity via `conversation_store` (`app:` session id).
5. Push + proactive heartbeat: **defer to v1.1** (Pushover v0 acceptable for a
   demo). "Notification tab" in v1 can be the OS's own notification for a
   foreground-service chat; true proactive outreach waits on the heartbeat loop.

Rationale: v1 proves "open → login → talk to your agent" with the **fewest new
server surfaces** by reusing the live MCP connector. The only hard blocker to a
*replying* agent is byo-llm-connect-flow **slice 1**; the only blocker to
*in-app connect* is **slice 2**. Everything else already exists.

### Dependency flags on byo-llm-connect-flow

- **Slice 1 (mint + wire + `set_serving`) is a HARD blocker for S3 replying.** No
  serving binding → `converse` fail-closes. The app cannot deliver "straight into
  chat" for a new user until slice 1 is live for that universe.
- **Slice 2 (provider-OAuth connect UX + vault capture) is a HARD blocker for
  in-app S2.** Its `connections` row + one-click "Connect Claude/ChatGPT" is
  exactly the app's default button. The app is the natural *first* client of
  slice 2 because a native WebView can complete the OAuth the connector cannot.
- **Slice 3 (prune) is not a blocker** but is a correctness invariant: the seed
  agent must never answer on an ambient host credential (§3). The app must show
  the fail-closed "Connect your provider" state honestly, never a fake reply.
- **Do not ship the Android app as its own OpenSpec change until slice 1 gives an
  agent something to run on** (memory directive: "no agent to talk to = no app to
  ship").

---

## Slice-3 prune kill-list

Read-only inventory of **every code path where the platform could supply an LLM
without a universe-authorized, requester-owned provider.** Line numbers are from
`origin/main` (see grounding caveat). This is the precise target set for
`byo-llm-connect-flow` slice 3 tasks 3.1/3.2. **Scope decisions (what to delete
vs. fail-close vs. keep) belong to the Codex-built, dual-family-reviewed slice —
this list only enumerates.**

### A. Ambient host-credential fallback (the core leak)

1. `tinyassets/providers/base.py:373-396` — `subprocess_env_for_provider`, the
   `resolved_universe is None` branch returns
   `subprocess_env_without_api_keys() or os.environ.copy()`, i.e. the host's own
   `CODEX_HOME` / `CLAUDE_CODE_OAUTH_TOKEN` / `CLAUDE_CONFIG_DIR` subscription
   env. The comment itself says fail-closing this is "deferred to the
   `TINYASSETS_PROVIDER_AUTHORITY_V2`-gated successor." **This is the ambient
   borrow slice 3 must fail-close.** (Related: memory
   `ambient-credential-fallback-is-an-identity-leak`.)
2. `tinyassets/providers/base.py:143-145, 186-190, 322-323` — the host-env var
   inventory (`CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME`) used
   to compose provider auth; audit that no path reads these outside a
   universe-scoped vault materialization.

### B. Router fallback to platform-supplied providers

3. `tinyassets/providers/router.py:1-6` — module invariant "every call has a
   fallback chain that terminates at `ollama-local`. The system NEVER stops due
   to provider unavailability." This *is* the platform-supplies-an-LLM guarantee;
   it must invert to fail-closed.
4. `tinyassets/providers/router.py:160-164` — `FALLBACK_CHAINS` (writer/judge/
   extract/embed) hard-code `claude-code, codex, gemini-free, groq-free,
   grok-free, ollama-local` — platform-owned providers reachable with no universe
   authority.
5. `tinyassets/providers/router.py:170-171` — `_JUDGE_PROVIDERS` fan-out list
   (same platform-owned set).
6. `tinyassets/providers/router.py:175` — `_LOCAL_PROVIDERS = {"ollama-local"}`
   and the ollama terminal routing at `:644` ("routing exclusively to local").
7. `tinyassets/providers/router.py:86, 148, 291` — process-global
   `runtime.universe_config` fallback in `_resolve_universe_config`,
   `_default_config`, `_current_allowlist`. A **contextless** call (no explicit
   `UniverseContext`) still resolves a chain — the "no-universe still routes"
   path that slice 3's sole-path resolution removes.

### C. `host_daemon` engine source (platform-runs-your-LLM as a first-class choice)

8. `tinyassets/api/universe.py:6171-6190` — `_set_engine_host_daemon`: records
   `engine_source="host_daemon"` ("platform runs your LLM"). Reached via
   `_set_engine` dispatch at `:6053-6054`; advertised in the action schema at
   `:6027-6034, 6058`.
9. `tinyassets/config.py:62` — `engine_source` doc/validation still lists
   `host_daemon` (and `market_rented`, `self_hosted_endpoint`) as accepted
   values; `host_daemon` must be removed/rejected.

### D. Cloud-worker `fantasy_daemon` supervisor (the host writer "fleet")

10. `tinyassets/cloud_worker.py:717, 783, 789` — `_select_worker_module` falls
    back to `"fantasy_daemon"` ("Falling back to fantasy_daemon so this worker
    can serve at all") — the platform standing in as the writer.
11. `tinyassets/cloud_worker.py:1218-1280` — `_spawn_fantasy_daemon` (spawns
    `python -m fantasy_daemon`), invoked at `:800-808`.
12. `tinyassets/cloud_worker.py:55, 556, 592, 2127` — `FANTASY_DAEMON_LLM_TYPES`
    / `TINYASSETS_PIN_WRITER` cloud-side writer pins that select a
    platform-supplied provider for the supervised writer.

### E. Host-pool / writer "fleet" plumbing (hosts-for-hire as LLM suppliers)

13. `tinyassets/host_pool/__init__.py`, `registration.py`, `heartbeat.py`,
    `bid_poller.py`, `client.py` — the Supabase `host_pool` fleet: hosts register
    capability, heartbeat liveness, poll bids to run others' work. This is the
    "writer fleet" plumbing named in the directive. **Scoping flag:** confirm
    whether the paid-market supply layer (Track E) is meant to survive as the
    *future* broker; the directive keeps "the market" as a later path. Slice 3
    should remove only the **host-as-free-LLM-supplier** paths, not necessarily
    the market ledger — a dual-family review call.

### F. `domains/fantasy_daemon/` — the "old fantasy writer" engine

14. `domains/fantasy_daemon/` (`producers.py`, `phases/*`, `graphs/*`,
    `skill.py`, `state/*`, `phases/_provider_stub.py`, …) — the ~500-line writer
    engine (`fantasy_daemon._run_graph`, per `cloud_worker.py:27`). **Scoping
    flag:** this is *both* the legacy host-writer engine *and* the reference
    domain example. Its LLM access is via the router (§B), so pruning here is
    about deleting the host-writer framing/entrypoints, not necessarily every
    domain graph. Decide the exact boundary in slice 3 with review; do not
    blind-delete the whole package without confirming nothing user-facing depends
    on it. Note `tinyassets/__main__.py:41-42` still `import fantasy_daemon.__main__`
    as the daemon controller bridge — a dependency to untangle first.

### G. API-key host-flag path

15. `tinyassets/providers/base.py:124` (`api_key_providers_enabled` /
    `TINYASSETS_ALLOW_API_KEY_PROVIDERS`) and its router gates
    (`router.py:_apply_api_key_provider_policy`). This is the "host flips a flag
    and the platform serves API-key providers" path. **Scoping flag:** BYO
    *API-key* (a user pasting their own key into their universe vault) is an
    *intended* path (proposal §1 "API key paste is the alternate"). The prune
    target is only the **host-global** flag that enables platform-owned API keys,
    not the per-universe user-supplied key. Separate the two carefully.

### Guard test target (task 3.2)

After the deletions, a differential/grep-based guard must assert no code path
reaches a provider `.complete()` without an explicit universe-authorized,
requester-owned binding — i.e. no `os.environ.copy()` provider env on a
no-universe branch, no `FALLBACK_CHAINS` terminal to a platform provider, no
`host_daemon` engine source, no `_spawn_fantasy_daemon` writer fallback. Grep
anchors: `os.environ.copy()` in `providers/`, `ollama-local`, `host_daemon`,
`fantasy_daemon`, `CLAUDE_CODE_OAUTH_TOKEN`/`CODEX_HOME` outside vault
materialization.

**Kill-list count: 15 enumerated code paths across 7 groups (A–G).** Three carry
explicit scoping flags (E host-pool/market, F fantasy_daemon engine vs. domain,
G host-flag vs. user-supplied key) that need the dual-family review call before
deletion — they are not clean deletes.

### Adjacent (not LLM-provisioning, do not fold into slice 3)

- STATUS P2: `engine_helpers.py:192` `_current_actor` env fallback bypasses
  `permissions.py` — an authority-derivation hole, related but a separate lane.
- STATUS: `resolve_interlocutor_tier` grants T2/FOUNDER to any `write` ACL holder
  (`api/interlocutor.py:130`, origin/main) — separate authority concern.
