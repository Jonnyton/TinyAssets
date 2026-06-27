# Integration Connectors Catalog — v1

**Status:** v1. Distinct from `integration-patterns.md` (composition patterns). This catalog is **specific two-way integrations with external systems** — Gmail, GitHub, arXiv, Voyager, Google Drive, etc. Each entry is a concrete connector pattern.
**Purpose:** give contributors a template for adding new integrations + give the chatbot a vocabulary for "push to X" / "pull from Y" when helping users design workflows.
**Audience:** contributor writing a new connector node (primary); chatbot reasoning about external-handoff steps (secondary).
**Licensing:** CC0-1.0.

---

## 1. Connector anatomy

Every two-way integration has a standard set of concerns. An integration-connector node must address all of them before shipping.

| Concern | Question | Typical answer |
|---|---|---|
| **Auth method** | How does the owner prove identity to the external system? | OAuth 2.1 / OAuth 1.0 / API key / personal token / certificate / SAML |
| **Credential storage** | Where do auth credentials live? | instance_ref (owner-local) + never concept-layer (per privacy catalog §2.T2) |
| **Rate-limit posture** | How does the external system throttle us? | Per-user token-bucket / per-IP / billing-tier-dependent |
| **Error handling** | What happens on transient errors? Hard errors? | Retry with backoff / dead-letter / fail-fast per error class |
| **Idempotency** | Can we safely retry without side-effects? | Client-generated request IDs / vendor-provided dedup / append-only semantics |
| **Consent UX** | How does the user approve the integration at runtime? | One-time OAuth consent screen + per-invocation confirmation for publish-to-external |
| **Dry-run support** | Can the integration simulate without side-effects? | Vendor sandbox mode / local mock mode / format-validation only |

---

## 2. Canonical connector entries

Each entry implements the §1 anatomy for a specific integration. These are the launch-day "first wave" connectors chosen by domain frequency.

### 2.1 Gmail — `push-to-gmail-draft`

**Shape:** push (writes to Gmail drafts; does NOT send — user sends manually).
**Auth method:** OAuth 2.1 via Google Identity. Scopes: `gmail.compose` (draft-write only; NOT `gmail.send`).
**Credential storage:** refresh token in instance_ref (owner-local); access tokens re-derived per invocation.
**Rate-limit posture:** Gmail API quota per-user = ~1 request/user/second sustained, bursts to 25. Bursty workloads throttled.
**Error handling:** retry with exponential backoff on 429 / 5xx; hard-fail on 403 (scope or auth issue).
**Idempotency:** draft creation returns a draft ID; dedup via client-generated `thread_id` header to avoid duplicate drafts on retry.
**Consent UX:** one-time OAuth (user sees Google consent screen) + explicit "create draft for [recipient]" confirmation per invocation. Draft-only scope means no automated sending ever — user reviews + sends.
**Dry-run support:** yes — returns the payload that WOULD be drafted without calling Gmail API.
**Category:** side-effecter-with-human-gate. User always reviews + sends.

### 2.2 GitHub — `push-to-github-release`

**Shape:** push (creates a release, attaches artifacts).
**Auth method:** GitHub App installation token OR personal-access-token. Prefer App (scoped per repo).
**Credential storage:** App private key in instance_ref or admin-vault; PAT in instance_ref only.
**Rate-limit posture:** 5000 req/h authenticated (User-to-Server) or per-installation for Apps. Release creation is 1 req + N artifact upload reqs.
**Error handling:** retry on 502/503/504; hard-fail on 422 (validation; release tag exists).
**Idempotency:** `tag_name` is the idempotency key. If a release with that tag exists, updating it is PATCH-idempotent.
**Consent UX:** OAuth installation at first-use; per-repo app scope. Per-invocation confirmation of the release name + tag.
**Dry-run support:** yes — returns the release payload + artifact list that would upload, without calling API.
**Category:** side-effecter, mostly-reversible (releases can be deleted but URLs may be cached by external links).

### 2.3 arXiv — `push-to-arxiv-submission`

**Shape:** push (submits preprint for moderation + eventual publication).
**Auth method:** arXiv account + API credentials (email + password currently; API key planned per arXiv DevRel). Instance-layer only.
**Credential storage:** instance_ref with tight owner-only ACL. arXiv credentials are high-stakes; discourage long-lived tokens.
**Rate-limit posture:** arXiv enforces per-user daily submission caps (typically 1-3/day for new authors, higher for established). Hard per-account.
**Error handling:** submission returns a submission-ID immediately; then async-verified by arXiv's moderation team. Hard-fail on category mismatch / format violation.
**Idempotency:** **NOT idempotent.** Repeat submissions create duplicate preprints. Client MUST dedup via local record-keeping; do not rely on arXiv to dedup.
**Consent UX:** MANDATORY per-invocation consent. The explicit "about to submit to arXiv; submissions are essentially irreversible" screen per node `research-paper-peer-review-prep.yaml`. Not cached consent — every time.
**Dry-run support:** yes — runs arXiv's format-validation endpoint without submission.
**Category:** publish-to-external (domain-pattern §2.4); irreversible-at-external per privacy catalog §7.7.

### 2.4 Voyager (accounting) — `push-csv-to-voyager`

**Shape:** push (posts invoice rows into Voyager AP module).
**Auth method:** Voyager API key per-account; enterprise deployments may use SAML or OAuth.
**Credential storage:** instance_ref with tight owner-only ACL. API keys rotate quarterly per Voyager security recommendations.
**Rate-limit posture:** per-company; typically 60 req/min. Batch posting reduces request count.
**Error handling:** retry on transient 5xx; hard-fail on 422 (GL account invalid or duplicate invoice number).
**Idempotency:** `invoice_number` + `vendor_id` as composite idempotency key. Voyager will reject duplicates with a specific error code that the connector treats as "already posted" (non-error).
**Consent UX:** one-time per-company setup; per-batch confirmation of row count + total amount before posting.
**Dry-run support:** yes — Voyager sandbox environment available for testing; our connector supports a dry-run flag that targets sandbox.
**Category:** side-effecter; reversible in-Voyager (entries can be voided) but audit-trailed.

### 2.5 Google Drive — `pull-from-google-drive`

**Shape:** pull (reads files from a shared Drive folder). No write.
**Auth method:** OAuth 2.1 via Google Identity. Scopes: `drive.file` (access only files the user has explicitly shared with our app).
**Credential storage:** refresh token in instance_ref.
**Rate-limit posture:** Drive API is generous — ~1000 req/100sec/user. Batch list + batch get minimize requests.
**Error handling:** retry on 429/5xx; hard-fail on 403 (file not shared with app) or 404 (file deleted).
**Idempotency:** read operations are naturally idempotent.
**Consent UX:** per-folder consent (user clicks "share this folder with TinyAssets" in Drive UI; OAuth scope is `drive.file` so we only see files the user explicitly shares).
**Dry-run support:** N/A for pull operations (reads are side-effect-free by definition).
**Category:** retriever (node-type §2.6); privacy-sensitive because read data may be T4 regulated content depending on folder.

### 2.6 cPanel (web hosting) — `pull-from-cpanel-file-manager`

**Shape:** pull (reads files from a cPanel-hosted filesystem).
**Auth method:** cPanel API token OR session-based (cPanel UI password). Token preferred.
**Credential storage:** instance_ref with owner-only ACL.
**Rate-limit posture:** per-account per-minute throttle varies by host. GoDaddy cPanel ~60 req/min.
**Error handling:** retry on 5xx; hard-fail on 401 (token expired).
**Idempotency:** reads are idempotent.
**Consent UX:** one-time token setup; per-invocation indication of which path is being read.
**Dry-run support:** N/A.
**Category:** retriever.

### 2.7 WordPress — `push-to-wordpress-draft`

**Shape:** push (creates a draft post; user publishes manually).
**Auth method:** WordPress REST API with application passwords (WordPress 5.6+) or OAuth (WordPress.com hosted).
**Credential storage:** instance_ref; application passwords are narrow-scope.
**Rate-limit posture:** varies by host plugin / CDN in front. Default ~100 req/min on most managed hosts.
**Error handling:** retry on 5xx; hard-fail on 401/403.
**Idempotency:** client-generated slug as dedup key; WordPress rejects duplicate slugs with a specific error code.
**Consent UX:** one-time application-password setup; per-invocation confirmation of title + category.
**Dry-run support:** yes — render the payload without calling API.
**Category:** side-effecter-with-human-gate (draft-only; user publishes).

### 2.8 Slack — `push-to-slack-channel`

**Shape:** push (posts a message to a channel).
**Auth method:** OAuth 2.0 via Slack app installation. Scope: `chat:write` + target-channel scopes.
**Credential storage:** bot token in instance_ref.
**Rate-limit posture:** Tier 1 (1 msg/sec average) up to Tier 4 (50+ msg/sec) depending on method. Chat-post is Tier 1.
**Error handling:** retry on 429 with Retry-After header; hard-fail on `channel_not_found` / `not_in_channel`.
**Idempotency:** **NOT idempotent** for new messages. Client must dedup via local state (don't re-post on retry).
**Consent UX:** one-time Slack-app install (workspace admin); per-invocation confirmation of channel + message preview.
**Dry-run support:** yes — render the message payload without posting.
**Category:** side-effecter; technically reversible (user can delete messages) but notifications fire immediately; treat as irreversible.

---

## 3. Patterns that span connectors

### 3.1 OAuth setup flow

Most push-to-external connectors use OAuth. Standard flow:

1. Tier-1 chatbot surfaces "Connect your [service]" when user needs the integration.
2. User clicks → browser opens vendor OAuth consent screen.
3. On approval: vendor redirects to `tinyassets.io/oauth-callback/<vendor>` with authorization code.
4. Gateway exchanges code for tokens; stores refresh token in owner's `instance_ref` storage.
5. Subsequent invocations re-derive access tokens from refresh token automatically.
6. Tokens visible in tier-2 tray under Settings → Connected Services; revoke-any-time.

### 3.2 API-key setup flow

For systems without OAuth (API keys only):

1. User creates API key in the vendor's admin UI.
2. Chatbot/tray prompts: "paste your [vendor] API key."
3. Key stored in instance_ref with owner-only ACL; never logged, never displayed in clear after entry.
4. Key rotation requires user to re-enter.

### 3.3 Per-invocation consent gate

Every push-to-external connector implements:

```
before_invoke():
  ui.show_confirmation({
    target: "Gmail draft to [email protected]",
    payload_preview: first_200_chars(payload),
    destination: "email",
    reversible: "no_recipient_will_see_until_user_sends",
  })
  if user.confirms():
    invoke()
  else:
    abort()
```

Cached consent is NOT allowed. Every invocation goes through the gate per privacy catalog §7.7.

### 3.4 Dry-run default for high-stakes targets

Publish-to-external connectors with irreversible destinations (arXiv, journal submissions, paid API calls) default `dry_run=true`. User must explicitly set `dry_run=false` to execute for real. Connectors where dry-run is meaningful (draft email, WordPress draft) don't need the default flip.

---

## 4. Contributing a new connector

Template:

```yaml
# connector-<vendor>-<operation>.yaml
node_type: side_effecter  # or retriever for pull-only
effect_class: external-effect
primary_pattern: publish-to-external  # from domain-pattern-catalog
connector_metadata:
  vendor: "vendor-name"
  operation: push | pull
  auth_method: oauth2 | api_key | token | saml
  rate_limit_tier: "1 req/sec" | "60 req/min" | etc
  idempotency_key: "field_name" | "composite: field1+field2" | "not idempotent"
  dry_run_supported: yes | no
  reversibility: none | async-reversible | reversible
```

PR checklist:
- [ ] §1 anatomy filled (all 7 concerns).
- [ ] Credential storage path documented (never concept-layer).
- [ ] Dry-run implementation OR explicit "not possible" rationale.
- [ ] Consent-UX confirmation flow implemented.
- [ ] Retry + backoff on transient errors.
- [ ] Idempotency key chosen + documented.
- [ ] Integration test against vendor sandbox (if exists).

---

## 5. OPEN flags

| # | Question |
|---|---|
| Q1 | Connector registry — Postgres table listing approved connectors vs. anyone can PR a new one? Recommend registry at v1 (prevents supply-chain attacks); extensible via PR-review. |
| Q2 | Token revocation propagation — if user revokes OAuth at vendor, how does gateway detect? Recommend: detect on next API call (vendor returns 401) + prompt user to re-consent. |
| Q3 | Multi-tenant connectors (e.g., Workspace Gmail vs personal Gmail) — same connector or separate? Recommend: same connector, auth flow handles both. |
| Q4 | Vendor-specific compliance (Voyager SOC 2 requirements, arXiv moderation coordination, etc.) — enumerate per-connector or defer to vendor docs? Defer; link out from each entry. |
| Q5 | Connector-discovery UX — how does the chatbot surface "hey, a Gmail connector exists" when user mentions email? Recommend: integration-connectors catalog is loaded as an MCP prompt for chatbot reasoning. |

---

## 6. References

- `docs/catalogs/node-type-taxonomy.md` — connectors are typically side_effecter or retriever per §2.
- `docs/catalogs/integration-patterns.md` — saga pattern (§2.6) wraps multi-step connector chains with rollback.
- `docs/catalogs/domain-pattern-catalog.md` §2.4 publish-to-external — the domain-level pattern connectors implement.
- `docs/catalogs/privacy-principles-and-data-leak-taxonomy.md` §7.6 + §7.7 — connector-push + real-world-handoff leak surfaces.
- Spec #27 §3.1 — MCP gateway's tool-surface exposes connector-invocation RPCs.
- Spec #30 Tray spec §1.2 — tray UI for "Connected Services" list.
