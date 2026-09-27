# Tasks

## Slice 1: agent node + agent tool grants

- [x] 1.1 `agent` marker in `tools_allowed` (no schema field, so no content-hash churn); served update_node unchanged.
- [x] 1.2 `shared_self.agent_node` resolver (snapshot + author + shape) and `served_tools.granted_engine_tools`.
- [x] 1.3 Compiler: `agent_node_id` on agent-node configs; agent slot bounded by the served cap.
- [x] 1.4 Foreground and background sessions: per-node decision; `prepare_shared_self_turn` carries the grant and the cap.
- [x] 1.5 Grant honoured by the HTTP loop, the codex native turn and the claude native turn.
- [x] 1.6 Tests: a background private-universe agent node does a brain read/write and `write_graph` through the real engine handlers; mixed branch; cross-user and author negatives; narrowed grant; mutation table for pin + grant.
- [x] 1.7 Served guidance + handbook sentence, PLAN.md design bullet, plugin mirror rebuild.

## Slice 2: code-node grants over served tools

- [x] 2.1 `invoke_mcp_action` routes a granted served-tool name through the run session's pinned engine route; aliases unchanged.
- [x] 2.2 Tests: granted call reaches own universe; ungranted refused; no cross-user reach; mutation-checked.

## Land

- [ ] 3.1 Cross-family refute round (gpt-6-astra) folded; PR(s) opened with auto-merge off.
- [ ] 3.2 Sync delta into `openspec/specs/`, and fold/archive `shared-background-self` with this change.
