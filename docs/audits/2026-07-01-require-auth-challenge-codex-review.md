VERDICT: adapt

Required fix: [tinyassets/auth/middleware.py](C:/Users/Jonathan/Projects/TinyAssets/.claude/worktrees/permissions-fail-closed/tinyassets/auth/middleware.py:107) builds the `WWW-Authenticate` `resource_metadata` URL as `https://tinyassets.io/.well-known/oauth-protected-resource` when `UNIVERSE_SERVER_URL=https://tinyassets.io`. The deployed routing docs say only `tinyassets.io/mcp*` is proxied to the MCP daemon, while apex non-`/mcp` paths hit the landing origin. That means the OAuth challenge can point clients at an unrouted/404 metadata URL, so WorkOS login discovery can fail before it starts.

Evidence:
- Branch emits: `Bearer resource_metadata="https://tinyassets.io/.well-known/oauth-protected-resource"`.
- Current public root well-known probe returned `404`.
- [deploy/cloudflare-worker/README.md](C:/Users/Jonathan/Projects/TinyAssets/.claude/worktrees/permissions-fail-closed/deploy/cloudflare-worker/README.md:28) says `/mcp*` is the Worker route.
- WorkOS docs require the 401 challenge’s `resource_metadata` URL to be fetchable so clients can discover the authorization server: https://workos.com/docs/authkit/mcp

Adaptation: in WorkOS mode, derive the challenge metadata URL from `WORKOS_MCP_RESOURCE` when it includes `/mcp`, producing `https://tinyassets.io/mcp/.well-known/oauth-protected-resource`, or route the root well-known path through the same Worker. Add a regression test asserting the exact header, not just `resource_metadata=`. Focused tests currently pass: `48 passed` for auth challenge/WorkOS provider, `14 passed` for write-boundary/first-contact, and ruff passed.