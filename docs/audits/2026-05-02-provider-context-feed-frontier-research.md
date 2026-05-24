# Provider Context Feed Frontier Research

Date: 2026-05-02
Initial provider: Codex
Status: Draft coordination implementation; opposite-provider review should
approve/adapt before this is treated as landed process.

## Question

Make provider-specific memories, ideas, automation findings, and unfinished
work flow into the GitHub/worktree discipline automatically, no matter whether
the user is talking to Claude, Codex, Cursor, or another MCP-capable agent.
The feed must run throughout the lifecycle, not only at session start.

## Current Workflow Evidence

- `CLAUDE.md` has provider-local memory under `.claude/agent-memory/<name>/`
  and Claude hooks in `.claude/hooks/`.
- `.codex/config.toml` points Codex at project docs, currently with no Codex
  memory mirror beyond shared `AGENTS.md`.
- `.cursor/` is absent in this checkout, so Cursor currently depends on
  `AGENTS.md` and any future `.cursor/rules/*.mdc` files.
- Shared idea/context feeds already exist: `ideas/INBOX.md`,
  `ideas/PIPELINE.md`, `.agents/activity.log`, `.agents/worktrees.md`,
  research artifacts, design notes, exec plans, and STATUS rows.

## Frontier Lab Pattern

1. GitHub/worktree/PR is becoming the visible control plane.
   OpenAI's Codex app has built-in worktrees and parallel agent threads; Codex
   app worktrees can become branches that push and open GitHub PRs. GitHub
   Copilot cloud agent researches, plans, changes a branch, and can open PRs
   from GitHub-centered entrypoints. Google Jules works against a selected repo
   and branch, produces summaries, creates branches, and can link PRs.

2. Repository-scoped memory is becoming standard, but it is advisory.
   Claude Code project memory lives in repository-derived memory directories.
   Cursor memories are project-scoped generated rules. GitHub Copilot Memory
   stores repository-specific memories with citations and validates them
   against the current codebase before use, with expiry for stale memories.
   Jules added repository memory for preferences, nudges, and corrections.

3. Automation is moving from one-shot chat into continuous loops.
   Claude Code exposes hooks such as SessionStart and UserPromptSubmit for
   context injection. Codex app automations can run on schedules and in
   background worktrees. Jules has scheduled tasks, suggested tasks, CI-fixer
   loops, PR feedback response, MCP support, and performance suggestions.

4. The safe convergence is "memory feeds lanes", not "memory edits truth".
   The common risk is hidden provider state becoming more influential than the
   repo. Workflow's answer is to keep memory/context as a feed and require
   promotion into STATUS/worktree/PR state before build authority.

## Sources Checked

- OpenAI Codex cloud/docs: https://developers.openai.com/codex/cloud
- OpenAI Codex app announcement: https://openai.com/index/introducing-the-codex-app/
- OpenAI Codex app worktrees: https://developers.openai.com/codex/app/worktrees
- OpenAI Codex app automations: https://developers.openai.com/codex/app/automations
- Anthropic Claude Code memory: https://code.claude.com/docs/en/memory
- Anthropic Claude Code hooks: https://code.claude.com/docs/en/hooks
- Cursor rules: https://docs.cursor.com/context/rules
- Cursor memories: https://docs.cursor.com/en/context/memories
- GitHub Copilot cloud agent: https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent
- GitHub Copilot Memory: https://docs.github.com/copilot/concepts/agents/copilot-memory
- Google Jules getting started: https://jules.google/docs/
- Google Jules running tasks: https://jules.google/docs/running-tasks/
- Google Jules changelog: https://jules.google/docs/changelog/

## Workflow Implication

Adopt a provider-context feed as a lifecycle checkpoint:

- `claim`: before claiming or adding STATUS rows.
- `plan`: before design notes, exec plans, specs, or `_PURPOSE.md`.
- `build`: before implementation and before broadening Files.
- `review`: before reviewing provider work.
- `foldback`: before push, PR update, merge, or STATUS retirement.
- `memory-write`: after provider memory, idea-feed, reflection, research, or
  `_PURPOSE.md` writes.

The feed scans provider memories/configs, shared idea feeds, research
artifacts, automation notes, and worktree handoffs. It does not mutate STATUS.
Agents promote relevant candidates into STATUS/worktree/PR lanes or record why
they do not apply.

## Implemented Slice

- `scripts/provider_context_feed.py`: shared scanner with phase filters and
  JSON/text output.
- `tests/test_provider_context_feed.py`: scanner and Claude hook coverage.
- `AGENTS.md`: cross-provider lifecycle gate.
- `PLAN.md`: design principle that provider memory feeds the GitHub/worktree
  spine instead of becoming parallel truth.
- `.agents/skills/git-workflow-and-versioning/SKILL.md`: lifecycle usage.
- `.agents/skills/external-research-implications/SKILL.md`: research pickup
  and foldback usage.
- `.claude/hooks/provider_context_feed_hook.py` + `.claude/settings.json`:
  Claude Code automatic feed on SessionStart and action-oriented prompts.

## Review Gate

Codex made the initial research finding and implementation slice. Claude should
independently review the sources, the local conventions, and the hook behavior
before this is pushed or treated as final. Verdict options: approve, adapt,
defer, reject.

## Next Hardening

- Add a PR-template/checklist item requiring the relevant
  `provider_context_feed.py --phase foldback` output or a "not applicable"
  note before merge.
- If Cursor-specific project rules are introduced, keep them as pointers to
  `AGENTS.md` plus any Cursor-only hook/rule behavior.
- If Codex automations are used for this repo, add an automation that runs the
  feed on a cadence and opens a draft coordination PR or STATUS proposal only
  when a human/provider can review the candidates.
