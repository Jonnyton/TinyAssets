"""Pure, closed evidence for a safe capacity transition; never launch authority.

The caller must additionally prove durable progress is quiescent and authorize
the next candidate. In particular, an empty native tool journal is NOT evidence
that a delegated agent did nothing. Missing execution telemetry stays unknown.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from tinyassets.providers.diagnostics import ProviderAttemptDiagnostic
from tinyassets.providers.model_capacity import MAX_RETRY_SECONDS
from tinyassets.providers.model_policy import Exhaustion, ModelRef

_FAILURES = frozenset({
    "provider_credit_exhausted", "provider_rate_limited", "provider_overloaded",
})


@dataclass(frozen=True, slots=True)
class CapacityBoundary:
    exhaustion: Exhaustion
    attempted: bool
    failure_class: str | None
    retry_after_s: float | None


@dataclass(frozen=True, slots=True)
class NativeCompletionEvidence:
    """Local adapter evidence for one reaped, completely observed native attempt.

    This value must be supplied by the installed executor, not remote metadata.
    A complete protocol can attest absence of effects only when every event is
    supported. Any unknown event, truncated stream or live child stays unproved.
    """

    provider: str
    protocol_complete: bool
    process_reaped: bool
    side_effect_state: str


def capacity_boundary(
    current: ModelRef, attempts: Any, *, execution_kind: str,
    native_evidence: Any = (),
) -> CapacityBoundary | None:
    """Return evidence only when every diagnostic permits this exact transition.

    A skipped quota gate is not relabelled as a remotely reported rate limit.
    Unknown scope excludes the account through the existing conservative policy;
    it never invents account independence. Callers cannot substitute exception
    summary fields for per-attempt evidence.
    """
    if execution_kind not in ("engine_inference", "native_agent"):
        return None
    if (type(current) is not ModelRef or type(current.connection_id) is not str
            or not current.connection_id or not current.connection_id.isprintable()
            or len(current.connection_id) > 4096 or type(current.model_id) is not str
            or len(current.model_id) > 4096
            or (current.model_id and not current.model_id.isprintable())):
        return None
    if type(attempts) not in (tuple, list) or not 1 <= len(attempts) <= 64:
        return None
    if type(native_evidence) is not tuple:
        return None
    if execution_kind == "native_agent":
        # Each proof belongs to that exact attempt slot; skipped slots need none.
        if len(native_evidence) != len(attempts):
            return None
    elif native_evidence:
        return None
    scopes = []
    delays = []
    failures = []
    attempted = False
    for index, item in enumerate(attempts):
        if (type(item) is not ProviderAttemptDiagnostic
                or item.provider != current.connection_id
                or item.status not in ("skipped", "failed")
                or item.capacity_scope not in (None, "model", "account", "unknown")
                or (item.failure_class is not None and type(item.failure_class) is not str)):
            return None
        if item.status == "skipped":
            if (item.skip_class != "quota_or_cooldown"
                    or item.side_effect_state not in (None, "none")
                    or item.failure_class not in (None, *_FAILURES)
                    or (execution_kind == "native_agent" and native_evidence[index] is not None)):
                return None
        else:
            if item.side_effect_state != "none" or item.failure_class not in _FAILURES:
                return None
            if execution_kind == "native_agent":
                proof = native_evidence[index]
                if (type(proof) is not NativeCompletionEvidence
                        or proof.provider != current.connection_id
                        or proof.protocol_complete is not True
                        or proof.process_reaped is not True
                        or proof.side_effect_state != "none"):
                    return None
            attempted = True
        delay = item.retry_after_s
        if delay is not None:
            if (type(delay) not in (int, float) or not 0 <= delay <= MAX_RETRY_SECONDS
                    or not math.isfinite(delay)):
                return None
            delays.append(delay)
        scopes.append(item.capacity_scope)
        if item.failure_class is not None:
            failures.append(item.failure_class)
    # Only unanimous model-local evidence allows a sibling on the same source.
    scope = "model" if all(value == "model" for value in scopes) else "account"
    return CapacityBoundary(
        Exhaustion(scope, current), attempted, failures[-1] if failures else None,
        max(delays) if delays else None,
    )
