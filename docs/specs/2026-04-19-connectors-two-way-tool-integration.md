---
status: active
---

# Connectors — Two-Way Tool Integration (§28 Exec Spec)

**Date:** 2026-04-19
**Author:** dev (task #68 pre-draft; navigator drift-audit #64 flagged this as missing spec)
**Status:** Pre-draft spec. No code yet. Executable on dispatch without design re-research.
**Source of truth:**
- `docs/design-notes/2026-04-18-full-platform-architecture.md` — §28 two-way tool integration, §17 privacy, §26.2 output kinds.
- `docs/specs/2026-04-18-full-platform-schema-sketch.md` — `request_inbox` cascade + per-request settlement.
- `docs/specs/2026-04-18-mcp-gateway-skeleton.md` — `connector_invoke` RPC routing.
- `docs/catalogs/integration-connectors-catalog.md` — 8 worked-example connectors.
- Memory `project_scenario_directives_A_B_C.md` — Scenario A: Voyager push is the reference case.

**Framing (host 2026-04-19):** "Here's your download" is a failure mode. Platform completion happens at the **user's tool boundary**: the artifact is INSIDE Gmail / Voyager / GitHub, not on a download page.

---

## 1. Responsibilities boundary

### Owns

- **`ConnectorProtocol`** — the single interface every connector implements (§2).
- **Connector registry** — `public.connectors` table + code-side registry that maps `connector_name` → module.
- **`connector_invoke(name, action, payload)` RPC** — the uniform entry point; routes to the connector module, enforces auth context, captures audit log.
- **OAuth flow generalization** — shared OAuth 2.0 handler for the ~80% of connectors that use OAuth; per-connector overrides for the rest (API-key, file-based).
- **Token storage** — Supabase Vault integration; owner-only RLS; refresh-token rotation.
- **Consent gate** — first-push-per-destination gating, per-user persistent consent records.
- **Audit log** — every push writes to `public.connector_audit_log`; what went where, when, by whom, with what scopes.
- **Error envelope** — maps connector-specific errors to the platform's structured MCP envelope.

### Delegates

- **OAuth app registration** to platform operator (humans register an OAuth app with GitHub, Google, etc. once per provider). Registration metadata lives in deployment config, not in code.
- **UI for connector management** to web app (spec #35). Track N just exposes RPCs; the "manage your connections" screen is web-app territory.
- **Rate limit enforcement** to the target service + the gateway's per-user bucket (spec #27 §5). Connectors surface 429 from the target but don't implement their own per-user rate limit.
- **Artifact format** to the node that produces it. Connectors push opaque bytes + metadata; semantic validity ("is this a valid CSV?") is the node's responsibility.

### Not-track-concerns (explicit non-goals)

- **No connector-level retries across catastrophic failures.** One retry with backoff (§7); beyond that, surface the error to the caller. Don't build a distributed retry queue.
- **No connector-to-connector composition at the connector layer.** "Push to Drive, then email the link" is orchestrated at the node/graph layer, not inside a single connector call.
- **No caching of pulled data.** `pull()` is always a live call; nodes that want caching implement it at the node level.
- **No polling loops inside connectors.** Connectors are request/response. Streaming / watching a Gmail inbox = a node-level concern using connector `pull()` on a schedule.

---

## 2. `ConnectorProtocol` interface

Every connector is a Python module under `TinyAssets/connectors/<name>/` that exposes a class matching this interface:

```python
class ConnectorProtocol(Protocol):
    name: ClassVar[str]                          # e.g. "gmail", "github"
    auth_kind: ClassVar[Literal["oauth2", "api_key", "file_path", "none"]]
    required_scopes: ClassVar[list[str]]         # OAuth scopes or analogues
    declared_actions: ClassVar[list[ActionSpec]] # typed push/pull operations

    def connect(self, ctx: AuthContext) -> ConnectionHandle: ...
    def push(self, handle: ConnectionHandle, action: str, payload: dict) -> PushResult: ...
    def pull(self, handle: ConnectionHandle, action: str, query: dict) -> PullResult: ...
    def disconnect(self, handle: ConnectionHandle) -> None: ...
    def status(self, handle: ConnectionHandle) -> ConnectorStatus: ...
```

Supporting types:

```python
@dataclass
class ActionSpec:
    name: str                             # e.g. "upload_file", "send_email"
    kind: Literal["push", "pull"]
    input_schema: dict                    # JSON Schema
    output_schema: dict
    scopes_required: list[str]            # subset of connector's required_scopes
    side_effect_class: Literal["reversible", "irreversible", "partial"]
    description: str                      # user-facing for consent prompts

@dataclass
class AuthContext:
    user_id: str
    token: Optional[str]                  # fetched from vault by registry
    api_key: Optional[str]
    file_path: Optional[Path]

@dataclass
class PushResult:
    status: Literal["ok", "retry", "error"]
    target_ref: Optional[str]             # URL / ID of the created object
    detail: dict                          # connector-specific metadata
    error: Optional[ConnectorError]

@dataclass
class PullResult:
    status: Literal["ok", "retry", "error"]
    records: list[dict]
    cursor: Optional[str]                 # for pagination
    error: Optional[ConnectorError]

class ConnectorStatus(TypedDict):
    healthy: bool
    last_check_at: datetime
    quota_remaining: Optional[int]
    detail: str
```

**Design rationale:** one interface, many implementations. Nodes declare `output.kind = "connector-push"` + `output.connector = "gmail"` + `output.action = "send_email"` — the runtime dispatches through `connector_invoke` → the connector's `push()`. No connector-specific code in the node layer.

---

## 3. Launch connector catalog

Per navigator's recommendation + §30 handoff needs. Listing is **code shipped at MVP**; non-MVP connectors are *plugin-able* but not in the default catalog.

### 3.1 MVP connectors (tier-1)

| Connector | Auth | Actions (MVP) | Scenario |
|---|---|---|---|
| `github` | OAuth2 | `create_issue`, `open_pr`, `push_file`, `create_release` | Scenario C3 (code-release handoff), general |
| `gmail` | OAuth2 | `send_email`, `create_draft` | Scenario A (email invoice summary), general |
| `gdrive` | OAuth2 | `upload_file`, `create_folder`, `share_link` | Scenario A (file delivery), general |
| `dropbox` | OAuth2 | `upload_file`, `create_shared_link` | Scenario A (file delivery) |
| `s3` | API key (AWS access/secret) | `upload_object`, `presigned_url` | Platform-infra handoff |
| `notion` | OAuth2 | `create_page`, `append_block`, `update_page` | Scenario C1 (team-notify with write-up) |
| `webhook_generic` | None (URL + optional HMAC) | `post_json` | Fallback for anything not yet supported |

### 3.2 Handoff-scenario connectors (MVP if §30 ships — per handoffs spec #69)

| Connector | Auth | Actions | Scenario |
|---|---|---|---|
| `arxiv` | API key (ORCID-linked) | `submit_preprint` | Scenario C3 (paper submission) |
| `crossref_doi` | API key | `register_doi` | Scenario C3 (DOI issuance) |
| `isbn_bowker` | API key | `register_isbn` | Book-publishing handoff |

Shipped only if #69 handoffs lands at MVP (per navigator's minimum-viable-launch narrowing proposal, this is borderline — could defer to v1.1).

### 3.3 Tier-2 (post-MVP, plugin-able day one)

- `slack` — `post_message`, `upload_file` (OAuth2, requires Slack app registration per-workspace or global TinyAssets app).
- `discord` — `post_message` (bot token or OAuth2).
- `sendgrid` / `mailgun` — transactional email alternative to Gmail's per-user OAuth (platform-managed key, useful for automated pipelines).

### 3.4 Tier-3 (community-contributed; not shipped by platform)

- `voyager_sage50` — Scenario A reference case. Built by Maya-persona-equivalent real user who needs it. See `docs/catalogs/integration-connectors-catalog.md` §4 for the pattern.
- `quickbooks` / `xero` — accounting integrations.
- Vertical-specific publisher APIs, FDA-submission, specialized medical/legal handoffs.

### 3.5 Per-connector auth flows

**OAuth2 (majority):**
- Platform operator registers an OAuth app with the provider once (deployment config).
- User invokes the connector → platform redirects to provider's OAuth page → user consents to scopes → provider redirects back with a code → platform exchanges for tokens → stores in vault.
- Refresh-token rotation runs on every token use: if the access token is within 5min of expiry, refresh inline.

**API key:**
- User enters the key in the connector-manage UI (web app spec #35); platform stores encrypted in vault.
- No refresh flow; key rotation is user-initiated when provider requires.
- `s3`, `sendgrid`, `crossref_doi` use this.

**File path:**
- User declares a local path (e.g. `~/Dropbox` for local Dropbox sync); platform validates readable at connect.
- Reserved for post-MVP scenarios where target service has no API.
- `voyager_sage50` (community connector) uses this as its primary path.

**None (webhook_generic):**
- URL + optional HMAC secret stored in vault.
- Per-invocation destination override via `payload.url` field.

---

## 4. OAuth flow generalization

### 4.1 Shared handler

```python
class OAuth2Handler:
    def begin(self, user_id: str, connector_name: str, scopes: list[str]) -> AuthUrl: ...
    def callback(self, code: str, state: str) -> OAuthTokens: ...
    def refresh(self, refresh_token: str) -> OAuthTokens: ...
    def revoke(self, tokens: OAuthTokens) -> None: ...
```

Connectors declare `auth_kind = "oauth2"` + `required_scopes`; the shared handler drives begin→callback→token-storage. Per-provider configuration (authorization URL, token URL, scope separator) comes from a static `connectors/<name>/oauth_config.py`.

### 4.2 PKCE

All OAuth2 flows use PKCE. No exceptions — even for server-side flows (defense-in-depth against code interception). State parameter is a signed JWT containing `{user_id, connector_name, nonce, exp}`.

### 4.3 Scope declaration

Each connector's `required_scopes` is the *maximal* set the connector could ever need. At connect-time, the user is only asked to grant the scopes needed for actions they've actually used (MVP: grant-all-upfront; post-MVP: incremental grants).

Scope format is per-provider (Gmail uses URLs, GitHub uses strings). The `ActionSpec.scopes_required` declares the subset each action needs; at `push()`/`pull()` call-time, the registry validates that the user's token has the required scopes — if not, surface `insufficient_scope` error to the chatbot, which prompts re-consent.

### 4.4 Token storage

Supabase Vault holds `access_token` + `refresh_token` + `expires_at` + `granted_scopes[]` per `(user_id, connector_name)` pair. Owner-only RLS. No raw token ever leaves the vault; connector code receives a short-lived handle.

```sql
CREATE TABLE public.connector_connections (
  user_id uuid NOT NULL REFERENCES auth.users(id),
  connector_name text NOT NULL,
  vault_secret_id uuid NOT NULL,        -- pointer into supabase vault
  granted_scopes text[] NOT NULL DEFAULT '{}',
  connected_at timestamptz NOT NULL DEFAULT now(),
  last_used_at timestamptz NOT NULL DEFAULT now(),
  status text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'revoked', 'expired')),
  PRIMARY KEY (user_id, connector_name)
);

ALTER TABLE public.connector_connections ENABLE ROW LEVEL SECURITY;
CREATE POLICY connections_owner_only
  ON public.connector_connections FOR ALL USING (user_id = auth.uid());
```

---

## 5. Push semantics — "complete at the tool boundary"

### 5.1 The principle

A node's output phase ends when the artifact is **inside the user's target tool**, not when it's on a download page. Gmail: the draft is in Drafts, attachment included. GitHub: the PR is open. Notion: the page exists in the declared database. Voyager (community): the CSV is imported + visible in AP.

### 5.2 Reversibility taxonomy

Every `ActionSpec` declares `side_effect_class`:
- **reversible** — creates artifacts that can be deleted/undone by the user (draft emails, Drive files, Notion pages). Safe to auto-execute.
- **partial** — can be partially undone (GitHub PR can be closed but not unreleased; published post can be deleted but viewers may have seen it). Chatbot narrates risk + confirms.
- **irreversible** — cannot be undone (send email — recipient already has it; arXiv submit — DOI issued; ISBN register — permanent). Chatbot MUST explicitly confirm with user before invoking.

Chatbot behavior tied to this:
- Reversible: invoke after consent-per-destination gate passes (§6). No per-invocation re-ask.
- Partial: narrate the partial-reversibility + confirm.
- Irreversible: always confirm per invocation, even after consent. Per-invocation confirmation is non-negotiable for irreversible actions.

### 5.3 Push result shape

Every successful push returns a `target_ref` (URL or stable ID) pointing at the created artifact. Chatbot uses this to narrate — "I sent the email, it's in your Drafts: https://mail.google.com/...#draft=abc123."

Push result also captured in `connector_audit_log` (§8.3).

### 5.4 Large payloads

Connectors that handle files >10 MB use a streaming/chunked path:
- Platform-side: payload comes in as a signed Supabase Storage URL, not inline bytes.
- Connector's `push()` streams from the URL → target service using the provider's chunked-upload API.

Sizes at MVP: Gmail 25 MB, Drive 5 TB per file (streamed), S3 5 TB per object (streamed), GitHub 100 MB per file + use release-asset path for larger. Payloads exceeding per-connector limit return `payload_too_large` pre-push.

---

## 6. Consent UX

### 6.1 Consent gates

Two consent levels:

**Connection-level consent** — first-time authorizing a connector. Full OAuth flow or explicit API-key entry. Creates a `connector_connections` row.

**Destination-level consent** — first time pushing to a specific *destination* within a connected service (e.g., first push to a specific Notion database, first time sending email to a specific recipient domain). Captured in `connector_destination_consents`:

```sql
CREATE TABLE public.connector_destination_consents (
  user_id uuid NOT NULL REFERENCES auth.users(id),
  connector_name text NOT NULL,
  destination_key text NOT NULL,        -- e.g. "notion:db:abc123", "gmail:domain:example.com"
  granted_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz NULL,
  scope_note text NULL,                 -- chatbot's narration of why consent needed
  PRIMARY KEY (user_id, connector_name, destination_key)
);

ALTER TABLE public.connector_destination_consents ENABLE ROW LEVEL SECURITY;
CREATE POLICY dest_consent_owner_only
  ON public.connector_destination_consents FOR ALL USING (user_id = auth.uid());
```

Chatbot queries this before a push via `connector_check_consent(connector, destination_key)` — if not granted, pauses + asks user + records consent on approval.

### 6.2 Destination-key patterns

Per-connector convention:
- **Gmail:** `gmail:domain:<tld>` (consent by recipient domain — not per-email-address; avoids flood of consent prompts).
- **GitHub:** `github:repo:<owner>/<repo>` (per-repo).
- **Notion:** `notion:database:<db_id>` or `notion:page:<page_id>`.
- **Drive:** `gdrive:folder:<folder_id>` or `gdrive:root` (root folder counts as one consent).
- **S3:** `s3:bucket:<bucket_name>`.
- **Webhook:** `webhook:host:<hostname>`.

The chatbot constructs the destination_key from the payload before checking consent.

### 6.3 Revocation

Two paths:
- **Per-connection revoke** — drops `connector_connections.status` to `revoked`, vault token revoked at provider. All downstream destination_consents become dormant (tokens gone; consent records preserved for audit but effectively unusable).
- **Per-destination revoke** — sets `revoked_at`; consent must be re-requested next time.

Web app (spec #35) surfaces both paths. Chatbot can also initiate revoke via `connector_revoke(name)` or `connector_revoke_destination(name, destination_key)` RPCs.

### 6.4 Consent persistence posture

Once granted, destination-level consent is **persistent until revoked**. Chatbot does NOT re-ask on every push — that's the pattern Maya-persona hated in Zapier ("please confirm you want to..." every invoice). Re-ask is reserved for:
- Irreversible actions (§5.2) — per-invocation confirm always.
- After 90-day inactivity on a destination (configurable; post-MVP).
- After detecting anomaly (payload size 100× typical, destination matches known phishing domain, etc.) — not MVP.

---

## 7. Error handling

### 7.1 Error taxonomy

Every connector error maps to one of:

| Code | Meaning | Chatbot response |
|---|---|---|
| `connector_unavailable` | Target service is down / 5xx | Retry once with backoff; if still down, narrate + offer to try later. |
| `auth_expired` | Access token expired, refresh failed | Prompt user to re-authorize. |
| `insufficient_scope` | Action requires scope user didn't grant | Prompt incremental consent. |
| `rate_limited` | 429 from target | Honor `Retry-After` header; backoff + retry once. If still limited, defer to node's retry config. |
| `unauthorized` | 401 with valid-looking token (revoked at provider) | Re-auth flow. |
| `forbidden` | 403 (scope OK but target-specific policy blocks) | Narrate + abort. |
| `not_found` | 404 on target (destination doesn't exist) | Narrate + offer to create / pick different destination. |
| `payload_too_large` | Request exceeds size limits | Narrate + offer to split / use alternate method. |
| `validation_failed` | Provider rejected payload shape | Narrate + escalate to node for re-generation. |
| `internal_error` | Anything else | Log + surface generic error. |

### 7.2 Retry policy

Connector-level retry:
- Try once.
- If `connector_unavailable` or `rate_limited`: sleep per `Retry-After` (default 2s for 5xx, 60s for 429). Retry once.
- If still failing: surface to caller.

**No distributed retry queue.** The caller (node) may implement higher-level retry using its own state (e.g., `retry_count` in node state, bounded by node's retry-cap). Connector layer stays thin.

### 7.3 Backoff

Exponential with jitter: 1s, 2s, 4s, 8s, max 30s. Applied only to the retry-once policy above. Cap total connector-side retry time at 60s; beyond that, fail fast.

### 7.4 Idempotency

Push actions declare `idempotency_key` in payload where the target API supports it (Stripe-style). For APIs that don't: connectors SHOULD accept a `client_request_id` and de-dup on the connector side (short-TTL cache of seen request IDs → cached result). MVP: implement where trivially possible; not universal.

---

## 8. Data passthrough + privacy

### 8.1 Instance data necessarily flows through connectors

A connector pushing an invoice to Voyager sees the invoice's instance data — it can't push what it can't see. The platform's privacy model (§17) is:

- **Concept-layer** (public-by-default) data flows through connectors freely.
- **Instance-layer** (owner-only) data flows only when the connector call is authenticated in the owner's RLS context. `connector_invoke` always runs with `SET LOCAL request.jwt.claims = '...'` set to the calling user.
- **Private-tagged fields** (per-field visibility from §17.2) pass through but are excluded from any telemetry or analytics. Connector code sees them; platform monitoring does not.

### 8.2 No telemetry on payloads

Connector payloads are NOT logged in plaintext. The audit log (§8.3) captures metadata (destination, action, size, timestamp, result status) but never payload content. If debugging requires payload inspection, user opts in per-session via explicit `connector_enable_debug_log()` RPC (not MVP).

### 8.3 Audit log

```sql
CREATE TABLE public.connector_audit_log (
  log_id bigserial PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES auth.users(id),
  connector_name text NOT NULL,
  action text NOT NULL,
  destination_key text NULL,
  payload_size_bytes bigint NULL,
  result_status text NOT NULL,
  target_ref text NULL,
  error_code text NULL,
  invoked_at timestamptz NOT NULL DEFAULT now(),
  -- No payload content. No provider tokens. Metadata only.
);

CREATE INDEX connector_audit_log_user_time
  ON public.connector_audit_log (user_id, invoked_at DESC);

ALTER TABLE public.connector_audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY audit_log_owner_read
  ON public.connector_audit_log FOR SELECT USING (user_id = auth.uid());
-- INSERT via SECURITY DEFINER function only (platform-side, never direct).
```

User can read their own audit log via web-app (spec #35). Chatbot can read via `connector_audit_log_read(limit, since)` RPC — used for "what did you do yesterday?" narration.

### 8.4 Third-party access

Connectors can be written by third parties (§3.4 tier-3). The code runs platform-side. **Review requirement:** PR review for every connector PR must include (a) no payload logging beyond metadata, (b) no credentials leakage, (c) bounded request patterns (no infinite loops, no recursive self-invocation). Moderation checklist maintained in `docs/catalogs/integration-connectors-catalog.md`.

### 8.5 Paid-market fulfillment + connector privacy

A daemon fulfilling a paid request may invoke a connector on behalf of the **requester** — not itself. The `connector_invoke` RPC signature carries `target_user_id` (the paid request's originator); daemon-host passes through but operates under requester's RLS context for vault/consent lookups. Daemon-host NEVER sees the requester's tokens directly — platform fetches token, invokes connector, returns result.

Cross-ref spec #29 paid-market settlement — connector invocations within paid fulfillment are metered + billed as part of the request's cost.

---

## 9. Plugin system — third-party connector additions

### 9.1 Directory + file layout

```
TinyAssets/connectors/<name>/
├── __init__.py              # exports class matching ConnectorProtocol
├── connector.py             # main implementation
├── oauth_config.py          # if auth_kind == "oauth2"
├── tests/
│   ├── test_connector.py    # unit tests against a mock
│   └── fixtures/            # sample payloads
├── README.md                # user-facing docs
└── MANIFEST.yaml            # declaration metadata (see §9.2)
```

### 9.2 MANIFEST.yaml

```yaml
name: example_connector
version: "1.0.0"
auth_kind: oauth2
required_scopes:
  - "example:read"
  - "example:write"
license: MIT                    # platform code MIT per §19
maintainer:
  name: "Example Contributor"
  github: "@example"
  contact: "email-or-discord"
actions:
  - name: upload_file
    kind: push
    side_effect_class: reversible
    description: "Upload a file to the user's example service account"
    input_schema: { ... }
    output_schema: { ... }
review_status: pending   # PR reviewer sets 'approved' on merge
```

### 9.3 Review criteria

Platform maintainers review each connector PR for:

1. **Privacy compliance** — no payload logging beyond metadata, no cross-user data leakage.
2. **Auth compliance** — uses shared `OAuth2Handler` for OAuth flows; no hand-rolled token storage.
3. **Error handling** — maps all provider errors to the §7.1 taxonomy; no unhandled exceptions escape `push()`/`pull()`.
4. **Testing** — unit tests for each declared action against a mock; at least one integration smoke test (can be marked `@pytest.mark.integration` + skipped by default).
5. **Documentation** — README covers setup (OAuth app registration for the provider, scope rationale), worked examples per action, known limitations.
6. **Ownership** — maintainer contact in MANIFEST; responsible for fielding bug reports.

Connector stays in `review_status: pending` until ≥1 maintainer approval. Users can authorize a `pending` connector only via an explicit opt-in flag (web app warns "this connector is unreviewed"). After approval, auto-available.

### 9.4 Dependency management

Connectors declare their Python dependencies in a local `requirements.txt`. Platform-level dependency deduplication at build-time (pip-compile merges). Conflicting version requirements block merge — maintainer resolves before PR lands.

### 9.5 Deprecation

Connector can be marked `deprecated` in MANIFEST with an `expires_at` date. Users with active connections get a web-app warning; chatbot narrates on any invocation. Post-expiration, connector removed from registry + users see `connector_deprecated` error on next invocation with a migration hint if the MANIFEST declares one.

---

## 10. Dev-day estimate

Navigator's §28.6 estimate was ~1.5d. Revising based on spec scope:

| Component | Dev-days |
|---|---|
| `ConnectorProtocol` interface + registry code | 0.25 |
| `connector_invoke` RPC + routing + audit log | 0.25 |
| `OAuth2Handler` shared infrastructure + vault integration | 0.4 |
| `connector_connections` + `connector_destination_consents` + `connector_audit_log` schema | 0.15 |
| Consent-gate RPCs (`check_consent`, `grant_consent`, `revoke`) | 0.15 |
| GitHub connector (OAuth + 4 actions + tests) | 0.3 |
| Gmail connector (OAuth + 2 actions + tests) | 0.25 |
| Google Drive connector (OAuth + 3 actions + tests) | 0.25 |
| Dropbox connector (OAuth + 2 actions + tests) | 0.2 |
| S3 connector (API-key + 2 actions + tests) | 0.15 |
| Notion connector (OAuth + 3 actions + tests) | 0.25 |
| Webhook-generic fallback + HMAC + tests | 0.15 |
| Error-taxonomy wiring + retry/backoff logic | 0.2 |
| Docs (per-connector README templates + review checklist) | 0.2 |
| **MVP subtotal** | **~3.15** |
| Handoff connectors (arXiv + CrossRef + ISBN) if §30 launches | +0.6 |
| **Full-MVP subtotal (with handoffs)** | **~3.75** |

**Revision rationale:** navigator's 1.5d was for `ConnectorProtocol` + registry + 4 launch connectors + webhook fallback. Actually drafting the connector code (not scaffolding) + consent schema + audit log + OAuth2Handler generalization is ~3d. Handoff connectors add ~0.6d if they ship at MVP.

**Deferral lever:** ship 4 connectors (GitHub + Gmail + Drive + webhook) at MVP; defer Dropbox, S3, Notion to v1.0.1 (~0.7d saved). Recommend NOT deferring — Notion is critical for Scenario C1 team-notify pattern, and Dropbox/S3 cover the long tail.

---

## 11. Acceptance criteria

**Gate 1 — OAuth connect flow:**
- User-sim T1 persona invokes "send an email" → chatbot initiates Gmail OAuth → consent screen loads in browser → user consents → `connector_connections` row appears → push succeeds.

**Gate 2 — consent gate:**
- First push to `notion:database:abc` triggers consent prompt with narration.
- Second push same destination → no prompt (consent persisted).
- After revocation → next push re-prompts.

**Gate 3 — error recovery:**
- Simulated 429 → connector retries once with backoff → success on retry.
- Simulated 401 → chatbot narrates re-auth needed → user re-consents → next push succeeds.
- Simulated 5xx persistent → both attempts fail → clean error envelope surfaces to caller.

**Gate 4 — audit log:**
- Every push lands a `connector_audit_log` row.
- `connector_audit_log_read` returns rows for invoking user only (RLS enforced).
- No payload content in log rows (spot check).

**Gate 5 — plugin path:**
- A contributor-authored connector (mock example) merges via PR → is auto-available after maintainer approves.
- Unreviewed (`pending`) connector requires explicit opt-in flag to authorize.

**Gate 6 — irreversible-action confirmation:**
- Push to `arxiv.submit_preprint` (irreversible) requires per-invocation user confirmation even after consent.

---

## 12. OPEN flags

| # | Question |
|---|---|
| Q1 | **OAuth app registration posture.** Every OAuth provider needs a registered app; platform operator registers each one. Who owns the app (TinyAssets LLC? personal?)? Recommend platform-operator entity; revisit when legal entity exists. |
| Q2 | **Incremental vs grant-all OAuth scopes.** MVP uses grant-all (simpler UX, more friction-upfront). Providers like Google support incremental grants. Should we move to incremental post-MVP? Recommend yes — lower upfront friction. |
| Q3 | **Vault choice at MVP.** Supabase Vault is assumed; self-host playbook (#57) would need HashiCorp Vault integration. Cross-ref §8 pluggable-vault abstraction. |
| Q4 | **Webhook HMAC algorithm default.** Recommend `HMAC-SHA256` with `X-TinyAssets-Signature` header. Host confirm or propose alternate. |
| Q5 | **Destination-key granularity.** Gmail at `domain:` level, not per-recipient. For B2B workflows where every email is the same domain (internal), this effectively grants consent to all internal mail. Acceptable? Recommend yes at MVP — reduces re-ask noise; can tighten if abuse observed. |
| Q6 | **Connector version pinning.** When a connector v1.0 → v1.1 introduces schema changes, what happens to in-flight workflows? Recommend: semver; connectors ship under `/connectors/<name>@<major>/`, breaking changes bump major and coexist. Not MVP but bake-in the URL structure. |
| Q7 | **Rate-limit reporting.** Should `connector_status()` report the user's current quota usage per provider? Useful for chatbot narration but requires per-provider quota-query endpoints (Gmail has one, GitHub has one, others don't). Recommend: expose where available, omit where not. |
| Q8 | **Tier-3 community connector incentives.** Who builds the `voyager_sage50` connector? Scenario A implicitly assumes the user's chatbot, possibly with nudging. Recommend: user-sim personas (Maya) should try to author a connector end-to-end as part of the real-world-effect-engine test; if they succeed, pattern is validated. |
| Q9 | **Deprecated-connector data migration.** When `voyager_sage50` v1.0 deprecates in favor of v2.0, can we auto-migrate user connections? Generally no — auth flow + scopes may change. Recommend: per-connector `migrate()` hook, called if declared; otherwise re-auth required. |
| Q10 | **Push-by-reference vs push-by-value at API gateway.** Large payloads come through as signed Storage URLs (§5.4); connector fetches. Does the chatbot know about this, or is it transparent? Recommend transparent — chatbot declares `connector-push` output; platform handles size-based routing. |

---

## 13. Cross-references

- Design note §28 — the source directive.
- Spec #25 full-platform-schema-sketch — `connector_connections` + audit log fit into the broader schema.
- Spec #27 MCP-gateway-skeleton — `connector_invoke` RPC routing.
- Spec #67 track-N (vibe-coding) — connectors are an `attach_tool` target from `/node_authoring.attach_tool`.
- Spec #69 handoffs (TBD) — §30 handoff pipeline uses `arxiv`, `crossref_doi`, `isbn_bowker` connectors.
- Spec #29 paid-market — §8.5 connector invocations within paid fulfillment.
- Catalog `docs/catalogs/integration-connectors-catalog.md` — 8 worked connector examples.
- §17 privacy — per-field visibility respected on push.
- §26.2 output kinds — `connector-push` routes here.

---

**Status on dispatch:** ready to implement. Spec is executable without further research. Estimated MVP: **~3.15 dev-days** (~3.75 with handoff connectors per §10).
