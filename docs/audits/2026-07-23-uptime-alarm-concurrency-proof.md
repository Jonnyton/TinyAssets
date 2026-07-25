# Uptime alarm concurrency proof — 2026-07-23

## Claim

The global `uptime-canary` workflow preserves one incident and one immediate
page decision when serialized or coalesced alarm-sink ticks observe a P0
outage. It keeps `cancel-in-progress: false`.

## Executed evidence

Environment: Windows PowerShell, `C:\Users\Jonathan\Projects\wf-openspec-conformance-audit2`, 2026-07-23.

```powershell
python -m pytest -q tests/test_p0_triage_workflow.py tests/test_uptime_canary_concurrency.py tests/test_uptime_canary_workflow.py
```

Result: `37 passed`.

`tests/test_uptime_canary_concurrency.py` extracts the exact `alarm-sink`
`actions/github-script` body from `.github/workflows/uptime-canary.yml` and
executes it repeatedly in one Node process. Its shared in-memory GitHub REST
model carries the issue, labels, comments, and prior-run conclusions between
invocations.

The serialized schedule executes first-red → threshold-red → red → unknown →
red → green. It proves:

- first red does not open an incident;
- threshold red creates exactly one incident and makes the first page eligible;
- unknown makes zero REST calls and zero state mutations;
- each later red appends to issue `#99` without creating another incident;
- green closes that same issue.

The same test passes the shared comment collection through the real
`scripts.pushover_page.should_page` function: the threshold page is eligible,
then the shared `[PAGED ...]` marker makes each later immediate decision
ineligible inside the one-hour window.

The burst proof models one running plus one replaceable pending run across
1,000 arrivals: threshold-red, 998 alternating unknown/red arrivals, then
green. The modeled executed schedule is threshold-red → green: the newest
pending observation replaces the earlier 998 pending arrivals. The exact
extracted sink opens one incident and then closes that same incident.

## Boundary and limitations

Node executes the exact alarm-sink JavaScript and the pager decision is the
actual Python implementation. The GitHub Actions scheduler itself is not run
locally; its documented one-running/one-pending replacement behavior is a
small explicit model in the test. This proof therefore validates incident and
paging transitions under that scheduling contract, not GitHub's scheduler
implementation or production Pushover delivery.
