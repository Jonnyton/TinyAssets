---
name: peer-agents
description: Dispatch a task to the Claude Code or Codex CLI as a subprocess peer agent on that subscription's budget. Use for opposite-provider (cross-family) review per AGENTS.md, second opinions from another model family, parallel independent tasks, or offloading a long grind (research, refactor, test-fixing) to Claude/Codex while you keep working. Works from any provider session (Kimi, Claude Code, Codex, Cursor).
---

# peer-agents

`scripts/peer_agent.py` runs `claude -p` or `codex exec` as a headless peer agent. The peer spends ITS OWN subscription budget (Claude Max / ChatGPT Pro), not your context — your only cost is launching the job and reading back the result file. Both CLIs must be installed and logged in (`claude --version`, `codex login status`).

## How to dispatch

Launch as a **background** Bash task (peers take minutes, not seconds), then read the `--out` file when the completion notification arrives:

```bash
# Review this repo with Claude (read-only default):
python scripts/peer_agent.py claude --out output/peer-review.md \
    --prompt-file brief.md

# Have Codex fix something in a worktree (write mode):
python scripts/peer_agent.py codex --out output/codex-fix.md \
    --prompt "Fix the failing test in tests/test_universe.py and run it" \
    --cwd ../wf-bug126 --write

# Quick foreground question (prints to stdout, no file):
echo "One paragraph: what does workflow/router.py do?" | python scripts/peer_agent.py claude
```

For big briefs, write the brief to a file with your Write tool and pass `--prompt-file` — avoids shell-quoting and Windows command-line limits. The prompt always goes to the peer via stdin.

## Output contract

- Success: `--out` file holds the peer's final message; exit 0. The full result is also on the task's stdout, so a background completion preview usually shows it directly.
- Failure: the file holds a `[peer_agent] ERROR ...` block; exit 2 (provider error), 124 (timeout), 127 (CLI not found — set `CLAUDE_BIN`/`CODEX_BIN` to the full `.cmd` path on Windows).
- Never treat a missing or stale `--out` file as a result; check the exit code in the task status first.

## Modes

- **Default (read-only-ish).** claude: plain `-p` (Read/Glob/Grep allowed, edit/bash denied). codex: `-s read-only -c approval_policy=never`. Safe to point at the live checkout.
- **`--write` (full agent).** claude: `--dangerously-skip-permissions`. codex: `--full-auto` (workspace-write sandbox — weak on Windows). **Always point `--cwd` at a `wf-*` worktree in write mode, never the live checkout or main.** The peer can then edit, run tests, and iterate on its own.

Useful flags: `--timeout SEC` (default 1800), `--effort minimal|low|medium|high|xhigh` (codex only — use `low` for trivial tasks, it's much faster), `--system TEXT` (codex: prepended to prompt), `--cwd DIR`.

**Model defaults are frontier, always.** claude runs `--model fable` (alias tracking the latest Claude model — currently claude-fable-5 on a Max subscription); codex runs with no `-m`, so it uses the model from the host's `~/.codex/config.toml` (currently `gpt-5.6-sol`) and automatically tracks whatever the host configures next. Override only with a reason: `--model M`, or `WORKFLOW_CODEX_MODEL` for codex.

## When to use which peer

- **Cross-family review is the AGENTS.md rule:** research-derived findings and non-trivial changes need opposite-family review. If you are Kimi/Claude, dispatch review to codex; if you are Codex/OpenAI, dispatch to claude.
- **claude**: strong at nuanced code review, design critique, long-document analysis. Read-only by default; write mode works but codex is usually the better coding workhorse on this host.
- **codex**: strong autonomous coding loops (edit → run tests → iterate) in `--write` mode inside a worktree. `--effort low` for small tasks.

## Notes

- API keys are stripped from the peer's environment (subscription auth only), matching the daemon's provider policy in `workflow/providers/`.
- `scripts/codex_review.py` is the older review-specialized wrapper (adversarial preamble + VERDICT line). Prefer `peer_agent.py` for new work; it generalizes both CLIs and arbitrary prompts.
- Peers do not see your chat context. Put everything they need in the prompt/brief: file paths, line numbers, what "done" means, and any constraints (e.g. "do not commit").
- Windows: the wrapper resolves `.cmd` shims and converts Git-Bash paths; run it with plain `python` from Git Bash.
