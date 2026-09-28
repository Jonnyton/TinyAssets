---
severity: P2
title: A renewal by one run voids the receipts of other runs already in flight
filed: '2026-09-28'
summary: every renewal of an accepted source moves the assignment generation, and any other foreground run or background attempt of that universe that retains a receipt naming the old generation refuses its next launch
---

# A renewal by one run voids the receipts of other runs already in flight

**Filed:** 2026-09-28
**Source:** gpt-6-astra refute review of PR #4082, finding 1, second half.

A foreground run keeps one receipt for its whole life, and a background attempt keeps one receipt across all of its nodes. Each receipt names the assignment generation it was minted under. When anything renews the accepted source, that generation moves. The things that renew are:
- a served turn's refresh (#4076)
- another run's first-node refresh (#4082)
- the owner re-depositing a credential

After that, every OTHER run of the universe that is still in flight refuses its next launch (`foreground_run_provider.py` `_validate_receipt_parent`, and the background receipt replay conflict).

#4082 closes the part within one run: a background attempt refreshes once, and a sibling sub-branch session does not refresh. Across runs, nothing orders a renewal against work that is already running.

**Why it was not fixed there:** the failure is loud and costs one retry, since the run fails held and nothing is launched on stale authority. The fix is a design choice, and the options are:
- a receipt that follows a same-account renewal (custody changed, consent unchanged)
- holding renewals while receipts are live
- re-admitting at the next node

**Closure:** pick one, then add a test with two concurrent runs of one universe where a renewal lands between their nodes.
