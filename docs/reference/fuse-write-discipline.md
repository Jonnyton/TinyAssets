# FUSE write & commit discipline (Cowork sessions)

Canonical reference for the two Cowork/FUSE stop-the-line rules. Pointer-loaded per
[ADR-002](../decisions/ADR-002-static-vs-dynamic-context-budget.md): `CLAUDE.md` keeps the
prohibitions themselves resident and points here for the recipes, hook coverage, and
escalation ladder.

**Applies to:** Cowork sessions, which mount this folder over FUSE. Native checkouts
(Claude Code on Windows/macOS/Linux, Codex, Cursor) are not affected by the truncation
or index-lock behavior described here.

---

## 1. Truncation rule — STOP-THE-LINE on recurrence

Cowork sessions mount this folder over FUSE, where the `Edit` and `Write`
tools silently truncate overwrites of existing files (chopping them
mid-line at the end of the buffer). The `Read` tool's cached view shows
the full file but on disk the tail is missing.

**Cowork rule (mandatory): for any file that already exists under this
repo, do NOT use `Edit` or `Write`.** Use one of:

```bash
# Option A — bash heredoc (good for inline content)
cat > "/full/path/to/file" << 'FILE_EOF'
... full file content ...
FILE_EOF

# Option B — fuse_safe_write.py (atomic temp+rename + size verify)
python3 scripts/fuse_safe_write.py --path /full/path/to/file --content-from /tmp/source.txt
```

Quote the heredoc delimiter so shell variable / backtick expansion stays
off. If your content contains the literal string `FILE_EOF`, pick a
different delimiter (e.g. `OUTER_EOF`).

**After every write, verify**: `wc -l <path>` plus `tail -5 <path>` to
confirm the file ends as expected. Do not move on until verified.

### Hook coverage (Claude Code only)

- `.claude/hooks/fuse_pre_write_reject.py` runs in PreToolUse for both
  `Write` and `Edit`. Rejects calls on existing FUSE-mount paths before
  they execute, with a heredoc/fuse_safe_write recipe.
- `.claude/hooks/fuse_write_truncation_guard.py` runs in PostToolUse for
  both `Write` and `Edit` as a backstop — compares on-disk size to sent
  content (Write) or verifies `new_string` substring presence (Edit),
  exits 2 with recovery instructions on truncation.

Cowork doesn't fire `.claude/settings.json` hooks, so Cowork sessions
follow the rule manually.

### Auto-iterate escalation ladder

**Host directive 2026-04-29 + reiterated 2026-05-02:** every truncation incident is a
stop-the-line event that must trigger a stronger preventive measure through skill +
hooks. The documented escalation ladder lives in `WebSite/HOOKS_FUSE_QUIRKS.md`. Current
rung (after 2026-05-02 status.py recurrence): PreToolUse REJECT hook +
`scripts/fuse_safe_write.py` Cowork wrapper + the rule made mandatory-not-advisory. If
recurrence happens again, the next rung is a SessionStart-printed banner that prints the
rule before the first user prompt is processed.

---

## 2. Git plumbing rule — STOP-THE-LINE on stale-index regressions

When committing via git plumbing on a FUSE-locked checkout (Cowork sessions
do this because regular `git add` + `git commit` race against FUSE locks),
**NEVER `cp .git/index $GIT_INDEX_FILE`**. The local `.git/index` reflects
whatever staged state was last in sync with origin, which can be many
commits behind. Building a tree from that copy regresses every file that
landed on origin since the local index timestamp.

**Mandatory pattern:**

```bash
# Use scripts/fuse_safe_commit.py — it does the safe pattern + scope verification.
python3 scripts/fuse_safe_commit.py \
    --base-ref origin/main \
    --file "REPO_PATH:CONTENT_PATH" \
    --message "commit message" \
    --max-files 1 \
    --update-ref .git/refs/heads/main
git push origin main
```

The wrapper:
- Builds a fresh `GIT_INDEX_FILE` (no `cp .git/index`).
- `git read-tree <base-ref>` from the canonical state.
- `hash-object` + `update-index --add --cacheinfo` for each declared file.
- Runs `git diff --stat <base-ref>..<new-commit>` and **REFUSES** to return
  the commit hash if file count exceeds `--max-files`.
- Optionally writes the resulting sha to a local ref via `--update-ref`.

If you must call git plumbing directly (rare — only when the wrapper's
shape doesn't fit), follow the same primitives: fresh temp index, no
`cp .git/index`, verify scope via `git diff --stat <parent>..<new>` BEFORE
pushing.

**Spec reference:** incident log at
`.agents/skills/loop-uptime-maintenance/incidents/2026-05-04-cowork-stale-index-regression.md`
(720-file regression on 66e7c6a, recovered to 631bae9, root cause was
`cp .git/index` pattern). Same kitchen-sink-diff failure mode that affects
auto-change writers — both share the structural vulnerability of capturing
state from "wherever the local checkout happens to be" instead of "the
known-good base ref."

> Note (2026-08-07): that incident-log path is currently absent from the working tree —
> the `loop-uptime-maintenance` skill directory shows as deleted-but-uncommitted. Restore
> it or repoint this reference before relying on the link.
