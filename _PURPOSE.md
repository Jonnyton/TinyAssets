# Active lane: BYO-LLM connect flow slice 1

- Purpose: implement the approved owner/founder-only BYO-LLM serving path without ambient or platform-provider authority.
- Provider/session: `codex-byo-llm-slice1`.
- Branch: `claude/byo-llm-slice1`.
- Base ref: `origin/main` at `7b451b2c98abb9b411d35b32def96a319d721594`.
- Worktree: `C:/Users/Jonathan/Projects/wf-byo-llm-slice1`.
- STATUS row: `Build BYO-LLM connect flow slice 1`.
- OpenSpec: `openspec/changes/byo-llm-connect-flow/`, tasks 1.1-1.6 only.
- Co-advanced contract: `openspec/changes/archive/2026-08-26-constrain-set-engine-provider-authority/`, request capability, requester-local admission, and sink validation only.
- PLAN refs: `Module: Providers`; `Module: API & MCP Interface`.
- Memory refs: no prior provider memory found; authored proposal/design/tasks are the durable handoff.
- Related implications: credential custody, custom-agent binding, Slack app ingress, provider routing, cloud-drain source overlap.
- Ship condition: focused/full relevant tests, Ruff, plugin mirror, mutation proof, exact-head dual-family approval, isolated canary, rendered proof, and production-SHA gate.
- Abandon condition: the approved design conflicts with current authoritative code in a way that cannot fail closed within slice 1.
- Pickup hints: preserve `ProviderWorkBinding`; reject caller authority fields; owner/founder only; no direct u-tiny patch; no rollout from this lane.
- PR expectation: commit locally only until review/canary prerequisites are independently satisfied.

## Idea feed refs

- None promoted; incidental findings stay out of this slice.
