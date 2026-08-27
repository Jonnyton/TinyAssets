# The outbound broker child fails to start, and nothing can say why

**Filed:** 2026-08-27
**Severity:** P0 — every `authenticated_external_call` in production fails; the
founder's first real outbound action has not completed in three days

## The finding

The founder has been trying to post `Hello World` to X since 2026-08-25. It has
never posted. Read from the shared cross-surface thread on universe
`u-01kxm1vszd8hwp7em418asq8h9` (30 turns, via the founder-only
`get_status include_conversation=true` peek).

The blocker has moved four times. Three of the four are fixed:

| Date | Failure | Status |
|---|---|---|
| 08-25 | `node_not_approved` — the static branch's `source_code` node | **open**, see below |
| 08-26 | `permission_denied:provider_not_bound` | fixed |
| 08-27 am | `provider_unavailable` — "provider invocation usage could not be settled" | fixed |
| 08-27 pm | `ProxyRequestError: outbound proxy failed to start` | **open — current blocker** |

The universe isolated the current one correctly and its evidence stands up:
under deploy `44c4e205` it ran `Webhook Channel Test Static v2`
(`4a18e60c0f04494b`) beside `X Hello World via Codex v2` (`a424177413074789`)
and **both** returned the same proxy-start failure. So this is not X-specific,
not the `x:posting` credential, and not the branch packet shape — it is the
shared `authenticated_external_call` egress. Earlier runs of that same webhook
branch had succeeded, so this is a regression, not a never-worked path.

## Why the cause is unknown

`tinyassets/storage/outbound_connections.py` made the failure structurally
undiagnosable, which is why three days produced no diagnosis:

- The spawned child wrapped `_load_dispatch_factory` in a bare
  `except Exception:` and replied with a hardcoded string. The real exception
  was discarded and never logged.
- The parent discarded even that reply, raising one fixed string whether the
  child had *timed out* or *failed*. `worker.exitcode` was never read, so a
  child killed outright (OOM, spawn failure) was indistinguishable from a slow
  one.

Hard Rule 8 (fail loudly, never silently) on the egress path.

## What landed

Branch `claude/outbound-proxy-start-diagnosable`. This does **not** fix the
outage — it makes the next run name its cause:

- The child prints its full traceback to stderr (the container log, host-side)
  and sends only the exception **class** across the wire. Startup runs before
  any credential resolution, so the class carries no credential material; the
  full detail — which includes host paths — stays server-side.
- The parent distinguishes three outcomes: handshake timeout, child-exited
  (with `exitcode`; a negative one is a signal, e.g. `-9` for the OOM killer),
  and child-reported startup failure (with the cause class).
- Handshake budget moved from a hardcoded `5.0` to
  `TINYASSETS_OUTBOUND_PROXY_STARTUP_TIMEOUT_S`, default `30`.

Verified end-to-end through a real spawned child: caller sees
`outbound proxy failed to start: FileExistsError`, traceback in the log.
`tests/test_outbound_proxy_startup_diagnosis.py`, 14 tests; the startup-failure
path previously had none.

## What is still open

1. **The actual cause.** The two candidates in the code are
   `runtime_root.mkdir()` and the `ConnectionLedger` sqlite open inside
   `_build_credential_broker_dispatch`. I could not confirm which — reading the
   droplet needs `~/.ssh/tinyassets_deploy_ed25519`, absent on this machine
   (filed in `docs/host-actions.md`).

   Two hypotheses I checked and **weakened**, recorded so the next session does
   not re-run them:

   - *Cold-import timeout.* The broker module is pure-stdlib; a fresh
     interpreter imports it in ~0.13s locally. The old 5s budget had real
     headroom. Raising it to 30s is insurance, not the diagnosis.
   - *`/data` ownership.* A bind-mounted `/data` would mask the Dockerfile's
     build-time `chown` and deny `mkdir` to uid 1001, which would fit "new grant
     ⇒ new `sha256(grant_id)` runtime dir ⇒ fails, while older grants work" —
     and the universe re-granted consent on every attempt. But
     `deploy/compose.yml:111` mounts the **named volume** `tinyassets-data`, not
     a bind, and a named volume initializes from the image *including*
     ownership. Weak unless the volume predates the current uid.

   **Next step: deploy this, re-run the post, read the named cause.**
2. **`source_code` nodes are permanently unrunnable.** `X Hello World Static`
   (`cc60c0c4f787`) is `runnable: false` on `node_not_approved`, and
   `mark_approved` has no callers — there is no approval handle to reach. The
   universe offered this as its fallback path in its last turn; it will fail
   again.
3. **Served onboarding copy is guessed.** The universe told the founder to tap
   "`Connect / add API connection` — or, if your build still has the older
   label, `Connect subscription`". It is hedging because it does not know the
   live label.
