# Workspace terminal release — cross-family review

**Review round:** 1 of 3
**Reviewed commit:** `eab16fbbf254d8a01dcc3abcddeaf9e987634942`
**Reviewer:** Claude Opus subprocess via `peer-agents`
**Verdict:** `DISAGREE_EVIDENCE`

## Findings returned

1. **P1 — completed runs could be rewritten as failed.** The second universe
   database enqueue ran after the root terminal commit but could raise into the
   background worker's outer exception handler. That handler would call
   `update_run_status(..., failed)`, reclassifying an already-completed run.
2. **P1 — sibling terminal writers omitted the universe enqueue.** Read-time
   orphan recovery, `get_run` orphan recovery, and startup
   `recover_in_flight_runs` still wrote terminal status only at the root and
   therefore relied solely on the periodic universe repair.

The reviewer reported two P2 findings and one P3 finding only by count; its
referenced detailed output artifact was not created. Round 2 must return every
remaining finding inline so no verdict depends on an absent artifact.

## Disposition

Both P1 findings were accepted. The follow-up centralizes the post-commit
second-WAL enqueue behind a no-throw helper, kicks the exact universe sweep on
failure, and routes all four terminal writers through the same protocol. Tests
prove a failed universe enqueue preserves the completed root status, the sweep
repairs the gap, and all three recovery entry points enqueue the owning
universe. Round 2 reviews the resulting exact commit.
