# Community watcher crash-boundary follow-up

September 19, 2026, 09:24 UTC. Root continues this existing change on
`codex/monitor-unavailable-signal`. This is not implementation or release proof.
Independent Fable review81809 identified the empty-output silent-monitor case;
its full artifact remains `output/community-typed-review.md` in this worktree.
Source freshness ordering and independent scheduler cadence remain separate.

Red-first Windows Python 3.14 command:
`python -m pytest -q tests/test_community_watch_result_boundary.py --tb=short`
reports 16 failed in 1.52s. Tests execute the actual workflow inline parser.
Empty/malformed output raises before outputs exist, `{}` defaults to red,
and incomplete `{"overall":"green"}` is accepted as recovery evidence.
The workflow lacks a distinct unavailable-monitor failure gate. No live crash,
incident mutation or workflow implementation change was performed.

Minimum proposed correction: validate the producer's existing version2 dict,
recognized overall, actual integer exit_code and stages list against the actual
process exit. Unrecognized/incomplete/inconsistent data emits overall unknown
and internal monitor_status unavailable. Valid green/yellow/unknown exit0,
measured red exit2 and structured GitHub evidence-read red exit3 keep current
semantics. A final always-run job gate fails unavailable/missing output even
though the watch step uses continue-on-error. Existing alarm-sink unknown means
zero REST mutations; a monitor crash must not manufacture an endpoint failure
or recovery. Use the inline parser and existing Actions outputs, not new runtime
state, public API, workflow, credentials or notification authority.

If parsing or writing outputs itself fails, absent monitor_status/overall still
reaches the final unavailable gate. Ordinary positively classified unknown
coverage remains a successful classification, unlike an unavailable watcher.
Keep diagnostic raw output in the summary with existing delimiter protection.

Independent pre-build disposition precedes workflow edits. Then parser/gate
tests, actual alarm JavaScript no-mutation controls, actionlint, exact-head
review, required CI and hosted normal-path execution gate landing. Failure-path
injection stays isolated; do not induce a live crash/false incident for proof.
This slice does not close natural cron, execution quality or rendered coverage.
