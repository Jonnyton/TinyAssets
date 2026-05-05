# Incident — Cowork stale-index regression on 66e7c6a

Filed by Cowork-busyclever, 2026-05-04 ~00:35Z.
Skill: `.agents/skills/loop-uptime-maintenance/SKILL.md` (entry condition: substrate broken via own action; loop-side dispatcher healthy throughout but main-branch trees broke).

## What happened

Pushed commit `66e7c6a` ("activity.log: operating-model reframe + Wave-2 prep refactor + asks for Codex") at 2026-05-04T00:30Z. The commit was intended to add ~35 lines to `.agents/activity.log` and nothing else.

The commit actually **regressed 730 files / -81390 / +35** vs `1b2bf83`. It removed `workflow/auto_ship.py`, `workflow/auto_ship_ledger.py`, `workflow/api/auto_ship_actions.py`, `workflow/daemon_memory.py`, `workflow/daemon_registry.py`, `workflow/daemon_wiki.py`, `workflow/wiki/trigger_receipts.py`, `workflow/providers/diagnostics.py`, and 720+ other recent additions.

Detected ~5 minutes later while running the PR #229 confirm-test exemplar: `git ls-tree origin/main workflow/api/` returned no `auto_ship_actions.py`, despite earlier reads of the same file content from origin/main. Tracing showed my local `.git/index` was stale and the commit was built from THAT tree rather than from `1b2bf83`'s actual tree.

The deployed daemon was running pre-66e7c6a code (queue stayed healthy, supervisor warnings stayed clear, get_status kept returning auto_ship_health). No deploy ran from main between push and recovery. No real-world impact beyond risk window.

## How it happened

Used git plumbing for FUSE-locked commit:

```bash
export GIT_INDEX_FILE=/tmp/git_idx_$$
cp .git/index $GIT_INDEX_FILE       # ← BUG: copied a stale index
git update-index --add .agents/activity.log
TREE=$(git write-tree)
COMMIT=$(... git commit-tree $TREE -p $PARENT -F -)
```

The local `.git/index` reflected an out-of-date staged state from earlier in the session. Pulling fresh from origin updates pack files but does not refresh `.git/index` unless explicitly told to (e.g., `git read-tree origin/main`). My `cp .git/index` snapshotted a tree from when the local checkout was last in sync — many commits behind origin/main as of the push.

This is **the same kitchen-sink-diff failure mode** I diagnosed in Codex auto-change branches ~30 minutes earlier (`outputs/drafts/finding-auto-change-kitchen-sink-diff.md`). I named the exact failure ("each new auto-change branch picks up `main + writer's accumulated local working tree`") and then committed it myself within the hour. Embarrassing and instructive.

## Recovery

Built recovery commit `631bae9` using the **correct** plumbing pattern:

```bash
export GIT_INDEX_FILE=/tmp/git_idx_recover_$$  # fresh, not copied
git read-tree 1b2bf83                          # fresh tree from KNOWN GOOD ref
BLOB=$(git hash-object -w /tmp/recovery_activity.log)  # the good activity.log only
git update-index --add --cacheinfo 100644,$BLOB,.agents/activity.log
TREE=$(git write-tree)
COMMIT=$(... git commit-tree $TREE -p 1b2bf83 -F -)
```

Force-pushed `631bae9` over `66e7c6a`. Verified: `git diff --stat 1b2bf83..631bae9` shows only `.agents/activity.log | 35 +++++++++++++++++++++++++++++++++++` — exactly the intended diff.

## Four reflection questions per skill

**1. How did the loop break this time?**
Local stale `.git/index` polluted a commit built via plumbing. The commit looked successful (no errors, push succeeded) but contained a 730-file regression masquerading as a 35-line addition.

**2. How can the loop notice this break next time, automatically?**
Pre-push hook (or commit-tree wrapper) that compares the resulting tree against `origin/main` and rejects if any file count delta exceeds N% (e.g., >10 files removed for what should be a 1-file commit). PostToolUse hook on git-push for FUSE-mount paths could enforce this.

**3. How can the loop fix this break next time, automatically?**
The recovery pattern (`git read-tree origin/main` from FRESH index, then add the intended single file) is the correct primitive. Wrap it in a `scripts/fuse_safe_commit.py` helper that takes (target_branch_ref, file_path, content_path) → commit_hash. Cowork sessions ALWAYS use this helper instead of raw plumbing. Same shape as `scripts/fuse_safe_write.py`.

**4. How can the loop avoid this break in the first place next time?**
Two layers:
- **Cowork rule update**: never `cp .git/index $GIT_INDEX_FILE`. Always `git read-tree <ref>` from the known-good base. CLAUDE.md update.
- **Discipline**: every git plumbing commit MUST be followed by `git diff --stat <parent>..<new>` verification before pushing. If the diff exceeds intended scope, abort.

## Meta-recursion observation

I diagnosed the kitchen-sink-diff pattern in auto-change branches at 00:25Z and named it as a substrate gap worth filing. At 00:30Z I triggered the same failure mode through my own commit plumbing. This is not coincidence — both share a root cause: **operations that capture state from "wherever the local checkout happens to be right now" instead of "the known-good base ref" pollute the resulting commit with whatever drift has accumulated.**

Codex auto-change writers and Cowork manual plumbing have the same structural vulnerability. The substrate fix proposed for auto-change writers (branch fresh from main, scope diff to issue) applies verbatim to Cowork's plumbing helpers.

## Substrate improvements named

1. **`scripts/fuse_safe_commit.py`** — wrapper that always builds from fresh `git read-tree <ref>`, never from `cp .git/index`. Verifies `git diff --stat <parent>..<new>` matches expected file count before producing the commit hash. Same shape + safety stance as `fuse_safe_write.py`.
2. **CLAUDE.md addition** — explicit rule: "for FUSE-locked git commits, NEVER copy `.git/index`; always `git read-tree <known-good-ref>` first; verify diff stat matches scope before pushing."
3. **Cowork session-start ritual addition** — when starting work that may involve git plumbing, run `git fetch origin && git read-tree origin/main` to refresh local index from canonical base. Same shape as the `claim_check.py + worktree_status.py` ritual.

## Connection to PLAN.md § Uptime And Alarm Path

Same shape as auto-change kitchen-sink: a layer-1.5 watchdog (commit-time diff scope check) catches whichever agent (loop, Cowork, Codex, future community) makes this mistake next. Proposed `fuse_safe_commit.py` is the substrate; CLAUDE.md rule is the discipline.

## Status

**Resolved at 2026-05-04T00:36Z**. Origin/main at 631bae9. All files restored. Activity.log entry preserved. Codex notified via this incident log + activity.log entry pointing here. Skill usage count: +1.
