# Owned provider processes: candidate evidence

2026-09-24 UTC. Claude-authored helper/adapters/tests; independently reviewed by
Codex root. No production or rendered acceptance claim. Candidate remains gated
by exact-head approval, required CI, protected deployed SHA and public canary.

## Scope and limits

New owned_process.py, Claude/Codex adapter call sites, plugin mirrors, focused
tests and provider-routing specification. Already-deployed compaction/base.py
from099fe185 is preserved, not part of the new behavior or rollback target.

On POSIX a fresh isolated -I -S Python wrapper starts in its own session, forks
a live in-group anchor, then execs the original argv. CLI environment, cwd and
stdio are preserved. The anchor drops CLI stdio, reports readiness and releases
the exec gate. Teardown writes/closes its control pipe; the anchor signals its
own group while alive. No daemon-side stale numeric group lookup or pidfd-number
reservation assumption. Invalid handshake fails closed. Descriptor ownership is
consumed once, including second-pipe allocation failure. Normal success, failure
and cancellation finish ownership; dropped handles close via weakref finalization.
Existing timeouts/retry/provider authority unchanged.

This is process-group lifetime management, not a containment security boundary:
deliberate setsid escape remains outside it. Windows termination is bounded best
effort, not a Job Object; descendants that reparent/escape may survive. The
existing sandbox remains required. Full resource-capability closure stays open.

## Verification

Initial hosted35952554020:67passed2failed0skipped. Both failures at stale argv
assertions before descendant checks: NOT slice proof. Claude correction15574
pins exact python,-I,-S,-c prefix, adds real interpreter isolation testing and
fixture transport cleanup. No runtime change in that correction.

Corrected cloud Linux/Python3.11 run
https://github.com/Jonnyton/TinyAssets/actions/runs/35953337015 succeeded03:54:47UTC:
**70passed0failed0errored0skipped**. Base099fe185cf09baa1c2f80d9eaed81503da74ca17
plus133584-byte patch0c58549ecc668c6f18271b908673b87805439dbf2ed74a44b1453c21266a31d0.
Hosted oracle ran complete real-adapter/deadline-reap, node-timeout subprocess-reap
and declared-compaction modules. Tests reach descendant state and exclusive-lock
reacquisition assertions. Toolingc3d9177a; no production credentials or local
Docker/WSL/service used.

Root Windows: python -m pytest -q tests/test_provider_real_adapter_deadline_reap.py
tests/test_provider_node_timeout_subprocess_reap.py tests/test_claude_compaction_liveness.py
tests/test_provider_stream_and_classify.py --basetemp
C:/Users/Jonathan/AppData/Local/Temp/ta-owned-root-final-20260924:
179passed12skipped in30.43s. Skips do not substitute for Linux proof.

Root review checked full helper, adapter diff against099fe185, exact frozen test
correction and cloud results. No basic-safety release blocker found. Final unchanged
commit SHA must be bound in PR review receipt; this document alone is not that receipt.

## Rollback and acceptance

Stateless runtime change: revert only ownership helper/adapter integration and
associated mirrors, preserving compaction/later unrelated fixes; rebuild mirror
and deploy through ordinary cloud gates. This restores direct-child-only behavior
and its known weakness, not a guarantee of no regressions. No migration, credential
change, private workflow edit or historical-data rewrite. Deploys can interrupt
in-flight turns: inspect progress before any resend.

After deployment ask exactly Retest your workflow checklist. A successful ordinary
reply supports this slice, not every process-lifetime edge case or closure of
historical intermittents. Organic-use and broader resource/uptime remain open.
