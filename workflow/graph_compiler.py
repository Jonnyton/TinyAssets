"""Compile a BranchDefinition into a LangGraph StateGraph.

Pure function: ``compile_branch(branch) -> CompiledBranch``. No side effects
beyond the returned object. Failures are programmer errors (invalid inputs)
not user errors — run ``branch.validate()`` first if needed.

The compiler synthesizes a dynamic TypedDict from ``state_schema`` with
``Annotated`` reducers per field, builds node adapters for prompt_template
and (host-approved) source_code nodes, and wires simple + conditional edges.

Design rules (from `docs/specs/community_branches_phase3.md`):
- prompt_template nodes are always safe — rendered via a custom regex
  substitution (see ``_render_template`` + ``_PLACEHOLDER_RE``), NOT
  ``str.format_map``. Single ``{``/``}`` characters are literal; only
  ``{ident}`` matching a valid Python identifier is substituted. Jinja
  ``{{ident}}`` is normalized to ``{ident}`` first. Authors escape
  literal placeholders as ``\\{ident\\}``. Rendered output is sent via
  the role-based provider router.
- source_code nodes require ``approved=True`` on the NodeDefinition.
  Unapproved code raises ``UnapprovedNodeError`` at compile time, not
  runtime, so ``run_branch`` can refuse cleanly.
- Conditional edges use a predicate over a single declared output_key.
  No user-code routers in v1.
"""

from __future__ import annotations

import concurrent.futures
import copy
import json
import logging
import operator
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Callable

from langgraph.graph import END, START, StateGraph

from workflow.branches import BranchDefinition, GraphNodeRef, NodeDefinition
from workflow.exceptions import AllProvidersExhaustedError

logger = logging.getLogger(__name__)

_POLICY_PROVIDER_RETRY_BACKOFF_SECONDS = (2.0, 4.0)


class CompilerError(Exception):
    """Raised when the compiler cannot produce a runnable graph.

    FEAT-006: optionally carries the structured ``chain_state`` and
    ``attempts`` from an underlying ``AllProvidersExhaustedError`` so
    chatbots and the auto-fix loop can see *why* the chain exhausted
    without having to walk ``__cause__`` themselves.
    """

    def __init__(
        self,
        *args: Any,
        chain_state: dict | None = None,
        attempts: list | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.chain_state = chain_state
        self.attempts = attempts


class BranchValidationError(CompilerError, ValueError):
    """Raised when branch structure fails compile-time validation."""


class UnapprovedNodeError(CompilerError):
    """Raised when a source_code node lacks host approval."""


class NodeTimeoutError(CompilerError):
    """Raised when a node's provider/source_code exceeds its timeout_seconds.

    Distinct from a generic CompilerError so the runner can emit a clean
    ``timeout`` event and set run status to ``failed`` with a specific
    reason, instead of the user seeing a silent stall (#61).

    ``node_id`` is exposed as an attribute so callers don't have to parse
    it out of the human-readable message.
    """

    def __init__(self, message: str, *, node_id: str = "") -> None:
        super().__init__(message)
        self.node_id = node_id


class EmptyResponseError(CompilerError):
    """Raised when an LLM provider returns an empty response.

    Distinct from a generic CompilerError so the runner can record a
    ``failed`` node event with ``reason: empty_response`` and surface a
    structured error rather than a generic crash message.

    ``node_id`` is exposed as an attribute mirroring ``NodeTimeoutError``.
    """

    def __init__(self, message: str, *, node_id: str = "") -> None:
        super().__init__(message)
        self.node_id = node_id


class ConcurrencyTracker:
    """Track concurrent node executions for observability + budget enforcement.

    Created per-run by ``compile_branch`` when ``concurrency_budget`` is set.
    Shared across all node callables in a single branch invocation via closure.
    Thread-safe: lock guards active_count + peak.
    """

    def __init__(self, budget: int | None) -> None:
        self.budget = budget
        self._semaphore = threading.Semaphore(budget) if budget else None
        self._lock = threading.Lock()
        self.active_count: int = 0
        self.peak: int = 0

    def acquire(self) -> None:
        if self._semaphore is not None:
            self._semaphore.acquire()
        with self._lock:
            self.active_count += 1
            if self.active_count > self.peak:
                self.peak = self.active_count

    def release(self) -> None:
        with self._lock:
            self.active_count = max(0, self.active_count - 1)
        if self._semaphore is not None:
            self._semaphore.release()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active_now": self.active_count,
                "peak": self.peak,
                "budget": self.budget,
            }


# Shared executor so every timeout-wrapped call doesn't spin up a
# fresh thread. Bounded worker count keeps a runaway graph from
# spawning unbounded threads on a slow provider.
#
# NOTE: when all 8 workers are busy, the 9th submit queues and its
# timeout is measured from submit(), not from worker-allocated-start —
# queued calls can exceed nominal timeout_seconds by the queue wait.
# Fine for single-run today; revisit if multi-run concurrency saturates.
_TIMEOUT_EXECUTOR: concurrent.futures.ThreadPoolExecutor | None = None


def _get_timeout_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _TIMEOUT_EXECUTOR
    if _TIMEOUT_EXECUTOR is None:
        _TIMEOUT_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
            max_workers=8, thread_name_prefix="node-timeout",
        )
    return _TIMEOUT_EXECUTOR


_SHARED_ROUTER: Any = None


def _get_shared_router() -> Any:
    """Return the shared ProviderRouter singleton, or None if not available.

    Lazily imports so test environments without providers don't fail at
    import time.  The router is cached module-level after first import.
    """
    global _SHARED_ROUTER
    if _SHARED_ROUTER is not None:
        return _SHARED_ROUTER
    try:
        from workflow.providers.router import ProviderRouter
        _SHARED_ROUTER = ProviderRouter()
    except Exception:
        pass
    return _SHARED_ROUTER


def _run_with_timeout(
    fn: Callable[[], Any],
    *,
    timeout_s: float,
    node_id: str,
) -> Any:
    """Call ``fn()`` on a worker thread, raise NodeTimeoutError on overrun.

    When a timeout fires, the worker thread is NOT killed — Python has
    no safe way to do that. The provider call keeps running in the
    background (the provider's own subprocess/HTTP timeout is the
    backstop). We return to the graph so the overall run can fail-fast
    instead of hanging the executor.
    """
    executor = _get_timeout_executor()
    future = executor.submit(fn)
    try:
        return future.result(timeout=timeout_s)
    except concurrent.futures.TimeoutError as exc:
        raise NodeTimeoutError(
            f"Node '{node_id}' exceeded {timeout_s:.0f}s timeout. "
            "The provider call may still be running in the background; "
            "its own subprocess/HTTP timeout is the backstop.",
            node_id=node_id,
        ) from exc


def _call_policy_router_with_retry(
    router: Any,
    *,
    role: str,
    prompt: str,
    system: str,
    policy: dict[str, Any],
) -> tuple[str, str]:
    """Retry policy-aware provider dispatch on transient chain exhaustion."""
    attempts = len(_POLICY_PROVIDER_RETRY_BACKOFF_SECONDS) + 1
    for attempt_index in range(attempts):
        try:
            return router.call_with_policy_sync(role, prompt, system, policy)
        except AllProvidersExhaustedError:
            if attempt_index == attempts - 1:
                raise
            delay = _POLICY_PROVIDER_RETRY_BACKOFF_SECONDS[attempt_index]
            logger.warning(
                "Policy provider chain exhausted for role=%s; retrying in %.1fs",
                role,
                delay,
            )
            time.sleep(delay)
    raise AssertionError("unreachable policy provider retry state")


_DANGEROUS_PATTERNS = (
    "os.system", "subprocess", "eval(", "exec(", "__import__",
)

# Phase G preflight §4.1 #5d: stricter list for NodeBid executor.
# Wrapper nodes (Phase D) trust the narrower list — they're
# domain-trusted-callables registered by the host at import time.
# Bid-referenced nodes are adversarially-accessible (anyone can
# post a bid), so the sandbox catches a wider surface. Network-call
# patterns (urllib, requests, socket, http.client) are intentionally
# EXCLUDED — approved nodes may legitimately call LLM APIs.
# Single source of truth: both producer-side + executor-side sandbox
# layers (invariant 1) import from here so the bid-market posture
# can't drift from the wrapper's.
_BID_DANGEROUS_PATTERNS = _DANGEROUS_PATTERNS + (
    "compile(", "open(", "importlib", "pickle", "marshal",
)


def _is_cancel_exception(exc: BaseException) -> bool:
    """Duck-type check for the runner's cancel exception.

    Declared as a name-match so `graph_compiler` has no import dependency
    on `runs` (which imports `compile_branch` from here). Any exception
    class named ``RunCancelledError`` propagates past the event_sink
    catch-all; everything else is logged and swallowed.
    """
    return type(exc).__name__ == "RunCancelledError"


def _emit_failed_event(
    event_sink: Callable[..., None] | None,
    node_id: str,
    exc: BaseException,
) -> None:
    """Emit a terminal failed event before re-raising CompilerError.

    FEAT-006: when the underlying exception carries ``chain_state``
    (an ``AllProvidersExhaustedError``), forward it as a structured
    ``provider_chain`` field on the event so downstream consumers
    (chatbots, auto-fix loop, get_run.events) can read per-provider
    skip reasons without parsing the human-readable error string.
    """
    if event_sink is None:
        return
    chain_state = getattr(exc, "chain_state", None)
    kwargs: dict[str, Any] = {
        "node_id": node_id,
        "phase": "failed",
        "error": str(exc),
        "error_type": type(exc).__name__,
    }
    if chain_state is not None:
        kwargs["provider_chain"] = chain_state
    try:
        event_sink(**kwargs)
    except TypeError:
        # Older event_sink signatures may not accept `provider_chain`;
        # retry without it so a kwarg-mismatch never blocks the failed event.
        try:
            event_sink(
                node_id=node_id,
                phase="failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
        except Exception as sink_exc:  # noqa: BLE001
            if _is_cancel_exception(sink_exc):
                raise
            logger.exception("event_sink raised in %s (failed)", node_id)
    except Exception as sink_exc:  # noqa: BLE001
        if _is_cancel_exception(sink_exc):
            raise
        logger.exception("event_sink raised in %s (failed)", node_id)


def _wrap_provider_failure(node_id: str, exc: BaseException) -> "CompilerError":
    """Wrap a provider-side exception into a ``CompilerError``.

    FEAT-006: when the cause carries ``chain_state`` / ``attempts``
    (an ``AllProvidersExhaustedError`` from the router), copy them
    onto the new ``CompilerError`` and append a compact JSON suffix
    to the error message so chatbots and the auto-fix loop can see
    per-provider skip reasons without walking ``__cause__``.

    Without this, the wrap stringifies the cause to just
    ``"All providers exhausted for role=writer. Daemon should retry
    with backoff."`` and the structured diagnostics are silently
    dropped — the failure mode that makes BUG-097's investigation
    daemon recursively self-block on the same opaque error.
    """
    chain_state = getattr(exc, "chain_state", None)
    attempts = getattr(exc, "attempts", None)
    base_msg = f"Provider call failed in node '{node_id}': {exc}"
    if chain_state is not None:
        try:
            suffix = json.dumps(chain_state, default=str, separators=(",", ":"))
            base_msg = f"{base_msg} [chain_state]: {suffix}"
        except Exception:  # noqa: BLE001
            # Never let a serialization edge case prevent the wrap.
            # `default=str` can re-enter into arbitrary user objects whose
            # ``__repr__`` raises, so the catch must be broad.
            logger.exception(
                "Failed to serialize chain_state on provider failure in %s",
                node_id,
            )
    return CompilerError(base_msg, chain_state=chain_state, attempts=attempts)


def _dict_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Shallow merge reducer for state fields declared ``reducer="merge"``."""
    out = dict(left)
    out.update(right)
    return out


_BUILTIN_TYPES: dict[str, Any] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "any": Any,
}


def _resolve_field_type(type_name: str) -> Any:
    """Map a state_schema ``type`` string to a Python type hint.

    Unknown types fall back to ``Any`` — the spec treats state_schema as an
    unvalidated JSON blob in Phase 2/3. Richer typing is Phase 4+.
    """
    return _BUILTIN_TYPES.get((type_name or "").strip().lower(), Any)


def _build_state_typeddict(schema: list[dict[str, Any]]) -> type:
    """Synthesize a TypedDict class from the branch's state_schema.

    Honors PLAN.md hard rule #5: fields declared with ``reducer="append"`` use
    ``Annotated[list, operator.add]``; ``reducer="merge"`` uses a shallow
    dict merger; anything else overwrites.
    """
    annotations: dict[str, Any] = {}
    for field in schema:
        name = (field.get("name") or "").strip()
        if not name:
            continue
        base_type = _resolve_field_type(field.get("type", "any"))
        reducer = (field.get("reducer") or "").strip().lower()
        if reducer == "append":
            annotations[name] = Annotated[list, operator.add]
        elif reducer == "merge":
            annotations[name] = Annotated[dict, _dict_merge]
        else:
            annotations[name] = base_type

    # Build a plain class-based TypedDict at runtime.
    # We construct it via the functional syntax because class-syntax
    # TypedDict requires name binding at class-definition time.
    from typing import TypedDict as _TypedDict

    return _TypedDict("BranchRuntimeState", annotations, total=False)  # type: ignore[operator]


# ─────────────────────────────────────────────────────────────────────────────
# Node adapters
# ─────────────────────────────────────────────────────────────────────────────


# Placeholder match: ``{ident}`` NOT preceded by a backslash. The
# negative lookbehind is what implements the literal-brace escape —
# templates that want a literal ``{foo}`` in output write ``\{foo\}`` and
# the leading backslash keeps the substitution regex from biting.
_PLACEHOLDER_RE = re.compile(r"(?<!\\){([a-zA-Z_][a-zA-Z0-9_]*)}")
# Matches Jinja/Handlebars-style {{ident}} placeholders. Claude.ai and many
# MCP clients emit this form by convention. We normalize to `{ident}` so
# the single regex-driven substitution below handles both forms.
_DOUBLE_PLACEHOLDER_RE = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")
# Matches ``\{ident\}`` — an explicitly-escaped placeholder. After
# substitution runs (skipping these thanks to ``_PLACEHOLDER_RE``'s
# lookbehind), we strip the backslashes so the rendered output contains
# ``{ident}`` verbatim.
_ESCAPED_PLACEHOLDER_RE = re.compile(r"\\{([a-zA-Z_][a-zA-Z0-9_]*)\\}")


def _normalize_placeholders(template: str) -> str:
    """Convert ``{{ident}}`` Jinja-style placeholders to Python's ``{ident}``.

    Claude.ai-authored templates typically use doubled braces by
    convention. We do the substitution ourselves (see ``_render_template``)
    so non-identifier braces — JSON examples like ``{"doc": "X"}``, code
    fences, math expressions — pass through as literal text.

    ``\\{ident\\}`` (escaped form) is untouched here — the normalizer only
    handles the Jinja→Python alias; the escape handling lives in
    ``_render_template`` + ``_PLACEHOLDER_RE``'s lookbehind.
    """
    if not template:
        return template
    return _DOUBLE_PLACEHOLDER_RE.sub(r"{\1}", template)


def _unescape_literal_braces(template: str) -> str:
    """Strip backslashes from ``\\{ident\\}`` so rendered output carries
    ``{ident}`` as literal text. Runs after placeholder substitution so
    the escape survives the lookbehind-gated rewrite."""
    if not template:
        return template
    return _ESCAPED_PLACEHOLDER_RE.sub(r"{\1}", template)


def _render_template(template: str, state: dict[str, Any]) -> str:
    """Substitute ``{ident}`` placeholders with ``state[ident]`` values.

    Unlike Python's ``str.format``/``str.format_map`` we do not treat
    single ``{`` / ``}`` as special. Literal braces in JSON examples,
    code fences, and math expressions survive verbatim. Only substrings
    matching a valid identifier placeholder (``{name}``) are replaced;
    everything else is left alone.

    Authors who need a literal ``{ident}`` (for example, documenting
    the substitution syntax itself) escape it as ``\\{ident\\}`` — the
    placeholder regex skips escaped forms and the unescape pass strips
    the backslashes after substitution.

    Raises ``KeyError`` if a valid placeholder references a state key
    that is not present — caller maps that to a ``CompilerError``.
    """
    if not template:
        return template

    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in state:
            raise KeyError(key)
        return str(state[key])

    normalized = _normalize_placeholders(template)
    substituted = _PLACEHOLDER_RE.sub(_sub, normalized)
    return _unescape_literal_braces(substituted)


def _missing_state_keys(template: str, state: dict[str, Any]) -> list[str]:
    normalized = _normalize_placeholders(template or "")
    refs = _PLACEHOLDER_RE.findall(normalized)
    return [k for k in refs if k not in state]


def _placeholder_keys(template: str) -> list[str]:
    """Return the set of placeholder identifiers referenced by a template.

    Static analysis — no state lookup, no rendering. Used by
    ``collect_build_warnings`` + the strict-isolation pre-check.
    Escaped ``\\{ident\\}`` forms are NOT placeholders — they render
    literally — so the lookbehind-gated regex naturally excludes them.
    """
    normalized = _normalize_placeholders(template or "")
    # de-dupe while preserving first-occurrence order for stable warnings
    seen: set[str] = set()
    out: list[str] = []
    for k in _PLACEHOLDER_RE.findall(normalized):
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _out_of_input_keys(node: NodeDefinition) -> list[str]:
    """Return placeholder identifiers that reference state keys outside
    the node's declared ``input_keys``.

    Empty list when no input_keys are declared (the node opted out of
    static isolation) or when every placeholder is covered.
    """
    if not node.prompt_template:
        return []
    if not node.input_keys:
        # Node didn't declare an input contract — nothing to check.
        return []
    declared = set(node.input_keys)
    return [k for k in _placeholder_keys(node.prompt_template) if k not in declared]


def collect_build_warnings(branch: BranchDefinition) -> list[dict[str, Any]]:
    """Return non-fatal warnings detected at compile time.

    Currently surfaces one warning per prompt_template node placeholder
    that references a state key outside the node's declared
    ``input_keys``. These leaks are often unintentional and almost
    always reduce the portability of a branch (it implicitly depends on
    producers upstream whose output_keys happen to match the reference).

    Warning shape::

        {
          "kind": "input_keys_leak",
          "node_id": "<id>",
          "placeholder": "<state_key>",
          "declared_input_keys": ["..."],
          "message": "<human-readable>",
        }

    Non-fatal regardless of ``strict_input_isolation`` — the flag
    controls *runtime* rejection. Build-time warnings always surface
    so authors see the leak whether they've opted into strict or not.
    """
    warnings: list[dict[str, Any]] = []
    for node in branch.node_defs:
        leaks = _out_of_input_keys(node)
        for placeholder in leaks:
            warnings.append({
                "kind": "input_keys_leak",
                "node_id": node.node_id,
                "placeholder": placeholder,
                "declared_input_keys": list(node.input_keys),
                "message": (
                    f"Node '{node.node_id}' prompt_template references "
                    f"state key '{placeholder}' which is not in declared "
                    f"input_keys {sorted(node.input_keys)!r}. This is "
                    f"an implicit cross-node dependency that reduces "
                    f"branch portability. Add '{placeholder}' to "
                    f"input_keys, or set strict_input_isolation=false "
                    f"only when the cross-key read is intentional."
                ),
            })
    return warnings


def inspect_node_dry(
    branch: BranchDefinition,
    *,
    node_id: str = "",
) -> dict[str, Any]:
    """Return a side-effect-free structural preview of one node (or all nodes).

    Zero state writes, zero provider calls, zero wiki touches.  Suitable for
    use from ``dry_inspect_node`` MCP action.

    Shape returned per node::

        {
          "node_id": str,
          "node_def": dict,                          # to_dict() snapshot
          "resolved_prompt_template": str | None,    # {{..}} → {..} normalized
          "declared_input_keys": list[str],
          "declared_output_keys": list[str],
          "state_schema_refs": list[str],            # placeholder keys found in template
          "placeholder_validation": {
            "missing": list[str],   # in template but not in state_schema
            "extra": list[str],     # in input_keys but not referenced
            "escaped": list[str],   # \\{ident\\} literals found
          },
          "policy_resolution": {
            "source": "node" | "branch" | "default",
            "effective_policy": dict | None,
            "fallback_chain": list,
          },
          "warnings": list[dict],   # from collect_build_warnings for this node
        }

    If ``node_id`` is empty the return is ``{"nodes": [<shape>, ...]}``.
    If ``node_id`` is given and not found the return is ``{"error": "...", "node_id": node_id}``.
    """
    schema_keys: set[str] = {
        (f.get("name") or "").strip()
        for f in (branch.state_schema or [])
        if (f.get("name") or "").strip()
    }

    def _inspect_one(nd: NodeDefinition) -> dict[str, Any]:
        template = nd.prompt_template or ""
        normalized = _normalize_placeholders(template) if template else ""
        placeholder_keys = _placeholder_keys(template) if template else []
        escaped: list[str] = _ESCAPED_PLACEHOLDER_RE.findall(template) if template else []

        # Keys in template but absent from state_schema
        missing = [k for k in placeholder_keys if k not in schema_keys]
        # Keys declared in input_keys but not referenced in template
        extra = [
            k for k in nd.input_keys
            if k not in placeholder_keys
        ] if nd.prompt_template else []

        # Policy resolution: node > branch > default
        effective_policy = nd.llm_policy or getattr(branch, "default_llm_policy", None)
        if nd.llm_policy is not None:
            policy_source = "node"
        elif getattr(branch, "default_llm_policy", None) is not None:
            policy_source = "branch"
        else:
            policy_source = "default"

        fallback_chain: list[dict[str, Any]] = []
        if isinstance(effective_policy, dict):
            fallback_chain = effective_policy.get("fallback_chain", [])

        # Per-node warnings from the branch-level collector (filter to this node)
        branch_warnings = collect_build_warnings(branch)
        node_warnings = [w for w in branch_warnings if w.get("node_id") == nd.node_id]

        return {
            "node_id": nd.node_id,
            "node_def": nd.to_dict(),
            "resolved_prompt_template": normalized if template else None,
            "declared_input_keys": list(nd.input_keys),
            "declared_output_keys": list(nd.output_keys),
            "state_schema_refs": placeholder_keys,
            "placeholder_validation": {
                "missing": missing,
                "extra": extra,
                "escaped": escaped,
            },
            "policy_resolution": {
                "source": policy_source,
                "effective_policy": effective_policy,
                "fallback_chain": fallback_chain,
            },
            "warnings": node_warnings,
        }

    if node_id:
        nd = branch.get_node_def(node_id)
        if nd is None:
            return {"error": f"Node '{node_id}' not found.", "node_id": node_id}
        return _inspect_one(nd)

    return {"nodes": [_inspect_one(nd) for nd in branch.node_defs]}


_JSON_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _state_type_map(state_schema: list[dict[str, Any]]) -> dict[str, str]:
    """Index ``state_schema`` entries by name for quick type lookup.

    Unknown entries resolve to ``str`` via the caller's fallback. Empty
    schemas yield an empty map — every caller defaults to ``str``.
    """
    types: dict[str, str] = {}
    for field in state_schema or []:
        name = (field.get("name") or "").strip()
        if not name:
            continue
        ftype = (field.get("type") or "str").strip().lower() or "str"
        types[name] = ftype
    return types


def _state_schema_defaults(
    state_schema: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Extract ``{field_name: default_value}`` for every state_schema entry
    that carries a non-None ``default_value``.

    BUG-085 M3: state_schema fields with declared defaults must be
    available to strict-isolation prompt placeholders even when the
    caller didn't pass them in ``inputs``. Callers merge this dict UNDER
    user-provided inputs so explicit caller values still win.

    Codex checker finding 2: each call returns FRESH deepcopies of the
    default values so mutable defaults (``[]``, ``{}``) cannot leak
    mutation across runs. This makes ``_state_schema_defaults`` the
    canonical "fresh defaults" entry point.
    """
    defaults: dict[str, Any] = {}
    for field in state_schema or []:
        if not isinstance(field, dict):
            continue
        name = (field.get("name") or "").strip()
        if not name:
            continue
        # BUG-094: prefer canonical ``default_value`` key (StateFieldDecl),
        # fall back to legacy storage key ``default`` so existing branches
        # built before the key alignment still seed correctly without
        # requiring a data migration.
        if "default_value" in field:
            value = field.get("default_value")
        elif "default" in field:
            value = field.get("default")
        else:
            continue
        if value is None:
            continue
        defaults[name] = copy.deepcopy(value)
    return defaults


def seed_initial_state(
    inputs: dict[str, Any],
    state_schema: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Return a fresh dict with state_schema defaults merged UNDER inputs.

    BUG-085 M3 — used at branch invocation to pre-populate the runtime
    state with any state_schema field that carries a ``default_value``.
    Explicit caller-provided ``inputs`` always win; defaults only fill
    keys the caller did not pass.
    """
    seeded = dict(_state_schema_defaults(state_schema))
    seeded.update(inputs or {})
    return seeded


def _needs_json_contract(
    node: NodeDefinition, state_types: dict[str, str],
) -> bool:
    """True when the node's outputs require structured JSON.

    Two triggers, matching the sibling-bug framing in the navigator
    spec: (1) >=2 output_keys — single-key plain-string write drops
    siblings; (2) any declared output_key has a non-``str`` type in
    ``state_schema`` — prose output can't satisfy a typed slot.
    """
    keys = list(node.output_keys or [])
    if len(keys) >= 2:
        return True
    for k in keys:
        if state_types.get(k, "str") != "str":
            return True
    return False


def _json_contract_suffix(
    node: NodeDefinition, state_types: dict[str, str],
) -> str:
    """Deterministic JSON-schema-style suffix to append to the prompt.

    Kept as a plain ``str`` append (no f-string in the caller) so the
    rendered prompt is still copy-pasteable into other tools. We do not
    use ``response_format`` — 3/6 providers are CLI-wrapped (claude,
    codex, ollama) where no native structured-output hook is wirable.
    """
    lines = [
        "",
        "",
        "RESPONSE FORMAT",
        "---------------",
        "Respond with a single JSON object, no prose, no fences. "
        "Each declared field is required:",
    ]
    for k in node.output_keys:
        t = state_types.get(k, "str")
        lines.append(f"  - {k!r}: {t}")
    lines.append(
        "Do not wrap the object in ``` fences. Do not include any text "
        "before or after the JSON object."
    )
    return "\n".join(lines)


def _coerce_value(raw: Any, t: str) -> Any:
    """Coerce ``raw`` into the declared state_schema type or raise.

    Caller turns failures into ``CompilerError`` with node context. The
    bool/int/float parsers accept common LLM shapes (``"true"`` etc.)
    since the LLM is producing JSON but may emit strings for scalar
    fields.
    """
    if t == "str":
        return str(raw)
    if t == "int":
        if isinstance(raw, bool):
            raise TypeError("bool is not int for this schema")
        return int(raw)
    if t == "float":
        if isinstance(raw, bool):
            raise TypeError("bool is not float for this schema")
        return float(raw)
    if t == "bool":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        if isinstance(raw, str):
            v = raw.strip().lower()
            if v in ("true", "yes", "1"):
                return True
            if v in ("false", "no", "0"):
                return False
            raise TypeError(f"cannot parse {raw!r} as bool")
        raise TypeError(f"cannot parse {type(raw).__name__} as bool")
    if t == "list":
        if not isinstance(raw, list):
            raise TypeError(f"expected list, got {type(raw).__name__}")
        return raw
    if t == "dict":
        if not isinstance(raw, dict):
            raise TypeError(f"expected dict, got {type(raw).__name__}")
        return raw
    # any / unknown — pass through.
    return raw


def _extract_json_object(response: str) -> dict[str, Any]:
    """Parse ``response`` as a JSON object.

    Tolerates a code-fenced object (```json {...}```), a bare object,
    or an object embedded in prose. Raises ValueError on failure so
    the caller can wrap with node context.
    """
    text = response.strip()
    if not text:
        raise ValueError("empty response")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        fence = _JSON_CODE_FENCE_RE.search(text)
        if fence:
            try:
                parsed = json.loads(fence.group(1))
            except json.JSONDecodeError as exc:
                raise ValueError(f"fenced JSON malformed: {exc}") from exc
        else:
            match = _JSON_OBJECT_RE.search(text)
            if not match:
                raise ValueError("no JSON object found in response")
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise ValueError(f"embedded JSON malformed: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(
            f"expected JSON object, got {type(parsed).__name__}"
        )
    return parsed


def _build_prompt_template_node(
    node: NodeDefinition,
    *,
    provider_call: Callable[..., str] | None,
    event_sink: Callable[..., None] | None,
    state_schema: list[dict[str, Any]] | None = None,
    llm_policy: dict[str, Any] | None = None,
    concurrency_tracker: ConcurrencyTracker | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Return a node function that fills the prompt template and calls an
    LLM. Output is stored under the node's first ``output_keys`` entry
    (or ``<node_id>_output`` if none declared).

    When ``llm_policy`` is set the call is routed through
    ``ProviderRouter.call_with_policy_sync`` if the router is importable;
    otherwise falls back to the plain ``provider_call`` callable.
    """

    output_key = (
        node.output_keys[0] if node.output_keys else f"{node.node_id}_output"
    )
    role = (node.model_hint or "writer").strip().lower() or "writer"
    template = node.prompt_template or ""
    timeout_s = float(node.timeout_seconds or 300.0)
    strict_isolation = bool(getattr(node, "strict_input_isolation", True))
    declared_inputs = list(node.input_keys)
    # BUG-085 (Codex checker finding 1): state_schema fields carrying a
    # default_value count as effectively-declared input. Without this,
    # the strict render filter drops seeded defaults when the node
    # declares any explicit input_keys, and the truly_outside partition
    # falsely flags defaulted-but-referenced keys as isolation
    # violations. Compute the union ONCE at closure-build time.
    schema_defaulted_keys = set(_state_schema_defaults(state_schema).keys())
    effective_declared = set(declared_inputs) | schema_defaulted_keys
    state_types = _state_type_map(state_schema or [])
    needs_json = _needs_json_contract(node, state_types)
    json_suffix = _json_contract_suffix(node, state_types) if needs_json else ""
    effective_policy: dict[str, Any] | None = llm_policy

    # Lazy import so graph_compiler doesn't hard-depend on providers at import
    # time. Aliased so the except-clauses below can reference it by name without
    # re-importing inside every invocation.
    try:
        from workflow.providers.base import SandboxUnavailableError as _SandboxUnavailableError
    except Exception:  # noqa: BLE001 — import failure must not break compilation
        _SandboxUnavailableError = type("_SandboxUnavailableError", (Exception,), {})  # type: ignore[assignment,misc]

    def _fn(state: dict[str, Any]) -> dict[str, Any]:
        # Normalize Jinja-style ``{{var}}`` into Python's ``{var}``.
        # Claude.ai-authored prompt_templates tend to use doubled braces
        # by convention; without this the braces are passed through to
        # the LLM as literal text.
        rendered_template = _normalize_placeholders(template)

        # Strict input-keys isolation: filter the state view to just
        # the declared input_keys BEFORE rendering. Out-of-input-keys
        # placeholders then trip the missing-state-keys check below
        # and raise CompilerError — never silently read leaked state.
        if strict_isolation and declared_inputs:
            # BUG-085: include state_schema-defaulted keys in the render
            # allow-list so seeded defaults are visible to the prompt
            # even when not duplicated into the node's input_keys.
            render_state: dict[str, Any] = {
                k: state[k] for k in effective_declared if k in state
            }
        else:
            render_state = state

        # Non-strict path: emit a warning event per out-of-input-keys
        # reference so the warning shows up in the per-run event log
        # even when the author hasn't opted into strict mode. Run-time
        # warnings mirror the build-time ones from collect_build_warnings.
        if not strict_isolation and declared_inputs and event_sink is not None:
            for placeholder in _out_of_input_keys(node):
                try:
                    event_sink(
                        node_id=node.node_id,
                        phase="warning",
                        kind="input_keys_leak",
                        placeholder=placeholder,
                        declared_input_keys=declared_inputs,
                    )
                except Exception as exc:  # noqa: BLE001
                    if _is_cancel_exception(exc):
                        raise
                    logger.exception(
                        "event_sink raised emitting input_keys_leak "
                        "warning for %s", node.node_id,
                    )

        missing = _missing_state_keys(template, render_state)
        if missing:
            if strict_isolation:
                # BUG-085: partition the missing keys into two categories
                # so the operator sees the ACTUAL failure mode, not a
                # contradictory "outside declared input_keys" message for
                # keys that ARE in the declared list but simply aren't in
                # state yet (upstream node hasn't produced them, or a
                # state_schema default wasn't seeded).
                # state_schema-defaulted keys count as effectively-declared
                # (Codex checker finding 1) — a referenced default key
                # that simply isn't in state at execution time is NOT an
                # isolation violation, it's an unavailability problem.
                truly_outside = [
                    k for k in missing if k not in effective_declared
                ]
                declared_but_unavailable = [
                    k for k in missing if k in effective_declared
                ]
                # Prioritize the actionable "outside" diagnosis when both
                # categories are present — that's the real isolation
                # violation; the unavailable-declared keys are noted as
                # secondary context so the operator gets the whole picture.
                if truly_outside and declared_but_unavailable:
                    raise CompilerError(
                        f"Node '{node.node_id}' (strict_input_isolation=true) "
                        f"prompt references state keys {truly_outside} "
                        f"outside declared input_keys "
                        f"{sorted(declared_inputs)!r}. "
                        f"Add the keys to input_keys or clear the flag. "
                        f"Additionally, declared input_keys "
                        f"{declared_but_unavailable} are not present in "
                        f"state at execution time — likely an upstream "
                        f"node did not produce them, or a state_schema "
                        f"default was not initialized."
                    )
                if truly_outside:
                    raise CompilerError(
                        f"Node '{node.node_id}' (strict_input_isolation=true) "
                        f"prompt references state keys {truly_outside} "
                        f"outside declared input_keys "
                        f"{sorted(declared_inputs)!r}. "
                        f"Add the keys to input_keys or clear the flag."
                    )
                # All missing keys ARE declared — the failure is that
                # state didn't contain them at execution time.
                raise CompilerError(
                    f"Node '{node.node_id}' (strict_input_isolation=true) "
                    f"prompt references declared input_keys "
                    f"{declared_but_unavailable} that are not present in "
                    f"state at execution time. "
                    f"Likely cause: an upstream node did not produce these "
                    f"keys, or a state_schema field default was not "
                    f"initialized into the run's initial state."
                )
            raise CompilerError(
                f"Node '{node.node_id}' prompt references missing "
                f"state keys: {missing}"
            )
        try:
            prompt = _render_template(rendered_template, render_state)
        except KeyError as exc:
            raise CompilerError(
                f"Node '{node.node_id}' prompt format failed: "
                f"missing state key {exc}"
            ) from exc

        # Multi-output or typed-output nodes get a JSON contract
        # appended. Providers stay untouched — the contract is plain
        # text so every provider (including CLI-wrapped ones) sees the
        # same prompt shape (hard-rule #8: no divergent silent-drop).
        if needs_json:
            prompt = prompt + json_suffix

        # Emit a "starting" event BEFORE the provider call so long-running
        # LLM nodes don't look frozen to a polling client (#60). The
        # matching "ran" event fires after the call completes.
        if event_sink is not None:
            try:
                event_sink(
                    node_id=node.node_id,
                    phase="starting", role=role,
                    prompt_preview=prompt[:200],
                )
            except Exception as exc:
                if _is_cancel_exception(exc):
                    raise
                logger.exception(
                    "event_sink raised in %s (starting)", node.node_id,
                )

        if concurrency_tracker is not None:
            concurrency_tracker.acquire()
        try:
            provider_served: str = "unknown"
            if provider_call is None:
                response = f"[Mock response for {node.node_id}]"
                provider_served = "mock"
            elif effective_policy:
                # Policy-aware path: route through ProviderRouter.call_with_policy_sync
                try:
                    _policy_router = _get_shared_router()
                    router_providers = getattr(
                        _policy_router, "available_providers", None,
                    )
                    router_has_providers = (
                        router_providers is None or bool(router_providers)
                    )
                    if _policy_router is not None and router_has_providers:
                        def _policy_call() -> tuple[str, str]:
                            return _call_policy_router_with_retry(
                                _policy_router,
                                role=role,
                                prompt=prompt,
                                system="",
                                policy=effective_policy,
                            )
                        text_and_name = _run_with_timeout(
                            _policy_call,
                            timeout_s=timeout_s,
                            node_id=node.node_id,
                        )
                        response, provider_served = text_and_name
                    else:
                        # Router unavailable or empty — fall through to the
                        # run_branch-injected provider bridge.
                        response = _run_with_timeout(
                            lambda: provider_call(prompt, "", role=role),
                            timeout_s=timeout_s,
                            node_id=node.node_id,
                        )
                except NodeTimeoutError:
                    raise
                except _SandboxUnavailableError:
                    raise
                except Exception as exc:
                    logger.exception("Policy provider call failed in %s", node.node_id)
                    _emit_failed_event(event_sink, node.node_id, exc)
                    raise _wrap_provider_failure(node.node_id, exc) from exc
            else:
                try:
                    response = _run_with_timeout(
                        lambda: provider_call(prompt, "", role=role),
                        timeout_s=timeout_s,
                        node_id=node.node_id,
                    )
                except NodeTimeoutError:
                    raise
                except _SandboxUnavailableError:
                    raise
                except Exception as exc:
                    logger.exception("Provider call failed in %s", node.node_id)
                    _emit_failed_event(event_sink, node.node_id, exc)
                    raise _wrap_provider_failure(node.node_id, exc) from exc
        finally:
            if concurrency_tracker is not None:
                concurrency_tracker.release()

        if not response:
            raise EmptyResponseError(
                f"Node '{node.node_id}': LLM returned empty response — "
                f"check provider availability and credentials",
                node_id=node.node_id,
            )

        # Defense-in-depth: if a subprocess provider leaked a bwrap failure
        # into the response text instead of raising, catch it here so the
        # garbage never propagates into state (hard-rule #8 fail-loudly).
        try:
            from workflow.providers.base import check_bwrap_failure
            check_bwrap_failure(response)
        except _SandboxUnavailableError:
            raise
        except Exception:  # noqa: BLE001 — import/probe errors must not block runs
            pass

        if event_sink is not None:
            try:
                event_sink(
                    node_id=node.node_id,
                    phase="ran",
                    prompt=prompt, response=response, role=role,
                    provider_served=provider_served,
                )
            except Exception as exc:
                if _is_cancel_exception(exc):
                    raise
                logger.exception("event_sink raised in %s", node.node_id)

        # JSON-contract path: parse response, assign EVERY declared
        # output_key from the parsed object, coerce types. Missing
        # key / wrong type / malformed JSON all raise CompilerError
        # (hard-rule #8). Fixes the multi-output silent-drop + typed
        # no-op bugs at the same layer.
        if needs_json:
            try:
                parsed = _extract_json_object(response)
            except ValueError as exc:
                raise CompilerError(
                    f"Node '{node.node_id}' expected JSON object response "
                    f"for output_keys {list(node.output_keys)!r}: {exc}. "
                    f"Raw response: {response[:400]!r}"
                ) from exc
            result: dict[str, Any] = {}
            for key in node.output_keys:
                if key not in parsed:
                    raise CompilerError(
                        f"Node '{node.node_id}' JSON response missing "
                        f"declared output_key '{key}'. Got keys: "
                        f"{sorted(parsed.keys())!r}."
                    )
                t = state_types.get(key, "str")
                try:
                    result[key] = _coerce_value(parsed[key], t)
                except (TypeError, ValueError) as exc:
                    raise CompilerError(
                        f"Node '{node.node_id}' output_key '{key}' type "
                        f"coercion to '{t}' failed: {exc}. "
                        f"Got: {parsed[key]!r}."
                    ) from exc
            return result

        return {output_key: response}

    return _fn


def _validate_source_code(node: NodeDefinition) -> None:
    """Gate source_code nodes: require approval + no obviously dangerous
    patterns. This is belt-and-suspenders; host approval is the primary
    defense. See spec §Risks — a proper sandbox is future work."""
    if not node.approved:
        raise UnapprovedNodeError(
            f"Node '{node.node_id}' is source_code and must be approved "
            f"by the host before running."
        )
    src = node.source_code or ""
    for pattern in _DANGEROUS_PATTERNS:
        if pattern in src:
            raise CompilerError(
                f"Node '{node.node_id}' source_code contains disallowed "
                f"pattern: '{pattern}'"
            )


_NODE_MCP_ACTION_ALIASES: dict[str, tuple[str, str]] = {
    "goals.leaderboard": ("goals", "leaderboard"),
    "goal_leaderboard": ("goals", "leaderboard"),
    "quality_leaderboard": ("goals", "leaderboard"),
    "goals.archive_consultation": ("goals", "archive_consultation"),
    "goal_archive_consultation": ("goals", "archive_consultation"),
    "gates.leaderboard": ("gates", "leaderboard"),
    "gates_leaderboard": ("gates", "leaderboard"),
    "gates.get_ladder": ("gates", "get_ladder"),
}


def _build_node_mcp_invoker(
    node: NodeDefinition,
    *,
    event_sink: Callable[..., None] | None,
) -> Callable[..., dict[str, Any]]:
    allowed = set(node.tools_allowed or [])

    def _invoke_mcp_action(action_name: str, **kwargs: Any) -> dict[str, Any]:
        requested = str(action_name or "").strip()
        if not requested:
            raise CompilerError(
                f"Node '{node.node_id}' invoke_mcp_action requires action_name."
            )
        resolved = _NODE_MCP_ACTION_ALIASES.get(requested)
        if resolved is None:
            raise CompilerError(
                f"Node '{node.node_id}' requested unsupported MCP action "
                f"'{requested}'. Supported actions: "
                f"{sorted(_NODE_MCP_ACTION_ALIASES)}"
            )
        canonical = ".".join(resolved)
        if requested not in allowed and canonical not in allowed:
            raise CompilerError(
                f"Node '{node.node_id}' is not allowed to call MCP action "
                f"'{requested}'. Declare it in tools_allowed first."
            )

        if event_sink is not None:
            try:
                event_sink(
                    node_id=node.node_id,
                    phase="mcp_action",
                    action_name=requested,
                    canonical_action=canonical,
                )
            except Exception as exc:
                if _is_cancel_exception(exc):
                    raise
                logger.exception(
                    "event_sink raised for node MCP action in %s",
                    node.node_id,
                )

        tool_name, action = resolved
        if tool_name == "goals":
            from workflow.api.market import goals

            raw = goals(action=action, **kwargs)
        elif tool_name == "gates":
            from workflow.api.market import gates

            raw = gates(action=action, **kwargs)
        else:  # pragma: no cover - mapping owns the dispatch domains.
            raise CompilerError(
                f"Node '{node.node_id}' requested unsupported MCP tool "
                f"'{tool_name}'."
            )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CompilerError(
                f"Node '{node.node_id}' MCP action '{requested}' returned "
                f"invalid JSON: {exc}"
            ) from exc
        if not isinstance(parsed, dict):
            raise CompilerError(
                f"Node '{node.node_id}' MCP action '{requested}' returned "
                f"{type(parsed).__name__}, expected object."
            )
        return parsed

    return _invoke_mcp_action


def _build_source_code_node(
    node: NodeDefinition,
    *,
    event_sink: Callable[..., None] | None,
    concurrency_tracker: ConcurrencyTracker | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Return a node function that exec()s the approved source_code.

    The source must define a callable named ``run(state)`` returning a dict.
    Keeps the runtime surface small and matches the existing extensions
    sandbox contract for node registration.
    """
    _validate_source_code(node)
    src = node.source_code
    timeout_s = float(node.timeout_seconds or 300.0)
    invoke_mcp_action = _build_node_mcp_invoker(node, event_sink=event_sink)

    local_scope: dict[str, Any] = {}
    try:
        exec(  # noqa: S102
            src,
            {
                "__builtins__": __builtins__,
                "invoke_mcp_action": invoke_mcp_action,
            },
            local_scope,
        )
    except Exception as exc:
        raise CompilerError(
            f"Node '{node.node_id}' source_code failed to load: {exc}"
        ) from exc
    runner = local_scope.get("run")
    if not callable(runner):
        raise CompilerError(
            f"Node '{node.node_id}' source_code must define `def run(state)`."
        )

    def _fn(state: dict[str, Any]) -> dict[str, Any]:
        # #60: emit a starting event so long-running source_code nodes
        # don't look frozen to polling clients.
        if event_sink is not None:
            try:
                event_sink(
                    node_id=node.node_id,
                    phase="starting", source_code=True,
                )
            except Exception as exc:
                if _is_cancel_exception(exc):
                    raise
                logger.exception(
                    "event_sink raised in %s (starting)", node.node_id,
                )
        if concurrency_tracker is not None:
            concurrency_tracker.acquire()
        try:
            result = _run_with_timeout(
                lambda: runner(state),
                timeout_s=timeout_s,
                node_id=node.node_id,
            )
        except NodeTimeoutError:
            raise
        except Exception as exc:
            logger.exception("source_code node %s raised", node.node_id)
            raise CompilerError(
                f"Node '{node.node_id}' raised at runtime: {exc}"
            ) from exc
        finally:
            if concurrency_tracker is not None:
                concurrency_tracker.release()
        if not isinstance(result, dict):
            raise CompilerError(
                f"Node '{node.node_id}' must return a dict, "
                f"got {type(result).__name__}."
            )
        if event_sink is not None:
            try:
                event_sink(
                    node_id=node.node_id,
                    phase="ran",
                    source_code=True, output=result,
                )
            except Exception as exc:
                if _is_cancel_exception(exc):
                    raise
                logger.exception("event_sink raised in %s", node.node_id)
        return result

    return _fn


def _build_opaque_node(
    node: NodeDefinition,
    fn: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    event_sink: Callable[..., None] | None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Wrap a domain-registered opaque callable as a graph node.

    Opaque nodes bypass ``_validate_source_code`` — the domain
    registry is host-controlled at registration time, not
    per-invocation, so the per-node ``approved`` flag is irrelevant.
    Emits ``phase="starting"`` and ``phase="ran"`` events so outer
    stream loops observe entry/exit at wrapper-boundary granularity
    (Phase D §4.10).
    """

    def _fn(state: dict[str, Any]) -> dict[str, Any]:
        if event_sink is not None:
            try:
                event_sink(
                    node_id=node.node_id,
                    phase="starting",
                    opaque=True,
                )
            except Exception as exc:
                if _is_cancel_exception(exc):
                    raise
                logger.exception(
                    "event_sink raised in %s (starting)", node.node_id,
                )
        try:
            result = fn(state)
        except Exception as exc:
            if _is_cancel_exception(exc):
                raise
            logger.exception("opaque node %s raised", node.node_id)
            raise CompilerError(
                f"Opaque node '{node.node_id}' raised at runtime: {exc}"
            ) from exc
        if not isinstance(result, dict):
            raise CompilerError(
                f"Opaque node '{node.node_id}' must return a dict, "
                f"got {type(result).__name__}."
            )
        if event_sink is not None:
            try:
                event_sink(
                    node_id=node.node_id,
                    phase="ran",
                    opaque=True,
                    output=result,
                )
            except Exception as exc:
                if _is_cancel_exception(exc):
                    raise
                logger.exception("event_sink raised in %s", node.node_id)
        return result

    return _fn


def _checkpoint_predicate_matches(
    reached_when: dict[str, Any], merged_state: dict[str, Any],
) -> bool:
    """Return True when merged_state satisfies reached_when.

    Supported shapes:
    - {"state_key": K, "value": V} — fires when merged_state[K] == V
    - {"state_key": K, "exists": true} — fires when K is present and non-None/non-empty
    - {"state_key": K} — same as exists=true (key presence)
    """
    key = reached_when.get("state_key", "")
    if not key:
        return False
    val = merged_state.get(key)
    if "value" in reached_when:
        return val == reached_when["value"]
    # exists check (default): truthy non-None value
    if val is None:
        return False
    if isinstance(val, (str, list, dict)):
        return bool(val)
    return True


def _wrap_with_checkpoints(
    inner_fn: Callable[[dict[str, Any]], dict[str, Any]],
    node: NodeDefinition,
    event_sink: Callable[..., None] | None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Wrap a node function to evaluate checkpoints after execution.

    After inner_fn returns a state delta, this evaluates each checkpoint's
    reached_when predicate against the merged state (incoming + delta).
    Matching checkpoints emit a checkpoint_reached event via event_sink
    and record the checkpoint_id in _fired_checkpoints to prevent re-firing.
    """
    checkpoints = list(node.checkpoints)
    if not checkpoints:
        return inner_fn

    node_id = node.node_id

    def _fn(state: dict[str, Any]) -> dict[str, Any]:
        delta = inner_fn(state)
        # Merge incoming state with delta to evaluate predicates.
        merged = {**state, **delta}
        # _fired_checkpoints uses an append reducer — LangGraph concatenates
        # the delta list onto the accumulated state list. We emit only
        # newly-fired IDs so each ID appears at most once in the final list.
        already_fired: set[str] = set(state.get("_fired_checkpoints") or [])
        newly_fired: list[str] = []

        for ckpt in checkpoints:
            ckpt_id = ckpt.get("checkpoint_id", "")
            if not ckpt_id or ckpt_id in already_fired:
                continue
            rw = ckpt.get("reached_when")
            if not isinstance(rw, dict):
                continue
            if _checkpoint_predicate_matches(rw, merged):
                newly_fired.append(ckpt_id)
                if event_sink is not None:
                    try:
                        event_sink(
                            node_id=node_id,
                            phase="checkpoint_reached",
                            checkpoint_id=ckpt_id,
                            earns_fraction=ckpt.get("earns_fraction", 0.0),
                        )
                    except Exception as exc:  # noqa: BLE001
                        if _is_cancel_exception(exc):
                            raise
                        logger.exception(
                            "event_sink raised emitting checkpoint_reached "
                            "for %s/%s", node_id, ckpt_id,
                        )

        if newly_fired:
            # Emit only the new IDs; the append reducer accumulates them.
            delta = {**delta, "_fired_checkpoints": newly_fired}
        return delta

    return _fn


# Phase A item 5 / Task #76b — threadlocal global cap on child-run retries
# within a single parent run. Each parent run executes on its own thread
# from the executor pool; threadlocal naturally scopes per-run. Children
# spawn into their own threads with independent counters; only the
# parent's invoke nodes consume from this counter.
_retry_state = threading.local()


def _retry_budget_max() -> int:
    """Read ``WORKFLOW_MAX_CHILD_RETRIES_TOTAL`` env (default 5)."""
    raw = os.environ.get("WORKFLOW_MAX_CHILD_RETRIES_TOTAL", "").strip()
    try:
        return max(0, int(raw)) if raw else 5
    except ValueError:
        return 5


def _retry_budget_remaining() -> bool:
    """True iff the threadlocal retry counter has budget left."""
    used = getattr(_retry_state, "used", 0)
    return used < _retry_budget_max()


def _retry_budget_consume() -> None:
    """Increment the threadlocal retry counter by 1."""
    _retry_state.used = getattr(_retry_state, "used", 0) + 1


def _retry_budget_reset() -> None:
    """Reset the threadlocal counter — called by ``_invoke_graph`` at run
    start so each parent run gets a fresh budget."""
    _retry_state.used = 0


def _classify_child_failure(child_status: str) -> str:
    """Map a child run's terminal status to a failure_class label.

    Phase A item 5 / Task #76b. Used by invoke_branch / invoke_branch_version
    builders when populating ``ChildFailure.failure_class`` on the parent's
    ``RunOutcome.child_failures`` list.
    """
    from workflow.runs import (
        RUN_STATUS_CANCELLED,
        RUN_STATUS_FAILED,
        RUN_STATUS_INTERRUPTED,
    )
    if child_status == RUN_STATUS_FAILED:
        return "child_failed"
    if child_status == RUN_STATUS_CANCELLED:
        return "child_cancelled"
    if child_status == RUN_STATUS_INTERRUPTED:
        return "child_timeout"
    return "child_unknown"


def _dispatch_invoke_outcome(
    *,
    child_status: str,
    child_run_id: str,
    child_output: dict[str, Any],
    output_mapping: dict[str, str],
    on_child_fail: str,
    default_outputs: dict[str, Any] | None,
    node_id: str,
) -> tuple[dict[str, Any], "object | None"]:
    """Apply the ``on_child_fail`` policy to a completed child run.

    Returns ``(updates, child_failure_or_none)``. ``child_failure_or_none`` is
    a ``ChildFailure`` instance when the child terminated non-completed
    (worth recording on the parent's ``RunOutcome.child_failures``); None on
    successful completion.

    Policies:
      - ``"propagate"`` (default): child failure raises ``ChildFailedError``
        so the parent run terminates with the structured error.
      - ``"default"``: parent continues; ``output_mapping`` populates from
        ``default_outputs`` dict (or None when not declared).
      - ``"retry"``: caller handles retry via the closure's retry counter;
        this helper treats retry-exhausted as ``"propagate"``.
    """
    from workflow.runs import RUN_STATUS_COMPLETED, ChildFailure

    if child_status == RUN_STATUS_COMPLETED:
        updates: dict[str, Any] = {}
        for parent_key, child_key in output_mapping.items():
            updates[parent_key] = child_output.get(child_key)
        return updates, None

    failure = ChildFailure(
        run_id=child_run_id,
        failure_class=_classify_child_failure(child_status),
        child_status=child_status,
        partial_output=dict(child_output) if child_output else None,
    )

    if on_child_fail == "default":
        defaults = default_outputs or {}
        updates = {
            parent_key: defaults.get(parent_key)
            for parent_key in output_mapping
        }
        return updates, failure

    # propagate (default) — raise so the parent's _invoke_graph catches.
    raise ChildFailedError(
        f"Sub-branch invocation in node '{node_id}' produced a "
        f"non-completed terminal status: {failure.failure_class} "
        f"(child run_id={child_run_id})",
        failure=failure,
    )


class ChildFailedError(Exception):
    """Raised by ``_dispatch_invoke_outcome`` under ``on_child_fail="propagate"``.

    Phase A item 5 / Task #76b. Carries the ``ChildFailure`` so the parent
    ``_invoke_graph`` can surface it via ``RunOutcome.child_failures`` rather
    than discarding the structured failure data.
    """

    def __init__(self, message: str, *, failure: object) -> None:
        super().__init__(message)
        self.failure = failure


def _emit_invoke_design_used(
    *,
    base_path: "Path",
    parent_run_id: str,
    parent_node_id: str,
    artifact_kind: str,
    artifact_id: str,
    branch_def_id_for_author_lookup: str,
    metadata_extra: dict[str, Any] | None = None,
) -> None:
    """Phase A item 5 / Task #76c — emit a ``design_used`` event for a
    successful sub-branch invocation.

    Fires only on child success per #56 + #75 discipline ("only successful
    uses count"). Resolves the credited author by reading the live
    ``BranchDefinition.author`` keyed by ``branch_def_id_for_author_lookup``;
    for ``invoke_branch_version_spec`` we still resolve via the live def
    because ``branch_versions.snapshot`` only carries topology, not author.

    Skips emit when author is empty or "anonymous" — orphan-row
    prevention. Per #48 §1.4 + impl-pair-read on #75: ``execute_step``
    events MAY carry actor_id="anonymous" (the run-claimer might not be
    a registered actor); ``design_used`` events MUST NEVER, because
    crediting "anonymous" pollutes the ledger with synthetic-actor
    attribution. Different events, different discipline.

    Wrapped in try/except by callers so emit failure never breaks the
    parent step (mirrors Task #72/#75 decoupling).
    """
    from workflow.daemon_server import get_branch_definition

    try:
        raw = get_branch_definition(
            base_path, branch_def_id=branch_def_id_for_author_lookup,
        )
    except KeyError:
        return  # Live def gone; skip emit (lineage walk handles attribution).

    author = (raw.get("author") if isinstance(raw, dict) else "") or ""
    if not author or author == "anonymous":
        return

    metadata = {
        "graph_node_id": parent_node_id,
        artifact_kind + "_id": artifact_id,
    }
    if metadata_extra:
        metadata.update(metadata_extra)

    from workflow.contribution_events import record_contribution_event

    record_contribution_event(
        base_path,
        event_id=f"design_used:{parent_run_id}:{parent_node_id}:{artifact_id}",
        event_type="design_used",
        actor_id=author,
        source_run_id=parent_run_id,
        source_artifact_id=artifact_id,
        source_artifact_kind=artifact_kind,
        weight=1.0,
        metadata_json=json.dumps(metadata),
    )


def _build_invoke_branch_node(
    node: NodeDefinition,
    *,
    base_path: str | Path,
    event_sink: Callable[..., None] | None,
    provider_call: Callable[..., str] | None = None,
    depth: int = 0,
    parent_run_id: str = "",
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Build a callable for an ``invoke_branch_spec`` node.

    The callable spawns a child branch run (blocking or async) and writes
    declared output_mapping fields back into the parent state.
    """
    from workflow.runs import (
        _runtime_max_invocation_depth,
        execute_branch,
        execute_branch_async,
    )

    spec = node.invoke_branch_spec or {}
    child_branch_def_id: str = spec.get("branch_def_id", "")
    inputs_mapping: dict[str, str] = spec.get("inputs_mapping", {})
    output_mapping: dict[str, str] = spec.get("output_mapping", {})
    wait_mode: str = spec.get("wait_mode", "blocking")
    on_child_fail: str = spec.get("on_child_fail", "propagate")
    default_outputs = spec.get("default_outputs")
    retry_budget: int = int(spec.get("retry_budget", 1) or 1)
    child_actor: str = spec.get("child_actor", "") or ""

    if not child_branch_def_id:
        raise CompilerError(
            f"Node '{node.node_id}': invoke_branch_spec missing 'branch_def_id'."
        )
    if wait_mode not in ("blocking", "async"):
        raise CompilerError(
            f"Node '{node.node_id}': invoke_branch_spec wait_mode must be "
            f"'blocking' or 'async', got '{wait_mode}'."
        )
    _depth_cap = _runtime_max_invocation_depth()
    if depth >= _depth_cap:
        raise CompilerError(
            f"Node '{node.node_id}': invoke_branch recursion depth cap "
            f"({_depth_cap}) reached. Circular sub-branch chain?"
        )

    _base = Path(base_path)

    def _resolve_actor() -> str:
        if child_actor:
            return child_actor
        if parent_run_id:
            from workflow.runs import get_run

            parent = get_run(_base, parent_run_id)
            if parent:
                return parent.get("actor") or "anonymous"
        return "anonymous"

    def _node_fn(state: dict[str, Any]) -> dict[str, Any]:
        from workflow.branches import BranchDefinition as _BD
        from workflow.daemon_server import get_branch_definition

        raw = get_branch_definition(_base, branch_def_id=child_branch_def_id)
        child_branch = _BD.from_dict(raw)

        child_inputs: dict[str, Any] = {
            child_key: state.get(parent_key)
            for parent_key, child_key in inputs_mapping.items()
        }

        actor_arg = _resolve_actor()
        if wait_mode == "blocking":
            # Phase A item 5 / Task #76b — on_child_fail policy + retry.
            # Blocking-mode invocation knows the child's terminal status
            # synchronously. async-mode failures surface at the await
            # node (#56 §8 Q6) and aren't policy-handled here.
            attempt = 0
            while True:
                attempt += 1
                outcome = execute_branch(
                    _base, branch=child_branch, inputs=child_inputs,
                    actor=actor_arg,
                    provider_call=provider_call,
                    _invocation_depth=depth + 1,
                )
                if outcome.status == "completed":
                    try:
                        _emit_invoke_design_used(
                            base_path=_base,
                            parent_run_id=parent_run_id,
                            parent_node_id=node.node_id,
                            artifact_kind="branch_def",
                            artifact_id=child_branch_def_id,
                            branch_def_id_for_author_lookup=child_branch_def_id,
                        )
                    except Exception:
                        pass
                    return {
                        parent_key: outcome.output.get(child_key)
                        for parent_key, child_key in output_mapping.items()
                    }
                # Non-completed terminal status — apply policy.
                retries_left = (
                    retry_budget - (attempt - 1)
                    if on_child_fail == "retry" else 0
                )
                if on_child_fail == "retry" and retries_left > 0 and (
                    _retry_budget_remaining()
                ):
                    _retry_budget_consume()
                    continue
                updates, _failure = _dispatch_invoke_outcome(
                    child_status=outcome.status,
                    child_run_id=outcome.run_id,
                    child_output=outcome.output,
                    output_mapping=output_mapping,
                    on_child_fail=(
                        "propagate" if on_child_fail == "retry"
                        else on_child_fail
                    ),
                    default_outputs=default_outputs,
                    node_id=node.node_id,
                )
                # _dispatch_invoke_outcome raised on propagate (default
                # for retry-exhausted); only "default" path returns here.
                return updates
        else:
            outcome = execute_branch_async(
                _base, branch=child_branch, inputs=child_inputs,
                actor=actor_arg,
                provider_call=provider_call,
                _invocation_depth=depth + 1,
            )
            # async: write the child run_id into the first output_mapping target.
            # design_used emit deferred to await_branch_run on success
            # (#56 §8 Q6 — async failures surface at the await site).
            updates = {}
            if output_mapping:
                first_parent_key = next(iter(output_mapping))
                updates[first_parent_key] = outcome.run_id
            return updates

    return _node_fn


def _build_invoke_branch_version_node(
    node: NodeDefinition,
    *,
    base_path: str | Path,
    event_sink: Callable[..., None] | None,
    provider_call: Callable[..., str] | None = None,
    depth: int = 0,
    parent_run_id: str = "",
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Build a callable for an ``invoke_branch_version_spec`` node.

    Phase A item 5 (Task #76a). Sibling to :func:`_build_invoke_branch_node`
    that resolves a frozen ``branch_version_id`` snapshot via
    :func:`workflow.runs.execute_branch_version_async` instead of calling
    :func:`execute_branch` against the live def. Same input/output mapping
    contract; same recursion-cap discipline.

    Failure-policy + retry-budget logic lands in Task #76b — this builder
    uses the default ``on_child_fail="propagate"`` semantics today: the
    parent step receives the child's outcome.output as-is, and child
    failures surface as ``None`` values in the mapping (matches existing
    invoke_branch behavior; structured propagation lands in 76b).
    """
    from workflow.runs import _runtime_max_invocation_depth

    spec = node.invoke_branch_version_spec or {}
    child_branch_version_id: str = spec.get("branch_version_id", "")
    inputs_mapping: dict[str, str] = spec.get("inputs_mapping", {})
    output_mapping: dict[str, str] = spec.get("output_mapping", {})
    wait_mode: str = spec.get("wait_mode", "blocking")
    on_child_fail: str = spec.get("on_child_fail", "propagate")
    default_outputs = spec.get("default_outputs")
    retry_budget: int = int(spec.get("retry_budget", 1) or 1)
    child_actor: str = spec.get("child_actor", "") or ""

    if not child_branch_version_id:
        raise CompilerError(
            f"Node '{node.node_id}': invoke_branch_version_spec missing "
            f"'branch_version_id'."
        )
    if wait_mode not in ("blocking", "async"):
        raise CompilerError(
            f"Node '{node.node_id}': invoke_branch_version_spec wait_mode "
            f"must be 'blocking' or 'async', got '{wait_mode}'."
        )
    _depth_cap = _runtime_max_invocation_depth()
    if depth >= _depth_cap:
        raise CompilerError(
            f"Node '{node.node_id}': invoke_branch recursion depth cap "
            f"({_depth_cap}) reached. Circular sub-branch chain?"
        )

    _base = Path(base_path)

    def _resolve_actor() -> str:
        if child_actor:
            return child_actor
        if parent_run_id:
            from workflow.runs import get_run

            parent = get_run(_base, parent_run_id)
            if parent:
                return parent.get("actor") or "anonymous"
        return "anonymous"

    def _node_fn(state: dict[str, Any]) -> dict[str, Any]:
        # Lazy module-attribute lookups so unittest.mock.patch on
        # workflow.runs.* takes effect (matches the patch-where-the-
        # function-is-looked-up gotcha from Task #46 Failure #1).
        from workflow.runs import (
            execute_branch_version_async,
            poll_child_run_status,
        )

        child_inputs: dict[str, Any] = {
            child_key: state.get(parent_key)
            for parent_key, child_key in inputs_mapping.items()
        }
        actor_arg = _resolve_actor()

        def _resolve_branch_def_id_for_author() -> str:
            """Map child_branch_version_id → branch_def_id for author lookup.

            ``branch_versions.snapshot`` is topology-only; author lives on the
            live BranchDefinition. ``get_branch_version`` returns None on
            missing — return "" so emit silently skips (orphan-row prevention).
            """
            from workflow.branch_versions import get_branch_version
            ver = get_branch_version(_base, child_branch_version_id)
            return ver.branch_def_id if ver else ""

        if wait_mode == "blocking":
            # Phase A item 5 / Task #76b — on_child_fail policy + retry,
            # mirroring _build_invoke_branch_node's blocking path.
            attempt = 0
            while True:
                attempt += 1
                # Async helper handles the snapshot-load + reconstruction +
                # SnapshotSchemaDrift + KeyError contract per Task #65b.
                outcome = execute_branch_version_async(
                    _base,
                    branch_version_id=child_branch_version_id,
                    inputs=child_inputs,
                    actor=actor_arg,
                    provider_call=provider_call,
                    _invocation_depth=depth + 1,
                )
                # Block until the child terminates; harvest its output dict.
                record = poll_child_run_status(_base, outcome.run_id)
                child_status = record.get("status", "")
                child_output = record.get("output") or {}

                if child_status == "completed":
                    try:
                        bdid = _resolve_branch_def_id_for_author()
                        if bdid:
                            _emit_invoke_design_used(
                                base_path=_base,
                                parent_run_id=parent_run_id,
                                parent_node_id=node.node_id,
                                artifact_kind="branch_version",
                                artifact_id=child_branch_version_id,
                                branch_def_id_for_author_lookup=bdid,
                            )
                    except Exception:
                        pass
                    return {
                        parent_key: child_output.get(child_key)
                        for parent_key, child_key in output_mapping.items()
                    }
                # Non-completed terminal status — apply policy.
                retries_left = (
                    retry_budget - (attempt - 1)
                    if on_child_fail == "retry" else 0
                )
                if on_child_fail == "retry" and retries_left > 0 and (
                    _retry_budget_remaining()
                ):
                    _retry_budget_consume()
                    continue
                updates, _failure = _dispatch_invoke_outcome(
                    child_status=child_status,
                    child_run_id=outcome.run_id,
                    child_output=child_output,
                    output_mapping=output_mapping,
                    on_child_fail=(
                        "propagate" if on_child_fail == "retry"
                        else on_child_fail
                    ),
                    default_outputs=default_outputs,
                    node_id=node.node_id,
                )
                return updates
        else:
            # Async: spawn and write child run_id; failure handling deferred
            # to the await_branch_run node per #56 §8 Q6.
            outcome = execute_branch_version_async(
                _base,
                branch_version_id=child_branch_version_id,
                inputs=child_inputs,
                actor=actor_arg,
                provider_call=provider_call,
                _invocation_depth=depth + 1,
            )
            # design_used emit deferred to await on success (mirrors
            # invoke_branch async path).
            updates = {}
            if output_mapping:
                first_parent_key = next(iter(output_mapping))
                updates[first_parent_key] = outcome.run_id
            return updates

    return _node_fn


def _build_await_branch_run_node(
    node: NodeDefinition,
    *,
    base_path: str | Path,
    event_sink: Callable[..., None] | None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Build a callable for an ``await_run_spec`` node.

    The callable reads a run_id from parent state, polls until the child run
    reaches a terminal status, then writes declared output_mapping fields.
    """
    from workflow.runs import poll_child_run_status

    spec = node.await_run_spec or {}
    run_id_field: str = spec.get("run_id_field", "")
    output_mapping: dict[str, str] = spec.get("output_mapping", {})
    timeout_seconds: float = float(spec.get("timeout_seconds", 300.0))

    if not run_id_field:
        raise CompilerError(
            f"Node '{node.node_id}': await_run_spec missing 'run_id_field'."
        )

    _base = Path(base_path)

    def _node_fn(state: dict[str, Any]) -> dict[str, Any]:
        import json as _json
        run_id: str = state.get(run_id_field, "") or ""
        if not run_id:
            raise RuntimeError(
                f"await_branch_run node '{node.node_id}': "
                f"state field '{run_id_field}' is empty or missing."
            )
        record = poll_child_run_status(
            _base, run_id, timeout_seconds=timeout_seconds,
        )
        raw_output = record.get("output") or {}
        if isinstance(raw_output, str):
            try:
                raw_output = _json.loads(raw_output)
            except Exception:
                raw_output = {}

        updates: dict[str, Any] = {}
        for parent_key, child_key in output_mapping.items():
            updates[parent_key] = raw_output.get(child_key)
        return updates

    return _node_fn


def _build_node(
    node: NodeDefinition,
    *,
    provider_call: Callable[..., str] | None,
    event_sink: Callable[..., None] | None,
    domain_id: str = "",
    state_schema: list[dict[str, Any]] | None = None,
    llm_policy: dict[str, Any] | None = None,
    concurrency_tracker: ConcurrencyTracker | None = None,
    base_path: str | Path | None = None,
    parent_run_id: str = "",
    invocation_depth: int = 0,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Dispatch a NodeDefinition to the right adapter.

    ``domain_id`` is threaded from ``compile_branch`` (Phase D
    Option B). NodeDefinition has no ``domain_id`` field; domain is
    a Branch-level attribute. When ``domain_id`` is non-empty and
    ``(domain_id, node.node_id)`` resolves in the domain registry,
    the opaque-node branch is taken.

    ``llm_policy`` is the effective policy for this node — the node's
    own policy or the branch default; resolved by ``compile_branch``.
    ``concurrency_tracker`` limits concurrent LLM/sandbox calls via a
    semaphore acquired before the provider call and released after.
    """
    from workflow.domain_registry import resolve_domain_callable

    has_template = bool((node.prompt_template or "").strip())
    has_source = bool((node.source_code or "").strip())
    if has_template and has_source:
        raise CompilerError(
            f"Node '{node.node_id}' has both prompt_template and "
            f"source_code — exactly one must be set."
        )
    if has_source:
        inner = _build_source_code_node(
            node, event_sink=event_sink, concurrency_tracker=concurrency_tracker,
        )
        return _wrap_with_checkpoints(inner, node, event_sink)
    if has_template:
        inner = _build_prompt_template_node(
            node, provider_call=provider_call, event_sink=event_sink,
            state_schema=state_schema, llm_policy=llm_policy,
            concurrency_tracker=concurrency_tracker,
        )
        return _wrap_with_checkpoints(inner, node, event_sink)
    if domain_id:
        # Ensure platform opaque callables (e.g. read_repo_files) are
        # registered before we resolve — importing the effectors package runs
        # its registration side effects. Lazy + best-effort so a missing
        # optional dependency can't break compilation of unrelated branches.
        try:
            import workflow.effectors  # noqa: F401
        except Exception:  # pragma: no cover - registration is best-effort
            logger.debug("effectors import for opaque registration failed", exc_info=True)
        opaque = resolve_domain_callable(domain_id, node.node_id)
        if opaque is not None:
            inner = _build_opaque_node(node, opaque, event_sink=event_sink)
            return _wrap_with_checkpoints(inner, node, event_sink)
    if node.invoke_branch_spec is not None:
        if base_path is None:
            raise CompilerError(
                f"Node '{node.node_id}' uses invoke_branch_spec but "
                f"compile_branch was not given base_path."
            )
        inner = _build_invoke_branch_node(
            node, base_path=base_path, event_sink=event_sink,
            provider_call=provider_call,
            parent_run_id=parent_run_id,
            depth=invocation_depth,
        )
        return _wrap_with_checkpoints(inner, node, event_sink)
    if node.invoke_branch_version_spec is not None:
        if base_path is None:
            raise CompilerError(
                f"Node '{node.node_id}' uses invoke_branch_version_spec but "
                f"compile_branch was not given base_path."
            )
        inner = _build_invoke_branch_version_node(
            node, base_path=base_path, event_sink=event_sink,
            provider_call=provider_call,
            parent_run_id=parent_run_id,
            depth=invocation_depth,
        )
        return _wrap_with_checkpoints(inner, node, event_sink)
    if node.await_run_spec is not None:
        if base_path is None:
            raise CompilerError(
                f"Node '{node.node_id}' uses await_run_spec but "
                f"compile_branch was not given base_path."
            )
        inner = _build_await_branch_run_node(
            node, base_path=base_path, event_sink=event_sink,
        )
        return _wrap_with_checkpoints(inner, node, event_sink)
    # Fallback: a genuine body-less node in a non-domain-trusted
    # context is a malformed Branch. Preserve the CompilerError
    # contract so user Branches that omit both template and source
    # (and don't resolve via a domain registry) fail loudly at
    # compile time rather than silently running as pass-throughs.
    # Phase D §4.1 #2.
    raise CompilerError(
        f"Node '{node.node_id}' must have either prompt_template or "
        f"source_code (or resolve via the domain-trusted opaque "
        f"registry when domain_id is set)."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Conditional edge predicate
# ─────────────────────────────────────────────────────────────────────────────


def _build_conditional_router(
    source_node: NodeDefinition | None,
    conditions: dict[str, str],
) -> Callable[[dict[str, Any]], str]:
    """Return a LangGraph-compatible router function.

    LangGraph's ``add_conditional_edges(source, router, path_map)``
    contract: the router returns a KEY into ``path_map``, and LangGraph
    looks up the target node via ``self.ends[router_result]``. Returning
    a target node directly makes LangGraph raise ``KeyError`` (the
    target isn't a path_map key). Conditions IS the path_map here, so
    the router reads the state's output_key and returns it verbatim
    when it's a valid label; otherwise falls back to the first declared
    label so the graph cannot hang on a missing/malformed output.

    Rationale for returning-label-not-target: matches
    ``graph.add_conditional_edges(..., path_map=conditions)`` semantics.
    Prior shape returned ``conditions[value]`` (a target) which LangGraph
    then tried to look up as a path_map KEY — always KeyError for any
    non-empty conditions dict. BUG-019/021/022 root cause (Tier-1
    investigation, 2026-04-23).
    """
    output_key = ""
    if source_node and source_node.output_keys:
        output_key = source_node.output_keys[0]

    # Fallback must be a LABEL (path_map key), not a target.
    fallback = next(iter(conditions.keys()), END)

    def _route(state: dict[str, Any]) -> str:
        if not output_key:
            return fallback
        value = state.get(output_key, "")
        if not isinstance(value, str):
            value = str(value)
        # Return the label when it's a valid path_map key; otherwise
        # fall back to the first declared label so the graph advances
        # rather than KeyError-ing.
        if value in conditions:
            return value
        return fallback

    return _route


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CompiledBranch:
    """Result of compiling a BranchDefinition.

    ``state_type`` is the synthesized TypedDict — useful for validating
    user-provided inputs before invoking the graph.
    ``graph`` is the uncompiled ``StateGraph``; callers attach their own
    checkpointer via ``graph.compile(checkpointer=...)`` so the runner can
    use a shared SqliteSaver.
    ``node_ids_in_order`` is the declared node ordering from graph_nodes.
    """

    graph: StateGraph
    state_type: type
    branch: BranchDefinition
    node_ids_in_order: list[str]
    concurrency_tracker: ConcurrencyTracker | None = None


def compile_branch(
    branch: BranchDefinition,
    *,
    provider_call: Callable[..., str] | None = None,
    event_sink: Callable[..., None] | None = None,
    concurrency_budget_override: int | None = None,
    base_path: str | Path | None = None,
    parent_run_id: str = "",
    invocation_depth: int = 0,
) -> CompiledBranch:
    """Compile a validated BranchDefinition into a StateGraph.

    Parameters
    ----------
    branch
        The branch to compile. Must have passed ``branch.validate()``.
    provider_call
        Synchronous LLM caller with signature ``(prompt, system, *, role)
        -> str``. When ``None``, prompt_template nodes return a mock
        string (useful for tests).
    event_sink
        Optional callable invoked after each node executes with
        per-node diagnostics. Used by the runner to record
        ``RunStepEvent`` rows.
    concurrency_budget_override
        Override the branch-level ``concurrency_budget`` for this
        compilation. When ``None``, falls back to ``branch.concurrency_budget``.
        When both are ``None``, concurrency is unbounded (current behavior).

    Returns
    -------
    CompiledBranch
        An uncompiled StateGraph + synthesized TypedDict. The caller
        attaches a checkpointer via ``graph.compile(checkpointer=...)``
        and invokes with the synthesized state type.
    """
    errors = branch.validate()
    if errors:
        raise CompilerError(
            "Cannot compile invalid branch:\n  - " + "\n  - ".join(errors)
        )

    # Build-time warnings (input_keys leaks, etc.) — emit through the
    # event_sink so callers' per-run event logs see them before the
    # first node runs. Warnings are non-fatal regardless of strict
    # isolation; strict mode only gates *runtime* behavior.
    if event_sink is not None:
        for warning in collect_build_warnings(branch):
            try:
                event_sink(
                    node_id=warning["node_id"],
                    phase="warning",
                    kind=warning["kind"],
                    placeholder=warning.get("placeholder", ""),
                    declared_input_keys=warning.get("declared_input_keys", []),
                    message=warning.get("message", ""),
                )
            except Exception as exc:  # noqa: BLE001
                if _is_cancel_exception(exc):
                    raise
                logger.exception(
                    "event_sink raised emitting build-time warning for %s",
                    warning.get("node_id", "?"),
                )

    # Inject _fired_checkpoints into the schema when any node uses checkpoints.
    # This field accumulates the list of fired checkpoint IDs across the run
    # so each checkpoint fires at most once (idempotent on resume).
    schema = list(branch.state_schema or [])
    has_checkpoints = any(
        getattr(nd, "checkpoints", None) for nd in branch.node_defs
    )
    if has_checkpoints:
        if not any(f.get("name") == "_fired_checkpoints" for f in schema):
            schema.append({"name": "_fired_checkpoints", "type": "list", "reducer": "append"})
    state_type = _build_state_typeddict(schema)
    graph: StateGraph = StateGraph(state_type)

    # Build concurrency tracker: override > branch-level > None (unbounded).
    effective_budget = (
        concurrency_budget_override
        if concurrency_budget_override is not None
        else getattr(branch, "concurrency_budget", None)
    )
    concurrency_tracker: ConcurrencyTracker | None = (
        ConcurrencyTracker(effective_budget) if effective_budget is not None else None
    )

    node_by_id: dict[str, NodeDefinition] = {
        n.node_id: n for n in branch.node_defs
    }
    graph_node_by_id: dict[str, GraphNodeRef] = {
        gn.id: gn for gn in branch.graph_nodes
    }

    node_ids_in_order = [gn.id for gn in branch.graph_nodes]

    # Add graph nodes to the StateGraph. Each graph_node points at a
    # node_def via ``node_def_id`` (usually the same as ``id``).
    for gn in branch.graph_nodes:
        def_id = gn.node_def_id or gn.id
        node_def = node_by_id.get(def_id)
        if node_def is None:
            raise CompilerError(
                f"Graph node '{gn.id}' references unknown node_def_id "
                f"'{def_id}'."
            )
        # Effective llm_policy: node-level takes precedence over branch default.
        effective_policy = node_def.llm_policy or getattr(
            branch, "default_llm_policy", None,
        )
        fn = _build_node(
            node_def,
            provider_call=provider_call,
            event_sink=event_sink,
            domain_id=branch.domain_id,
            state_schema=branch.state_schema,
            llm_policy=effective_policy,
            concurrency_tracker=concurrency_tracker,
            base_path=base_path,
            parent_run_id=parent_run_id,
            invocation_depth=invocation_depth,
        )
        graph.add_node(gn.id, fn)

    # Entry point: connect START to the declared entry node.
    if branch.entry_point:
        graph.add_edge(START, branch.entry_point)

    # Simple edges.
    for edge in branch.edges:
        src = START if edge.from_node == "START" else edge.from_node
        dst = END if edge.to_node == "END" else edge.to_node
        if src == START and branch.entry_point == edge.to_node:
            # Already wired via add_edge(START, entry_point) above.
            continue
        graph.add_edge(src, dst)

    # Conditional edges.
    for cedge in branch.conditional_edges:
        source_ref = graph_node_by_id.get(cedge.from_node)
        source_def_id = source_ref.node_def_id if source_ref else cedge.from_node
        source_def = node_by_id.get(source_def_id or cedge.from_node)
        conditions = {
            label: (END if tgt == "END" else tgt)
            for label, tgt in cedge.conditions.items()
        }
        router = _build_conditional_router(source_def, conditions)
        graph.add_conditional_edges(cedge.from_node, router, conditions)

    return CompiledBranch(
        graph=graph,
        state_type=state_type,
        branch=branch,
        node_ids_in_order=node_ids_in_order,
        concurrency_tracker=concurrency_tracker,
    )


# ── Teammate messaging primitives ─────────────────────────────────────────────
# These are graph-compiler-level helpers that nodes call at runtime to send /
# receive teammate messages.  They are thin wrappers around workflow.runs so
# that graph_compiler owns the dispatch contract.


def compile_send_message_spec(
    base_path: "Path | str",
    *,
    run_id: str,
    to_node_id: str,
    message_type: str,
    body: "dict[str, Any]",
    reply_to_id: str = "",
) -> "dict[str, Any]":
    """Send a teammate message from a running node.

    Calls post_teammate_message and returns the persisted record dict.
    Raises KeyError if run_id does not exist; raises ValueError on invalid args.
    """
    from workflow.runs import post_teammate_message

    record = post_teammate_message(
        base_path,
        from_run_id=run_id,
        to_node_id=to_node_id,
        message_type=message_type,
        body=body,
        reply_to_id=reply_to_id or None,
    )
    return record


def compile_receive_messages_spec(
    base_path: "Path | str",
    *,
    node_id: str,
    timeout: int = 0,
    run_id: str = "",
    message_types: "list[str] | None" = None,
    since: "str | None" = None,
    limit: int = 50,
) -> "dict[str, Any]":
    """Receive queued teammate messages for a node.

    Non-blocking (timeout=0 is the contract; positive timeout ignored for now).
    When run_id is given, returns only messages sent from that run (cross-run
    isolation).  Returns ``{"messages": [...], "count": N}``.
    """
    from workflow.runs import read_teammate_messages

    rows = read_teammate_messages(
        base_path,
        node_id=node_id,
        since=since,
        message_types=message_types,
        limit=limit,
    )
    if run_id:
        rows = [r for r in rows if r.get("from_run_id") == run_id]
    return {"messages": rows, "count": len(rows)}


def validate_message_recipients(
    branch: "BranchDefinition",
    send_message_specs: "list[dict[str, Any]]",
) -> None:
    """Compile-time validation: every to_node_id must exist in the branch.

    Raises BranchValidationError (subclass of ValueError) listing all unknown
    recipients so the caller gets a single actionable error.
    """
    known_node_ids = {n.node_id for n in branch.node_defs}
    unknown = [
        spec["to_node_id"]
        for spec in send_message_specs
        if spec.get("to_node_id") and spec["to_node_id"] not in known_node_ids
    ]
    if unknown:
        raise BranchValidationError(
            "send_message_spec recipient(s) not found in branch: "
            + ", ".join(repr(u) for u in unknown)
        )
