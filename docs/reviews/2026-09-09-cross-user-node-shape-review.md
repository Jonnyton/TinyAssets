# Cross-user node delivery — first independent shape review

September 9, 2026, local Windows source/design, no production writes. Reviewed
draft committed as 82398741 on `codex/connect-cross-user-nodes`. No runtime change.
Command: `python scripts/peer_agent.py claude --timeout 420 --out
output/cross-user-node-shape-review.md --prompt-file
output/cross-user-node-shape-review-brief.md`. One read-only dispatch, no nested
agents requested. Exec session31932 completed exit0 after381 seconds at08:40 UTC.
The output file contains a stop-hook closing note and ADAPT verdict. Recovered
the substantive review from the SAME session26770c65-783e-432a-a484-f38c3aa23d6b;
no replacement review was dispatched. No live review process remains.

## Verdict and disposition

**ADAPT**, five pre-build findings. The reviewer agrees the selected-node,
selected-sender, copy-not-share goal fits PLAN and needs no new top-level handle.
This is not runtime/landing/deployment approval.

1. **Queued row is not a durable work queue.** Agree, independently verified in
   `_execute_branch_core` and `recover_in_flight_runs`. Revised design makes the
   committed delivery the intent, with a unique `(delivery_id, attempt)` run
   reservation and reconciliation through the existing executor. Never-started
   recovery must differ from interrupted/ambiguous execution; do not blindly
   restart possibly executed side effects. Exact fenced dispatch seam remains
   pre-build work. The existing assigned consumer is automation-only, not a
   drop-in universal delivery worker.
2. **No production sandbox artifact-handle boundary exists.** Agree; authoring's
   handles require owner/session and are not runtime file inputs. Design now
   explicitly requires a run-owned immutable read-only input bundle. Reuse safe
   file descriptors, atomic staging and byte-accounting helpers, not a pretend
   writable checkout. Adapt reviewer suggestion: an ancestor registry keyed only
   to the entry would exclude the receiving node itself; entry plus downstream
   scope must be explicit. Keep exact large-file access, not base64-only scope.
   Actual descriptor/reader and reservation interfaces remain pre-build work.
3. **Declared node effects fire once per run, not per loop iteration.** Agree,
   verified in effectors `fire_node_effects` (`effect_already_fired`). Preserve
   that rule for declared delivery effects. Do not take the offered deferral of
   per-iteration sends: user-authored explicit delivery RPC with stable occurrence
   IDs supports repeated loop deliveries without widening the existing effect rule.
4. **Reject invalid projections at exposure time.** Agree. Validate topology,
   missing input contract and workspace ancestor references when exposing/revising
   a node, then recheck with actual inputs at acceptance. Do not accept a delivery
   and only later discover a removed workspace predecessor. Preserve authorship.
5. **Sender ledger must not carry receiver run IDs.** Agree, verified the current
   `_dispatch_run_action` run_id target default. Return/ledger delivery_id only;
   receiver privately resolves its own run. Add explicit dispatch/receipt tests.

No founder choice identified by the review. Default-deny selected sender policy,
receiver provider default and non-retractable accepted transfers match the owner
request. Do not convert proposed storage attribution into approval for pricing or
the broader unresolved storage-overhead responsibility decision.

## Progress / next gate

Revised design and spec scenarios reflect these findings. Follow-through in the
design's implementation-interface section resolves the engineering shape: permanent
delivery intent plus unique attempt/run, OS-held attempt lock and pre-execution
durable marker, and parent-mediated run-authorized file chunk reads. Task1.1 is
now closed as design work, not runtime proof. Actual process/recovery/file tests
remain required. Avoid another broad review repeating known findings. Exact-head
cross-family implementation review still gates landing.

The tests-only resolver fix passed 53 focused tests in the originally failing
order, 74 with reverse order plus file I/O, and Ruff. Those results establish a
usable local oracle, not cross-user delivery implementation or live acceptance.

## First implementation unit — September 9, 08:57 UTC

`tinyassets/graph_ingress.py` provides a detached selected-node projection, source
and snapshot hashes, precise required-input preflight and retained-workspace-
ancestor checks. It performs no storage write, provider call, exposure grant or
enqueue. Consumers receive fresh BranchDefinition copies from the pinned JSON;
the original user definition is not mutated. Valid selected components do not
require repair of unrelated unreachable components. Reachable dangling edges,
duplicate placements, exitless cycles and routes back to START are refused.

`tests/test_receiver_projection.py` first failed collection because the capability
did not exist. The first invocation fixture had a one-argument fake provider where
the real bridge supplies prompt/system; corrected the fixture, not runtime.
Final Windows/Python3.14 command:

`python -m pytest -q tests/test_receiver_projection.py
tests/test_required_run_input_preflight.py tests/test_graph_compiler_literal_braces.py
tests/test_graph_compiler_reducer_law.py --tb=short`

65 passed, 180 LangGraph deprecation warnings, 4.19 seconds. Includes 24 new tests
with real compiler invocation (test provider only), downstream fan-in, conditional
loop revisits, default inputs, shared definition placements, omitted upstream
effects and detached snapshot checks. The existing three-file group alone passed
41 tests in4.46 seconds; its source and compiler/runs/branches files are identical
to baseline0dd24d59 (empty scoped git diff). Ruff passed for both new files;
plugin runtime rebuilt (397 files), import probe passed and diff check passed.

Initial Linux oracle command failed before tests because the Docker Linux engine
was offline. `docker desktop start --timeout 45` launched the backend, but its
08:56:03 UTC log confirms a crash while initializing the inference manager:
the local `Docker/run/dockerInference` socket could not be removed/accessed.
All local engines were stopped. Startup/status CLI waiters (sessions76271/48048)
were interrupted after that authoritative terminal failure; no repeated startup,
factory reset, socket deletion, settings change or user-data deletion occurred.
No Linux pass, independent code approval, public exposure or deployment is claimed.
Receiver/link storage and full delivery integration remain unfinished; this local
test-environment failure does not block those implementation tasks.
