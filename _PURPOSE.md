# Worktree purpose

Purpose: sse-keepalive-proof
Provider: claude-code
Branch: claude/sse-keepalive-proof
Base ref: origin/main
Issue/PR: corrects docs/concerns/2026-08-28-converse-sse-stream-has-no-keepalive.md — the premise ("a converse SSE response sends nothing until the result") is false at the origin: the MCP SDK answers over sse_starlette.EventSourceResponse, which pings every 15s while the tool runs; end-to-end delivery stays open until a >3-minute live converse is captured (Codex ADAPT)
PLAN refs: live MCP connector surface; served turns run until finished
Ship condition: tests/test_mcp_sse_keepalive.py drives the production app construction with a tool that outlives the (scaled) ping interval and reads >= 2 `: ping` frames before the result, and asserts SSE mode at runtime; the concern is rewritten with the corrected premise and its original resolution bar; no unsupported causal claim remains; Codex refute folded
Abandon condition: the wire test fails against the production app (then the concern stands and the keepalive must be built)
Pickup hints: tests/test_mcp_sse_keepalive.py; tinyassets/universe_server.py::create_streamable_http_app; docs/concerns/2026-08-29-a-deploy-kills-in-flight-turns-silently.md
Memory refs: deploy-kills-in-flight-turns, grep-typed-homes-before-rederiving
Related implications: the web-app in-flight hold bound in claude/codex-turn-wait only has to exist, not be tight
Idea feed refs: (none)
