# Retired Claude Code agent definitions

These five files were the project's agent (teammate) definitions until the
2026-04-16 roster consolidation. They are kept for git/decision history.
**Do not edit, do not extend, do not cite as live.** The live roster is
whatever is in `.claude/agents/`.

| Retired role | Superseded by | Note |
|---|---|---|
| `planner` | `navigator` | Strategic direction |
| `explorer` | `navigator` | Codebase research folded into the same role |
| `tester` | `verifier` | Test-running gate |
| `reviewer` | `verifier` | Diff review gate; `verifier` runs both gates |
| `story-author` | `verifier` | Per the consolidation note; no live domain-collaborator role |

Sources: `.agents/activity.log` (2026-04-16T20:04, "Agent roster:
explorer/planner/reviewer/story-author/tester moved to
`.claude/agents/retired/`; navigator.md + verifier.md are the replacements")
and commit `01a704d8` "refine: consolidate agent roster + refresh living docs".

## Why they moved here (2026-07-22)

The 2026-04-16 consolidation retired them by moving them into
`.claude/agents/retired/`. **That did not retire anything.** Claude Code
discovers `.claude/agents/` *recursively*, so all five stayed live spawnable
agent types for 3+ months — a session's agent roster listed `explorer`,
`planner`, `reviewer`, `story-author`, and `tester` alongside the five real
roles, with descriptions read verbatim from those files.

That is worse than not retiring them, because two pairs collide directly with
live roles (`tester`/`reviewer` vs `verifier`, `planner` vs `navigator`) — the
exact role-confusion the consolidation was meant to end — and a lead following
`CLAUDE.md` § Agent Teams ("spawn teammates by referencing a role in
`.claude/agents/`") had no signal that any of them were superseded.

Moving them fully outside `.claude/agents/` is what actually retires them.
The durable rule is recorded in `CLAUDE.md` § Agent Teams so the next
retirement does not repeat the no-op.

Precedent for the destination: `docs/historical/README.md` — same pattern
(preserve git-history value, signal superseded, remove from the live surface).
