@AGENTS.md

## Claude Code

`AGENTS.md` is how to work here. This file is only harness quirks.

### Merging and deploying

**Background-job sessions cannot merge or push to `main`** — that restriction is
injected into that session type and cannot be lifted from inside one. Check which
session type you are in before claiming you cannot merge; an interactive session
repeating "this session cannot merge" is misapplying the rule. Interactive
sessions merge normally; `gh pr merge --auto` works from either.

**Green checks are not sufficient — inspect diff scope.** PR #1491 presented as a
two-file auth fix and carried seven workflow files plus `deploy-prod.yml` and a
Dockerfile, because the branch sat on an unmerged 217-commit lineage. CI passed
on the parts it looked at. `pr-scope-guard` now catches this class; do not merge
around it.

### Cross-family dispatch

Codex CLI is a second model family already in the harness, not something only a
human can start. Dispatch it as a **background subprocess on its own budget** via
the `peer-agents` skill — never wrap it in a Claude teammate to relay, which
burns a Claude context to do nothing.

Dispatch by default, not on request: before a review verdict, before a risky
change, before a "done" claim on non-trivial work, and whenever stuck 3+
iterations. Ask it to *refute*, and log the verdict. A dispatched review gates
landing, not your forward progress — take the next lane while it runs.

### Session start

Read `AGENTS.md` (imported above) and let the sync gate report whether the
checkout is behind. There is no startup ritual beyond that.

### Memory and skills

Per-agent memory lives in `.claude/agent-memory/<name>/` — the named owner
writes, everyone reads. Skills are in `.claude/skills/` (mirrored from the
canonical `.agents/skills/`); ten of them, named for their task, no router.

### Verification

`AGENTS.md` owns the invariants. In Claude Code the independent path is a Codex
subprocess — a genuinely different model family, which a Claude teammate
reviewing Claude's work never was. The live `ui-test` route remains the final
proof for chatbot-facing behaviour.
