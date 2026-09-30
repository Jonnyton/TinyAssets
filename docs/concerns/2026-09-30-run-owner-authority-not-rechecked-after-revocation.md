---
severity: P3
title: Run-owner authority is not re-checked after the owner loses the universe
filed: '2026-09-30'
summary: >-
  Handoff initiation, outcome attestation and market outcomes trust a run's recorded
  owner_user_id without re-checking current universe access, so an owner whose admin
  grant was revoked after the run finished keeps those powers over it.
---

# Run-owner authority is not re-checked after revocation

2026-09-30, gpt-6-astra refute round 3 on PR #4107 (automation runs now record
`owner_user_id`), left open after the three-round cap.

`tinyassets/handoffs/authority.py` (subject comparison on the run owner),
`tinyassets/handoffs/service.py` (outcome attestation) and `tinyassets/api/market.py`
(outcome record) accept the run's persisted `owner_user_id` as the subject. They do
not re-check that the owner still administers the run's universe.

This predates #4107 for every `universe:<id>` run that already recorded its owner
(direct input, conversation turns, deliveries). #4107 adds automation runs to that
set, which is intended: an owner's automation run is the owner's own run, and
owner-recorded is what the invoke owner path needs (the co-admin counterexample it
closes). The residual is the revocation case only: an owner acts on their OWN past
run after losing the universe. Not a cross-user read.

Fix shape: a single "current owner of this run" check (recorded owner AND a live
admin grant on the run's universe) used by all three call sites.
