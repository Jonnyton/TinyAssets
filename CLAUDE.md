@AGENTS.md

## Claude Code

Two harness quirks; `AGENTS.md` is the rest.

**Background-job sessions cannot merge or push to `main`.** The restriction is
injected into that session type; an interactive session repeating it is
misapplying it. `gh pr merge --auto` works from either.

**Codex CLI is already installed here**, so the other model family is a
background subprocess you start yourself — `peer-agents` skill.
