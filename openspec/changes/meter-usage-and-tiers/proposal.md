## Why

On 2026-08-28 the founder's universe fixed a real branch bug, then could not run the
repair: `run_graph rate limit reached (max 20 per 60m)`. Fifteen *failed* X posts (403s
while the app was read-only, then 401s after the token was regenerated) had already spent
the budget the one successful post needed.

The limit counts the wrong thing. It is a **security bound** — Codex gate #5, stopping a
prompt-injected engine from spamming an already-approved effect branch — but it is
enforced at *admission*, so reads, writes, edits and failed attempts all decrement it. It
is also being asked to do two incompatible jobs at once: protect the outside world from
spam, and implicitly bound our compute.

It is additionally **unspecced**: `_RUN_GRAPH_RATE_MAX = 20` /
`_RUN_GRAPH_RATE_WINDOW_S = 3600` live only in `tinyassets/engine_mcp_server.py:69-70`,
hardcoded with no env var. Neither founder nor universe can change them, and no
`openspec/specs/` requirement describes the behaviour.

Separately, the platform now needs a commercial shape. Cost work (2026-08-28) established
that marginal cost per user asymptotes near **$0.12/month**: WorkOS is free to 1M MAU,
Cloudflare is free at our volume, and — decisively — **we supply no inference**, so the
usual dominant cost of an AI product is not on our books. Generosity is therefore
affordable; the binding constraints are abuse reaching the outside world and price
anchoring, not compute cost.

## What Changes

**Split one counter into two.** A billable **effect quota** counted at effect
*completion*, and a separate, far more generous **compute guard** on run admission. Reads,
writes, edits and failed attempts stop consuming the billable budget.

**Meter three dimensions per universe** — effects, compute-minutes (run subprocess
wall-time on our box), and storage. There are no GPU-minutes: we own no GPUs and buy no
inference; every universe runs on the user's own subscription or key.

**Resolve a tier per universe** — a generous free tier, and one paid tier at $20/month —
with limits configurable rather than hardcoded.

**Report usage to Stripe** via Billing Meters, keyed by the WorkOS `sub` that is already
our canonical founder key. Nothing outside the billing adapter imports Stripe: metering
writes to our own ledger, and the adapter reads that ledger and reports upward, so the
meter stays correct when Stripe is unreachable and the processor stays swappable.

**Make refusals actionable.** Today's message is "try again shortly" with no reset time
and no indication of which budget ran out.

## Capabilities

### New Capabilities
- `usage-metering-and-tiers`: per-universe metering of effects, compute-minutes and
  storage; tier resolution and quota enforcement from that meter; usage reporting to an
  external billing processor across an adapter boundary.

### Modified Capabilities
- `external-effect-receipts`: a receipt reaching terminal success SHALL increment the
  owning universe's effect meter; receipts that fail, hold, or are released SHALL NOT.
  This is the requirement that makes the quota count effects rather than attempts.
- `daemon-runtime-and-dispatch`: the engine-triggered run admission bound becomes an
  explicitly-specified compute guard, separate from the billable effect quota, with
  configurable limits and a stated fail-open/fail-closed posture.

## Impact

- `tinyassets/engine_mcp_server.py` — `_engine_run_admit()` (`:86-148`) and its four call
  sites (`:377` run_graph, `:884` write_graph, `:1163`, `:1405`), which today share one
  ledger keyed only by `universe_id`.
- `tinyassets/storage/external_write_receipts.py` — `finalize_receipt` becomes the effect
  counting point; the DB is already per-universe via `receipts_db_path(universe_dir)`.
- `tinyassets/runs.py` — run wall-time capture; the 4-worker top-level pool (`:3002`) is
  the current concurrency ceiling.
- `tinyassets/api/status.py:1252-1277` — storage attribution; only three subsystems are
  attributed per universe today, so run transcripts must be attributed before storage can
  be metered honestly.
- New billing adapter module + Stripe dependency, isolated behind the boundary rule above.
- `docs/reference/environment-variables.md` — new tier/limit variables.
- Secrets are vault-first (`scripts/load_secrets.sh`); note that compose-level env changes
  are currently inert in production (`docs/concerns/2026-08-27-deploy-drops-compose-sync.md`).
