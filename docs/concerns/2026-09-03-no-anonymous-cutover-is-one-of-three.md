# The no-anonymous cutover is one of three and still leaves a public read

**Filed:** 2026-09-03
**Verified:** 2026-09-03, Windows, live `https://tinyassets.io/mcp`, local branch
`claude/no-anonymous-principal` at `3e4999fbd60044865765ad3737c39bca04c212c0`.
**Severity:** P1 — the live MCP endpoint still creates an anonymous session, and the
only existing cutover is an unmerged, explicitly partial source change.

## Source (verbatim)

> The user's firm product decision is that anonymous access must not exist
> anywhere platform-wide. Local Codex and Claude agent sessions on a user's
> computer are ordinary user clients: the user must be able to sign them in,
> and their MCP connection must then enter that user's TinyAssets universe
> exactly as authenticated browser chatbot connections do.

Founder directive, 2026-09-03.

## What is true now

An unauthenticated MCP `initialize` request to the canonical live endpoint
returned HTTP 200 and a session instead of an authentication challenge. The
session could not read the founder's recent conversation, because it had an
anonymous identity. Explicit OAuth login did reach the founder universe from a
fresh Codex process, so the identity mapping works once a bearer is present.

The prior work is not missing: `claude/no-anonymous-principal` owns
`openspec/changes/no-anonymous-principal`, has no PR, is 14 commits ahead and 18
behind `origin/main`, and records 11 of 12 tasks complete. Its design calls itself
"PR 1 of 3: sources". It intentionally keeps `GET /mcp/pulse` as an
unauthenticated read, while the founder directive allows only discovery and
sign-in bootstrap that confer no platform data or action. Source search on that
branch also still finds live anonymous defaults and string gates in the daemon,
run, graph, and storage paths; its own design assigns removal of those sinks to
later changes that do not yet exist.

The targeted authority suite on that exact branch head was run on 2026-09-03:

```text
python -m pytest -q tests/test_no_anonymous_principal.py tests/test_require_auth_challenge.py tests/test_predeploy_auth_hardening.py tests/test_mcp_public_canary.py tests/test_deployed_sha.py tests/test_current_actor_auth_context.py tests/test_optional_auth_mode.py
136 passed, 1 failed, 1 warning
```

`test_get_status_carries_the_daemon_block` expects only `last_activity_at`, but
the current payload also has `has_work` and `worker_liveness`.

## Why this cannot be silently finished in a duplicate change

The existing branch is actively owned and is the correct OpenSpec home for the
public authority boundary. It has already used all three permitted cross-family
review rounds, and its head changed after the last review, so it has neither
review budget nor an exact-head approval receipt. The owner/founder must decide
how to land or supersede that branch. After that, the sink-removal and migration
slices still need explicit owners and OpenSpec changes. `/mcp/pulse` must use a
named service principal or become a discovery-only response before the
platform-wide no-anonymous claim is true.
