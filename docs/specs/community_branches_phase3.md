---
status: shipped
shipped_date: 2026-04-12
shipped_in: c85efa1  # Community Branches Phases 2-5 + cross-universe cluster + user-sim harness
---

# Community Branches Graph Runner — Shipped Spec

**Status:** shipped in `c85efa1` (2026-04-12)
**Depends on:** MCP builder surface, #29 (execution action gap)
**Unblocked:** eval + iteration, multi-domain validation of engine thesis

## Goal

Compile a validated `BranchDefinition` into a live LangGraph + SqliteSaver and run it against user-supplied inputs. Output must be observable step-by-step so evaluation and iteration can judge runs. Long runs must checkpoint and resume. Non-fantasy domains (research workflow, recipe tracker, etc.) must run end-to-end without any fantasy-specific node being required.

## Design decisions

1. **Compiler is a pure function.** `BranchDefinition → StateGraph` lives in `tinyassets/graph_compiler.py`. No side effects. Takes a validated branch + resolved tool allowlist, returns a compiled StateGraph. Compiler failures are programmer errors, not user errors (user errors are caught by `validate_branch`).

2. **TypedDict synthesized at runtime.** The state_schema JSON blob is materialized into a dynamic TypedDict with `Annotated[list, operator.add]` for `reducer=append` fields, `Annotated[dict, dict_merge]` for `merge`, plain field for `overwrite`. Honors PLAN.md hard rule #5.

3. **Separate runtime per run, shared SqliteSaver backend.** Aligns with PLAN.md "Swarm runtime": runtime capacity and identity are separate. Each `run_branch` call spawns a fresh LangGraph `Runnable` with a unique `thread_id`, but all checkpoints land in one shared `output/.runs.db` (SqliteSaver only — not Async). The fantasy daemon's own runtime is untouched.

4. **Sandbox model mirrors existing `extensions` approval.**
   - `prompt_template` nodes: always safe. Rendered with `str.format_map(state)`, sent to provider via role-router. No user code execution.
   - `source_code` nodes: require host `approved=True` (existing NodeDefinition field). Unapproved source-code nodes are rejected at compile time, not runtime. The existing `_ext_register` dangerous-pattern guard (`os.system`, `subprocess`, `eval`, `exec`, `__import__`) still applies.
   - Conditional edges run a predicate synthesized from the source node's `output_keys` — no user-code routing function in v1. Routing reads a single declared output key and maps its value through the `conditions` dict. Richer routers are future work.

5. **Runs are async by default.** Phone-based users cannot hold a 30-minute chat open. `run_branch` returns immediately with a `run_id`; execution happens in a background task within the TinyAssets Server process. Clients poll `get_run` or call `stream_run` for incremental updates.

## MCP actions (extend `extensions` tool)

- `run_branch(branch_def_id, inputs_json, run_name?)` — start a run. Inputs are validated against state_schema. Returns `{run_id, status: "queued"}`.
- `get_run(run_id)` — return run metadata + state snapshot + per-node trace. One-shot, phone-legible.
- `list_runs(branch_def_id?, status?, limit?)` — summaries only (run_id, branch name, status, started_at, last_node).
- `cancel_run(run_id)` — cooperative cancel; sets a flag the node loop checks between steps.
- `stream_run(run_id, since_step?)` — poll for new step events since cursor. Phone-friendly (no SSE required). Returns new trace events + current status.
- `get_run_output(run_id, field_name?)` — extract final state, optionally one field. Avoids dumping huge state blobs.

## Observability contract

Every step emits a `RunStepEvent`: `{run_id, step_index, node_id, started_at, finished_at, status, input_snapshot, output_snapshot, tool_calls, error?}`. Events land in `output/.run_events.db` (SQLite, one row per event). This is the backbone for evaluation and iteration — without per-step diffs users cannot identify which node produced weak output.

Tool calls made by prompt_template nodes are recorded with arguments + return value (truncated to 2KB per field). Source_code nodes run inside a subprocess that pipes a structured event stream back to the parent.

## Scope cuts

**Shipped scope:** the 6 MCP actions above, the compiler, async runner with checkpointing, step event emission, cooperative cancel.

**Deferred scope:** side-by-side run comparison, per-node quality scoring, re-run from checkpoint with edits, human-in-the-loop interrupts. Rerunning a whole branch from scratch after an edit is acceptable for v1.

**Defer permanently unless proven needed:** multi-tenant runtime quotas, cross-host runtime (PLAN.md "multi-host destination" is a separate architecture track), custom Python routing functions for conditional edges.

## Risk & dependencies

- **#29 (no execution action)** — this spec addressed that gap.
- **#22 (commit write-back)** — done. This spec did not touch commit pipeline.
- **#15 (cross-universe context leak)** — same threat surface here. The runner MUST use `thread_id = run_id` exclusively and MUST NOT read any universe state unless a node explicitly declares it. Flag during review.
- **Source-code sandbox escape risk.** The existing regex guard is weak (blocks `subprocess` in source text but not `__builtins__['sub'+'process']`). Keep host approval as primary defense and treat pattern checks as belt-and-suspenders. A proper sandbox (resource limits, restricted builtins) is future work, tracked as a new concern.
- **SqliteSaver contention.** PLAN.md hard rule #1 is SqliteSaver-only. Many concurrent runs share one DB file. WAL mode is required; add to compiler init.

## Acceptance criteria

1. Recipe-tracker branch from the builder-surface vignette runs end-to-end via `run_branch`, produces a final state readable via `get_run_output`.
2. A long-running branch (>60s) checkpoints correctly: killing the server mid-run, restarting, and resuming via a resume action (or rerunning with same thread_id) picks up at the last committed node.
3. `stream_run` returns incremental events legibly on a phone — each event is ≤ 3 short lines.
4. Unapproved source_code node is rejected at `run_branch` time with a clear error, not silently executed.
5. Two runs of different branches on the same host do not bleed state between each other (thread isolation test).
6. No fantasy-domain imports required to run a non-fantasy branch.
