@AGENTS.md

## Claude Code

`AGENTS.md` is how to work here. This file is only harness quirks, and there are
two.

**Background-job sessions cannot merge or push to `main`** — the restriction is
injected into that session type and cannot be lifted from inside one. Check which
type you are before claiming you cannot merge; an interactive session repeating
"this session cannot merge" is misapplying the rule. `gh pr merge --auto` works
from either.

**Codex CLI is already in this harness**, so the other model family is a
background subprocess you start yourself via the `peer-agents` skill — not
something only a human can run, and not something to wrap in a Claude teammate to
relay.
