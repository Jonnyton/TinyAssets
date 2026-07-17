"""Shared test double for the Codex S3 r17/r18/r19 isolated-executor contract.

A sandbox-required adapter (source_exec / repo_read / coding+prompt_template / …)
is DISPATCHED to a TYPED :class:`tinyassets.sandbox_policy.IsolatedExecutor` as a
SERIALIZABLE, JSON-VALIDATED execution request (data — node spec + inputs + the
complete effective context: state schema, effective llm_policy, concurrency
budget, an OPAQUE workspace reference, and an OPAQUE job-scoped credential grant;
NO callable, NO raw host path, NO forgeable universe id). The isolated worker
resolves the opaque refs, compiles + executes the node INSIDE itself, and returns
a TYPED response ENVELOPE (``status`` ok | error | cancelled). In production Phase
1 no executor exists, so the daemon REFUSES every sandbox-required adapter and
holds no in-process adapter callable (verified by
``test_patch_loop_sandbox_enforcement``).

Mechanics tests (source_code / opaque-adapter / in-node-enqueue / draft_patch
coding+prompt_template behavior) need the adapter to actually run. They install
``WorkerSimExecutor`` (a PROPER TYPED executor) AND a TEST credential broker (a
signed/expiring, single-universe-scoped grant issuer + redeemer). The worker's
``dispatch`` reconstructs the node + full context from the request, REDEEMS the
opaque credential grant to a SCOPED provider context (failing closed for a
missing / malformed / expired / cross-universe grant), and runs the node AS the
isolated worker would (in a test the worker is in-process and uses the PURE
adapter builders, not the daemon's gated ``_build_node``). This exercises the real
dispatch contract end-to-end — proving the request carries enough to run a node,
that credentials are scope-bound at the worker boundary, and that the daemon
reconstructs a remote failure — without patching out the security gate.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Test credential broker (stand-in for the vault-broker workstream's primitive).
#
# Codex S3 r19 #1/#4: the worker must redeem an OPAQUE, JOB-SCOPED grant to a
# SCOPED credential context and FAIL CLOSED for a missing / malformed / expired /
# cross-universe (forged) grant. The real broker is owned by the credential-vault
# slice; this test double implements the SAME shape (HMAC-signed, expiring,
# single-universe) so the dispatch seam can be exercised without inventing a
# parallel production store. S3 CONSUMES the seam; it does not implement the real
# broker.
# --------------------------------------------------------------------------- #

_TEST_BROKER_KEY = b"s3-test-broker-hmac-key"
# Redemption spy: each successful redemption appends its resolved universe dir, so
# the two-universe isolation test can assert WHICH universe each dispatch bound to
# (proving B never resolves A's scope).
_REDEEMED_UNIVERSE_DIRS: list[str] = []


def redeemed_universe_dirs() -> list[str]:
    """The universe dirs redeemed since the broker was installed (spy for tests)."""
    return list(_REDEEMED_UNIVERSE_DIRS)


def _test_issue_grant(*, run_id: str, universe_dir: "str | Path | None") -> "str | None":
    """Issue an OPAQUE, signed, expiring, single-universe grant (test broker)."""
    if universe_dir is None or not str(universe_dir).strip():
        return None  # unscoped run → no grant → worker fails closed
    payload = {
        "run_id": run_id,
        "universe_dir": str(universe_dir),
        "exp": time.time() + 3600.0,
    }
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    sig = hmac.new(_TEST_BROKER_KEY, body, hashlib.sha256).hexdigest()
    return "grant:" + base64.urlsafe_b64encode(body).decode("ascii") + "." + sig


def _test_redeem_grant(grant: Any) -> Any | None:
    """Redeem a signed grant to a SCOPED ``UniverseContext``; FAIL CLOSED (``None``)
    for a missing / malformed / tampered / expired grant (test broker)."""
    if not isinstance(grant, str) or not grant.startswith("grant:"):
        return None  # missing / wrong shape / a raw forgeable universe id
    try:
        b64, sig = grant[len("grant:"):].split(".", 1)
        body = base64.urlsafe_b64decode(b64.encode("ascii"))
        expected = hmac.new(_TEST_BROKER_KEY, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None  # tampered / forged signature
        payload = json.loads(body.decode("utf-8"))
        if float(payload.get("exp", 0.0)) < time.time():
            return None  # expired
        universe_dir = payload.get("universe_dir")
        if not universe_dir:
            return None
    except Exception:  # noqa: BLE001 — any malformation ⇒ fail closed
        return None
    from tinyassets.providers.base import UniverseContext

    _REDEEMED_UNIVERSE_DIRS.append(str(universe_dir))
    return UniverseContext(universe_dir=Path(universe_dir), config=None)


def install_test_credential_broker(monkeypatch: Any) -> None:
    """Install the test credential broker over the Phase-1 fail-closed seams so a
    valid grant redeems to a scoped context and a bad grant fails closed. Resets
    the redemption spy."""
    import tinyassets.credential_vault as cv

    _REDEEMED_UNIVERSE_DIRS.clear()
    monkeypatch.setattr(cv, "issue_job_credential_grant", _test_issue_grant)
    monkeypatch.setattr(cv, "redeem_job_credential_grant", _test_redeem_grant)


class WorkerSimExecutor:
    """A TYPED :class:`IsolatedExecutor` that simulates the Phase-2 worker
    IN-PROCESS: it declares supported capabilities + request schema, resolves the
    request's OPAQUE workspace + credential references, then compiles the node spec
    (with the reconstructed effective context) and executes it, returning a TYPED
    response ENVELOPE."""

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

        try:
            result = self._run(request)
        except Exception as exc:  # noqa: BLE001 — REMOTE failure ⇒ typed envelope
            # Codex S3 r19 #3: a worker-side failure is reported as a typed
            # ENVELOPE (real cross-process IPC), NOT an in-process raise, so the
            # daemon RECONSTRUCTS the remote failure from the envelope. A
            # cancellation (detected by exception-class name, as the daemon does)
            # maps to status="cancelled".
            status = "cancelled" if gc._is_cancel_exception(exc) else "error"
            return gc.make_execution_response(
                status=status,
                error={"type": type(exc).__name__, "message": str(exc)},
            )
        return gc.make_execution_response(status="ok", result=result)

    def _run(self, request: dict[str, Any]) -> dict[str, Any]:
        import functools

        import tinyassets.graph_compiler as gc
        from tinyassets import credential_vault, sandbox_policy
        from tinyassets.branches import NodeDefinition

        # WORKER-SIDE request validation (Codex S3 r20 #4): the worker re-validates
        # the strict-JSON discriminated contract before acting on it — it does not
        # trust the transport to have validated.
        gc.validate_execution_request(request)
        node = NodeDefinition.from_dict(request["node_spec"])
        inputs = request.get("inputs", {}) or {}
        ec_dict = request.get("enqueue_context")
        enqueue_context = gc.NodeEnqueueContext(**ec_dict) if ec_dict else None
        # OPAQUE workspace ref → the worker's OWN workspace path (never a host path
        # in the request). Resolution is bound to THIS job's run_id + executor
        # audience → a replayed / cross-job ref fails closed (Codex S3 r19 #3 / r20 #3).
        base_path = sandbox_policy.resolve_workspace_ref(
            request.get("workspace_ref") or "",
            run_id=request.get("parent_run_id", "") or "",
            audience=request.get("capability_class", "") or "",
        )
        depth = int(request.get("invocation_depth", 0) or 0)
        state_schema = request.get("state_schema") or []
        effective_llm_policy = request.get("effective_llm_policy")
        concurrency_budget = request.get("concurrency_budget")

        # REDEEM the OPAQUE, job-scoped credential grant to a SCOPED provider
        # context. Codex S3 r19 #1/#4:
        #   - SCOPED run (``credential_scope_required`` — the daemon had an
        #     AUTHORITATIVE universe binding): the worker MUST redeem the grant to
        #     the run's OWN scope, and FAIL CLOSED (raise) for a missing / malformed
        #     / expired / cross-universe (forged) grant — NEVER fall back to
        #     process-global creds for a scoped run (the exact defect r19 #1 flags).
        #   - GENUINELY UNSCOPED legacy single-universe run (no bound tenant, no
        #     grant): the process-global provider is acceptable — there is no bound
        #     tenant to leak (matches ``api/runs.py::_run_universe_context``).
        from tinyassets.providers.call import call_provider

        provider_call = None
        credential_grant = request.get("credential_grant")
        scope_required = bool(request.get("credential_scope_required"))
        if scope_required or credential_grant is not None:
            scoped = credential_vault.redeem_job_credential_grant(credential_grant)
            if scoped is None:
                raise PermissionError(
                    "isolated worker could not redeem the job credential grant for a "
                    "scoped run (missing/malformed/expired/cross-universe) — fail closed."
                )
            provider_call = functools.partial(
                call_provider, universe_context=scoped,
            )
        else:
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
    declares its capabilities + schema) AND install the TEST credential broker so a
    dispatched grant redeems to a scoped context. The daemon's fail-closed default
    (no executor) and the data-not-code contract stay intact — this installs a
    genuine Phase-2-shaped executor + broker, it does NOT bypass the gate."""
    import tinyassets.sandbox_policy as sp

    install_test_credential_broker(monkeypatch)
    monkeypatch.setattr(
        sp, "resolve_isolated_executor", lambda cls: WorkerSimExecutor(cls),
    )
