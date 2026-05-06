---
name: auto-iterate
description: Ratchets prevention every time an agent (you, a teammate, a future session) makes the same behavioral mistake twice. Use when you fix a behavioral failure — a bad heuristic, a bad default, a missed convention, a recurring bug pattern, or a "you should have known better" moment. Each recurrence must add a stronger preventive layer (doc → script → hook → gate) so the failure cannot recur silently.
---

# Auto-iterate (prevention ratchet)

## What this is

Some failures are not one-off bugs in the code — they're patterns of agent
behavior that will recur in future sessions if nothing changes. Two examples
this repo has lived through:

- **FUSE truncation:** Cowork's Edit/Write silently chop file overwrites.
  An agent writes, gets a "success" response, moves on, and the file is
  truncated mid-line. Each recurrence has produced a stronger preventive
  layer in turn (atomic temp+rename → PostToolUse hook on Write → hook also
  matches Edit → standing rule in CLAUDE.md/AGENTS.md/memory). See
  `WebSite/HOOKS_FUSE_QUIRKS.md` for the documented ladder.

- **Cross-provider drift:** Project-level conventions get added to
  `CLAUDE.md` or agent memory instead of `AGENTS.md`. Future Codex/Cursor
  sessions miss the convention. The 1st occurrence was caught by the user
  manually; the 2nd added an explicit rule to `AGENTS.md`; the 3rd built
  `scripts/check_cross_provider_drift.py`; the 4th wired it as a Claude
  Code PostToolUse hook. The ladder is documented in `AGENTS.md` §
  *Where new conventions live*.

The shape is identical. **This skill formalizes the shape so we apply it
deliberately, not after the next surprise.**

## When to invoke

Reach for this skill when **any** of these is true:

- You just fixed a problem that you — or a previous agent — had already
  fixed before in a different session, and might have to fix again.
- The user redirects you on something that "feels like" you should have
  known. ("You shouldn't have needed to be reminded of X.")
- A guard, hook, or check fails. Even if you fix the immediate issue,
  the failure is data — invoke this skill to decide whether to ratchet.
- You're about to write a doc/rule that says "future sessions should…"
  — that's a soft prevention layer; ask whether a hard one (script,
  hook) is warranted instead.
- Two similar incidents reach two different fixes. That divergence is
  the signal to consolidate behind a hook.

**Not for:** one-shot code bugs in a feature branch. Use
`debugging-and-error-recovery` for those. Use `auto-iterate` only when
the failure is about *agent behavior* — something a future session
could repeat.

## Relationship to failure protocols

Some recurring failures are product/runtime patterns, not agent-behavior
patterns. Those belong first in a living failure protocol: an error signature,
root cause, verified fix, and optional proactive check. Promote those into
tests, probes, validators, or specialist skill checklists.

Use this skill when the recurring pattern is that agents keep making the same
bad choice: skipping the protocol, ignoring the check, inventing APIs, loading
the wrong context, or placing conventions in the wrong file. In that case the
fix must make the behavior harder to repeat, not just document the bug again.

## The ratchet (apply in order; each rung is stronger than the last)

```
Recurrence 1  →  Fix the symptom in place. Add a brief note in the
                  relevant doc so the agent who reviews this PR sees it.
Recurrence 2  →  Write the rule down explicitly in the canonical
                  cross-provider place (AGENTS.md). Reference it from
                  any provider-specific file that mentioned it.
Recurrence 3  →  Build a runnable check in `scripts/`. Anyone in any
                  provider can invoke it as a self-check. Exits non-zero
                  on the failure pattern, with a fix prescription in
                  the error message.
Recurrence 4  →  Wire the check as a PostToolUse / pre-write / pre-edit
                  hook in `.claude/hooks/` so Claude Code sessions can't
                  miss it. Update `.claude/settings.json`. Cowork /
                  Codex / Cursor sessions invoke the script per the
                  AGENTS.md convention.
Recurrence 5  →  Move the check to a pre-commit / CI gate so the
                  failure can't even land in the repo silently.
```

If a check is too noisy or has too many false positives at any rung,
add an explicit opt-out marker (e.g., `[harness-specific]`,
`<!-- @harness-specific -->`, `# noqa: <rule>`) and document the
marker in the check itself so agents who hit a false positive know
how to silence it correctly.

## Required artifacts at each rung

When you ratchet, you must leave behind enough that the next session
can extend the ladder without context. The standard kit:

1. **A check script in `scripts/<name>.py`** — runnable from any provider.
   Standalone Python, no imports outside stdlib if avoidable. Exit 0 on
   pass, exit 2 on fail. Stderr carries the human-readable fix
   prescription. Stdout carries `OK — …` on pass.

2. **A Claude Code wrapper in `.claude/hooks/<name>_guard.py`** — reads
   the tool-use payload from stdin (JSON), matches the relevant tool
   (`Write` / `Edit` / `Agent` / etc.), filters to the relevant file
   path or condition, calls the script. Exits 2 with the script's
   stderr on failure. Wire it into the matching `PostToolUse` matcher
   (or `PreToolUse` if blocking is appropriate) in
   `.claude/settings.json`.

3. **A paragraph in `AGENTS.md`** under the relevant section — names
   the script, gives the runnable command, explains the failure mode
   and the opt-out. Cross-provider visibility is the point.

4. **An entry in the auto-iterate ladder of the relevant subsystem doc**
   — for FUSE that's `WebSite/HOOKS_FUSE_QUIRKS.md`. For drift, the
   ladder lives in `AGENTS.md` itself. Each new rung is an entry.

5. **A line in `STATUS.md` or the relevant runbook** — so the next
   session reading the standard surfaces sees the new guard.

## Style of the prescription

When a check fails, the error message must do three things:

- **Quote the offense exactly** (file, line, the specific text).
- **Name the convention being violated**, in plain language.
- **Give the agent two paths forward**: (A) the canonical fix (what
  the convention requires), (B) an explicit opt-out if the case is a
  legitimate exception. Always show the opt-out marker syntax verbatim
  so the agent can paste it.

Example shape (from `check_cross_provider_drift.py`):

```
CROSS_PROVIDER_DRIFT — N convention(s) found …

  CLAUDE.md:18  ###  Verification Implementation
    body: AGENTS.md defines the project-wide verification invariants…

Fix one of two ways:
  (A) PROJECT-LEVEL rule: move the section into AGENTS.md, replace with a
      one-line pointer 'Cross-provider — see AGENTS.md § …'.
  (B) HARNESS-SPECIFIC rule: keep it where it is; add `[harness-specific]`
      in the heading or `<!-- @harness-specific -->` on the next line.
```

This format makes the check self-documenting. An agent that hits the
failure for the first time gets enough information to decide and fix
without reading the script source.

## What NOT to do

- **Don't ratchet without recurrence.** Every guard adds friction. If
  it's the first time the failure happens, fix it and note it; build
  the script on recurrence 2 or 3. Premature guards become noise.
- **Don't make the check probabilistic.** "Looks suspicious" doesn't
  scale. Define the failure pattern precisely so opt-outs are clean.
- **Don't lose the opt-out.** Every check needs a documented escape
  hatch for legitimate exceptions, in the script's source AND in the
  error message it prints.
- **Don't bury the check.** A guard nobody runs is not a guard.
  Document the runnable command in `AGENTS.md` and (for Claude Code)
  wire the hook so it fires automatically.

## Cross-references

- `debugging-and-error-recovery` — for one-shot code bugs that don't
  fit the recurring-behavior pattern.
- `team-iterate` — for tuning teammate role definitions when an agent
  underperforms (different shape: the failure is in the agent's
  prompt, not in a check).
- `WebSite/HOOKS_FUSE_QUIRKS.md` — full worked example of the ladder
  for FUSE truncation.
- `AGENTS.md` § *Where new conventions live* — full worked example of
  the ladder for cross-provider drift.
