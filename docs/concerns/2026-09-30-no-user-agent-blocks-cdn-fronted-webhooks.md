---
severity: P1
title: Outbound calls send no User-Agent, so a CDN-fronted receiver blocks them
filed: '2026-09-30'
summary: >
  _SsrfHardenedHttpDriver sends no User-Agent on an ordinary call. Cloudflare
  answers a UA-less POST with "error code: 1010" (HTTP 403) before the origin
  sees it, so a user-built channel to any Cloudflare-fronted webhook receiver
  fails with a body that names nothing the owner can act on. Reproduced against
  tinyassets.io's own /mcp/hooks receiver by clean A/B.
---

# Outbound calls send no User-Agent, so a CDN-fronted receiver blocks them

**Filed:** 2026-09-30
**Verified:** 2026-09-30, clean A/B against the live `https://tinyassets.io/mcp/hooks/<token>`
receiver through the real `authenticated_external_call` effector (the
capability-URL live-proof rehearsal on PR #4115).
**Severity:** P1 — it makes a *correct* user-built channel look broken, on the
single most common integration shape.

## Evidence (one variable changed)

Identical packet, identical connection, identical vault credential. The only
difference between the two runs is one caller-supplied header.

**Without `User-Agent`:**

```
status 403
body   "error code: 1010\n"
headers cf-ray: ..., server: cloudflare
```

Cloudflare error 1010 is "the owner of this website has banned your browser" —
a client-fingerprint block, raised at the edge. The origin never sees the
request, so the receiver's own contract (202 deliverable / uniform 404) never
applies.

**With `"User-Agent": "TinyAssets-capability-url-proof/1.0"`:**

```
status 404
body   {"error":"not_found"}
headers cf-cache-status: DYNAMIC, cf-ray: ...
```

That 404 is the receiver's own uniform non-deliverable answer
(`tinyassets/webhook_inbound.py`) — i.e. the request reached the application.

## Why it matters

`_SsrfHardenedHttpDriver.__call__` builds `request_headers` from
`_validated_request_headers(headers)` plus the auth headers. It adds no
`User-Agent`. The only place the codebase sets one is the redirect download
path (`outbound_connections.py:3737`, `"User-Agent": "TinyAssets-download"`).

So every ordinary outbound call — **every** auth scheme, not just the new
`url_secret` — goes out UA-less. And the destinations users actually want are
CDN-fronted: Slack, Discord, Zapier and Make webhooks all sit behind one, as
does `tinyassets.io` itself.

The failure is also **unactionable from the owner's seat** — and the owner is
never told at all.

**Re-verified 2026-09-30, and the original wording here was too strong.** This
file first said "the agent's documented repair for a 4xx is to rotate or widen
the credential". That is not what the guidance says: the `connections` chapter
conditions rotation on failure **class** `credential_rejected` (a delivered 401,
or a 403 whose body names the key itself), and a `1010` body carries no
credential vocabulary, so it never reaches that class. Corrected in place
rather than left standing — a premise a reader would act on has to be the real
one.

What actually happens, reproduced against `_classify_external_write`:

```
'far side answered http 403: error code: 1010'  ->  external_write_failed
```

whose served advice is *"An effect failed for a reason you can fix … Fix that
and run again yourself, in this turn — this is yours to fix. Try at most twice"*
and whose owner routing is `chatbot`. So the universe is told an edge block is
its to fix, retries it twice, and the **founder — who holds both of the real
repairs — never hears about it.** That is the half that makes this a P1 rather
than a cosmetic omission.

## Repair

Send a default `User-Agent` from the driver when the caller supplies none, and
let a caller-supplied one win:

```python
request_headers.setdefault("User-Agent", "TinyAssets/1.0 (+https://tinyassets.io)")
```

Not done in PR #4115 on purpose: it changes the wire bytes of **every**
outbound call on every scheme — a shared hot path — and it deserves its own
review and its own live check rather than riding in on a scheme change.

Conditions the repair must satisfy:

1. A caller-supplied `User-Agent` is preserved, not overwritten (the packet
   already carries arbitrary non-auth headers).
2. `_reject_forbidden_header_name` / `_SSRF_FORBIDDEN_HEADER_CHARS` still apply
   — the default must not become a way around the framing denylist.
3. A test that asserts the header on the wire through the loopback stub in
   `tests/test_outbound_ssrf_driver.py`, mutation-checked.
4. Re-run the live A/B above: the default alone must get past the edge.

## Also worth doing

Classify a CDN edge block as its own failure class rather than
`far_side_error`. A 403 whose body matches `error code: 1010` (or 1020/1015) is
not a credential problem, and telling the agent it is sends the owner to rotate
a key that was never rejected.
