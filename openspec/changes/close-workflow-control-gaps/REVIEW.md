# Review and reproduction state

September 9 UTC. No runtime edits yet; branch codex/close-workflow-control-gaps
starts from c2ed4534 (runtime 8f1b4760). Independent Claude shape/basic-safety
review dispatched with eight-minute timeout to `output/workflow-gaps-shape-review.md`.
Command: `python scripts/peer_agent.py claude --out output/workflow-gaps-shape-review.md --prompt-file output/workflow-gaps-shape-brief.md --timeout 480`.
Claude completed exit 0 after 282 seconds: VERDICT ADAPT. Its self-contained
final artifact confirms all five source anchors and gives four bounded
adaptations, incorporated in design/spec before runtime edits:
keep the existing edit-field restrictions but correct all four wrong operation
strings; pass separate compiler ancestry to workspace only; use bounded exact
output chunks; emit failed code events with the same graph key as starting.
Basic-safety blocker added to scope: existing served run read drops the pin and
can admit another public universe's run. Require uniform not-found graph-match
checks for existing run, output and cancel, then normal ACL. Cancel guidance
must also stop claiming cancellation is unavailable. No tests run by reviewer.

Baseline Windows command:
`python -m pytest -q tests/test_engine_mcp_write_graph_patch.py tests/test_engine_mcp_server.py tests/test_api_runs.py tests/test_workspace_effector.py tests/test_cancel_reaches_the_running_child.py tests/test_queue_cancel_cooperative.py --junitxml=output/workflow-gaps-windows-base.xml`
Result **282 passed, 6 skipped**, 21.28 seconds. This is not Linux proof; the
legacy queue-helper tests also do not establish run cancellation surface behavior.

New two-case real-dispatch workspace regression at unchanged runtime:
`python -m pytest -q tests/test_workspace_effector.py -k discard_uses_graph_ancestry_through_real_dispatch --junitxml=output/workflow-gaps-discard-red.xml`
Result **1 expected failure, 1 pass**: actual creation registers a held workspace
under a graph-instance ID, but legitimate descendant discard falsely refuses
"not one of its graph ancestors" because the HTTP-result map is empty. A parallel
non-ancestor correctly refuses. This reproduces the reported gap without editing
a live workflow or pretending a workspace produced an HTTP result. The first test
draft had an incorrect cleanup-helper import; corrected to the existing chain
settle method before this substantive red result. Test data root is explicitly
temporary and outside the repository.

Source localization also finds ordinary output omitted by _compose_run_snapshot,
existing legacy output/cancel implementations, wrong patch_node prose versus
update_node vocabulary, and missing code failure event emission. Those are
source findings pending their own executable regression and end-to-end proof.
The primitive checker reports false-negative CLEAN for legacy cancel/output
actions; reuse actual inspected handlers, do not invent duplicates.

Failed-event baseline: `python -m pytest -q tests/test_graph_compiler_failed_event.py --junitxml=output/workflow-gaps-failed-event-base.xml`
reported 9 passed. Two new real-child code-failure cases (same ID and distinct
graph/definition IDs) fail because no failed node event is recorded. The initial
test draft lacked branch authorship and correctly refused foreign code; giving
the fixture its actual actor as author reaches the intended error and reproduces
the missing event without bypassing production authorship. The local launcher
override exists only in the isolated test; production sandbox remains unchanged.

## Initial candidate, not ready to ship

Separate trusted ancestry now reaches workspace create/push/discard; direct
internal callers and the two prior ancestry tests use the new keyword rather
than HTTP-result membership. The full workspace effector suite passes 144 tests
with its two unchanged Windows skips (9.07 seconds); the new real-dispatch valid
and sibling cases pass. Linux proof remains required.

Code failure now emits the existing failed event and graph-instance wrappers
normalize starting/terminal event identity. Both real-child regression cases pass.
Five (not four) wrong patch_node guidance strings were found and corrected;
unknown-op guidance supplies a payload accepted by the actual sanitizer.
Combined failed-event/edit/API suite: 51 passes, 18 deprecation warnings before
the final guidance relational test addition. More parallel/cancel/timeout and
real owned-branch coverage is still required; these changes are not live.

Remaining implementation: shared pinned run-scope checks, exact bounded output
catalog/field reads, and reachable cancellation with actual queued/running/
terminal semantics. No review is running now: shape review finished. No app
prompt has been sent since the owner's read-only inspection.

Final partial candidate Windows check, September 9 UTC:
`python -m pytest -q tests/test_engine_mcp_write_graph_patch.py tests/test_engine_mcp_server.py tests/test_api_runs.py tests/test_workspace_effector.py tests/test_cancel_reaches_the_running_child.py tests/test_queue_cancel_cooperative.py tests/test_graph_compiler_failed_event.py --junitxml=output/workflow-gaps-partial-head.xml`
reported **296 passed, 6 skipped**, 18 deprecation warnings, 19.33 seconds.
This equals 282 original passes + 9 existing failed-event cases + 5 new cases.
Ruff on the nine changed canonical/test files passes, generated six-file plugin
mirror rebuild/import passes, strict OpenSpec and diff check pass. No Linux
candidate proof or exact-head code approval yet; do not push this partial branch
as ready or deploy it before output/cancel/scope work and the remaining proof.
