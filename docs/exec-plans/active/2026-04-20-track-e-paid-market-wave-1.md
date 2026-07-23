# Track E Wave 1 — Paid-Market Flow (First-Draft Economy Primitive)

> **Liveness verified:2026-07-22 — ACTIVE: `request_inbox` is implemented in no `.py` file; STATUS carries an in-flight Wave 2 row. Triage: `docs/audits/2026-07-22-exec-plan-liveness-triage.md`.**

**Date:** 2026-04-20
**Author:** navigator
**Status:** Dispatch-ready exec plan. Consumes Track A schema (commit `98055aa`) and pairs with Track D Wave 1 host_pool client (commit `72e86a2`).
**Foundation classification:** **FOUNDATION** for CRUD + claim semantics; **FEATURE** for UX polish on top.
**Scope:** daemon-economy first-draft per `docs/exec-plans/active/2026-04-19-daemon-economy-first-draft.md` §2 — Wave 1 is tier-1 user posts a paid request + daemons see + bid. Claim + settle arrive in Wave 2. Tray wiring in Wave 3.

---

## 1. What Wave 1 ships

Four CRUD surfaces + wire-up tests. Nothing more.

- `submit_request(node_type, llm_model, max_price, details) → request_id`.
- `list_requests(capability_id=None, state='pending') → list[Request]`.
- `place_bid(request_id, price, daemon_id) → bid_id`.
- `list_bids(request_id=None, daemon_id=None) → list[Bid]`.

Intentionally absent from Wave 1:
- **No claim semantics** (`SELECT FOR UPDATE SKIP LOCKED`) — Wave 2.
- **No settlement** (ledger write + fee transfer + testnet integration) — Wave 2.
- **No tray UX** — Wave 3.
- **No realtime broadcast channel** (`bids:<capability_id>`) — poll-based for Wave 1; Supabase Realtime wiring in Wave 2 alongside claim.
- **No flagging / moderation hooks** — Track A schema already ships `flags` table + `state='flagged'`; Wave 1's CRUD respects the state column (reads exclude flagged rows) but does not ship the flag verbs. Wave 3.

This keeps Wave 1 small enough for one dev-day.

---

## 2. Files

New package `tinyassets/paid_market/` mirroring `tinyassets/host_pool/` structure (Track D Wave 1 precedent). Stdlib-only, urllib.request, no supabase-py dep.

| Path | Purpose | LOC target |
|---|---|---|
| `tinyassets/paid_market/__init__.py` | Package exports: `PaidMarketClient`, `PaidMarketError`, `Request`, `Bid`, `submit_request`, `list_requests`, `place_bid`, `list_bids`. | ~40 |
| `tinyassets/paid_market/client.py` | Supabase REST wrapper. `PaidMarketClient` with 4 verbs + `_HttpClient` protocol injection seam + service-role auth via env. `Request` + `Bid` dataclasses matching Track A schema row shapes. | ~250 |
| `tinyassets/paid_market/requests.py` | `submit_request` + `list_requests` convenience wrappers over the client. Handles capability_id lookup (split `node_type:llm_model` → resolve `capabilities.id` → FK into `requests.capability_id`). | ~80 |
| `tinyassets/paid_market/bids.py` | `place_bid` + `list_bids` convenience wrappers. Validates price floor against the request's `max_price`. | ~80 |
| `tests/test_paid_market_client.py` | Client config, each verb, error paths, capability-id resolution, price-floor validation, state-filter semantics. Target: 20+ tests. | ~400 |

**Deferred to Wave 2 (named now to prevent scope creep):**
- `tinyassets/paid_market/claim.py` — SELECT FOR UPDATE SKIP LOCKED claim semantics. Needs a Postgres-function RPC call (Supabase REST doesn't natively expose SKIP LOCKED). Wave 2.
- `tinyassets/paid_market/settle.py` — ledger write + 1% treasury fee + settlement-mode enum dispatch. Blocked on testnet wallet-connect (not Wave 1 scope).
- `tinyassets/paid_market/realtime.py` — Supabase Realtime WebSocket subscription to `bids:<capability_id>`. Wave 2 with claim.

---

## 3. Schema consumption (Track A commit `98055aa`)

Wave 1 reads/writes these Track A tables:

| Table | Wave 1 operation | RLS posture |
|---|---|---|
| `requests` | INSERT (submit), SELECT (list) | RLS per `003_rls.sql`: requester self + capability-matched daemons read; `requester_user_id = auth.uid()` write. Wave 1 writes via service-role key to match Track D pattern; tier-1 chatbot-side write via anon+JWT lands when Track C MCP gateway ships. |
| `bids` | INSERT (place), SELECT (list) | RLS: requester reads bids on own requests; bidder reads own bids; `bidder_user_id = auth.uid()` write. Same service-role posture as above. |
| `capabilities` | SELECT only (resolve capability_id from `node_type:llm_model`) | Public-readable per RLS. Read-only in Wave 1. |
| `host_pool` | Not directly touched | Track D's client owns writes; Track E only reads transitively via `requests.capability_id` → `capabilities` → daemons-with-matching-capability in bid-polling (Track D Wave 1 already ships this). |

**Foundation invariant held:** schema shape locked at Track A. Wave 1 is pure behavior on top; no migration, no schema addition.

**No schema changes proposed for Wave 1.** If claim semantics need a Postgres function in Wave 2, it's additive (`005_claim_function.sql`).

---

## 4. Client shape (mirrors Track D Wave 1)

```python
class PaidMarketClient:
    def __init__(self, supabase_url: str, service_role_key: str, *, http_client: _HttpClient | None = None): ...

    def submit_request(self, *, requester_user_id: str, capability_id: str, max_price_cents: int, details: dict) -> Request: ...
    def list_requests(self, *, capability_id: str | None = None, state: str = "pending", limit: int = 50) -> list[Request]: ...
    def place_bid(self, *, request_id: str, bidder_user_id: str, price_cents: int, daemon_id: str) -> Bid: ...
    def list_bids(self, *, request_id: str | None = None, bidder_user_id: str | None = None, limit: int = 50) -> list[Bid]: ...

@dataclass
class Request:
    id: str
    requester_user_id: str
    capability_id: str
    max_price_cents: int
    details: dict
    state: str  # pending / bidding / claimed / running / completed / failed / flagged
    created_at: str

@dataclass
class Bid:
    id: str
    request_id: str
    bidder_user_id: str
    price_cents: int
    daemon_id: str
    state: str  # active / claimed / superseded / flagged
    created_at: str
```

**Pattern match:** same shape as `tinyassets/host_pool/client.py` (verifier already cleared Track D Wave 1). `_HttpClient` protocol seam for tests. No outbound async; Track E Wave 1 is synchronous REST. Async wrapping (if needed) comes when realtime ships in Wave 2.

**Errors:** `PaidMarketError` raises on non-2xx responses or JSON parse failures. Fail-loud per AGENTS.md Hard Rule 8. No silent fallbacks.

**Capability-id resolution:** `submit_request` callers pass either a capability_id directly OR a `(node_type, llm_model)` pair. Convenience wrapper in `requests.py` handles the resolution with a small cache; client.py stays capability_id-only to keep the boundary clean.

**Price units:** cents throughout the Wave 1 API. Matches Track A schema `max_price_cents` / `price_cents` integer columns. Testnet-token conversion lives in Wave 2 settlement; Wave 1 is currency-agnostic.

---

## 5. Test floor — ~20 tests

Target 20-25 tests in `tests/test_paid_market_client.py`, matching Track D Wave 1's 24-test density.

Coverage brief:

**Client construction (~3 tests):**
- Config from env (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY).
- Config from explicit params.
- Missing-env raises `PaidMarketError`.

**submit_request (~5 tests):**
- Happy path: insert + return Request dataclass with filled fields.
- Invalid capability_id: returns 4xx → raises `PaidMarketError`.
- max_price_cents validation (must be positive integer).
- Details dict serialization (JSON-serializable).
- State defaults to 'pending' (Track A schema default asserted).

**list_requests (~4 tests):**
- Filter by capability_id.
- Filter by state (default 'pending', exclude 'flagged').
- Limit respected.
- Empty result → empty list.

**place_bid (~5 tests):**
- Happy path.
- Price floor: reject bid price > request's max_price_cents.
- Invalid request_id: 4xx → raises.
- Daemon_id FK into host_pool must exist.
- Bid state defaults to 'active'.

**list_bids (~3 tests):**
- Filter by request_id.
- Filter by bidder_user_id.
- Both filters combined.

**Integration glue (~2 tests):**
- `submit_request` + `list_requests` round-trip (fake-db in-memory).
- `place_bid` against a just-submitted request.

Test fixtures use the `_HttpClient` protocol injection pattern Track D established — no live Supabase needed for the unit suite. Full end-to-end against live Supabase is Wave 2 smoke (once claim ships).

---

## 6. 24/7-friendly posture (same as Track D)

- **Stdlib only:** `urllib.request` + `json` + `dataclasses`. No `supabase-py`, no `requests`, no `httpx`. Matches Track D Wave 1 + `scripts/mcp_public_canary.py` + `uptime_canary.py` — the whole daemon ecosystem stays dependency-light.
- **Service-role auth via env:** `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` read at client construction. Same pattern Track D uses.
- **Fail-loud on all errors:** per Hard Rule 8. No silent retries, no best-effort swallowing.
- **Synchronous-only at Wave 1:** no asyncio. Wave 2 adds realtime subscription with async; Wave 1's sync API is compatible (callers wrap in `asyncio.to_thread` if needed).
- **No blocking I/O in hot paths:** CRUD calls are one-shot REST requests with a 30-second timeout. Failed calls raise, daemon recovers per its own restart posture.

---

## 7. Foundation-vs-feature split (per CLAUDE_LEAD_OPS.md Foundation End-State rule)

**FOUNDATION (Wave 1 — end-state shape, no reshape later):**
- `PaidMarketClient` class + 4 verb signatures.
- `Request` + `Bid` dataclasses + their field shapes.
- Price-unit semantics (cents integer).
- State-enum values (match Track A schema).
- Error-class contract (`PaidMarketError`).
- Capability-id resolution boundary (client takes id; convenience wrapper splits strings).
- Service-role auth pattern.

**FEATURE (iterates as signal arrives):**
- Convenience-wrapper signatures in `requests.py` / `bids.py` — may grow optional params (e.g., auto-retry, batch submit, cached capability lookup).
- Error-message copy — human-readable prose iterates with user-sim signal.
- Performance tuning — if a specific CRUD verb gets hot, add caching; but don't pre-cache.
- Testing depth — 20 tests is the floor; grows organically as regressions surface.

---

## 8. Sequence within daemon-economy first-draft

| Wave | Scope | Status | Blocks |
|---|---|---|---|
| **Wave 1 (this spec)** | CRUD: submit_request, list_requests, place_bid, list_bids | dispatch-ready | Wave 2 |
| **Wave 2** | claim semantics (SELECT FOR UPDATE SKIP LOCKED via Postgres function), settle (ledger write + 1% fee), realtime subscription | blocked on Wave 1 | Wave 3 |
| **Wave 3** | Tray UX wiring: chatbot invokes submit_request via MCP tool; tray's bid-poller (from Track D Wave 1) surfaces pending requests to daemon operator; manual-approve claim in Wave 3 UI | blocked on Wave 2 | Paid-market demo |

Wave 1's 4 CRUD verbs are the minimum subset where a tier-1 user can post a request and a tier-2 daemon can see + bid. Demo-able end-to-end:
- Developer runs `PaidMarketClient.submit_request(...)` as a tier-1 user proxy.
- Daemon's existing Track D bid-poller returns the request.
- Operator runs `PaidMarketClient.place_bid(...)` as the daemon proxy.
- Developer runs `PaidMarketClient.list_bids(request_id=...)` to confirm.

The actual transaction completes in Wave 2 (claim + execute + settle). Wave 1 proves the wire shape.

---

## 9. Dispatchability

- **Collision check:** `tinyassets/paid_market/` is a new package. No overlap with Track D Wave 1 (`tinyassets/host_pool/`). No overlap with ongoing cutover work (infra side). Safe to dispatch parallel to anything.
- **Schema dependency:** Track A (`98055aa`) already landed. `requests` / `bids` / `capabilities` tables exist with correct shape.
- **Foundation dependency:** `tinyassets/host_pool/` pattern (Track D Wave 1) sets the idiom Wave 1 mirrors. Dev can copy shape.
- **Effort:** ~1 dev-day single contributor, based on Track D Wave 1's similar scope landing in ~1 dev-day.
- **Test floor:** hard. 20 tests minimum; verifier gate.

---

## 10. Acceptance

Wave 1 is complete when all of:

1. Four CRUD verbs return correct shapes end-to-end against a fake `_HttpClient`.
2. Test suite ≥20 tests passes green.
3. Ruff clean on `tinyassets/paid_market/` + `tests/test_paid_market_client.py`.
4. `PaidMarketError` raised on every documented failure case.
5. Capability-id resolution works from either `capability_id` or `(node_type, llm_model)` strings.
6. `list_requests(state='pending')` excludes `state='flagged'` rows (moderation hook respected without Wave 1 shipping the flag verbs).
7. Service-role auth pattern matches Track D exactly (same env-var names, same header shape, same failure posture).
8. No new dependencies in `pyproject.toml`.

---

## 11. Out of scope (explicit, to prevent drift)

- No MCP tool wrappers — `submit_request` as an MCP verb is Track C (MCP gateway slice). Wave 1 gives Track C the Python API to wrap.
- No tray UI — Wave 3.
- No testnet wallet — Wave 2 settlement.
- No realtime channel — Wave 2.
- No autoresearch integration — autoresearch tracks (§32 in full-platform note) are downstream consumers; they'll call Wave 1 verbs.
- No web-app surface — web is a separate track entirely.

---

## 12. Summary for dispatcher

- **4 CRUD verbs, ~1 dev-day, ~20 tests, stdlib-only, mirrors Track D Wave 1 idiom.**
- **New package `tinyassets/paid_market/` — 4 files + test file.**
- **Schema consumption is read-only additive** over Track A `98055aa`.
- **Foundation-end-state on the client class + dataclass shapes + state enum;** feature-iteration latitude on convenience wrappers + error copy + test depth.
- **Unblocks Wave 2 (claim + settle + realtime) and then Wave 3 (tray UX).**
- **Dispatchable NOW** — no collisions with infra cutover or any in-flight work.

Go.
