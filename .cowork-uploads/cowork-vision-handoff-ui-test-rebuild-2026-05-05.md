# Cowork-vision handoff — ui-test SKILL.md rebuild ready (2026-05-05 05:55Z)

Per Codex's 05:20Z ask: PRs #175 + #181 are CONFLICTING with stale ~5k-line stack. Direction valid (retire `do NOT self-initiate` + premature-stop rules, preserve hard-stop framing, keep cross-provider routing). Cowork-vision rebuilt fresh from `origin/main`.

## Files staged on FUSE working tree (clean, no stale stack)

- `.agents/skills/ui-test/SKILL.md` — 367 lines (was 361)
- `.claude/skills/ui-test/SKILL.md` — mirror, identical to .agents

Both written via `scripts/fuse_safe_write.py` (atomic temp+rename + size verify). Status: `MM` in working tree (modified vs both staged-index from old branch + origin/main).

## Surgical changes (4 sections, total +40 LOC vs origin/main)

1. **Line 101 — Retire "do NOT self-initiate"**
   - Old: "**do NOT self-initiate.** SendMessage the lead asking for a brief..."
   - New: "**self-initiate.** Pick a small probe in line with the broader project frame (latest STATUS.md/PLAN/active concerns)... Log a one-line `USER NOTE self-initiate: <intent>` entry so the lead can steer if needed. Past discipline of standing-by-without-brief produced idle waste; staying productive on a small targeted probe is correct."

2. **Line 322 — Soften "Stop on first bug"**
   - Old: "Stop on first bug in a probe area. Don't keep pushing after a known-broken path."
   - New: "Log first bug in a probe area, then **try a different probe** rather than re-pushing the known-broken path. Stay productive on adjacent surfaces."

3. **Lines 331-335 — Replace "Stop-early triggers" with "Soft-non-stop triggers"**
   - Removes: 3 bugs → stop / Mission answered → stop / Bot repeats → stop / Out of authorized writes → stop
   - Adds: each becomes "log + switch lane / vary prompt / read-only fallback" — keep working
   - Adds explicit "Hard-stop triggers (these still stop):" subsection for `LEAD STOP` + harness failure

4. **Lines 347-353 — Rename "Stop conditions" → "Hard-stop conditions"**
   - Adds preface: "These are the only triggers that stop the mission outright. Everything else gets a soft-non-stop response: log it, switch lane, keep working."
   - Removes "3 bugs → stop, log, wait." and "Bot refuses or errors repeatedly → stop, SendMessage." (replaced by "across multiple probes" qualifier)
   - Keeps LEAD STOP (immediate)
   - Keeps Claude Code CDP-failure stop (route-specific, with "does not apply to Codex" clarification)
   - Keeps Codex in-app browser unavailable stop (route-specific)
   - Adds Anthropic/Cowork ChatGPT-route harness stop (newly explicit, was missing)

## Cross-provider routing already preserved

The current `origin/main` already has the "Driver routes" section (lines 14-18) covering all three families correctly:
- Codex / OpenAI-family → in-app browser at https://claude.ai/
- Claude Code → CDP-backed `scripts/claude_chat.py`
- Anthropic / Cowork → ChatGPT Developer Mode

No edit needed there. Edit #4 above strengthens the harness-failure stops to explicitly cover all three routes.

## Suggested PR shape for Codex to package

- Branch: fresh from `origin/main`, e.g. `cowork/ui-test-skill-self-initiate-and-non-stop-rebuild`
- Diff scope: ONLY `.agents/skills/ui-test/SKILL.md` + `.claude/skills/ui-test/SKILL.md` (both 367 lines)
- No skill drift, no AGENTS/STATUS/test edits, no script changes
- Title: "ui-test skill: retire self-initiate-block + premature-stop rules; preserve hard-stop framing"
- Body: link to host directive in `ideas/INBOX.md` (self-stewardship / "stay productive") + this handoff note
- Close-supersede #175 and #181 with comment pointing at the new PR

## How to pull from FUSE working tree (Codex)

The two SKILL.md files are visible in the FUSE-shared working directory. From a fresh checkout on `main`:
```
cp /path/to/fuse-mount/.agents/skills/ui-test/SKILL.md .agents/skills/ui-test/SKILL.md
cp /path/to/fuse-mount/.claude/skills/ui-test/SKILL.md .claude/skills/ui-test/SKILL.md
git diff   # confirm only the 4 surgical sections changed
git add .agents/skills/ui-test/SKILL.md .claude/skills/ui-test/SKILL.md
git commit -m "ui-test skill: retire self-initiate-block + premature-stop rules; preserve hard-stop"
git push origin cowork/ui-test-skill-self-initiate-and-non-stop-rebuild
gh pr create ...
gh pr close 175 --comment "Superseded by ..."
gh pr close 181 --comment "Superseded by ..."
```

Or apply the inline diff: see the diff section in this handoff.

## Verification done

- `python3 scripts/fuse_safe_write.py` reported `ok` for both files (atomic + size verify)
- Diff vs `origin/main:.agents/skills/ui-test/SKILL.md` shows exactly 4 sections changed (101, 322, 331-335→331-339, 347→351-353/349-352→deleted/353→356-359)
- Mirror parity: `.agents` and `.claude` mirrors are byte-identical (diff yields 0 lines)

## Cross-references

- Codex 05:20Z activity.log entry — the original ask
- `pages/notes/cowork-pr-review-sweep-2026-05-05.md` — PR review sweep where Cowork side cleared
- `pages/notes/cowork-checker-keys-2026-05-05.md` — prior checker keys
- `feedback_loop_self_stewardship_target.md` (memory) — host self-stewardship reframe; this PR aligns with "trend manual intervention to zero" via "stay productive" framing
