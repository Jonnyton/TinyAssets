# Active lane: retire the cloud worker fleet

- Purpose: remove the fixed provider-shaped cloud fleet and make queued automation execution resolve each universe workflow's assigned serving credential.
- Provider/session: `codex-gpt5-desktop`.
- Branch: `claude/fleet-removal-complete`.
- Base ref: `origin/main` at `04eb0f60344c82d23520dab32d6d03fd8afbcbae`.
- Worktree: `C:/Users/Jonathan/Projects/wf-byo-llm-slice1`.
- STATUS row: `Retire the cloud worker fleet; credential-driven daemon execution`.
- OpenSpec: `openspec/changes/retire-cloud-worker-fleet/`.
- PLAN refs: `Module: Providers`; `Module: Daemon Platform`.
- Memory refs: founder architecture and acceptance criteria in the 2026-08-11 task request; no external research required.
- Related implications: supersedes the provider-shaped cloud-drain/fleet runtime; preserves the queue, ingress, memory, canaries, and non-LLM daemon machinery.
- Ship condition: full required-test surface has zero new failures vs origin/main, changed-file Ruff is clean, plugin mirror rebuilt, independent review complete, and the branch committed without merge/deploy.
- Abandon condition: the merged serving-binding contract cannot resolve branch-task universe authority without changing its approved public interface.
- Pickup hints: fail closed with `no_requester_owned_executor`; never borrow ambient host credentials, choose another provider, or add platform fallback chains.
- PR expectation: commit locally only; do not merge or deploy.

## Idea feed refs

- None promoted; the founder architecture is direct build authority.
