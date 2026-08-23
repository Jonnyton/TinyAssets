# Desktop app — a third synced client surface over the shared universe

**Date:** 2026-08-22
**Status:** scaffold (branch `feat/desktop-app`); not merged, not deployed.
**Founder vision (2026-08-22):** "the core of the app is mirrored and synced
across all surfaces — the Android app, the computer app, and the later iPhone
app. All apps take the user to their universe, and the agent knows what you said
recently on the computer when you're talking to it on the phone, because it's all
saved to the same universe if it's the same user."

## What this is

A thin **desktop shell (Electron)** whose window loads the *same* live
onboarding SPA the Android app already wraps — `https://tinyassets.io/mcp/app`.
No second chat UI, no reimplementation. The desktop app is a fourth window onto
one shared brain (chatbot connector, phone, web, and now desktop), so continuity
is automatic rather than something the client has to synchronise.

This is deliberately the **mobile pattern, again**: `mobile/` is a Capacitor
shell over `tinyassets.io/mcp/app`; `desktop-app/` is an Electron shell over the
same URL. Product logic (WorkOS sign-in, connect-subscription, chat) stays in the
SPA and is reused verbatim; web-app changes ship to all three surfaces the moment
the daemon deploys, with no client rebuild.

## Not to be confused with `tinyassets/desktop/`

`tinyassets/desktop/` (packaged_entrypoint.py, tray.py, host_tray.py, launcher.py,
updater.py) is the **Tier-2 host tray daemon** — the single-binary role dispatcher
that *runs a TinyAssets daemon/MCP server on a host machine*. It is infrastructure
the operator installs, not the user-facing universe client. The desktop app in
this note is a Tier-1 **client** of the hosted `/mcp` service, analogous to the
Android app; it runs no daemon and holds no host authority. Keeping the two
distinct (`desktop-app/` at repo root vs `tinyassets/desktop/`) is intentional.

## Continuity is already in the backend — cited

The crux ("phone knows what you said on the computer") is a **server property,
already implemented**, not something the desktop client has to build:

1. The universe is resolved from the *authenticated WorkOS principal*, not the
   device or transport. `converse` resolves the home universe with
   `ensure_founder_home(_base_path(), current_actor_id())`
   (`tinyassets/universe_server.py:1542-1546`), and `current_actor_id()` is
   "exactly the authenticated request subject … A universe-server env var must
   never confer write authority" — no device/surface component
   (`tinyassets/api/permissions.py:249-256`, via `current_request_actor_id`
   reading `current_identity().user_id`, `permissions.py:235-246`).

2. Cross-turn memory is keyed on the *verified principal*, per-universe. In
   `converse`:
   ```python
   memory_universe_dir = _memory_universe_dir(uid)          # the user's home universe
   memory_session = f"principal:{current_actor_id()}"       # the WorkOS subject
   ```
   with the explicit comment (2026-08-22): *"One continuous session per founder
   per universe, keyed on the VERIFIED principal, so every surface (phone app,
   claude.ai connector, web) shares the same thread and it survives app restarts
   and token renewals."* (`tinyassets/universe_server.py:1585-1600, 1626-1629`).

3. The conversation store persists to one SQLite file per universe
   (`<universe_dir>/.conversation_memory.db`), keyed by that `session_id`
   (`tinyassets/conversation_store.py:24-34, 105-107`). Same user → same
   `principal:<sub>` session id → same durable transcript, regardless of which
   surface sent the turn.

**Conclusion:** because the desktop app authenticates the same WorkOS user and
calls the same `/mcp` `converse`, it lands in the same universe and the same
`principal:<sub>` conversation thread as the phone and the connector. Continuity
needs *no new client work* — only that the desktop shell sign in the same user.
This was proven live on the phone 2026-08-22 (memory
`served-codex-answers-as-universe-two-fixes`, git_sha `988150a4`: back-and-forth
with cross-turn recall). The desktop app is the same principal on a different
surface, so it inherits the same guarantee.

### The one continuity nuance worth stating

`session_id` is `principal:<sub>` and is **surface-agnostic** — that is what makes
phone/desktop/connector share one thread. That also means they share *literally
one* thread: this is a single continuous conversation across devices, not
per-device threads that later merge. That is exactly the founder's stated intent
("it's all saved to the same universe if it's the same user"). One true edge is
that there is no *concurrent-session* story (two surfaces talking the same second
interleave into one turn_no sequence). `record_exchange` serialises writes per db
file and the store is best-effort, so this is a post-live hardening edge, not an
MVP blocker (§ Review sequencing: multi-tenant / concurrent edges defer).

## The synced core spans all THREE surface classes — unified identity map

The "synced universe" is a *unified user-action system*, not just app-to-app.
Every surface must route to the SAME universe + brain for the same human. There
are two layers to unification: **(1) which universe/brain** (resolved from an
identity), and **(2) which conversation thread** (the `conversation_store`
`session_id`). Verified against origin/main `250f931a`:

| Surface class | Raw identity | → universe resolution | conversation `session_id` | Same universe? | Same thread as apps? |
|---|---|---|---|---|---|
| **Apps** (Android / desktop / iPhone) — SPA over `converse` | WorkOS access token → `sub` | `ensure_founder_home(base, current_actor_id())` | `principal:<sub>` | ✅ | ✅ |
| **Browser chatbot connector** (claude.ai / ChatGPT at `/mcp`) — founder via `converse` | WorkOS access token → `sub` | same `converse` path | `principal:<sub>` | ✅ | ✅ |
| **User-built channel** (Slack, or any composed channel) | `slack:<workspace>:<sender>` | principal-mapping → WorkOS `sub` → home universe | `slack:<channel>` | ✅ (via mapping) | ❌ **gap** |

**Layer 1 (universe/brain) — unified for all three, by the WorkOS principal.**
- Apps + connector are the *same code path*: both hit `universe_server.converse()`;
  identity is `current_identity().user_id`, which the WorkOS provider sets to the
  JWT `sub` claim (`tinyassets/auth/workos_provider.py:216-236`), no
  device/transport component. For one human, the AuthKit access token (app) and
  the connector's OAuth access token carry the same `sub` (same AuthKit issuer),
  so both resolve to the same `ensure_founder_home` universe. The desktop shell,
  loading the same SPA → same `converse`, joins this set automatically.
- Slack's raw conversation actor is `slack:<workspace>:<sender>`, NOT a WorkOS
  sub. The code makes the unification explicit: the run's authority principal
  MUST be the "VERIFIED request principal … the WorkOS subject … NEVER the raw
  `actor_id` conversation param: on the Slack path that param is
  `slack:<workspace>:<sender>`" (`tinyassets/universe_intelligence.py:215-220`).
  The resolver that maps `slack:<workspace>:<sender>` → the founder's WorkOS
  principal → their home universe is `app_principal_mapping.py` (proven live in
  Slack 2026-08-22 — memory `founder-mapping-proven-live-slack`; STATUS
  "Founder-account setup surface"). **Caveat: that mapping file and the Slack
  conversation-memory worker are live/branch-only — they are NOT in this
  checkout.** On origin/main the only `conversation_store` writer is
  `converse()`, and Slack ingress is `webhook_inbound.py` firing a branch as the
  `universe:<uid>` actor (no conversation-store write). So Slack's universe
  unification is design-confirmed + live-proven, not present as code on `main`.

**Layer 2 (conversation thread) — apps + connector unify; Slack does NOT.**
- Apps + connector + desktop all key on `principal:<sub>` → one continuous
  verbatim thread (`universe_server.py:1596`).
- The Slack path keys the store on `slack:<channel>`
  (`tinyassets/conversation_store.py:26`) — *channel*-scoped, not principal-scoped.
  So even when the Slack sender maps to the same universe as the app user, the
  Slack recent-transcript lives under a *different* `session_id` than the
  `principal:<sub>` thread the apps share.

### Continuity gaps flagged (Slack / channel class)

1. **Slack conversation thread is not principal-unified.** Same human, same
   universe brain (persona, `commit_learning` output, wiki, credentials are all
   shared), but "what you just said" recent-turn recall does NOT cross between
   Slack and the apps — Slack's `session_id` is `slack:<channel>`, the apps' is
   `principal:<sub>`. **Fix direction:** key the Slack conversation-store session
   on the mapped principal (`principal:<sub>`) instead of `slack:<channel>`, or
   add a cross-session summary/merge layer. This matches `conversation_store.py`'s
   own note that a "future authenticated app-conversation authority owner" is
   where this integrates.
2. **Channel-keyed, not sender-keyed.** `slack:<channel>` means a multi-party
   channel is one shared thread across senders, and one human's Slack DM vs their
   app are separate threads. Principal-keying (fix #1) resolves this too.
3. **The Slack→principal mapping is live/branch-only.** A fresh clone of `main`
   has no `app_principal_mapping.py`; Slack identity does not unify to a universe
   at all in this checkout. Anyone building channel continuity from `main` must
   land that mapping as required substrate first.

Net: **apps + browser connector are already a fully unified action system** (one
universe, one thread, by WorkOS principal); **user-built channels share the
universe/brain but fork the conversation thread** — the one real continuity gap,
plus the mapping substrate being live-only rather than on `main`.

## Least-effort correct-shape client: Electron vs Tauri

Both are thin native shells that load a remote URL; the SPA does all the work.

| | Electron | Tauri |
|---|---|---|
| Renderer | Bundles Chromium — identical to Claude.ai + the Chrome-based flows | OS webview (WebView2 / WKWebView / WebKitGTK) — renders differ per OS |
| OpenAI loopback listener | Node `http` in the main process — zero extra toolchain, mirrors Android's `LocalCallbackService` | Needs Rust |
| Toolchain | Node only (already required for the `mobile/` build) | Node **+** Rust |
| Bundle / memory | Large (~150 MB, ships Chromium), higher RAM | Tiny, low RAM |
| Ecosystem / signing / auto-update | Mature (`electron-builder`, `electron-updater`), abundant signing docs | Newer, smaller |

**Decision: Electron.** Rationale specific to this project:

1. **Rendering consistency is the whole point.** The vision is one core mirrored
   across surfaces. Electron ships Chromium, so the desktop renders the SPA
   *identically* to the Claude.ai connector surface and the Chrome sign-in flows.
   Tauri's per-OS webview divergence undercuts "identical everywhere" and adds a
   test matrix we do not want for a first MVP.
2. **The OpenAI one-tap loopback maps cleanly.** Electron's Node main process
   gives a built-in loopback HTTP listener with no new language — a direct analog
   of the Android `LocalCallbackService`, and *simpler* here (the Java comment
   notes "a desktop CLI never hits" the Android-14 background-freeze problem, so
   no foreground-service dance).
3. **MVP velocity.** The team already runs Node for the Capacitor build; Electron
   adds no Rust toolchain. Fastest path to a runnable, correct-shape shell.

Bundle size / memory is the accepted tradeoff and is explicitly a *later*
migration lever: if desktop footprint ever matters, Tauri is the target — but not
for the first correct-shape MVP.

## Native-OAuth handling on desktop

The SPA exposes two sign-in paths (`tinyassets/onboarding/__init__.py`):

- **WorkOS AuthKit (primary, MVP-complete with zero native glue).** Authorization
  Code + PKCE with `redirect_uri = https://tinyassets.io/mcp/app` — *same origin*
  as the page. The token exchange is proxied same-origin through `/mcp/app/token`
  and the refresh token lives in an HttpOnly cookie (`ta_rt`, path
  `/mcp/app/token`, 7-day max-age). Because the whole round-trip is same-origin
  inside the Chromium window, it "just works" exactly as in the Android WebView —
  **no deep-link / custom-protocol plumbing.** Electron's default *persistent*
  session partition keeps the `ta_rt` cookie across app restarts, so the SPA's
  `grant_type=refresh_token` silent-renew path restores the session — this is what
  gives "survives app restarts and token renewals" on desktop too.

- **OpenAI one-tap (secondary — connect-subscription convenience; a follow-up).**
  Uses a *loopback* redirect `http://127.0.0.1:<port>/auth/callback`
  (`valid_loopback_redirect`, `openai_device.py:478-494`; default port 1455). In a
  webview, JS cannot itself listen on a loopback port; Android runs a native
  `LocalCallbackService`. On desktop, the Electron main process runs a short-lived
  Node `http` loopback listener, opens the system browser to OpenAI's authorize
  URL, catches the `?code=` on `127.0.0.1:<port>/auth/callback`, and posts
  `(flow, code, verifier)` to `/mcp/app/openai/exchange`. This is **not required
  for the MVP loop** — WorkOS sign-in + the Claude/Codex browser deposit form
  cover "sign in → connect → chat" — so it is scaffolded as a documented follow-up,
  not built in the first slice.

## Scope / what remains

Built in this scaffold (branch `feat/desktop-app`, `desktop-app/`):
- Electron main + preload, hardened (contextIsolation, no nodeIntegration,
  sandbox, navigation allow-list, external links to system browser).
- Loads `https://tinyassets.io/mcp/app`; local loading/offline fallback page.
- `npm start` runs it; README with run + build notes.

Remains (host/founder + later hardening — tracked, not MVP-blocking):
- OpenAI one-tap loopback listener in the Electron main (design above).
- Packaging + code-signing (Windows EV / Apple notarization) + auto-update
  (`electron-builder` + `electron-updater`), analogous to the tray's own updater.
- Apple Developer / Windows signing identities (host-owned, like the Android
  keystore / Play account).
- iPhone: `npx cap add ios` on the *existing* `mobile/` Capacitor project reuses
  the same `server.url`; no new client codebase needed.
- OpenSpec: the thin shell reuses the already-shipped `onboarding-web-app`
  contract (no new backend behavior/MCP surface/storage), so the scaffold needs
  no new change; the *productionization* phase (packaging/signing/auto-update/
  OpenAI loopback) should front an OpenSpec change before it ships.
