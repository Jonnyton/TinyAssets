# Repeatable scoped reset and multi-user testing

## Why

First-contact behaviour cannot currently be tested, and the reason is identity, not data.

A live ui-test on 2026-07-21 tried to reach a genuine first-contact state three ways and failed each
time: Claude.ai Incognito chat (only stops chat persistence), a clean browser profile (connectors are
account-level, the grant lives server-side at Anthropic), and browser cookie inspection (a remote MCP
connector is called by Anthropic's servers, so browser cookies were never on that auth path).
Cross-family analysis then showed a valid bearer alone authorizes universe creation — so wiping
universes would not change first-contact behaviour at all.

The existing clean-slate reset is also the wrong instrument: it is global and destructive, it does not
clear OAuth/WorkOS recognition, and it does not remove the daemon or workers (those are compose
services plus deployed operator credentials). Running it would destroy state and leave the test just
as invalid.

Separately, the platform has never been exercised with more than one identity, so multi-tenant
behaviour — isolation, per-founder scoping, visibility between users — is entirely unverified.

## What Changes

- **A scoped, repeatable reset.** Reset the state belonging to ONE test identity, idempotently, as an
  ordinary operation rather than a destructive global wipe. It must be safe to run between every
  ui-test iteration.
- **Non-destructive by construction.** Resetting one test identity SHALL NOT touch another identity's
  universes, the branch commons, run history, or the wiki.
- **Multiple test identities.** Provide a supported way to exercise the platform as several distinct
  founders so isolation and visibility can actually be observed rather than assumed.
- **Identity observability for tests.** A test must be able to establish which principal a request
  resolved to WITHOUT inspecting secrets — the absence of this is exactly what produced three wrong
  conclusions in one session.

## Impact

- New spec: `test-identity-and-reset`.
- Affected: `tinyassets/reset.py` (currently global-only), founder/home binding, and the ui-test loop.
- Interacts with `universe-visibility` (what a second user may see) and
  `identity-auth-and-access-control` (who the caller is).
- Explicitly NOT a production data-deletion feature; the existing global reset stays host-gated.
