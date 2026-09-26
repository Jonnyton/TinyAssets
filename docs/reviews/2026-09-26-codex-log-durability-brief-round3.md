ROUND 3, and the LAST: AGENTS.md caps review at three rounds, after which the
findings go to the founder rather than into a fourth round. So be explicit about
what genuinely blocks landing versus what you would accept as a follow-up — a
finding you mark as blocking here stops the change.

You returned ADAPT twice. Round 1 (`output/codex-log-durability-review.md`) had five
blockers; round 2 (`output/codex-log-durability-review-round2.md`) cleared part 1
and left three on part 2. All three are addressed.

HARD CONSTRAINTS ON HOW YOU WORK:
- Do NOT dispatch sub-agents. No scripts/peer_agent.py, no claude/codex
  subprocess, no new worktree. You are the reviewer; review it yourself.
- Do NOT run the full suite. At most one or two test files.
- Budget ~12 minutes. Read the diff and the cited files and reason.
- Do NOT edit any file.

## Heads

- PR #4016 (part 1, base `main`): `84f63572f0b3707b20b6fe3949b7a97cbc1547d2` —
  UNCHANGED since you cleared it in round 2. Do not re-review unless part 2 broke
  something in it.
- PR #4017 (part 2, base = part 1): `9a516066` (`git diff 4cea8d91..HEAD`)

## The three round-2 blockers, and what I did

**§4 labelled-value redaction.** Replaced the regex with a scanner,
`_redact_labelled_values` in `scripts/redact_log_bundle.py`. The end of a value is
decided by its opening: a quoted value (plain, single, or backslash-escaped) ends at
its matching closing quote, so spaces/commas/brackets inside are consumed; a bare
value ends at whitespace or a structural delimiter, because an unquoted field cannot
contain one. A key with no separator and no `--` flag is prose, which restores
`authentication succeeded` / `authorization failed`. Attack: (a) a labelled value
that still escapes — nested or doubly-escaped quotes, a quote inside a quoted value,
CRLF, a value beginning with whitespace; (b) a case where the scanner now eats
evidence; (c) whether `password=a]b}c` leaving `]b}c` is acceptable, given I argue
consuming through `}`/`]` destroys every ordinary `k=v,k=v` line — I have documented
it as an accepted limit rather than fixed it, so say if that is wrong.

**A defect neither round caught, found by my own slow test.** The scanner was
QUADRATIC — unbounded leading `[A-Za-z0-9_.-]*` with no anchor, so `finditer` tried
every offset of a long identifier run. 1 KiB line: 27.85 ms, versus 0.028 ms short.
That is ~23 minutes for 50,000 records, i.e. the tier times out nightly and ships
nothing. Fixed with a width-1 lookbehind (`_KEY_START`, on the field form only,
because inside the key it rejected `--password`) plus a `{0,40}` bound: 0.118 ms,
236x. Attack: is the lookbehind + bound actually sound, or did I trade the blowup for
a missed key shape? A key longer than 40 characters either side, or one preceded by a
character I did not consider?

**§5 memory bound.** `JournalRead` is now a lazy reader (`lines()` generator +
`finish()`), and `collect_source` slides a byte-bounded tail over it, so memory is
bounded by `max_bytes` rather than by what the query matched. A mid-read failure is a
skipped tier. Attack: can the tail accounting drift from reality (the `while
kept_bytes > max_bytes and len(kept) > 1` guard, the oversized-single-record branch);
is `finish()` correct about rc and stderr after the generator is exhausted or
abandoned; can the child be left running.

**§3 retirement convergence.** A unit provided from a tree we do not own is now
MASKED (a `/dev/null` link under `SYSTEMD_DIR`), and `retired_unit_is_masked` is a
terminal state the gate accepts — checked first, or the mask link fails the
"no file of ours" test and loops. The mask is verified after issuing it. The
enablement-link search is narrowed to `*.wants/` and `*.requires/`. Attack: a state
that still fails to converge; whether masking is the right call at all versus leaving
a foreign unit alone; whether the extra `mask` loop is safely placed in the
transaction (it runs after the removals and the reload, while managed timers are
still paused).

Verified on Linux ext4 against the real `git archive` artifact: /run-provided masks
then converges with no repeat; a saved copy in a subdirectory is untouched; the four
earlier scenarios still pass.

## Your round-2 follow-ups, and where they went

- Stale comment describing the old byte-only gate: still there? I did not find one
  after the stamp rewrite — point me at the line if it survives.
- `MAX_LINE_CHARS` docstring inaccuracy: corrected, the limit list now says the
  opposite (redaction precedes truncation).
- Manual-interruption `/tmp` cleanup: NOT changed. I am treating your own note that
  `PrivateTmp=yes` narrows this to manual invocation as sufficient to defer it. Say
  if you disagree.
- Rate-limit calibration and the 1 GiB choice: left as documented-but-unvalidated.

## Return contract

Plain markdown. For §3, §4, §5, the quadratic fix, and each follow-up: `AGREE`,
`DISAGREE_EVIDENCE` (`path:line` + failure sequence), or `DISAGREE_CONCERN`.

Then `## Verdict`: `APPROVE`, `ADAPT`, or `REJECT`, with blockers separated from
notes. If you would still block, say plainly what the smallest correct change is,
because this goes to the founder rather than to another round.
