## Why

Agent Village currently binds to every interface by default, serves
host-private coordination/session state without authentication when no token is
supplied, and accepts talk/hire mutations from cross-site form requests. Its
query-string bearer also leaks through history, logs, and referrers, so the
shipped phone-access surface is a P0 host-security boundary failure.

## What Changes

- Default the command center to loopback and generate a high-entropy bearer
  token whenever the operator does not supply one.
- Keep static bootstrap assets and the liveness probe reachable, but require
  the bearer for every state/chat/provider read and every talk/hire mutation.
- **BREAKING:** stop accepting `?token=` API authentication. Bootstrap the
  browser from a URL fragment, remove the fragment from visible history, keep
  the bearer in session storage, and send it only in a request header.
- Use constant-time bearer comparison, reject oversized request bodies before
  reading or invoking collectors, and add defensive browser response headers.
- Preserve intentional phone/LAN use through `--host 0.0.0.0`; the generated
  fragment share URL remains copyable without making unauthenticated LAN mode
  possible.
- Add exact HTTP and browser-source contract tests for unauthorized reads,
  CSRF-shaped writes, query-token rejection, generated-token startup, bounded
  request bodies, and fragment/header bootstrap.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: Agent Village becomes authenticated by
  default, with header-only API bearer use and a safe static bootstrap path.

## Impact

Affected code is confined to `command_center` server/config/browser bootstrap,
its README, and focused server tests. Existing direct scripts or bookmarks
that call sensitive endpoints without a bearer or use `?token=` must move to
`X-Village-Token`; no MCP action, storage shape, dependency, or public
`tinyassets.io` surface changes.
