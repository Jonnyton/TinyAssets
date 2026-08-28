# A refused credential deposit leaves no trace on either side

**Filed:** 2026-08-27
**Verified:** 2026-08-27 against `be4f2b67` (the deployed sha) and the live droplet
**Severity:** P2 — no data is lost and no surface is down, but a user who cannot
complete a deposit cannot be helped by anyone, including an operator with root

## The finding

The founder tried twice to deposit a GitHub API connection through the app and
reported "i think i deposited it" both times. It had never landed:
`read_graph target=connections` returns only `webhook:test`, `x:posting` and the
legacy `jonnyton/tinyassets` repo pipe.

Neither end of the system can say why.

**The user's end** rendered the error code without the explanation.
`tinyassets/onboarding/app.html` printed `"Couldn't add it: "+r.error`, so a
refusal carrying

```json
{"error": "connection_setup_invalid",
 "detail": "destination must be 2-127 chars of [a-z0-9._:-] starting alphanumeric"}
```

showed on screen as `Couldn't add it: connection_setup_invalid`. Fixed in
PR #2599 (render `detail` first, and state the name rule on the field).

**The operator's end has nothing at all.** `connect_http`
(`tinyassets/api/http_connection.py:223`) returns every refusal — auth,
validation, conflict — to the caller and logs none of them. The only record a
deposit attempt leaves in production is the access line

```
INFO: 172.18.0.1:43434 - "POST /mcp HTTP/1.1" 200 OK
```

A refusal is HTTP 200 with an error payload, so it is **byte-identical in the log
to a successful deposit**. Confirmed on the live droplet: 153,758 daemon log
lines over the six hours covering both attempts, `grep -iE
'connect_http|connection_setup_invalid|endpoint_not_permitted|unsupported_auth_scheme'`
matches zero.

## Why it matters

The user-facing half is fixed, but the operator half is what makes the next
occurrence unfalsifiable. With PR #2599 deployed the founder would have seen the
reason — but **I still could not confirm which validation actually fired**, and
neither could anyone else. The cause recorded in PR #2599 (a Name containing a
space) is the strongest candidate, not an observation: the endpoint half
validates clean, so the destination slug rule is the remaining door. That
inference is exactly the kind of claim this repo requires evidence for, and the
evidence does not exist.

This is the deposit path — the single step between a user and a working
universe, and the one place a silent failure costs the most.

## What would resolve it

Log every `connect_http` refusal at WARNING with `error`, `detail`,
`destination`, and the endpoint hosts — **never** the secret, and never anything
derived from it. The function already sanitizes what it returns; the same
sanitized object is what should be logged. The refusal paths all sit before any
write, so this adds no failure mode to the provisioning path.

Deliberately **not** folded into PR #2599: that PR is a UI render fix with no
credential-path change and therefore no cross-family review gate, and the
founder is blocked behind its deploy. This change touches the credential
provisioning file and needs the gate (`AGENTS.md`: self-review never suffices
for auth changes).

## Related

- PR #2599 — the user-facing half.
- `docs/concerns/2026-08-27-deploy-drops-compose-sync.md` — same class: a real
  effect that no surface reports.
