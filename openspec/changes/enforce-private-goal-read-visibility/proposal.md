# Enforce private Goal visibility on reads

## Why

Goal writes accept and persist `visibility=private`, but the canonical anonymous
`read_graph` paths for Goal listing, search, and direct lookup do not enforce
that state. A caller can therefore recover a private Goal's content and
metadata without authenticating, contradicting the write contract.

## What Changes

- Keep private Goals as a supported product concept and enforce owner-only
  reads instead of rejecting or migrating the state.
- Resolve the Goal viewer exclusively from signed request identity through
  `tinyassets.api.permissions.current_actor_id()`; caller parameters and the
  `UNIVERSE_SERVER_USER` environment fallback confer no read authority.
- Omit another actor's private Goals from list and search results, and return
  the existing not-found envelope for direct lookup so existence is not
  disclosed.
- Preserve trusted internal Goal access for daemon operations that are not
  user-facing reads.

## Impact

- Affected capability: `shared-goals-and-convergence`.
- Affected runtime: `tinyassets/api/market.py` Goal read actions and
  `tinyassets/daemon_server.py` Goal selectors.
- Public Goal reads remain anonymous and public Goals remain readable.
