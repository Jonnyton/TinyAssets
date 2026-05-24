# FUSE Mount Quirks — Notes for future sessions

The Cowork sandbox mounts the Windows project folder over FUSE. The Edit
and Write tools both silently truncate file overwrites on this mount.
Only **bash heredoc** OR `scripts/fuse_safe_write.py` are reliable.

## STANDING RULE — both Edit and Write can truncate

Every truncation incident triggers a stronger preventive measure. The
current rule:

**For any file that already exists anywhere under the FUSE mount, do
not use the `Edit` or `Write` tools. Use bash heredoc OR
`scripts/fuse_safe_write.py`.**

```bash
# Option A — heredoc (good for inline content)
cat > "/full/path/to/file" << 'FILE_EOF'
... full file content ...
FILE_EOF

# Option B — fuse_safe_write.py (atomic temp+rename + size verify)
python3 scripts/fuse_safe_write.py --path /full/path/to/file --content-from /tmp/source.txt
```

Quote the heredoc delimiter so shell variable / backtick expansion stays
off. After every write, **verify integrity**: `wc -l <path>` plus
`tail -5 <path>` to confirm the file ends as expected.

If a single heredoc would clash with content (literal `FILE_EOF` inside),
pick a different delimiter (e.g. `OUTER_EOF`, `RAW_EOF`).

New files (file did not previously exist) are usually fine via Write.
But once a file has been written, treat all subsequent overwrites or
edits as heredoc-only or fuse_safe_write-only.

## Hook coverage

`.claude/hooks/fuse_write_truncation_guard.py` runs in **PostToolUse**
for both `Write` and `Edit`:

* **Write**: compares on-disk size to the size of the content sent. If
  they differ by more than 32 bytes, exits 2 with a clear message
  prompting a heredoc retry.
* **Edit**: reads the file and verifies that the supplied `new_string`
  is present as a contiguous substring. If only a prefix is present
  (the FUSE truncation chops the tail), reports how many characters
  survived and exits 2.

`.claude/hooks/fuse_pre_write_reject.py` runs in **PreToolUse** for
both `Write` and `Edit`. If the target path exists AND is under the
FUSE mount, the hook rejects the call before it runs and prints the
heredoc/fuse_safe_write recipe. This is the rung added 2026-05-02 after
the next recurrence on `workflow/api/status.py`.

Wired into `.claude/settings.json` under `hooks.PreToolUse[matcher="Write"]`
plus `[matcher="Edit"]` (PreToolUse) and `hooks.PostToolUse[...]` (PostToolUse).

The hook only fires inside Claude Code (which honors `.claude/settings.json`).
**Cowork agents do not get the hook** — they have to follow the standing
rule manually plus use `scripts/fuse_safe_write.py` when bash heredoc is
awkward (binary content, CRLF preservation, very large files, content that
would clash with delimiter).

The rule is repeated in:

- `Workflow/CLAUDE.md` (under "FUSE truncation rule")
- `WebSite/HOOKS_FUSE_QUIRKS.md` (this file)
- `.agents/skills/auto-iterate/SKILL.md` (canonical example)
- agent memory: `feedback_fuse_truncation.md`

## Why "auto-iterate" matters

User directive (2026-04-29 + reiterated 2026-05-02): "truncation should
never happen in the first place, each time it does we auto reiterate to
it never happening." And on 2026-05-02 after the status.py recurrence:
"this truncation issue needs to be solved and reiterated upon over and
over every time it happens through the skill and hooks."

So every recurrence is a signal that the prevention layer is too weak
and should be hardened immediately:

| #  | Incident                                  | Iteration                                                                                  |
|----|-------------------------------------------|--------------------------------------------------------------------------------------------|
| 1  | First mcp-snapshot.json truncate          | atomic temp+rename in snapshot script                                                      |
| 2  | package.json + ChatDemo truncate          | initial PostToolUse Write hook                                                             |
| 3  | graph/+page.svelte Edit truncate          | hook now also matches Edit + Edit-mode substring check + standing rule documented in CLAUDE.md |
| 4  | workflow/api/status.py Edit truncate (2026-05-02 Cowork session, mid-PR for get_status.supervisor_liveness) | PreToolUse REJECT hook for Edit/Write on any FUSE path + `scripts/fuse_safe_write.py` Cowork-callable wrapper + reiterate-on-recurrence directive added to CLAUDE.md so Cowork sessions catch the standing rule on session start |

If it happens again the next iteration is:
**A startup-banner block in CLAUDE.md / a SessionStart hook that prints
the FUSE rule before the first user prompt is processed**, so Cowork
sessions see the rule even if they skim CLAUDE.md.

## Other quirk: `node_modules/.bin/` symlinks don't materialize

`npm install` succeeds but `node_modules/.bin/` is missing executable
shims, so `npm run dev` errors with "vite: not found".

**Workaround:** invoke binaries via `npx` or directly via
`node node_modules/<pkg>/bin/<name>.js`. Better: run the build on the
Windows host (where the FUSE quirk doesn't exist) — that's what the
GitHub Actions deploy job does anyway.
