## Context

The production MCP server uses a resolve-always OAuth posture: anonymous reads
remain public, while pure-write handles receive a pre-dispatch OAuth challenge.
That correctly removed PROBE-003's anonymous write half. A standing CI
credential is acceptable only if it cannot become a general identity or widen
the write surface beyond one reserved draft.

The request crosses the HTTP auth middleware, the plain `write_page` handler,
wiki storage, the stdlib canary client, and GitHub Actions. The credential must
be safe when unset, misconfigured, replayed against another tool, or paired
with attacker-controlled `write_page` arguments.

## Goals / Non-Goals

**Goals:**

- Restore persisted write/read evidence for `drafts/notes/uptime-probe.md`.
- Keep anonymous writes closed and OAuth behavior unchanged.
- Make a configured service token useless for every other path and auth check.
- Keep scheduled uptime green when the CI secret is simply unavailable.

**Non-Goals:**

- Create an OAuth client, founder identity, capability, or reusable service
  account.
- Permit dynamic canary filenames, wiki patches, filings, universe canon, or
  any other authenticated action.
- Add a new MCP handle or dependency.

## Decisions

### Dedicated request-local authority, never an identity

A small stdlib-only auth helper will validate `TINYASSETS_WIKI_CANARY_TOKEN`
and hold a dedicated request-local boolean while one eligible call dispatches.
The current identity remains anonymous. Existing `require_auth`,
`require_action_scope`, permission, and founder checks therefore cannot observe
the token as authentication.

Alternative considered: synthesize a restricted `Identity`. Rejected because
generic auth checks could accidentally treat any non-anonymous identity as
sufficient now or in future code.

### Three exact scope checks

The ASGI middleware will accept the token only for one non-batch JSON-RPC
`tools/call` whose tool and argument shape exactly match the canary full write.
Because stateful Streamable HTTP executes tools in the persistent MCP session
task rather than the ASGI request task, a FastMCP `on_call_tool` middleware
will re-read the actual HTTP request and re-establish the authority only around
that tool execution. It independently requires one bearer header, canonical MCP
path and method, the configured token, the exact tool name, and the exact
parsed arguments. Missing or ambiguous HTTP context fails closed.

The `write_page` handler will then re-check its normalized function arguments
before using the dedicated authority. Any extra or changed routing argument
fails into the existing invalid-token or anonymous-write behavior.

The handler will call a dedicated fixed-path writer for
`drafts/notes/uptime-probe.md`; it will not use the general writer's
"update promoted page if present" resolution. This makes the filesystem path,
not merely the category/slug pair, the security boundary.

Alternative considered: bypass only `write_gate_rejection` and reuse the
general writer. Rejected because a promoted page with the same slug would
silently redirect the authority to a different path.

### Fail-closed credential handling

The server feature is disabled unless the environment value contains at least
32 UTF-8 bytes. Presented and configured bytes are compared with the standard
library constant-time comparator. The value is never included in errors,
diagnostics, or logs. A missing, short, mismatched, or wrongly scoped bearer
continues through the existing invalid-token challenge.

### Credentialed probe with anonymous fallback

`wiki_canary.py` will attach the bearer only to the reserved write call, write a
fresh per-run marker, verify that the returned path is exact, then read and
match that same marker. It
will keep the existing anonymous OAuth-gate-plus-persisted-read behavior when
the environment variable is absent or empty. A present but rejected credential
is red, because that is a configured roundtrip failure rather than missing
credential.

## Risks / Trade-offs

- **Standing credential is copied into two runtimes** → Keep both copies
  single-purpose, rotate them together, never print them, and make either
  missing copy disable or fall back safely.
- **Scope predicate accidentally widens** → Test adjacent filenames, extra
  routing arguments, batch calls, and non-wiki tools; perform an explicit
  mutation run that widens the filename predicate and confirm tests fail.
- **Request-body classification adds buffering** → Reuse the existing 1 MiB
  anonymous-body cap and replay mechanism; oversized candidates fail before
  dispatch.
- **Secret absent during rollout** → Server stays unchanged and PROBE-003 uses
  its existing gate/read mode, avoiding a credential-availability outage.

## Migration Plan

1. Deploy the server code with the feature disabled by default.
2. Install the same randomly generated value of at least 32 bytes in the
   production server environment and the GitHub Actions
   `TINYASSETS_WIKI_CANARY_TOKEN` secret.
3. Observe PROBE-003 write/read green evidence.
4. Rotate by replacing both values in one maintenance window. Roll back
   authority immediately by removing the server environment value; the
   scheduled probe then safely returns to anonymous fallback if its secret is
   also removed.

## Open Questions

None. The host decision fixes the credential type, scope, fallback, and wiring.
