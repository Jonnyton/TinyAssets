# Codex review record — daemon log durability (PRs #4016 / #4017)

Three refute-review rounds on the two-PR stack that moves the daemon's container
output into the host journal (#4016) and ships a redacted window of it off-box
(#4017). Dispatched with `python scripts/peer_agent.py codex --prompt-file <brief>`
from the PR worktree, on Codex's own budget, asked to REFUTE with
`AGREE` / `DISAGREE_EVIDENCE` / `DISAGREE_CONCERN` per AGENTS.md.

These files are tracked because nine committed files cite them, and because
`output/` is gitignored — a citation to an untracked path is the dangling pointer
AGENTS.md warns about. Filed here so the artifact outlives the author's checkout.

| Round | Brief | Report | Verdict |
|---|---|---|---|
| 1 | [brief](2026-09-26-codex-log-durability-brief.md) | [report](2026-09-26-codex-log-durability-review.md) | ADAPT — 5 blockers |
| 2 | [brief](2026-09-26-codex-log-durability-brief-round2.md) | [report](2026-09-26-codex-log-durability-review-round2.md) | ADAPT — part 1 cleared, 3 blockers on part 2 |
| 3 | [brief](2026-09-26-codex-log-durability-brief-round3.md) | [report](2026-09-26-codex-log-durability-review-round3.md) | ADAPT — part 1 cleared again, 2 blockers on part 2 |

Three rounds is the AGENTS.md cap, so the remaining findings went to the founder
rather than into a fourth round. The reviewer also declined a fourth.

## Outcome

**#4016 (part 1) — cleared** by rounds 2 and 3, at head
`84f63572f0b3707b20b6fe3949b7a97cbc1547d2`. Any push to that branch voids the
clearance, so the citation paths inside it still read `output/...` rather than the
`docs/reviews/` paths used here; correcting them means re-review of a
comment-only change.

**#4017 (part 2) — held.** Two blocking classes, both reproduced independently of
the reviewer:

1. Credential fragments still reach the shipped bundle — an escaped interior quote
   terminates the value early, and the key-length bound added to fix a quadratic
   blowup silently excludes long keys (which also breaks the superset relationship
   with `codex_provider._SECRET_SHAPES` that a test claims to enforce).
2. The per-source deadline does not fire during a blocking read (measured 4.04s
   against `timeout=1`), and a mid-read error leaves the child running.

## What the rounds cost, and the lesson

The redaction filter failed all three rounds, each on a different input class:
quote handling, then terminator choice, then key-length bounds. Round 2 found that
round 1's fix destroyed evidence (`authentication succeeded` →
`authentication [redacted]`); round 3 found that round 2's performance fix
introduced a silent miss. That oscillation is the signal AGENTS.md describes — the
shape is wrong, not the parameters.

The shape that removes the class: the lines are **JSON** (Vector's console sink uses
`codec: json`), so redact by parsing each record and walking keys, recursing into the
embedded `log` string, with a fail-closed fallback that drops a record it cannot
parse rather than exporting a guess. A line-oriented regex cannot know where a value
ends; a parser does not have to guess.

## Findings the reviewer got right that I had not considered

Worth keeping separately from the blockers, because each was a claim of mine that did
not survive contact:

- `journalctl` writes `-- No entries --` to **stdout** and exits 0 (round 1, via my
  own real-binary run) — an empty journal read as a healthy source.
- `MaxRetentionSec` is a maximum age, **not** a minimum retention guarantee, so
  `SystemMaxUse=1G` can mean hours; my comment claimed the opposite.
- Disabling journald rate limiting entirely was justified by a Docker volume limit
  that **is not configured anywhere**.
- GitHub-release retention is **one pool** across prefixes, so adding a third tier
  silently shortened brain/data history.
- Both pruners owned more than they generate, including a manual bundle name **this
  repo's own runbook** told operators to create.
- `docker logs` refusing a fluentd-driver container — my justification for retiring
  `tinyassets-ship-logs` — is probably false (Docker dual logging keeps a readable
  cache by default). Withdrawn rather than repeated.
