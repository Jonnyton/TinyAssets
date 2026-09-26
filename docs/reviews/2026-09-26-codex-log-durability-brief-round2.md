ROUND 2. You reviewed this stack earlier today and returned ADAPT with five
blocking items; your report is at `output/codex-log-durability-review.md`. I acted
on all of them. Your job now is to check the FIXES, and specifically to find where
a fix is incomplete, wrong, or created a new problem. Do not re-litigate what you
already agreed with.

HARD CONSTRAINTS ON HOW YOU WORK:
- Do NOT dispatch sub-agents. No scripts/peer_agent.py, no claude/codex
  subprocess, no new worktree. You are the reviewer; review it yourself.
- Do NOT run the full suite. At most one or two test files.
- Budget ~12 minutes. Read the diff and the cited files and reason.
- Do NOT edit any file.

## Heads

- PR #4016 (part 1, base `main`): `84f63572f0b3707b20b6fe3949b7a97cbc1547d2`
- PR #4017 (part 2, base = part 1): `4cea8d911524e6600365f0305a5eaf7c39facfa3`

```
git log --oneline 31a1776c..4cea8d91
git diff e9141910..84f63572    # part 1 fixes
git diff 4f71acda..4cea8d91    # part 2 fixes
```

## What I changed, and what to attack

**§4 redaction.** Rewrote the labelled-value rule in
`scripts/redact_log_bundle.py`: quotes may now be plain, backslash-escaped, or
absent on both sides of the key; the value terminator no longer stops at a comma;
the `\b` before `sk-` is gone; argv style (`--password v`) is covered. I reproduced
all four of your leaks before and after. Attack: (a) find a NEW leak, especially one
created by the wider terminator; (b) find a case where the wider match now EATS
legitimate log content (over-redaction is the new risk and there is a test for it);
(c) check `test_covers_the_canonical_secret_shapes` now asserts the secret VALUE is
absent rather than that the line changed. The limits I accepted rather than fixed
(unlabelled high-entropy blob, secret split across records, value past
MAX_LINE_CHARS) are written into the module docstring — tell me if any of those is
actually tractable and I ducked it.

**§5 ordering and bounds.** The logs tier moved from section 4b to 5b in
`deploy/backup.sh`, i.e. AFTER the state tiers ship to GitHub, so it can no longer
spend the unit's 30-minute budget before the brain tier is offsite.
`scripts/backup_log_tier.py` now passes `--lines` (bounding what journalctl emits,
hence memory) and a per-source `timeout` well inside the unit's, and a
`TimeoutExpired` is a skipped tier. Truncation now keeps the NEWEST lines in
chronological order. Attack: is the new order actually safe for every failure path;
can the tier still leave a stale `/tmp` archive on interruption (you raised this and
I have NOT changed the trap — tell me if that still blocks); is `--lines` the right
bound given `--since` is also present.

**§2 journald policy could be permanently unapplied.** New applied-stamp:
`${RUNTIME_ROOT}/.journald-applied` holds the SHA-256 of the drop-in journald
actually loaded, written only after a successful restart, removed when a restart
fails, and required by `current_release_is_exact` via `journald_applied`. Attack:
find a sequence where the stamp says applied and journald is not running that
policy, or where the installer now loops, or where the stamp's own failure mode is
worse than the bug it fixes. Note it lives under the runtime root, not in
journald.conf.d.

**§7 retention honesty and rate limiting.** The drop-in no longer claims
`MaxRetentionSec` guarantees a window; it states "at most 14 days, and at most
1 GiB, whichever runs out first" and names the knob. Rate limiting is no longer
disabled: `RateLimitIntervalSec=30s` / `RateLimitBurst=100000`. Attack: is that
ceiling actually generous enough not to drop this daemon's normal output, and finite
enough to matter; and is 1 GiB still the wrong number given the nightly tier asks
for 3 days.

**§3 retirement.** One `retired_unit_is_gone` predicate used by both the gate and
the transaction, checking the unit file (with `-L` separately, for dangling links),
any `*.wants/` / `*.requires/` link naming the unit anywhere under the systemd tree,
and systemd's `LoadState`. Removal deletes the links and ends with a
`daemon-reload`. Attack: a state still escaping; whether the `find` can match
something it should not; whether the extra `daemon-reload` placement is safe inside
this transaction.

**§6 pruner ownership.** The logs tier is pinned to the exact generated grammar in
both pruners — `scripts/backup_prune.py` TIER_PATTERNS and a new named
`is_prunable_tag` in `scripts/backup_ship_gh.py` — and the runbook's manual bundle
is renamed to the `tinyassets-manual-logs-` prefix, outside every pruned prefix. I
deliberately did NOT tighten the data/brain patterns. Attack: does the generated
name still get pruned (a fix that creates an unbounded hoard is not a fix); does
`is_prunable_tag` change state-tier behaviour; is leaving the looser patterns alone
defensible.

**Your closing note on `docker logs`.** You were right that I could not assert it.
I could not re-verify it either (no local Docker daemon), so the claim is WITHDRAWN
in the installer comment, DEPLOY.md, the runbook and a test comment, with the
withdrawal recorded in the runbook. Attack: is the surviving justification for
retiring ship-logs sufficient on its own?

## Return contract

Plain markdown. For each of §2 §3 §4 §5 §6 §7 and the `docker logs` note, exactly
one of `AGREE` (fix is complete), `DISAGREE_EVIDENCE` (`path:line` plus the concrete
failure sequence), or `DISAGREE_CONCERN` (a risk you cannot prove).

Then `## Verdict`: `APPROVE`, `ADAPT` (list what still blocks), or `REJECT`. Keep
what BLOCKS landing separate from notes. This is round 2 of a 3-round cap, so be
explicit about which findings are genuinely landing-blockers and which you would
accept as follow-ups.
