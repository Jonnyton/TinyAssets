# Harness vs AVO — a structural alignment audit

The reset's stated goal is to duplicate NVIDIA AVO's result: the same base model
(Claude Opus 5) went from **30% to 100% RHAE on ARC-AGI-3** on harness changes
alone, using **12% fewer environment actions** than the prior best. The same
architecture also ran **7 days continuously** on GPU-kernel optimisation,
exploring **500+ directions** and producing **40 committed kernel versions**.

The load-bearing claim is not any single mechanism:

> "the same agent architecture transferred from highly specialized GPU-kernel
> optimization to a very different interactive reasoning task **without
> domain-specific redesign**."

and

> "memory determines what survives, tools determine what actions are possible,
> feedback grounds progress, and recovery allows work to continue."

Those four axes are the audit frame.

---

## Scorecard

| AVO component | What AVO does | What we have | Verdict |
|---|---|---|---|
| **Main agent loop** | inspect context → plan → implement → **evaluate** | `AGENTS.md` § *Orient* covers inspect; plan/implement are ad hoc; **evaluate is not a step** | **Partial** |
| **Persistent memory** | prior implementations, **evaluation results**, tool output, accumulated reasoning — "resume from the current state rather than repeatedly reconstructing the search" | `.claude/agent-memory/` (durable lessons), `docs/concerns/` (known-bad), git log (what landed) | **Weakest axis** |
| **Supervisor** | monitors trajectory for stagnation and repeated unproductive cycles; redirects | `scripts/supervisor.py` — 3 predicates, warns, never blocks | **Aligned** |
| **Tools / environment** | what actions are possible | 97 scripts, 10 skills, 5 hooks | **Aligned after the reset** (was 101/34/15) |
| **Feedback** | grounds progress | invariants in pre-commit **and** CI, required checks, canary, `deployed_sha` | **Strongest axis** |
| **Recovery** | work continues after a wrong assumption | supervisor redirect + `peer-agents` cross-family handoff | Aligned |

## The one real gap: memory that lets you resume

Everything we call memory records **conclusions**. Nothing records **attempts**.

- `.claude/agent-memory/` — durable lessons, written after the fact
- `docs/concerns/` — findings that are known-bad
- git log — what landed
- supervisor events — that a command ran and its exit code, pruned at 24h

None of that answers the question a resuming session actually has: *what has
already been tried here, and what happened?* So each session re-derives it —
re-reads the instruction files, re-runs the audit, re-greps, and sometimes
re-attempts an approach a previous session already disproved. That is precisely
the "repeatedly reconstructing the search" AVO's memory exists to eliminate, and
it is invisible in any per-PR metric because the cost is paid before the PR
exists.

Measured on this repo the same day: PR created → merged is **median 0.1h**,
while `openspec/changes` holds **67 active changes at median 23 days idle**. The
bottleneck is upstream of the PR, in exactly the region memory would cover.

### What is deliberately NOT being built

AVO's memory holds compiler and profiler output because its inner loop is
kernel optimisation. The analogue here is **not** a new store: the supervisor
already records attempts and outcomes (command signature + exit code) and
already resets them on a commit. What was missing is a **view** — surfacing that
record at session start instead of letting it expire unread.

So the fix is one subcommand and one existing hook, not a memory subsystem. Per
the founder's tiebreak (2026-08-26): where doing more would be over-engineering,
lean to AVO or cut.

## Where we deliberately diverge from AVO

**AVO's harness is domain-general; ours is deliberately domain-specific.** AVO's
transfer result is about one architecture working across unrelated tasks. Our
`AGENTS.md` is full of TinyAssets specifics — the live connector, the canonical
`/mcp` endpoint, provider routing, the deploy chain. That is correct for a
*project* harness and should not be "fixed": the generality lesson applies to
the mechanisms (memory, supervisor, gates), not to the project knowledge they
carry. The mechanisms here are general; the content is not, on purpose.

**AVO blocks nothing; neither do we.** Its supervisor redirects rather than
halts. Ours warns and never blocks, for the same reason: a supervisor that can
stop a session is a new ratchet, and ratchets are what this reset removed.

## Actions

1. **Close the memory gap** — `scripts/supervisor.py resume`, surfaced at
   session start. Attempts and outcomes for the current lane, so a session
   resumes instead of reconstructing. *(Implemented alongside this audit.)*
2. **Make `evaluate` a real loop step** — the loop is inspect → plan →
   implement → **evaluate**, and evaluation here means running the gate that
   matches the change, not "looks right". Already true for merges; stated
   explicitly in `AGENTS.md` § *Quality Gates*.
3. **Do not add a memory subsystem.** The supervisor's store is the memory.
