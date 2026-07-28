---
name: subagent-driven-development
description: Executes plans and independent tasks via fresh subagents with isolated context. Use when implementing a plan task-by-task in the current session, or when facing 2+ independent tasks/failures that can be worked concurrently without shared state.
---

# Subagent-Driven Development

## Overview

Delegate work to fresh subagents with precisely-crafted, isolated context — they
never inherit your session history; you construct exactly what each needs. This
keeps them focused and preserves your context for coordination. Two modes:

- **Sequential plan execution** — one implementer per task + review after each.
- **Parallel dispatch** — one agent per independent problem domain, concurrently.

**Core principle:** fresh subagent per unit of work + review = high quality, fast
iteration. **Narrate at most one short line between tool calls** — the ledger and
tool results carry the record.

---

## Mode A — Sequential plan execution

Use when you have an implementation plan with mostly-independent tasks and are
staying in this session. **Execute all tasks continuously** — don't pause for
"should I continue?" between tasks. Stop only for an unresolvable BLOCK,
genuine ambiguity, or completion.

**Pre-flight:** scan the plan once for tasks that contradict each other or the
Global Constraints, or that mandate something the review rubric treats as a
defect. Batch any findings to the human before starting; if clean, proceed.

**Per task:**
1. Run `scripts/task-brief PLAN_FILE N` → hand the implementer the printed brief
   path as its requirements (exact values live only in the brief), plus where the
   task fits, interfaces/decisions from earlier tasks, your resolution of any
   ambiguity, and the report-file path. Don't paste the whole plan or prior-task
   history.
2. Implementer implements (TDD), tests, commits, self-reviews, writes its full
   report to the report file, returns only status + commits + one-line test
   summary + concerns.
3. Handle status: DONE → review; DONE_WITH_CONCERNS → address correctness/scope
   first; NEEDS_CONTEXT → provide and re-dispatch; BLOCKED → fix context / use a
   stronger model / split the task / escalate. Never force the same model to
   retry unchanged.
4. Generate the diff: `scripts/review-package BASE HEAD` (BASE = the commit
   recorded before dispatch — never `HEAD~1`). Dispatch the task reviewer
   ([task-reviewer-prompt.md](task-reviewer-prompt.md)) with brief + report +
   package paths and the verbatim Global Constraints. Require BOTH verdicts: spec
   compliance AND code quality.
5. Dispatch ONE fix subagent for Critical/Important findings (re-runs covering
   tests, reports results); re-review. Log Minor findings in the ledger for the
   final review. Resolve any "⚠️ cannot verify from diff" items yourself.
6. Mark complete in todos and the ledger.

**Final:** dispatch one whole-branch review on the most capable model using
[../code-review-and-quality/code-reviewer.md](../code-review-and-quality/code-reviewer.md)
with `scripts/review-package MERGE_BASE HEAD`; one fix subagent for all findings;
then finish via `git-workflow-and-versioning`.

**Model selection.** Always specify the model explicitly (omitting it inherits
your expensive session model). Cheapest tier for transcription/single-file
mechanical tasks; mid-tier floor for reviewers and prose-driven implementers;
most capable for design and the final review. Turn count beats token price —
cheap models often take 2–3× the turns.

**File handoffs.** Everything pasted into a dispatch (and returned) stays
resident in your context and is re-read every turn. Move artifacts as files:
task brief, report file (named after the brief), reviewer inputs (brief + report
+ package). Never pre-judge findings for a reviewer ("at most Minor", "don't
flag X") — let it raise and adjudicate.

**Context-isolating precedent scouts.** A task-scoped
`implementation-precedent-scout` is one read-only research dispatch, not a Mode
B implementation worker. Give it the exact implementation question and local
constraints, not the plan/session. Enforce read/search/fetch-only tools and the
scout skill's no-shell/no-secret boundary in the actual dispatch. It writes raw
output under ignored `output/precedent-scout/`; the coordinator validates or
format-repairs exactly one JSON source map before returning only status,
artifact path, stop reason, and concerns. Accept verified partial output when
the budget expires; allow at most one targeted follow-up for a named evidence
gap.

**Durable progress.** Conversation memory doesn't survive compaction; re-running
completed tasks is the most expensive failure observed. Keep a ledger
(`$(git rev-parse --show-toplevel)/.superpowers/sdd/progress.md`): at start, tasks marked
complete are DONE — resume at the first unmarked one; append
`Task N: complete (commits <base7>..<head7>, review clean)` per task. Trust the
ledger and `git log` over recollection after compaction.

Templates: [implementer-prompt.md](implementer-prompt.md),
[task-reviewer-prompt.md](task-reviewer-prompt.md). Subagents follow
`test-driven-development`; isolate via `git-workflow-and-versioning`.

---

## Mode B — Parallel dispatch

Use when 2+ failures/tasks are genuinely independent (different files/subsystems,
no shared state). Don't use for related failures (fix one may fix others),
exploratory debugging, or work that would edit the same files.

1. **Group by independent domain** (one agent per domain).
2. **Write focused tasks:** specific scope (one file/subsystem), clear goal,
   constraints ("don't change other code"), and required output (summary of root
   cause + what changed). Paste the actual error messages/test names — give
   context, not just "fix the race condition."
3. **Dispatch in parallel:** issue all subagent calls in ONE response (multiple
   calls in one response = concurrent; one per response = sequential).
4. **Review and integrate:** read each summary, check fixes don't conflict, run
   the full suite, spot-check (agents make systematic errors).

---

## Red Flags

Starting on main/master without consent · skipping task review or accepting one
verdict (spec AND quality both required) · proceeding with unfixed
Critical/Important issues · dispatching parallel implementers that edit the same
files · making a subagent read the whole plan (hand it the brief) · pasting
session history into dispatches · pre-judging findings for a reviewer ·
re-dispatching a task the ledger marks complete · per-finding fixers instead of
one batched fix.

## Verification

- [ ] Each task passed both verdicts; Critical/Important fixed and re-reviewed
- [ ] Final whole-branch review clean; ledger reflects true state
- [ ] Parallel fixes integrated with no conflicts; full suite green
