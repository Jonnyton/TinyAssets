---
severity: P1
title: A renewal by one session voids the receipts of other sessions in flight
filed: '2026-09-28'
summary: every renewal of an accepted source moves the assignment generation, and any other in-flight session of that universe that retains a receipt naming the old generation refuses its next launch; a background attempt caught this way is stranded, not retried
---

# A renewal by one session voids the receipts of other sessions in flight

**Filed:** 2026-09-28
**Source:** gpt-6-astra refute review of PR #4082, rounds 1 and 2.
**Decision (lead, 2026-09-28):** receipts carry forward on renewal. A renewal of the SAME owner's SAME accepted source (same account, new tokens) must not void receipts in flight. A different account or owner still must.

Each of these keeps one receipt for its whole life:
- a foreground run;
- each async sub-branch session;
- a background attempt, across all its nodes.

Every receipt names the assignment generation it was minted under. Any renewal of the accepted source moves that generation:
- a served turn's refresh (#4076);
- another session's first refresh (#4082);
- the owner re-depositing.

After a renewal, every OTHER in-flight session of the universe refuses its next launch. That happens in `foreground_run_provider.py` `_validate_receipt_parent` and in the background receipt replay conflict.

**Impact is worse than one retry.** Codex reproduced it: a background attempt whose receipt was voided between nodes ended with one launch done, the task back to pending, the queue owner `TARGET_AUTHORITY_HELD`, and the attempt still `RUNNING`. Re-claim then returns `attempt_not_reserved`, and releasing the task does not repair that authority. So the attempt is stranded, not retried. A foreground resume (`api/runs.py` resume) builds a fresh session for the same run, which can renew before it re-admits against the run's existing receipt. No launch on stale authority was observed; the failure is a refusal.

**Why it matters now:** the founder's always-on background agent wakes about once a minute. Every 12h rotation would cancel a live run.

**Closure:** a receipt follows a renewal that keeps the owner, universe, provider, account and accepted model access, and changes only credential bytes, custody generation and assignment generation. Anything else still voids it. Add regression tests for all of these:
- two overlapping sessions where one renews between the other's nodes;
- a child-first sub-branch;
- the stranded background attempt;
- a foreground resume.
