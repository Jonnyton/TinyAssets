# Identified provider tool waits: deployment and acceptance

Verified September 21, 2026 UTC. PR3905 merged as
`89b47e00f26deec4e707f97dbfac381687e39e69`; reviewed candidate
`baf1733f18ec30b9c52126baf618246b0fdcb804`. `git diff` between their trees
is empty. Independent Fable approval:
https://github.com/Jonnyton/TinyAssets/pull/3905#issuecomment-5766143801.

## Regressions and deployment

- Focused Windows: 291 passed, 1 skipped. Linux oracle: 356 passed, 1 skipped.
  Base comparisons, mirror/import, Ruff and strict spec validation passed.
- Required CI35644169025: 19891 passed, 100 skipped, 10 deselected;
  existing quarantine covers 5 failures and 2 errors, zero new failures and
  zero stale entries. Slow suite: 10 passed, 1 skipped. This is a passing
  release gate, not a claim of a completely clean full repository suite.
- Image35646751178 succeeded; deployment35647143562 succeeded.
- Hosted authenticated `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --assert-handles`
  passed at19:49:54–19:50:01UTC.
- Hosted authenticated `python scripts/deployed_sha.py --url https://tinyassets.io/mcp --assert-contains 89b47e00f26deec4e707f97dbfac381687e39e69`
  returned SHIPPED at19:50:04UTC, reporting89b47e00f26d.
- Image digest: `sha256:f751ae27ef00cd4248cff6c2d33838ed13deb48c1e7322865005f6097e71b05c`.
  No rollback required. Prior healthy image remains rollback target; no migration.

Evidence inspected via `gh run view 35644169025 --log`,
`gh run view 35647143562 --log`, and terminal run watchers.
Credentials stayed in CI; no local secret retrieval.

## Rendered acceptance and limits

Refreshed the existing primary account through its owner-opened Chrome extension
session after deployment. Sent exactly `Retest your workflow checklist` once;
full user bubble12:51PDT, empty composer, Send disabled, thinking state verified.
No operator workflow edits, failed-run replay, or free-user onboarding restart.
Await original response and specific long-tool acceptance; smoke passes alone
do not prove the pending-tool boundary. Historical run6ffec5e973734074 lacks
tool-phase evidence, so its exact cause remains unknown. No organic owner use
since this deployment observed yet.

Original12:54PDT response confirms five control regressions: edit8248d00d0abf4bf1
returned RETEST/restored branch627a9a07; workspace create/discard36d56e3b8c9c4c3e
lease133/restored4c342216; output reads; in-flight cancellation320cd2616ee14748
with correct node state. It did not retest sequential/parallel/long-tool paths.
Do not treat its historical concurrency/load claims as measured cause.

At12:55PDT sent a natural follow-up requesting sequential/parallel first attempts
plus an approximately minute-long disposable task, waiting for completion and
reporting failures without retry. Full user bubble/empty composer/Send disabled
verified. At that point the follow-up was pending; five control passes alone do not close
the pending-tool defect.

At12:58PDT the follow-up reported all first attempts completed: sequential
6e850fca91c64113 (~48s, both nodes), parallel2aa70b09b69a4a1b (~65.8s,
both angles and synthesis), and60s workspace task5e122f8955bf4041 (~61s,
lease134). No retries or failures reported. The claim of a first-ever parallel
success contradicts earlier rendered successes and is not adopted.

This proves ordinary workflow completion, not yet a single native-tool wait:
the deployed `api/runs.py` run path starts `execute_branch_async` and returns a
queued acknowledgement. At13:00PDT asked whether it polled and, if so, whether
it can test one disposable tool operation staying open over30s; requested the
concrete blocker if unavailable and no failed-work retries. Also corrected the
historical parallel claim.

Original13:01PDT admitted polling and instead claimed native WebFetch against
httpbin.org/delay/35 proved a35s wait. This is NOT accepted: official
https://httpbin.org/legacy and
https://github.com/postmanlabs/httpbin/blob/master/httpbin/core.py document and
implement min(n,10) for that route. After a factual correction, original13:04PDT
retracted the35s inference and reported no per-call timing field or known
uncapped test endpoint. At that point no single-call>30s proof existed. Independent
Fable was assessing existing timing/receipt sources, not giving release approval.

### Measured single-call acceptance,20:13UTC

Independent Fable proof assessment85758 completed exit0/349s: existing native
CLI transcript timestamps can bracket one tool call; no release blocker found.
It distinguished whole-turn duration from tool duration and noted that tool
progress heartbeats could also preserve liveness. This was a proof-path review,
not the closeout's exact-head approval.

Root confirmed scoped transcripts exist with read-only SSH/container access.
The diagnostic extracts only tool name, timestamps, elapsed seconds and error
boolean, matching the tool id in memory. No transcript bodies, arguments,
credentials, reasoning, raw principal ids, tool ids or auth-home paths are
copied. The earlier delay/35 call actually took14.718s, not35s.

At13:12PDT asked the app agent to fetch one fresh, nonce-tagged public httpbin
drip URL with a40s initial delay and one-byte body, once, without retry. The
official implementation above distinguishes this uncapped initial-delay route
from /delay. The actual measurement, not that configured delay, is the proof:

- Native WebFetch tool start: `2026-09-21T20:12:42.360+00:00`.
- Matching tool result: `2026-09-21T20:13:24.486+00:00`.
- Elapsed: **42.126 seconds**, `tool_reported_error=false`; exactly one match.
- Original13:13PDT rendered reply confirms one successful call, expected
  single-byte `*` response, no error. Answered by Claude Sonnet4-6.

This is a real successful single native-tool wait over30s, followed by normal
conversation completion, not asynchronous workflow polling or a URL inference.
It closes the scoped live acceptance in conjunction with the reviewed real-reader
red/green regressions. It does NOT establish whether this call emitted internal
tool-progress heartbeats, or attribute the earlier historical timeout to pending
tools. Broader intermittent sequential/parallel reliability remains open.
No organic owner use after deployment was visible as of20:14UTC; retained in
the observation watch. At13:14PDT supplied the measured duration to the agent
and asked it to update its checklist without retiring those unrelated failures.

The existing `TINYASSETS_ALLOW_CLAUDE_SERVING` deployment flag read1 through
read-only SSH; the old pending host-action saying it was unset is obsolete.
No flag, credential, permissions or provider-policy change was made here.

Original13:16PDT rendered reply confirms the agent saved the measured42.126s
single-tool success, retracted its earlier capped-delay inference, and kept
parallel/sequential intermittent failures OPEN with cause not established.
The user-facing scoped capability is accepted; the entire platform checklist
is not closed. Closeout synchronizes/archives the spec and corrects only stale
comments/documentation, with no changed runtime behavior.
