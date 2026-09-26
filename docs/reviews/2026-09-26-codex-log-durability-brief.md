You are reviewing a two-PR stack in THIS checkout (a git worktree). Your job is to
REFUTE it, not to summarise it. I wrote it; I want the things I got wrong.

HARD CONSTRAINTS ON HOW YOU WORK:
- Do NOT dispatch sub-agents. No scripts/peer_agent.py, no claude/codex
  subprocess, no new worktree. You are the reviewer; review it yourself.
- Do NOT run the full suite. No scripts/ci_required_tests.py, no
  `pytest -m "not slow"`. Run at most the one or two test files you need.
- Budget ~12 minutes. Read the diff and the cited files and reason.
- Do NOT edit any file. Review only.

## What to review

Two stacked commits plus one test commit, all present in this worktree:

- `98f1b2e5` + `e9141910` = PR #4016 (part 1, base `main`)
- `20adf894` + `f79a7fda` = PR #4017 (part 2, base = part 1's branch)

Useful commands:

```
git log --oneline 31a1776c..HEAD
git diff 31a1776c..e9141910     # part 1 only
git diff e9141910..HEAD         # part 2 only
```

## The problem being fixed

The daemon's container output existed only in a container-scoped Docker log, so
every deploy that recreated a container erased it; on 2026-09-26 a latency
investigation lost the evidence it needed. The chain is:

```
daemon/cloudflared/slack-agent stdout
  -> Docker fluentd driver (async) -> tinyassets-logs (Vector sidecar)
  -> Vector console sink (its own stdout) -> ??? -> durable?
```

Part 1 points the `logs` container at `driver: journald` with `tag:
tinyassets-logs`, adds `deploy/journald-tinyassets.conf` (retention drop-in the
host-uptime installer converges), and makes `deploy/deploy_fail_safe.sh`'s compose
validator refuse a bundle that loses the driver or the tag.

Part 2 adds a third `deploy/backup.sh` tier that queries the journal, redacts it
(`scripts/redact_log_bundle.py`), and ships `tinyassets-logs-<TS>.tar.gz` to the
existing private GitHub release repo; retires `tinyassets-ship-logs` (deleted
files + host-side removal via `RETIRED_UNITS` in
`deploy/install-host-uptime-services.sh`); extends both retention pruners.

## Claims I most want attacked

Attack these specifically. For each, either refute it with a code citation or say
it holds.

1. **Durability.** Does `journalctl CONTAINER_NAME=tinyassets-logs` actually read
   across PAST container generations, given Docker's journald driver? Is there a
   case where the tag or CONTAINER_NAME is absent or differs, so the query I put
   in the runbook returns nothing? Note `network_mode: host` on cloudflared and
   that `slack-agent` is behind a profile.
2. **Part 1 must be safe to deploy ALONE.** A previous split (#3975/#3978) broke a
   deploy because a part-1 host guard needed part 2. Find any guard, gate or
   assertion that part 1 introduces which cannot be satisfied until part 2 lands,
   or which changes behaviour on a droplet whose current state lacks part 2. I
   claim the validator and the compose it validates always travel together because
   `deploy-prod.yml` scps `deploy/deploy_fail_safe.sh` from the PR checkout to
   /tmp and runs that copy — verify that, and verify the installer converges with
   part 1 alone.
3. **Retirement correctness.** `current_release_is_exact()` returns 0 and exits
   BEFORE the first mutation on a converged host. I added a `RETIRED_UNITS` check
   inside that gate so the removal happens at all. Is there a state where a retired
   unit survives forever, or where the gate now never converges (install loops), or
   where `disable --now` on a `not-found`/`masked` unit aborts the transaction? Is
   not rolling back the retirement on failure defensible?
4. **Redaction bypass.** `scripts/redact_log_bundle.py` is claimed to be a strict
   SUPERSET of `tinyassets/workspace_git.scrub_text` and
   `tinyassets/providers/codex_provider._SECRET_SHAPES`, enforced by
   `tests/test_backup_log_tier.py::test_covers_the_canonical_secret_shapes`. Find a
   credential shape the daemon plausibly logs that reaches the shipped tarball
   anyway. Consider: a secret split across two lines, a secret inside a JSON blob
   on one very long line near MAX_LINE_CHARS truncation, base64 of a secret, a
   `--password foo` argv style, and the `KEY=value` rule's terminator set
   `[^\s,;&"']+`.
5. **The logs tier must never harm the backup.** `deploy/backup.sh` section 4b runs
   before the GH ship. Can it abort the run, corrupt a state tier, leave a stale
   `/tmp` tarball, or make `set -euo pipefail` exit early? I read `PIPESTATUS[0]`
   after a pipeline under `set +e` — is that correct here?
6. **Retention arithmetic.** GitHub-release retention is one pool across prefixes,
   so I raised `DEFAULT_RETAIN` 30 -> 45 for three tiers. Check that is right and
   that neither pruner can now delete a name it does not own
   (`scripts/backup_prune.py` TIER_PATTERNS, `scripts/backup_ship_gh.py`
   PRUNABLE_TAG_PREFIXES).
7. **journald sizing on a real droplet.** `SystemMaxUse=1G`, `SystemKeepFree=2G`,
   `MaxRetentionSec=14day`, and rate limiting DISABLED
   (`RateLimitIntervalSec=0`/`RateLimitBurst=0`) on a box whose disk is already
   watched by `scripts/disk_watch.py`. Is disabling the rate limiter safe with a
   chatty container, or did I trade an outage for evidence? Is 1G reachable in a
   way that silently shortens the 14-day window the nightly tier depends on?
8. **Known gap, filed as `docs/concerns/2026-09-26-fluentd-driver-drops-while-vector-is-down.md`.**
   I did NOT close it. Tell me if my reason is wrong: that Vector's `journald`
   source shells out to a `journalctl` binary absent from the pinned
   `timberio/vector:0.40.0-alpine` image.

## Return contract

Plain markdown. For each numbered claim above, exactly one of:

- `AGREE` — with one line on what you checked.
- `DISAGREE_EVIDENCE` — a code citation (`path:line`) and the concrete failure
  sequence.
- `DISAGREE_CONCERN` — a risk you cannot prove, stated as a risk.

Then a `## Verdict` section: `APPROVE`, `ADAPT` (land after specific fixes, list
them), or `REJECT` (wrong shape, say what the right one is). Separate anything that
BLOCKS landing from anything that is a note. Be blunt; do not soften findings.
