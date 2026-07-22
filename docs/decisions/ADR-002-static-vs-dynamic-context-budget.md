# ADR-002: Static vs Dynamic Context Boundary + Always-Loaded Budget

## Status

Accepted

## Date

2026-06-25

## Context

The "New SDLC with Vibe Coding" whitepaper frames an agent's context as split
between **static** context (system instructions + rule files + global memory,
loaded on *every* turn — reliable but paid for on every call) and **dynamic**
context (skills, tool results, RAG docs, loaded on demand). Its guidance: *"The
best systems treat this boundary as a first-class architectural decision,
reviewed and versioned like any other configuration."*

This repo had the split in practice but never as a *reviewed* decision, and the
always-loaded payload had grown unaudited: a 2026-04-28 cross-check measured
`AGENTS.md` at ~17.6 KB; by 2026-06-24 it had tripled to ~56 KB with no
guardrail noticing. Basis:
`docs/audits/2026-06-24-sdlc-vibe-coding-claude-best-practices-adoption.md`
(R4 / context-engineering).

## Decision

1. **The always-loaded (static) set is exactly:** `CLAUDE.md`, which imports
   `@AGENTS.md` and `@STATUS.md`. These load every session. `PLAN.md` is
   deliberately **not** imported — it is pointer-loaded (`docview.py` /
   section-load). Skills, the provider-context feed, and agent-memory are the
   **dynamic** layer (loaded on demand / by task match).

2. **Budgets** (enforced — see below):
   - `STATUS.md` — **HARD** 4 KB / 60 lines. This is the file's own declared
     contract, so it is enforceable, not a judgement call.
   - `AGENTS.md` — **SOFT** 30 KB / 450 lines (advisory; the exact ceiling is a
     host call — was ~17.6 KB at the last audit).
   - `CLAUDE.md` — **SOFT** 12 KB / 200 lines (should stay a thin pointer layer).
   - Combined always-loaded — **SOFT** 40 KB (~10K tokens).

3. **Enforcement.** `scripts/check_context_budget.py` measures the set;
   `--strict` exits 2 when a HARD budget is busted. It is wired as the
   **propose-only** `context-budget` invariant (`scripts/invariants/context_budget.py`)
   — it surfaces drift but never blocks a commit (host-managed content), the
   same stance as `concerns-staleness`. Soft overages WARN only. Numbers are
   tunable in the script's `CONFIG`.

   **Amended 2026-07-22 — the gate.** The above was reporting, not enforcement:
   nothing in the repo passed `--strict` and no CI workflow ran the script, so
   on 2026-07-22 STATUS.md sat at 7485 bytes against its declared 4096 ceiling
   with the checker printing `OVER-HARD` and exiting 0. The gate is now
   `.github/workflows/context-budget.yml`, running on every PR:

   - a **report** job publishes the absolute table and warns on a HARD breach;
   - a **ratchet** job (`--strict --baseline <merge-base>`) FAILS the PR when a
     change pushes a file over its ceiling, grows a file already over it (bytes
     and lines ratcheted independently — no offsetting), or relaxes the budget
     definition itself (raising `max_bytes`/`max_lines`, downgrading a HARD
     entry to SOFT, or dropping an entry from `CONFIG`).

   The ratchet, not absolute `--strict`, is the enforced mode **while main is
   non-compliant** — an absolute gate would have gone red on every open PR for
   debt none of them created, and a permanently-red check is one people route
   around. Green means "not made worse", never "within budget", and the tool
   says so explicitly. Once main is compliant the ratchet and absolute `--strict`
   converge, and the enforced mode should be switched to absolute. Trimming the
   always-loaded files to get there remains the separate lean/layer work below.

4. **The lever when a soft budget is exceeded:** move reference-only content out
   of the always-loaded files into pointer-loaded docs or on-demand skills
   (e.g. the AGENTS.md env-var table, the worktree-discipline procedure), rather
   than leaving it in static context. Adding new always-loaded content is a
   deliberate tradeoff to be justified in review.

## Consequences

- Always-loaded budget drift is now visible (a guard measures it), instead of
  silently tripling between audits.
- New rule-file content is a reviewed cost decision, not a free add.
- The exact SOFT numbers remain the host's to tune; the HARD STATUS.md budget is
  the file's own stated contract and stays enforceable.
- This ADR records the boundary; it does not by itself shrink `AGENTS.md` —
  that lean/layer work is tracked separately (audit R3) and needs the host's
  budget-number sign-off.
