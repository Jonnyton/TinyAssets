# Claude post-live cancelled-node shape review

September 9, 2026 UTC, against deployed00826957 plus uncommitted red tests/design;
no runtime follow-up edits existed when dispatched. Command:
`python scripts/peer_agent.py claude --out output/workflow-cancel-node-shape-review.md --prompt-file output/workflow-cancel-node-shape-brief.md --timeout 480`.
Completed exit0 after219seconds. Substantive review recovered verbatim from the
same Claude session f6591172-2040-4607-8b2a-846c8c15bd06 because the final wrapper
output contains a stop-hook acknowledgement. Not an exact-head code approval.

**AGREE** with the proposed shape. The four cited anchors check out, and every piece the fix needs is already in place except the phase itself.

**Evidence, per anchor**

- `tinyassets/graph_compiler.py:2186-2192` raises `NodeCancelledError` with no event. The plain-failure branch six lines later calls `_emit_failed_event` first. The sandbox sets `cancelled=True` only on the `outcome == "cancelled"` branch at `tinyassets/node_sandbox.py:2686-2695`, so gating the new event on that flag already means "actual sandbox cancel", with no string matching.
- The instance wrapper at `tinyassets/graph_compiler.py:3301-3307` rewrites `node_id` and forwards `**detail` untouched. A new `phase="cancelled"` kwarg inherits graph-instance identity for free. No new normalization code.
- Both translators (`tinyassets/runs.py:3492-3505` and `5176-5189`) return early only for starting, effect and failed. Anything else falls into the cancel check before the ran write. A cancelled event emitted without a translator branch would therefore hit `is_cancel_requested` as true and raise from inside the sink, and nothing would be recorded. The translator branch is required, not a nicety, and it must return early exactly like `failed`.
- `build_node_status_map` at `tinyassets/runs.py:5424-5431` gives unknown statuses priority 0, so a recorded cancelled row still loses to `running`. The fold change is required too.
- `api/runs.py:353-363` maps unknown statuses to the `pending` class, not `running`. Without a `cancelled` class the diagram reads "never executed" while the structured list says cancelled. That is a contradiction the retest agent could flag.

**Storage-shape blocker: none.** `run_events.status` is unconstrained `TEXT NOT NULL` (`tinyassets/runs.py:972`), `record_event` writes the string verbatim, `RunStepEvent.status` is a bare `str`. A grep across `tinyassets/` for hard-coded `{ran, failed}` terminal sets found no readers, and the only read-time relabel (`api/runs.py:1191-1199`) is gated on run status `failed`, so it cannot touch a cancelled run. No as-built spec enumerates the node-status vocabulary. This is a dynamic string addition, nothing more.

**Smallest change**

1. `graph_compiler.py` before the raise at 2189: emit `event_sink(node_id=node.node_id, phase="cancelled", error=..., error_type="NodeCancelledError")`, wrapped like `_emit_failed_event` so a sink exception does not swallow the cancel. Do not touch the timeout or workspace-timeout branches.
2. `runs.py`: add `NODE_STATUS_CANCELLED = "cancelled"`, a `phase == "cancelled"` early-return branch in both translators mirroring `failed`, and `NODE_STATUS_CANCELLED: 2` in the fold priority.
3. `api/runs.py`: add `"cancelled"` to `status_classes` plus one `classDef`. Also key the diagram on `branch.graph_nodes` (fallback to `node_defs`) because `_compose_run_snapshot:1182` keys statuses by instance id while the diagram looks up definition ids. Any branch with distinct ids renders every node grey today. The regression test's own branch has that shape, so the spec scenario about diagrams cannot pass without it.

**Between-node cancel: yes, handle it, and the honest minimal handling is a reorder.** In both translators the `is_cancel_requested` check runs before the `ran` row is written. A node that finishes normally while a cancel is pending is never recorded as ran and shows `running` under a cancelled run, which is the same complaint on a different timing. Move the check below `record_event(... NODE_STATUS_RAN ...)`. The node did run, its output is real, and the raise still propagates the same way through `graph_compiler.py:2230-2231`. Two lines per translator, no lifecycle rewrite.

**Test requirements**

- Keep the strengthened assertion at `tests/test_graph_run_controls.py:211-212` and confirm it is red on the unfixed tree. Add: the cancelled event row carries `node_id == "instance"` (not `definition`) and `error_type == "NodeCancelledError"`, proving identity and origin rather than inference.
- Sibling preservation through the real runner: sequential fast A then sleeping B then C, cancel during B. Assert A `ran`, B `cancelled`, C `pending`, run `cancelled`.
- Between-node path: reuse the existing sandbox override in that test to pass `should_cancel=lambda: False`, request cancel after the child starts, let the node finish. Assert node `ran`, run `cancelled`, nothing left `running`.
- Pure fold test on `build_node_status_map`: running then cancelled gives cancelled; a stale running after cancelled does not regress it; a `ran` sibling is untouched.
- Mermaid test with instance id different from definition id: output contains `class <instance> cancelled` and the `classDef cancelled` line.
- Resume translator: cover it through an existing interrupt-and-resume fixture if one has a code node. If none exists, record that gap in tasks.md explicitly rather than claim it verified.

VERDICT: APPROVE
