# Founder & Universe Identity — who a universe belongs to, and which persona a chatbot wears

- **Status:** Proposed (design). Host-ratified principles 2026-06-25/26. Opposite-provider review (Codex) = **ADAPT, blocking** — folded (§8). **AS provider decided 2026-06-26: WorkOS AuthKit (managed) — §3.0; resolves the §2 auth-subject crux + §6 Q1.** Spec currency: tracks MCP auth **2025-11-25** (DCR→CIMD) + **EMA stable 2026-06-18**, not only the 2025-06-18 revision §1 was first drafted against.
- **Author:** Claude Code session (host design dialogue 2026-06-26).
- **Upstream of:** the blank-slate universe brain (`2026-06-25-blank-slate-universe-brain.md`). The persona can only "align with its founder" once a founder identity exists.
- **Touches:** `workflow/auth/*` (provider, middleware, wellknown), `workflow/api/engine_helpers.py`, `workflow/api/universe.py`, `workflow/api/helpers.py`, `workflow/api/status.py`, `workflow/universe_server.py` (`create_streamable_http_app`), `fantasy_daemon/__main__.py` (the single-universe loop), `deploy/cloudflare-worker/worker.js`.

---

## 1. The problem (from the live ui-test, 2026-06-25/26)

The blank-slate persona reads honestly curious, but `get_status` returns
`account_user: "anonymous"` even for the host's authenticated claude.ai session.
The persona's premise is *"align with my founder"*; with no founder identity, there
is no founder to align with. This is upstream of the persona work.

## 2. What's actually true (verified in code; Codex 2026-06-26 corrected my first draft)

- ✅ **The OAuth Bearer reaches the daemon.** `deploy/cloudflare-worker/worker.js`
  forwards `Authorization` (only hop-by-hop headers stripped; CF-Access service-token
  headers added for the Worker itself). `worker.test.js` asserts it. **Not the gap.**
- ❌ **Gap 0 (deepest) — the OAuth flow never captures a real user subject.** The
  daemon's OAuth (`workflow/auth/provider.py`) is DCR + token issuance, but
  `authorization_codes.user_id` **defaults to `"anonymous"`**, `create_authorization()`
  inserts no human subject, and token exchange copies that anonymous value into the
  access token. So `resolve_token()` returns a *stable* id that is **structurally
  anonymous**. There is no login / upstream-IdP step that establishes *who the human
  is*. **"OAuth = a person" is not true today** — turning on gating would just make a
  stable anonymous, not a founder.
- ❓ **Gap 0b — OAuth routes may not be mounted.** `wellknown.py` defines discovery/DCR/
  token routes, but Codex found no caller mounting `create_wellknown_routes()` in
  `create_streamable_http_app()`. Must prove the OAuth server is actually served live.
- ❌ **Gap 1 — gating is off.** `UNIVERSE_SERVER_AUTH` unset → `_current_actor()` falls
  to env `"anonymous"`. But flipping it on does NOT give "anonymous-read/OAuth-write"
  (see §3.1).
- ❌ **Gap 2 — no universe→founder binding.** No `founder`/`owner_id`/`claim` in
  `universe.py`; `created_by` is on daemons/goals only.

**Conclusion:** the foundation is *real user authentication in the OAuth flow*, not
"flip a flag." Until a real human subject lands in the token, none of founder /
capability / routing can work. **The mechanism is now decided (§3.0): a managed
Authorization Server — WorkOS AuthKit — federates upstream to Google/GitHub OIDC and
issues a token with a real `sub`; our MCP server becomes a pure OAuth 2.1 Resource
Server that validates it. That is what makes Gap 0 closeable.**

## 3. The model (host-ratified) — unchanged in intent, corrected in mechanism

### 3.0 The Authorization Server — WorkOS AuthKit (managed; decided 2026-06-26)
**Decision:** we do NOT self-host an OAuth Authorization Server. Our MCP server is a pure
**OAuth 2.1 Resource Server**; a **managed AS — WorkOS AuthKit — is the separate
Authorization Server**, federating upstream to **Sign in with Google / GitHub (OIDC)**.
The user logs in with an existing account; WorkOS issues a JWT with a stable `sub`; our
server validates it against WorkOS's JWKS. **`sub` = the founder key.**

- **Why managed, not self-host:** owning an AS forever (PKCE, refresh rotation, upstream-IdP
  plumbing, SAML/SCIM, the EMA/ID-JAG extension) is a long-term security liability; managed
  is the industry standard + where it's going, and is *less* code than self-hosting. (Host
  principle: build the known long-term design, not the easy reuse of the existing
  `workflow/auth` AS code.)
- **Why WorkOS (head-to-head 2026-06-25, vs Auth0 + 7 others):** $0 + no credit card now,
  **1M MAU free incl. social login**, a production "AuthKit for MCP" AS, **CIMD** (the
  post-DCR client-identity model from the 2025-11-25 spec), SAML/SCIM ready for enterprise
  "later" (per-connection cost only when an enterprise customer arrives), an ID-JAG/EMA
  path, independent vendor (low roadmap risk). Auth0 splits *worse on both horizons* for a
  customer-facing MCP server (DCR friction now; growth-penalty pricing later) — fallback
  only if a future enterprise customer mandates Okta.
- **Lock-in posture:** all standards-based (OAuth 2.1 / OIDC / JWKS / PRM discovery), so the
  Resource Server stays insulated and the AS is swappable later; the only real switching
  cost is the identity store (`sub`s) — identical for any managed AS, which is why we pick
  one that covers both horizons up front.
- **What `workflow/auth` becomes:** the self-issued anonymous-subject provider
  (`provider.py`) is no longer the production identity source — retire it or demote it to
  local-dev only; production identity comes from WorkOS. (Slice-1 work.)
- **Implementation recipe → `docs/reference/workos-authkit-integration.md`** (token
  validation, PRM/RFC 9728, claims, dashboard config, env). Load-bearing: validate via
  **PyJWT + JWKS** (NOT the sealed-session SDK — that's the web-app pattern); `sub` =
  founder key (email is custom-claim-only); **dev/staging uses WorkOS's shared Google +
  GitHub creds → no own OAuth apps needed yet**; the write-gate enforces in the **dispatcher
  via the scope taxonomy**, the middleware only parses the token. 4 VERIFY-flags to confirm
  against a live token before shipping.

### 3.1 Capability model — anonymous reads, OAuth writes (needs a NEW auth mode)
- **Anonymous = read-only; OAuth = write/create.** Principle fixed.
- **Mechanism correction (Codex):** the existing two modes don't express this.
  *Gated* mode: `require_action_scope` rejects anonymous **before** action semantics —
  so reads would be rejected too. *Optional* mode: it returns early and enforces
  **nothing**. We need a **third mode**: *resolve the bearer when present, allow
  anonymous READS, enforce named scopes only on writes/costly/admin.*
- **Scopes — the taxonomy ALREADY EXISTS (verified 2026-06-26); do NOT rebuild it.**
  `workflow/auth/provider.py` `build_action_scope_registry()` already maps every
  `{tool}.{action}` → a read/write/costly/admin effect with
  `oauth_scope = workflow.{tool}.{effect}`, incl. `_UNIVERSE_COSTLY_ACTIONS`
  (create_universe, post_to_goal_pool, submit_node_bid, daemon_create/summon,
  daemon_memory_promote) and `_UNIVERSE_ADMIN_ACTIONS` (control_daemon, set_tier_config,
  daemon_banish/pause/resume/restart/update_behavior). Slice 2 **consumes** this via
  `action_scope_for(tool, action)` — it must NOT author a parallel table. (A 2026-06-26
  scaffold that rebuilt a universe-only taxonomy was discarded once this primitive was
  found — a cohit; the existing registry is richer, e.g. it marks `control_daemon`/
  `set_tier_config` admin, not plain write.) So the genuinely-new work is NOT the
  taxonomy but: **(a)** the anonymous-read consumption policy (reads pass with no/invalid
  token; enforce the existing scope only on write/costly/admin effects), **(b)** making
  OAuth **grants actually carry** `workflow.universe.write/costly/admin` — the defaults
  grant coarse `"read write"`, which is the real gap, and **(c)** the **resolve-always**
  auth mode.

### 3.2 Founder by construction — no claim flow (net-new ACL)
- **Creating a universe requires OAuth → every universe has a founder by construction**
  (creator's real user_id at creation). No claim action.
- **ACL correction (Codex):** current ACLs only restrict *private* universes; public
  ones return allowed before checking grants, and `create_universe` accepts a
  caller-supplied id and writes no founder. So *founder storage* + a *founder-write
  policy* (founder-only writes to their universe) are **net-new**, plus migration
  behavior for legacy/fantasy/API-created universes that have no founder.

### 3.3 Universe ID = immutable serial; identity is learned
- `universe_id` = opaque creation **serial**, immutable forever — not a descriptive
  slug. `"patch-loop-live"` is legacy. Identity (persona name/purpose/body) is **learned
  + mutable** in the self-model.
- **Compatibility (Codex):** `universe_id` is the on-disk dir name + the active-universe
  marker + `UNIVERSE_SERVER_DEFAULT_UNIVERSE` + countless references. Serial ids for NEW
  universes must coexist with legacy descriptive ids; design the path/marker/default
  compatibility before switching.
- **Open fork:** monotonic serial (`u-000142`) vs UUID.

### 3.4 Per-request persona routing — READ-side only; the loop is separate (Codex)
At scale, which persona a chatbot wears is resolved per request from `(identity,
prompt)`:
1. Prompt names a universe → that universe's persona (anyone *reads*; only founder
   *writes*).
2. Else → caller's **main universe** (OAuth: theirs, auto-created if new; anonymous:
   no main → prompt-only, read-only, ask to name one).
3. Ambiguity → caller's main universe.

**Architecture correction (Codex):** this is **read/status/persona** routing. The
**execution loop is single-universe**: `fantasy_daemon/__main__.py` picks ONE universe
at startup and runs ONE `DaemonController` with one `_universe_path`/`_universe_id`.
`get_status(universe_id)` can already read an explicit universe, but the *default* is
the active marker/env/first-subdir, not identity. So: per-request **read/persona**
routing is buildable on the status surface; per-request **execution** (many universes'
daemons concurrently) is a separate, bigger design (multi-daemon scheduling) and is
explicitly out of scope for this note's read-side routing.

## 4. What changes in code (audit)

| Area | Today | Direction |
|---|---|---|
| OAuth flow | issues anonymous-subject tokens; routes maybe unmounted | **WorkOS AuthKit = the AS** (upstream Google/GitHub OIDC → real `sub`); our server = Resource Server validating WorkOS JWTs vs JWKS; retire/demote self-issued anon provider |
| `workflow/auth` modes | gated (rejects anon) / optional (enforces nothing) | New mode: resolve-always, anon reads, enforce named scopes on writes/costly/admin |
| Scopes | coarse `read write` | `workflow.universe.read/write/costly` taxonomy + OAuth grants that match |
| Universe ACL | only private universes gated | Founder field + founder-only-write policy; public reads stay open |
| `create_universe` | caller id; no founder; not gated | OAuth-gated; serial id; record `founder = real user_id`; seed blank self-model |
| Default routing | active marker / env / first subdir | Identity→main-universe map; per-request read/persona routing |
| `get_status` | env `account_user`; no founder | Surface serial `universe_id`, `founder`, `is_founder` |
| Execution loop | single universe at startup | UNCHANGED here; multi-daemon scheduling is a separate note |

## 5. Rollout caution
Gating on is production-impacting and — per §2 — premature: it would gate the live MCP
to a stable *anonymous*, helping no one, until a real subject is captured. Stage:
real-subject-in-token first (with live proof), then the new capability mode behind a
flag, then founder metadata, then routing.

## 6. Open questions
1. ~~**How does a real human subject enter the token?**~~ **RESOLVED 2026-06-26 (§3.0):**
   managed AS = **WorkOS AuthKit**, federating upstream to Google/GitHub OIDC → real `sub`.
   Remaining build detail: wire AuthKit, validate JWTs vs JWKS, map `sub` → founder.
2. Are the OAuth discovery/token routes actually mounted + reachable live?
3. Serial-ID format (monotonic vs UUID) + legacy-id compatibility.
4. Exact read/write/costly capability split.
5. Founder migration for legacy/fantasy/API-created universes.
6. Multi-daemon execution (separate note) — does the loop ever need to serve >1 universe?

## 7. Proposed slices (reordered per Codex — compatibility/identity proof FIRST)
1. **Adopt WorkOS AuthKit as the AS (auth-subject proof).** Integrate WorkOS AuthKit as the
   separate Authorization Server with upstream Google/GitHub OIDC; make our MCP server a
   Resource Server that validates AuthKit JWTs against WorkOS's JWKS so `resolve_token()`
   returns a real `sub`; retire/demote the self-issued anonymous provider in `workflow/auth`.
   Live proof: an authenticated claude.ai session yields a non-anonymous `account_user`.
   *(Blocks everything. AS-provider decision made; integration is the build.)*
2. **New capability mode.** Resolve-always + anonymous-reads + enforce named scopes on
   writes/costly/admin by **consuming the existing `provider.py` registry**
   (`action_scope_for`) — do NOT rebuild the taxonomy (§3.1) — plus make OAuth grants
   carry `workflow.universe.write/costly/admin`. Behind a flag.
3. **Founder metadata + founder-write ACL.** `create_universe` (OAuth-gated) records a
   serial id + `founder`; founder-only writes; migration for founderless universes.
4. **Identity→main-universe storage** + default routing to it.
5. **Per-request read/persona routing** + `get_status` founder surface.
6. **Legacy cleanup** (delete / substrate-claim / fake-OAuth) once the above land.

Each slice: TDD, Codex review, live `ui-test` via the CDP route.

## 8. Opposite-provider review (Codex, 2026-06-26) = ADAPT (blocking) — folded
- **Critical:** OAuth doesn't identify a Claude user (`user_id` anonymous by
  construction) → §2 Gap 0 added; §7 slice 1 makes auth-subject proof the blocker.
- **Critical:** OAuth routes may be unmounted → §2 Gap 0b; slice 1 proves them.
- **Critical:** anonymous-read/OAuth-write isn't a gating flip → §3.1 new auth mode +
  scope taxonomy.
- **Required:** founder-write ACL + founder storage are net-new (public universes
  currently allow-by-default) → §3.2/§4.
- **Required:** per-request routing collides with the single-universe daemon loop →
  §3.4 splits read/persona routing from execution; multi-daemon deferred.
- **Required:** serial-id compatibility with on-disk paths / markers / defaults → §3.3.
- **Confirmed:** the Worker forwards `Authorization` (not the gap).
- Slices reordered: auth-subject proof → capability mode → founder metadata →
  identity→main → serial/routing.

**Post-review AS-provider decision (2026-06-26, host-ratified):** managed AS = **WorkOS
AuthKit** (head-to-head vs Auth0 + 7 others, §3.0). Resolves §2 Gap 0's "how does a real
subject enter the token" (§6 Q1) — federate upstream OIDC, validate WorkOS JWTs, `sub` =
founder. Slice 1 reframed from "prove the self-hosted routes" to "adopt WorkOS AuthKit."
Spec currency bumped to track 2025-11-25 (CIMD) + EMA-stable 2026-06-18.
