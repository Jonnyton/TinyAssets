## Why

The production GitHub Pipes connection path can inherit a stale
`WORKOS_PIPES_RETURN_TO` host override. WorkOS then returns only a generic
request failure, so a phone user cannot obtain the authorization URL.

## What Changes

- Pin Pipes authorization returns to the canonical `https://tinyassets.io/mcp`
  target required by the connection design.
- Ignore incompatible legacy overrides rather than sending them to WorkOS.
- Add regression coverage for the stale-override case.

## Impact

Only the owner-authenticated GitHub connection authorization flow changes.
No credentials, ledger records, or automation state are altered by this
change.
