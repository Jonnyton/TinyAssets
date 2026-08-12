# Active lane: BYO-LLM connect flow slice 2 deposit boundary

- Purpose: add the authenticated MCP LLM-subscription deposit boundary, redacted connection projection, and isolated Claude launch snapshot without changing serving or routing authority.
- Provider/session: `codex-gpt5`.
- Branch: `claude/enable-claude-serving`.
- Base ref: `origin/main` at `04eb0f60344c82d23520dab32d6d03fd8afbcbae` plus serving fixes through `99505df085063138468c59d68291d9199fb5d783`.
- Worktree: `C:/Users/Jonathan/Projects/wf-slack-routing-fix`.
- STATUS row: `Build BYO-LLM deposit boundary (slice 2)`.
- OpenSpec: `openspec/changes/byo-llm-connect-flow/`, bounded deposit portion of tasks 2.1-2.2 only; do not mark the full OAuth UX tasks complete.
- Co-advanced contract: none; reuse slice-1 custody and serving-binding seams unchanged.
- PLAN refs: `Module: Providers`; `Module: API & MCP Interface`.
- Memory refs: no prior provider memory found; authored proposal/design/tasks are the durable handoff.
- Related implications: credential custody, connection projection, provider assignment admission, and plugin mirror parity.
- Ship condition: focused deposit/bind tests, Ruff, plugin mirror rebuild, independent exact-diff review, and durable audit note.
- Abandon condition: the boundary cannot validate and persist one usable subscription without exposing secret material or weakening the existing ACL/custody model.
- Pickup hints: extend `target=connection` through its existing router; require exact admin ACL; do not touch the provider adapters or serving/router authority modules.
- PR expectation: commit locally on the requested branch; no merge, rollout, or live credential deposit from this lane.

## Idea feed refs

- None promoted; incidental findings stay out of this slice.
