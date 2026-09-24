# Independent review: declared compaction is bounded provider work

2026-09-24 UTC, Codex root reviewing Claude/Fable implementation on
codex/declared-provider-busy, baseff1320d5. APPROVE for shape and basic safety;
exact final head named in PR body. No public API, storage, authority or workflow
definition change. Normalization and attempt-local reader state are changed;
process spawning, OS limits, sandbox/filesystem paths and teardown are unchanged.

Root inspected canonical source, event-kind contract, all24new regressions and
spec delta. Only published system/status compacting opens the new internal busy
state; explicit null, compact boundary or real progress clears it. Ordinary
post-tool silence, unknown statuses and requesting do not gain this allowance.
The bounded tool-wait shape applies without relaxing absolute/node deadlines,
cancellation, receipt semantics or automatically replaying side effects.

Primary protocol verification: root fetched the published
@anthropic-ai/claude-agent-sdk0.3.281/sdk.d.ts from unpkg02:53UTC using
Invoke-WebRequest. SDKStatus names compacting/requesting/null; status and compact
boundary are documented message types. No assumption of heartbeat cadence is
used. This fixes the reproduced2RED/6green defect; it does NOT establish the
cause of the live19:11 post-tool30067ms failure.

Root final Windows/Python3.14 verification03:01UTC:
`python -m pytest tests/test_claude_compaction_liveness.py
tests/test_provider_stream_and_classify.py
tests/test_a_failed_turn_says_what_actually_happened.py -q -p no:cacheprovider
--basetemp=C:/Users/Jonathan/AppData/Local/Temp/ta-root-compaction-final`:
188passed,1skipped,23.16s. Skip is existing bwrap-stderr classification on
Windows; hosted Linux CI remains necessary. Ruff on all edited canonical Python
and new test module passed. Plugin mirror regenerated, import probe passed.

Additional tests pin busy bound separately from absolute cap, explicit and
real-progress clears, rejection of unknown/nonstring/missing status, cancellation
and unchanged side-effect evidence. Finalizer73744 reached its300s process bound
after writing its completion report; root treats its file as an artifact, not a
successful subprocess outcome, and independently reran tests on final bytes.

Remaining limitations: requesting needs separate evidence; persisted diagnostics
do not yet distinguish a declared window; actual live incident cause is unknown.
No broader provider compatibility or reliability closure follows from this fix.
As-built provider-routing scenario is included. Deployment, original rendered
retest and clean-user-use observation remain release/acceptance gates. Reverting
this patch restores prior normalization without data migration.
