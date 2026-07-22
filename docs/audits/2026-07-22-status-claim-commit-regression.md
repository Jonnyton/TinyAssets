# A "+6 line STATUS claim" commit reverted four merged PRs

**Date:** 2026-07-22
**Commit:** `0bc841aa` — *"status: claim the four round-2 lanes before two sessions collide"*
**Author:** `cowork-agent`, 2026-07-21 22:28:02 -0700
**Class:** stale-index / stale-checkout regression (CLAUDE.md § *FUSE git plumbing rule*)
**Severity:** STOP-THE-LINE — recurrence of a documented class; reverted a safety guard
**Cross-family review:** Codex, verdict `adapt` (3 corrections, all folded in below)

---

## What happened

The commit intended one change: add four R2 lane claims to `STATUS.md`. It did
that. It also changed 15 files and removed 361 lines.

```
$ git show --stat --pretty=format: 0bc841aa | tail -1
 15 files changed, 11 insertions(+), 361 deletions(-)
```

## Root cause: a current parent pointer on a stale tree

The commit's **tree** is identical to `144eaba7` (#1501, 19:53:43) except for
`STATUS.md`. Its **parent pointer** is `a69dd70a` (#1519, 21:39:24).

```
$ git diff --stat 144eaba7 0bc841aa
 STATUS.md | 75 ++++++++++------------------------------------
 1 file changed, 34 insertions(+), 41 deletions(-)     <- exactly one file

$ git log -1 --pretty=%p 0bc841aa
a69dd70a                                                <- a *current* parent
```

That is the whole defect in two commands. The snapshot the tree was built from
was **2h34m19s old** at commit time, and **1h45m41s behind its own parent**.
Git records this as an ordinary commit — nothing in it says "revert" — but every
file that landed in the `144eaba7..a69dd70a` window was silently reset.

This is the pattern `CLAUDE.md` describes:

> **NEVER `cp .git/index $GIT_INDEX_FILE`**. The local `.git/index` reflects
> whatever staged state was last in sync with origin, which can be many commits
> behind. Building a tree from that copy regresses every file that landed on
> origin since the local index timestamp.

The author is a Cowork session — the exact session type that rule governs. Prior
incident: `.agents/skills/loop-uptime-maintenance/incidents/2026-05-04-cowork-stale-index-regression.md`
(720 files).

## Blast radius — four merged PRs, not two

```
$ git log --oneline 144eaba7..a69dd70a
a69dd70a  #1519  move seven brain scratch dumps off the repo root
0c3495a1  #1504  ui-test: merged is not deployed — verify the build under test
b6be48d4  #1532  PR #1506's two Codex verdicts — 10 of 11 items already landed
398b3256  #1506  STATUS.md janitor pass
```

Per Codex's correction: this reverted **changes from** four merged PRs, not all
four wholesale. #1506 was only *partially* reverted — its `STATUS.md` outcome
survived (the author hand-merged that one file, and the commit body says so),
while its `PLAN.md` and `.agents/activity.log` changes were lost.

Five distinct regressions resulted, all still standing on `origin/main`
(`f605bb99`) when this audit was written:

| # | Regression | From |
|---|---|---|
| a | `docs/audits/2026-07-22-pr1506-verdict-landedness.md` deleted (300 lines) | #1532 |
| b | `docs/audits/2026-05-03-brain-subsystems-deep-dive/README.md` deleted (46 lines) | #1519 |
| c | seven `BRAIN_*.txt` / `brain_*.txt` renamed back to the repo root (`R100`, exact reversal) | #1519 |
| d | `PLAN.md` lost the "Universe intelligence owns the user-facing control flow" Design Decision | #1506 |
| e | both `ui-test` SKILL.md mirrors lost the "Merged is not deployed" preflight | #1504 |

**(e) is the most serious.** That preflight is the operational enforcement of
AGENTS.md Hard Rule 14 — it stops a UI tester from filing findings against a
build that was never deployed. Reverting it removes a guard, silently, in a
commit whose message is about STATUS.md housekeeping.

### Blast radius beyond the repo

PR **#1534** has been stranded at `mergeStateStatus: DIRTY` since. Its only file
is the audit deleted in (a); the API reports it `modified` (+116/−49) against a
base branch that no longer has the file — a modify/delete conflict.

## The misleading part: the diff looks intentional

`git show --name-status` reports the seven moves as `R100` — pure renames — and
the two losses as `D`. Read without the parent-tree comparison, that is
indistinguishable from a deliberate reorganisation. Only comparing the tree
against ancestors reveals it as a snapshot artifact.

This is why the class survives review. A reviewer looking at the diff sees
plausible intent. The signature is only visible in the *shape of the history*.

## Why the existing guard did not stop it

Initial hypothesis — "`fuse_safe_commit.py`'s scope check is too weak" — was
**refuted** by the cross-family review, and the correction matters for the fix.

Codex verified that the wrapper *would* have caught this had it been used:

- `git read-tree a69dd70a` starts from the real parent, so stale content never
  enters the tree in the first place;
- the post-build check counts 15 paths against `--max-files 1` and raises
  `SafeCommitError`;
- even with a larger cap, the undeclared-path check rejects the other 14.

So the guard is not weak. **It was bypassed.** It is an opt-in local wrapper, and
nothing observes a commit made by any other route.

That flips the prescription. Strengthening `fuse_safe_commit.py` protects only
the sessions that already choose to use it — i.e. not the ones that cause this.
The ratchet has to run on commits that **already exist**, where tool choice
cannot skip it.

(Codex also noted a minor implementation nuance: `fuse_safe_commit.py` creates
the commit object *before* the scope check, leaving an unreachable object on
rejection. It does not return the sha or move the ref, so this is cosmetic —
noted, not filed.)

## The ratchet: `scripts/check_stale_base_commit.py`

Detects the signature directly, with no heuristic about messages or deletion
counts.

A healthy commit is **closest to its own parent**. A stale-tree commit is closest
to some **ancestor** of its parent — the snapshot it was really built from. So
for commit `C` with parent `P`, if any ancestor `A` satisfies
`|diff(A,C)| < |diff(P,C)|`, then `C` was built from `A` and reverts everything
in `A..P`.

On the real commit, with no prior knowledge:

```
$ python scripts/check_stale_base_commit.py --commit 0bc841aa
  STALE-BASE COMMIT: 0bc841aa  status: claim the four round-2 lanes ...
    parent            a69dd70a  -> 15 files differ
    real (stale) base 144eaba7  -> 1 files differ
    ... silently reverts the 4 commit(s) merged in between:
      - a69dd70a #1519 ... / 0c3495a1 #1504 ... / b6be48d4 #1532 ... / 398b3256 #1506 ...
Exit 2
```

It recovers the stale base, the 1-vs-15 signature, and all four reverted PRs.

**Why this shape over the alternative.** A "deletion count exceeds the message's
implied scope" heuristic was considered and rejected: it needs a threshold, it
cannot name the stale base or the lost commits, and it silently misses the
rename half of this incident (the seven `R100` moves delete nothing). The
ancestor-distance test is exact, threshold-free, and explains itself.

Deliberate reverts are the one legitimate case where a tree resembles an
ancestor more than its parent; those are recognised by `Revert "..."` /
`This reverts commit` and skipped. Merge commits are skipped — differing from
each parent by the other side's history is normal.

### Calibration — measured, not asserted

Swept 400 commits of real `main` history. It is a **triage signal, not a clean
oracle**, and the honest numbers are:

| Commit | Verdict | Notes |
|---|---|---|
| `0bc841aa` | **true positive** | this incident |
| `575c7059` | false positive → **fixed** | `revert(backfill): …` — a declared revert in conventional-commits form, which the first matcher (git's `Revert "…"` only) missed. Matcher extended; now exempt. |
| `5e50cc06` | **false positive — inherent** | deliberate approach swap: replaced the SPA-fallback route with a query-param route 7 min later, correctly deleting the superseded files. Confirmed genuine by the shared `package.json`: it kept the parent's `preview` line while removing only the `spa-fallback` build step — a stale tree would have reverted both. |

After the matcher fix: **2 flags / 400 commits (0.5%), 1 true positive.**

The `5e50cc06` mode is not fixable by shape. A commit that intentionally
supersedes the approach its parent introduced *does* legitimately resemble the
pre-approach ancestor. So supersession is an explicit opt-out — a
`Stale-base-check: intentional` trailer — rather than a guess. That keeps the
check a hard gate (this class is STOP-THE-LINE; a warning would be ignored)
while giving the rare legitimate case a documented, greppable escape hatch.

Also worth stating plainly: the sweep found this class **twice in 400 commits**
before triage, both from the same session type. Whatever the second turned out
to be, the first-pass rate is not "once in May, once in July".

**Verified:** fires on `0bc841aa` (exit 2, 0.58s); `575c7059` exempt after fix;
8/8 unit tests pass (`tests/test_check_stale_base_commit.py`, including a
red-green guard that the override trailer is *required* to exempt); `ruff` clean.

### Where it should run

1. **Pre-push hook** — cheapest feedback, catches it before it reaches `main`.
2. **CI on PRs** — the unbypassable layer; a local hook can be skipped with
   `--no-verify`, and this repo already runs `pr-scope-guard.yml` as precedent.

CI is the one that matters. Recommend wiring both, CI first.

## Recurrence ladder

| Date | Incident | Rung added |
|---|---|---|
| 2026-05-04 | 720-file Cowork regression | `fuse_safe_commit.py` + CLAUDE.md rule (opt-in, local) |
| 2026-07-22 | this — 15 files, 4 PRs, one safety guard | `check_stale_base_commit.py` on existing commits (unbypassable once in CI) |

The ladder's direction is the lesson: 2026-05-04 added a **better tool**, and the
next incident came from a session that did not use that tool. Rung 3, if there is
one, should not be a better tool either — it should be branch protection making
the CI check required.

## What was restored, and what was left alone

Restored on `claude/restore-0bc841aa-stale-index-regression`: (a)–(e) above, by
re-adding content from history — blobs verified byte-identical to the originals
(`301574e9`, `0f13ccf3`).

**Deliberately not reverted:** `0bc841aa`'s `STATUS.md` (+6). Those four R2 lane
claims are the commit's genuine intent. `git revert 0bc841aa` would have removed
them, so the restore is surgical rather than a wholesale revert.

## Note on the brief

The brief that opened this lane identified two regressions (#1519, #1532) and
stated the six modified-status files were legitimate changes to leave alone,
naming "the `ui-test` SKILL.md edits" specifically. Five of those six were
themselves reversions; only `STATUS.md` was a forward change. Had the brief been
followed as written, the `ui-test` safety guard (e) and the `PLAN.md` design
decision (d) would have stayed reverted.

Recorded because it generalises: *a brief describing a regression can itself
under-report the blast radius.* The instruction "leave the modified files alone"
encoded an assumption — that a file showing as `M` was edited on purpose — which
is exactly the assumption this bug class violates. Checking each `M` file against
the parent tree cost one command and found three more regressions.

This extends the `stale-backlog-rows-misdirect` pattern from STATUS rows and
task files to *incident briefs*: verify the premise against the repo, including
when the premise is a description of a bug you have already confirmed is real.
