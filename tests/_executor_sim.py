"""Shared test double for the Codex S3 r17/r18 isolated-executor contract.

A sandbox-required adapter (source_exec / repo_read / coding+prompt_template / …)
is DISPATCHED to a TYPED :class:`tinyassets.sandbox_policy.IsolatedExecutor` as a
SERIALIZABLE execution request (data — node spec + inputs + the complete effective
context: state schema, effective llm_policy, concurrency budget, a serializable
provider-bridge reference; NO callable); the isolated worker compiles + executes
it INSIDE itself. In production Phase 1 no executor exists, so the daemon REFUSES
every sandbox-required adapter and holds no in-process adapter callable (verified
by ``test_patch_loop_sandbox_enforcement``).

Mechanics tests (source_code / opaque-adapter / in-node-enqueue / draft_patch
coding+prompt_template behavior) need the adapter to actually run. They install
``WorkerSimExecutor`` — a PROPER TYPED executor that DECLARES its supported
capabilities + request schema and whose ``dispatch(request)`` reconstructs the
node + full context from the request and runs it AS the isolated worker would (in
a test the worker is in-process, and the worker uses the PURE adapter builders,
not the daemon's gated ``_build_node``). This exercises the real dispatch contract
end-to-end — proving the request carries enough to run a node — without patching
out the security gate.
"""
from __future__ import annotations

from typing import Any


class WorkerSimExecutor:
    """A TYPED :class:`IsolatedExecutor` that simulates the Phase-2 worker
    IN-PROCESS: it declares supported capabilities + request schema, then compiles
    the serializable request's node spec (with the reconstructed effective context)
    and executes it, returning the state updates."""

    def __init__(self, executor_class: str) -> None:
        self.executor_class = executor_class

    def supports(self, capability_class: str) -> bool:
        # This test worker handles every sandbox-required class it is resolved for.
        return capability_class == self.executor_class

    def supported_request_schema_versions(self) -> frozenset[int]:
        from tinyassets.graph_compiler import EXECUTION_REQUEST_SCHEMA_VERSION

        return frozenset({EXECUTION_REQUEST_SCHEMA_VERSION})

    def is_healthy(self) -> bool:
        return True

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        import tinyassets.graph_compiler as gc
        from tinyassets.branches import NodeDefinition

        node = NodeDefinition.from_dict(request["node_spec"])
        inputs = request.get("inputs", {}) or {}
        ec_dict = request.get("enqueue_context")
        enqueue_context = gc.NodeEnqueueContext(**ec_dict) if ec_dict else None
        base_path = request.get("base_path") or None
        depth = int(request.get("invocation_depth", 0) or 0)
        state_schema = request.get("state_schema") or []
        effective_llm_policy = request.get("effective_llm_policy")
        concurrency_budget = request.get("concurrency_budget")
        provider_ref = request.get("provider_ref")

        # Reconstruct the provider bridge from the SERIALIZABLE reference (never a
        # callable). In a test the platform provider is the mock (conftest sets
        # force_mock); a real worker would rebind its OWN scoped provider.
        provider_call = None
        if provider_ref and provider_ref.get("kind") == "platform_call_provider":
            from tinyassets.providers.call import call_provider

            provider_call = call_provider
        concurrency_tracker = (
            gc.ConcurrencyTracker(concurrency_budget)
            if concurrency_budget else None
        )

        # Inside the isolated worker, build the adapter DIRECTLY via the PURE
        # builders (the worker IS the isolated boundary) — NOT _build_node's gate.
        if (node.prompt_template or "").strip():
            fn = gc._build_prompt_template_node(
                node, provider_call=provider_call, event_sink=None,
                state_schema=state_schema, llm_policy=effective_llm_policy,
                concurrency_tracker=concurrency_tracker,
            )
        elif (node.source_code or "").strip():
            fn = gc._build_source_code_node(
                node, event_sink=None, invocation_depth=depth,
                base_path=base_path, enqueue_context=enqueue_context,
                concurrency_tracker=concurrency_tracker,
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
    :class:`WorkerSimExecutor` (a TYPED, healthy, dispatch-available executor that
    declares its capabilities + schema), so mechanics tests exercise the real
    serializable-request dispatch. The daemon's fail-closed default (no executor)
    and the data-not-code contract stay intact — this installs a genuine
    Phase-2-shaped executor, it does NOT bypass the gate."""
    import tinyassets.sandbox_policy as sp

    monkeypatch.setattr(
        sp, "resolve_isolated_executor", lambda cls: WorkerSimExecutor(cls),
    )
