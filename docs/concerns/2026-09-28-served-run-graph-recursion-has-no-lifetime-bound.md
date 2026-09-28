---
severity: P2
title: A branch that run_graphs itself has no lifetime bound
filed: '2026-09-28'
summary: served run_graph starts a fresh run with fresh bounds and no inherited depth, deadline or budget, so a self-launching branch runs indefinitely, paced only by the rolling served-run limiter. It stays inside the owner's own universe; the bound belongs to plan item 6 (usage limits)
---

# P2 - a branch that `run_graph`s itself has no lifetime bound

**Filed:** 2026-09-28 | **Verified:** 2026-09-28 against the agent-node branch merged with main `a9384000` | **Severity:** P2

## Source (verbatim)

gpt-6-astra refute review of the agent-node change, 2026-09-28:

- **DISAGREE_EVIDENCE: P1 — Served recursion has no lifetime bound.** [engine_mcp_server.py:833](/C:/Users/Jonathan/Projects/wf-agent-node/tinyassets/engine_mcp_server.py:833) launches fresh runs without inherited depth, deadline, or budget. The new code-tool path at [graph_compiler.py:2076](/C:/Users/Jonathan/Projects/wf-agent-node/tinyassets/graph_compiler.py:2076) makes this deterministic: an owner-authored code branch sleeps 20 seconds, calls `run_graph` on itself, then exits. Descendants continue indefinitely at roughly 180 runs/hour, below the rolling limits; each gets fresh execution bounds. **Fix:** propagate trusted root lineage with a shared lifetime budget and deadline through served run admission.

## Premise

The served `run_graph` handler (`tinyassets/engine_mcp_server.py`, the run
launch path) admits each run on its own. No root lineage, depth, deadline or
budget flows from a run that launches another. The rolling per-hour served-run
limiter paces a chain, but a chain that stays under it never ends.

The agent node does not create this: a conversation turn with `run_graph` could
already do it. The code-node grant (`invoke_mcp_action` reaching served tools)
makes it deterministic, with no model in the loop.

## Why P2, not P1

Every run in the chain is the owner's own, in the owner's own universe, on the
owner's own compute. No other user is affected, which is the only platform
floor. It is a runaway-cost hazard for the owner.

## What would close it

Plan item 6 (per-automation lease and usage limits): carry a trusted root
lineage through served run admission and charge descendants against one
lifetime budget. Not a count cap on runs.
