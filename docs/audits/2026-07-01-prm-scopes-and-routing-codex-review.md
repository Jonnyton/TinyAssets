VERDICT: adapt

Required: [tinyassets/auth/wellknown.py](C:/Users/Jonathan/Projects/TinyAssets/.claude/worktrees/permissions-fail-closed/tinyassets/auth/wellknown.py:116) mounts AS metadata only at `/.well-known/oauth-authorization-server`; `GET /mcp/.well-known/oauth-authorization-server` returns `404`. That contradicts the project’s `/mcp` OAuth submission docs and leaves older/direct-discovery MCP clients without the AuthKit proxy fallback. Add the `/mcp/.well-known/oauth-authorization-server` route to `_handle_authz_server_metadata` and a regression in `tests/test_wellknown_discovery.py`.

Required before merge/live: this branch is 3 commits behind `origin/main`; rebase/merge current main and rerun the focused auth/ACL tests.

Evidence checked:
- WorkOS MCP docs: AuthKit is AS; RS should validate tokens and can proxy AS metadata for compatibility: https://workos.com/docs/authkit/mcp
- MCP auth spec: PRM + AS metadata discovery are core auth discovery mechanisms: https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
- Repro: local `TestClient(starlette_discovery_routes())` returns `404` for `/mcp/.well-known/oauth-authorization-server`.
- Passing checks: 215 focused auth/ACL/onboarding tests; 76 WorkOS/reset/bundle tests; mirror parity invariant; plugin import probe; ruff on changed auth/ACL/status/universe files. Full ruff on `tinyassets/api/runs.py` still hits existing long separator lines.