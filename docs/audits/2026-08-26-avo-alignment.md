# Harness vs AVO — a structural alignment audit

**Revised 2026-08-26** after an independent Codex research pass corrected four
sourcing claims and found a defect in the change this audit originally proposed.
Codex's full pass: `docs/audits/2026-08-26-avo-harness-reset-independent-codex.md`.

---

## What AVO actually establishes (and what it does not)

**Verified.** AVO reports **100 RHAE across all 25 public ARC-AGI-3
environments / 183 levels**, using **6,624 actions versus VISTA's 7,542 —
12.17% fewer**. Its architecture is **inspect / plan / edit / evaluate over a
scored git lineage**, persistent history, and a supervisor responding to
**stalled evaluated search**. The same architecture ran 7 days continuously on
GPU-kernel optimisation (500+ directions, 40 committed versions) and transferred
to interactive reasoning **without domain-specific redesign**.

**NOT established — and previously asserted here in error.** NVIDIA explicitly
says the AVO / VISTA / base-model comparison is **not a controlled ablation**.
"The same model went 30% → 100% on harness changes alone" is therefore
unsupported, and both this audit and `PLAN.md` claimed it. Corrected.

Three further claims that shaped earlier decisions did not survive checking:

| Claim used earlier | Status |
|---|---|
| AGENTS.md beyond ~150 lines shows a performance cliff | **No primary evidence.** An uncited heuristic. |
| Generated instruction files cost 20–23% more | **Real, but the wrong comparison** — generated instructions vs *no file*, not length vs cost. The study found **no clear relationship between instruction-file length and success or cost**. |
| Prose guidance gets 25–40% compliance vs ~95% for hooks | **Unsupported.** Harness-IF reports 72.1–85.9% instruction accuracy and makes no hook comparison. |

The reset's direction — move rules into checks — still stands on its own
measured evidence in this repo (three checks that could not go red; a budget
invariant registered and VIOLATED for months). It does **not** stand on that
25/95 split, and should not be justified with it.

## Scorecard

| AVO component | What AVO does | Ours | Verdict |
|---|---|---|---|
| **Main loop** | inspect → plan → edit → **evaluate**, over a scored git lineage | inspect covered; evaluate not a named step | **Partial** |
| **Persistent memory** | prior implementations, evaluation results, accumulated reasoning | git history, `openspec/specs/`, `docs/concerns/`, `.claude/agent-memory/` | **Adequate — see below** |
| **Supervisor** | responds to stalled **evaluated** search | `repeat_failure` only, after the 2026-08-26 cut | Aligned |
| **Tools** | what actions are possible | 97 scripts, 10 skills, 5 hooks | Still too many |
| **Feedback** | grounds progress | invariants in pre-commit and CI, required checks, canary | Strongest |
| **Recovery** | work continues | supervisor redirect + cross-family handoff | Aligned |

## The memory gap was misdiagnosed

This audit originally claimed memory was the weakest axis and shipped
`supervisor.py resume` plus a SessionStart hook to close it. **That was wrong
twice over**, and Codex caught both:

1. **It did not work.** `resume()` filtered events to the *current* session id.
   At a fresh `SessionStart` that id is new, so the result is empty **by
   construction** — precisely when it was supposed to be useful. Reproduced:
   session A records 3 dead ends, session B sees 0.
2. **A test asserted the broken behaviour.** `test_resume_is_session_scoped`
   locked the bug in. The root cause is that session isolation is *correct* for
   the predicates — one session's failures must not trip another's redirect —
   and I reused that filter for resume, where isolation destroys the purpose.
   Two requirements, one implementation.

Both were reverted. The deeper correction is Codex's: **git, specs, and concerns
are already enough storage. The missing capability was never memory volume — it
is outcome-centred supervision.** AVO's memory is a *scored git lineage*: each
candidate carries its evaluation result. Ours records that a command ran, not
what the run established.

## The supervisor now watches outcomes, not activity

`edit_thrash` (same file 5×) and `no_landing` (40 calls without a commit) were
**deleted**. They measured busyness: five edits and forty commands say nothing
about convergence, and their thresholds were arbitrary where 3 at least matched
`AGENTS.md`'s existing "stuck 3+ iterations". A supervisor that flags activity
becomes noise, and a noisy supervisor is worse than none — it costs tokens and
trains the reader to skip it.

What remains is `repeat_failure`: the same command failing identically 3× since
the last commit. That *is* outcome-centred — a test or gate result is an
evaluation, and repeating one that keeps returning the same failure is the stall
AVO's supervisor exists to break.

**Open, not yet built:** feeding the supervisor a compact outcome from the gate
that just ran — evaluation name, result, candidate commit, next action. That is
the honest analogue of AVO's scored lineage and maps to feedback + supervisor.
It is deliberately not built yet: the last time this audit proposed a memory
mechanism it shipped one that did nothing.

## Where we diverge from AVO on purpose

**AVO's harness is domain-general; ours is domain-specific.** The transfer
result is about mechanisms — memory, supervisor, gates — not about the project
knowledge they carry. Our mechanisms are general; the content is TinyAssets-
specific, correctly.

**AVO blocks nothing; neither do we.** Its supervisor redirects rather than
halts, for the same reason ours warns and never blocks.
