---
name: auto-iterate
description: Improves recurring agent behavior — ratchets prevention when an agent repeats a mistake, and tunes agent-team definitions. Use when you fix a behavioral failure that could recur (bad default, missed convention, recurring pattern), when a guard/hook fires, or when a teammate underperforms or roles overlap.
---

# Auto-iterate (improving agent behavior through use)

Agent behavior improves through use, not upfront planning. Two modes: **ratchet**
a recurring behavioral failure into a stronger guard, and **tune** agent-team
definitions when a teammate underperforms.

---

## Mode A — The prevention ratchet

Some failures aren't one-off code bugs — they're patterns of agent behavior that
recur in future sessions unless something changes (e.g. FUSE truncation: Edit/
Write silently chop overwrites; cross-provider drift: conventions added to
CLAUDE.md instead of AGENTS.md so Codex/Cursor miss them). Each lived recurrence
has produced a stronger preventive layer in turn. This skill formalizes that shape
so it's applied deliberately, not after the next surprise.

**Invoke when:** you fixed something you (or a past session) had already fixed
before · the user redirects you on something you "should have known" · a guard/
hook/check fails (the failure is data, even after you fix the immediate issue) ·
you're about to write "future sessions should…" (a soft layer — ask if a hard one
is warranted) · two similar incidents reached two different fixes (consolidate).
**Not for** one-shot feature-branch bugs — use `debugging-and-error-recovery`.
Product/runtime recurrences belong first in a failure protocol (signature → root
cause → verified fix → proactive check); use this skill when the recurring pattern
is agents making the same bad *choice*.

**The ratchet — each rung stronger than the last, apply on recurrence:**

```
1  Fix the symptom in place; note it in the relevant doc for this PR's reviewer.
2  Write the rule explicitly in the canonical cross-provider place (AGENTS.md);
   reference it from any provider-specific file that mentioned it.
3  Build a runnable check in scripts/ — any provider can invoke it; exit non-zero
   on the pattern with a fix prescription in the message.
4  Wire it as a PostToolUse / pre-write / pre-edit hook in .claude/hooks/ (+
   .claude/settings.json) so Claude Code can't miss it; other providers invoke the
   script per the AGENTS.md convention.
5  Move it to a pre-commit / CI gate so the failure can't land silently.
```

Don't ratchet without recurrence (premature guards are noise). Don't make checks
probabilistic — define the pattern precisely. Every check needs a documented
opt-out marker (`[harness-specific]`, `# noqa: <rule>`) in both the script source
and its error message. Don't bury a check — document the runnable command in
AGENTS.md and wire the hook.

**Artifacts when you ratchet:** a `scripts/<name>.py` (stdlib-only, exit 0 pass /
2 fail, stderr = fix prescription); a `.claude/hooks/<name>_guard.py` wrapper
wired into the right matcher; a paragraph in AGENTS.md (script, command, failure
mode, opt-out); a rung entry in the relevant subsystem ladder doc; a line in
STATUS.md/runbook. **Prescription style:** quote the offense exactly (file/line/
text), name the violated convention in plain language, and give two paths —
(A) the canonical fix, (B) the verbatim opt-out marker for legitimate exceptions.

---

## Mode B — Tuning agent-team definitions

When a teammate underperforms, roles overlap, or the launch prompt needs tuning.
Definitions evolve through use. **Don't enumerate the roster here** — read it fresh
each time from `.claude/agents/*.md`; `CLAUDE_LEAD_OPS.md` is the source of truth for
lead/team norms and wins on conflict. Research current best practices first (pin
the Claude Code agent-teams + sub-agents docs — norms shift release-to-release;
don't write from memory).

**Per-agent rubric** (use each agent's own stated job, not assumed role shapes):
mandate clarity (owns vs consults vs ignores) · responsiveness (went silent? did
respawn fix it?) · evidence discipline (evidence proportional to claims) ·
hand-off shape (clean inputs/outputs to adjacent roles) · standing-team behavior
(idles correctly, self-claims when free) · earning its keep (could a stronger
model absorb it?). **Team-level:** coverage gaps (work that fell between or got
duplicated) and composition (add/combine/retire — 3–5 teammates is the sweet
spot). **Harness alignment:** verify against docs whether idle/task hooks,
plan-approval gates, tool allowlists (don't assume per-teammate `permissionMode`
is enforced), task sizing, and `message` vs `broadcast` are used deliberately.

**How to iterate:** good behavior → record what worked in `.agents/activity.log`,
don't change it; poor behavior → fix *that agent's* prompt (or `CLAUDE_LEAD_OPS.md`
for a team norm); general fixes → AGENTS.md or this rubric; team-shape changes →
`CLAUDE_LEAD_OPS.md` only. After 2 unanswered messages, respawn with a sharper
prompt. After editing skills, run `scripts/sync-skills.ps1`.

## Cross-references

`debugging-and-error-recovery` (one-shot code bugs) · `skill-authoring` (when the
fix is a skill change). FUSE ladder: `WebSite/HOOKS_FUSE_QUIRKS.md`. Drift ladder:
AGENTS.md § *Where new conventions live*.
