# The edge Worker destroys the body of every origin 5xx

**Severity:** P2 · **Found:** 2026-08-28, driving the live subscribe/cancel flow as a user
**Surface:** `deploy/cloudflare-worker/worker.js` (in front of `tinyassets.io`)

## What happens

`worker.js:168-181` intercepts any upstream response with status 500-599 and replaces
the **entire body** with its own:

```json
{"error": "bad_gateway", "detail": "tunnel origin returned 5xx", "upstream_status": 503}
```

and rewrites the status to 502. The origin's own JSON never reaches the browser.

## How it surfaced

Subscribing and cancelling both worked. Clicking **Upgrade** again immediately after
cancelling showed the user:

> Billing unavailable: tunnel origin returned 5xx

The origin had in fact answered `503 {"error": "checkout_already_in_progress"}` — a
deliberate, correct refusal. The Worker stripped the reason and substituted an
infrastructure diagnosis. The user is told the tunnel is sick; the operator reading logs
is told the same thing. Neither is true.

The 503 half of that is fixed (checkout refusals are now 409, and only genuine
unavailability answers 5xx). **This concern is the other half, and it is not fixed:** the
origin still cannot send *any* meaningful 5xx.

## Why it still matters after the billing fix

`_CHECKOUT_STATUS["billing_unavailable"] = 503` is correct — billing being unconfigured
*is* a server-side condition. But that is precisely the case where the operator most needs
the real detail (`no key`, `webhook secret missing`), and it is the one the Worker will
still overwrite. Same for `onboarding/__init__.py:278` (`not_configured`, 503) and any
unhandled origin 500, whose `{"detail": ...}` is discarded before anyone can read it.

The general shape: **we have no way to distinguish "the origin deliberately answered 5xx"
from "the origin is sick", because the rewrite erases the evidence that would tell them
apart.** Lowering statuses in application code to dodge it would be the wrong fix — it
trades a truthful status for a readable body.

## The Worker's rewrite has a real purpose

It is not gratuitous. Its comment states the goal: distinguish *tunnel origin sick* from
*Worker code broken* from *apex fallthrough to the GoDaddy 404*. That is worth keeping;
the 2026-04-19 P0 outage was exactly this class of confusion
(`docs/audits/2026-04-20-public-mcp-outage-postmortem.md`).

## Suggested fix (not yet made)

Pass a 5xx through unchanged when it carries `Content-Type: application/json` — a
cloudflared or gateway failure emits an HTML error page, not our JSON, so the
discrimination the Worker exists for survives. Synthesize `bad_gateway` only for the
non-JSON case. Consider adding `X-TA-Origin-Status` so a passed-through 5xx is still
attributable at the edge.

Deliberately left for its own change: this is public-surface infra with a separate deploy
path (wrangler), and Hard Rule 11 requires
`python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp` green afterwards.
Landing it alongside a billing fix would put an edge regression and an app fix in one
blast radius.

## Reproduce

```bash
# any origin 5xx, e.g. with billing unconfigured:
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://tinyassets.io/mcp/app/billing/checkout
# body is the Worker's bad_gateway JSON, never the origin's
```
