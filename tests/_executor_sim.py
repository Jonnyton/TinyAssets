"""Shared test double for the Codex S3 r17 isolated-executor contract.

A sandbox-required adapter (source_exec / repo_read / …) is DISPATCHED to a TYPED
:class:`tinyassets.sandbox_policy.IsolatedExecutor` as a SERIALIZABLE execution
request (data — node spec + inputs + context; NO callable); the isolated worker
compiles + executes it INSIDE itself. In production Phase 1 no executor exists, so
the daemon REFUSES every sandbox-required adapter and holds no in-process adapter
callable (verified by ``test_patch_loop_sandbox_enforcement``).

Mechanics tests (source_code / opaque-adapter / in-node-enqueue behavior) need the
adapter to actually run. They install ``WorkerSimExecutor`` — a TYPED executor
whose ``dispatch(request)`` compiles + runs the request AS the isolated worker
would (in a test the worker is in-process). This exercises the real dispatch
contract without patching out the security gate.
"""
from __future__ import annotations

from typing import Any


class WorkerSimExecutor:
    """A TYPED :class:`IsolatedExecutor` that simulates the Phase-2 worker
    IN-PROCESS: it compiles the serializable request's node spec and executes it
    with the reconstructed run context, returning the state updates."""

    def __init__(self, executor_class: str) -> None:
        self.executor_class = executor_class

    def is_healthy(self) -> bool:
        return True

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        import tinyassets.graph_compiler as gc
        from tinyassets.branches import NodeDefinition

        node = NodeDefinition.from_dict(request["node_spec"])
        inputs = request.get("inputs", {}) or {}
        ec_dict = request.get("enqueue_context")
        enqueue_context = (
            gc.NodeEnqueueContext(**ec_dict) if ec_dict else None
        )
        base_path = request.get("base_path") or None
        depth = int(request.get("invocation_depth", 0) or 0)
        # Inside the isolated worker, build the adapter DIRECTLY (this is the
        # isolated boundary where running it is the whole point) — NOT via
        # _build_node's choke point (the daemon never reaches the adapter builder
        # for a sandbox-required node).
        if (node.source_code or "").strip():
            fn = gc._build_source_code_node(
                node, event_sink=None, invocation_depth=depth,
                base_path=base_path, enqueue_context=enqueue_context,
            )
        else:
            from tinyassets.domain_registry import resolve_domain_callable

            opaque = resolve_domain_callable(
                request.get("domain_id", ""), node.node_id,
            )
            fn = gc._build_opaque_node(node, opaque, event_sink=None)
        return fn(inputs)


def install_worker_sim(monkeypatch: Any) -> None:
    """Point ``resolve_isolated_executor`` at a per-class
    :class:`WorkerSimExecutor` (a TYPED, healthy, dispatch-available executor), so
    mechanics tests exercise the real serializable-request dispatch. The daemon's
    fail-closed default (no executor) and the data-not-code contract stay intact —
    this installs a genuine Phase-2-shaped executor, it does NOT bypass the gate."""
    import tinyassets.sandbox_policy as sp

    monkeypatch.setattr(
        sp, "resolve_isolated_executor", lambda cls: WorkerSimExecutor(cls),
    )
