"""Trajectory (process) evaluation for the coding / community-patch lane.

This grades *how a coding-lane run behaved* — the execution path — as opposed
to ``coding_packet_rubric.py`` which validates *what the packet claims* against
evidence (output eval). The two are deliberately different axes:

- ``validate_coding_packet_rubric`` -> claim-validity *block rules* (KEEP needs
  child-output evidence, no overclaim, etc.).
- ``evaluate_coding_trajectory``     -> path-quality *score* (did the run
  progress cleanly, without excessive provider retries, recursion-limit
  ceilings, or broken child runs?).

This is the coding-lane analog of ``tinyassets/evaluation/process.py`` (the prose
scene-loop trajectory evaluator), but it is NOT a port: the coding lane emits no
``quality_trace``. Its path data is assembled from a run record + ``run_events``
+ ``provider_calls`` + ``child_failures`` + ``__system__`` telemetry (all keyed
by ``run_id``; see ``tinyassets/runs.py``). ``coding_trajectory_from_packet`` and
``coding_trajectory_from_run`` normalize those sources into the input dict this
evaluator scores.

Design constraints (from the S3 design note + Codex review precedent):

1. **Fail-open.** Only *positive* evidence of a bad path deducts. A signal that
   is simply absent makes its check *not applicable* (excluded from the
   aggregate), never a failure. With < 2 applicable checks the verdict is
   ``skip`` (inconclusive) with the reserved score ``-1.0`` — so warn mode emits
   nothing and any future enforce mode never blocks on missing data.
2. **Separate axis.** Signals this evaluator shares with the output rubric
   (``recursion_limit_applied``, child attachment) are scored as quality
   deductions here, NOT re-emitted as block rules. When this is later wired into
   the ship gate it must surface on its own ``trajectory_warnings`` channel,
   distinct from ``rubric_warnings`` — avoiding the S2 double-reporting trap.
3. **Pure.** No IO, no network, no LLM. Callers assemble the trajectory dict and
   decide whether to log, warn, or (host-gated) gate on the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tinyassets.evaluation import EvalResult

# Minimum applicable checks required before the evaluation is conclusive.
# Below this, the trajectory data is too thin to judge -> skip, never fail.
MIN_APPLICABLE_CHECKS = 2

# Default aggregate pass bar over applicable checks. Callers may override.
DEFAULT_PASS_THRESHOLD = 0.8

# Ground-truth dimensions that cannot be offset by clean modifier checks: if one
# of these is applicable AND failed, the trajectory fails regardless of how high
# the weighted aggregate climbs. Without this, a hard terminal failure (0.3) or a
# child_timeout (0.2) plus four clean checks averages >= 0.8 and would spuriously
# pass. These are exactly the two heaviest-weight dimensions.
_CRITICAL_FAIL_CHECKS = frozenset({"terminal_health", "child_integrity"})

# Relative weights per dimension. Child integrity is the heaviest because
# attached child-run evidence is the grounding of any coding KEEP; node
# progression is the lightest because step_index is an opaque cursor, not a
# node ordinal (see tinyassets/runs.py:1443).
_CHECK_WEIGHTS: dict[str, float] = {
    "terminal_health": 0.25,
    "provider_efficiency": 0.20,
    "recursion_discipline": 0.15,
    "child_integrity": 0.25,
    "node_progression": 0.15,
}

# run_status values that count as a clean terminal state.
_HEALTHY_TERMINAL = {"completed", "succeeded", "success"}
# run_status values that are clean-but-not-success (refused / awaiting review).
_CLEAN_NONSUCCESS = {"review_ready", "blocked", "observe"}
# failure_class -> how much the path was the run's own fault vs infra.
# Infra-class failures still indicate an unhealthy path the loop took.
_INFRA_FAILURE_CLASSES = {
    "provider_exhausted",
    "quota_exhausted",
    "provider_overloaded",
    "provider_unavailable",
    "sandbox_unavailable",
}
# ChildFailure.failure_class severities (1.0 = clean, lower = worse).
_CHILD_FAILURE_SCORE = {
    "child_failed": 0.0,
    "child_timeout": 0.2,
    "child_cancelled": 0.3,
    "child_unknown": 0.2,
}


@dataclass
class CodingTrajectoryCheck:
    """Result of one path-quality dimension.

    ``applicable`` is False when the trajectory carried no signal for this
    dimension; non-applicable checks are excluded from the aggregate so absent
    data never counts as failure.
    """

    name: str
    applicable: bool
    passed: bool
    score: float
    details: dict[str, Any] = field(default_factory=dict)
    observation: str = ""


@dataclass
class CodingTrajectoryEvaluation:
    """Aggregated result across coding-lane path-quality checks."""

    checks: list[CodingTrajectoryCheck]
    aggregate_score: float
    failing_checks: list[str] = field(default_factory=list)
    conclusive: bool = True
    pass_threshold: float = DEFAULT_PASS_THRESHOLD

    @property
    def applicable_checks(self) -> list[CodingTrajectoryCheck]:
        return [check for check in self.checks if check.applicable]

    @property
    def verdict(self) -> str:
        """One of ``pass`` / ``fail`` / ``skip``.

        ``skip`` means inconclusive (too little trajectory data) — never a
        failure. ``fail`` requires positive evidence, via either path:
        - a *critical* dimension (terminal_health / child_integrity) is
          applicable and failed — it cannot be offset by clean modifier checks;
        - or any applicable check failed AND the weighted aggregate is below the
          pass bar.

        The boundary is ``>= pass_threshold`` passes (a score that meets the bar
        passes, consistent with the rubric's ``>= 9.0`` KEEP convention); the
        two offset cases the threshold alone would miss are caught by the
        critical-fail rule, not by tightening the boundary.
        """
        if not self.conclusive:
            return "skip"
        if any(
            check.applicable
            and not check.passed
            and check.name in _CRITICAL_FAIL_CHECKS
            for check in self.checks
        ):
            return "fail"
        if self.failing_checks and self.aggregate_score < self.pass_threshold:
            return "fail"
        return "pass"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict (mirrors ProcessEvaluation)."""
        return {
            "verdict": self.verdict,
            "conclusive": self.conclusive,
            "aggregate_score": self.aggregate_score,
            "pass_threshold": self.pass_threshold,
            "failing_checks": list(self.failing_checks),
            "checks": [
                {
                    "name": check.name,
                    "applicable": check.applicable,
                    "passed": check.passed,
                    "score": check.score,
                    "details": check.details,
                    "observation": check.observation,
                }
                for check in self.checks
            ],
        }

    def to_eval_result(self) -> "EvalResult":
        """Convert to a unified EvalResult for protocol-compatible routing.

        Inconclusive evaluations use the reserved not-applicable score -1.0 with
        verdict ``skip``, per the EvalResult convention.
        """
        from tinyassets.evaluation import EvalResult

        verdict = self.verdict
        if verdict == "skip":
            score = -1.0
        else:
            score = max(0.0, min(1.0, self.aggregate_score))
        return EvalResult(
            score=score,
            verdict=verdict,  # type: ignore[arg-type]
            kind="process",
            label="coding_trajectory_evaluation",
            details={
                "conclusive": self.conclusive,
                "aggregate_score": self.aggregate_score,
                "failing_checks": list(self.failing_checks),
            },
        )


def evaluate_coding_trajectory(
    trajectory: dict[str, Any],
    *,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
) -> CodingTrajectoryEvaluation:
    """Score coding-lane execution-path quality from a normalized trajectory.

    ``trajectory`` is a normalized view (see ``coding_trajectory_from_packet`` /
    ``coding_trajectory_from_run``). All keys are optional; absent keys make the
    corresponding check non-applicable rather than failing. Recognized keys:

    - ``run_status``: terminal status string.
    - ``failure_class``: ``_classify_failure`` output (or None).
    - ``provider_calls``: list of ``{node_id, attempts, degraded, ...}``.
    - ``recursion_limit_applied``: bool.
    - ``child_failures``: list of ``{failure_class, child_status, ...}``.
    - ``receipt_waiting``: bool (child invoke timed out, unresolved).
    - ``child_attached``: bool (a child run was cleanly attached).
    - ``node_events``: list of ``{node_id, status}`` (run_events rows).
    """
    if not isinstance(trajectory, dict):
        trajectory = {}

    checks = [
        _check_terminal_health(trajectory),
        _check_provider_efficiency(trajectory),
        _check_recursion_discipline(trajectory),
        _check_child_integrity(trajectory),
        _check_node_progression(trajectory),
    ]

    applicable = [check for check in checks if check.applicable]
    conclusive = len(applicable) >= MIN_APPLICABLE_CHECKS

    weighted_total = 0.0
    weight_sum = 0.0
    failing_checks: list[str] = []
    for check in applicable:
        weight = _CHECK_WEIGHTS.get(check.name, 1.0)
        weighted_total += check.score * weight
        weight_sum += weight
        if not check.passed:
            failing_checks.append(check.name)

    aggregate = weighted_total / weight_sum if weight_sum else 0.0
    return CodingTrajectoryEvaluation(
        checks=checks,
        aggregate_score=aggregate,
        failing_checks=failing_checks,
        conclusive=conclusive,
        pass_threshold=pass_threshold,
    )


def _check_terminal_health(trajectory: dict[str, Any]) -> CodingTrajectoryCheck:
    raw_status = trajectory.get("run_status")
    status = str(raw_status or "").strip().lower()
    failure_class = str(trajectory.get("failure_class") or "").strip().lower()

    if not status and not failure_class:
        return _not_applicable("terminal_health", "no terminal status recorded")

    if status in _HEALTHY_TERMINAL and not failure_class:
        score, passed, obs = 1.0, True, ""
    elif status in _CLEAN_NONSUCCESS and not failure_class:
        # Clean refusal / awaiting review — a valid, sound trajectory.
        score, passed, obs = 0.7, True, ""
    elif status == "interrupted":
        score, passed, obs = 0.4, False, "Run was interrupted before a terminal verdict."
    elif failure_class in _INFRA_FAILURE_CLASSES:
        score, passed, obs = (
            0.1,
            False,
            f"Run path failed on infrastructure class {failure_class!r}.",
        )
    elif failure_class:
        score, passed, obs = (
            0.3,
            False,
            f"Run terminated with failure class {failure_class!r}.",
        )
    else:
        # Unknown non-terminal / unrecognized status: positive evidence of an
        # unclean path, but mild.
        score, passed, obs = 0.5, False, f"Unrecognized terminal status {status!r}."

    return CodingTrajectoryCheck(
        name="terminal_health",
        applicable=True,
        passed=passed,
        score=score,
        details={"run_status": status, "failure_class": failure_class},
        observation=obs,
    )


def _check_provider_efficiency(trajectory: dict[str, Any]) -> CodingTrajectoryCheck:
    calls = trajectory.get("provider_calls")
    if not isinstance(calls, list) or not calls:
        return _not_applicable("provider_efficiency", "no provider calls recorded")

    total = len(calls)
    degraded = 0
    retried = 0
    for call in calls:
        if not isinstance(call, dict):
            continue
        if _is_truthy(call.get("degraded")):
            degraded += 1
        attempts = call.get("attempts")
        if isinstance(attempts, (int, float)) and attempts > 1:
            retried += 1

    degraded_frac = degraded / total
    retried_frac = retried / total
    score = max(0.0, 1.0 - 0.5 * degraded_frac - 0.4 * retried_frac)
    # A path is healthy if no provider was degraded and retries were rare.
    passed = degraded == 0 and retried_frac <= 0.5

    obs = ""
    if not passed:
        obs = (
            f"{degraded}/{total} provider calls degraded, "
            f"{retried}/{total} required retries."
        )

    return CodingTrajectoryCheck(
        name="provider_efficiency",
        applicable=True,
        passed=passed,
        score=score,
        details={
            "total_calls": total,
            "degraded": degraded,
            "retried": retried,
        },
        observation=obs,
    )


def _check_recursion_discipline(trajectory: dict[str, Any]) -> CodingTrajectoryCheck:
    # A negative signal: its *absence* is good. Applicable whenever we have any
    # of the run-level signals that would have carried it.
    if not _has_run_level_signal(trajectory):
        return _not_applicable(
            "recursion_discipline", "no run-level telemetry recorded"
        )

    applied = _is_truthy(trajectory.get("recursion_limit_applied"))
    if not applied:
        return CodingTrajectoryCheck(
            name="recursion_discipline",
            applicable=True,
            passed=True,
            score=1.0,
            details={"recursion_limit_applied": False},
        )

    # The ceiling was hit. Worse if it produced no usable child output.
    empty_output = _is_truthy(trajectory.get("recursion_limit_empty_output"))
    score = 0.0 if empty_output else 0.4
    obs = "Run hit the recursion limit"
    obs += " and produced empty output." if empty_output else "."

    return CodingTrajectoryCheck(
        name="recursion_discipline",
        applicable=True,
        passed=False,
        score=score,
        details={
            "recursion_limit_applied": True,
            "recursion_limit_empty_output": empty_output,
        },
        observation=obs,
    )


def _check_child_integrity(trajectory: dict[str, Any]) -> CodingTrajectoryCheck:
    child_failures = trajectory.get("child_failures")
    has_failures_key = isinstance(child_failures, list)
    receipt_waiting = _is_truthy(trajectory.get("receipt_waiting"))
    child_attached = _is_truthy(trajectory.get("child_attached"))

    # Applicable only when the run involved a child dimension at all.
    if not has_failures_key and not receipt_waiting and not child_attached:
        return _not_applicable("child_integrity", "run had no child-run dimension")

    failures = [f for f in (child_failures or []) if isinstance(f, dict)]

    if receipt_waiting and not failures:
        return CodingTrajectoryCheck(
            name="child_integrity",
            applicable=True,
            passed=False,
            score=0.3,
            details={"receipt_waiting": True, "child_failure_count": 0},
            observation="Child invocation timed out, unresolved (receipt-waiting).",
        )

    if not failures:
        return CodingTrajectoryCheck(
            name="child_integrity",
            applicable=True,
            passed=True,
            score=1.0,
            details={"child_failure_count": 0, "child_attached": child_attached},
        )

    worst = min(
        _CHILD_FAILURE_SCORE.get(
            str(f.get("failure_class") or "").strip().lower(), 0.2
        )
        for f in failures
    )
    classes = sorted(
        {str(f.get("failure_class") or "?").strip().lower() for f in failures}
    )
    return CodingTrajectoryCheck(
        name="child_integrity",
        applicable=True,
        passed=False,
        score=worst,
        details={"child_failure_count": len(failures), "failure_classes": classes},
        observation=f"Child run(s) failed: {', '.join(classes)}.",
    )


def _check_node_progression(trajectory: dict[str, Any]) -> CodingTrajectoryCheck:
    events = trajectory.get("node_events")
    if not isinstance(events, list) or not events:
        return _not_applicable("node_progression", "no node events recorded")

    statuses: list[str] = []
    failed_nodes: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        status = str(event.get("status") or "").strip().lower()
        statuses.append(status)
        if status in {"failed", "error"}:
            node_id = str(event.get("node_id") or "?")
            failed_nodes.append(node_id)

    ran = sum(1 for s in statuses if s in {"ran", "completed", "succeeded"})
    total = len(statuses) or 1
    score = max(0.0, ran / total - 0.25 * len(failed_nodes))
    score = min(1.0, score)
    passed = not failed_nodes and ran > 0

    obs = ""
    if failed_nodes:
        obs = f"Node(s) failed mid-path: {', '.join(sorted(set(failed_nodes)))}."
    elif ran == 0:
        obs = "No node reached a completed state."

    return CodingTrajectoryCheck(
        name="node_progression",
        applicable=True,
        passed=passed,
        score=score,
        details={"node_count": len(statuses), "failed_nodes": sorted(set(failed_nodes))},
        observation=obs,
    )


# ── Normalizers (source -> trajectory dict) ────────────────────────────────────


def coding_trajectory_from_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Extract a trajectory view from an auto-ship / coding packet.

    This is the *gate-time* source: it sees only what the assembled packet
    carries, which is intentionally thin. Many checks will be non-applicable —
    that is correct, not a bug (fail-open).
    """
    if not isinstance(packet, dict):
        return {}

    system = packet.get("__system__")
    recursion_applied = False
    if isinstance(system, dict):
        recursion_applied = _is_truthy(system.get("recursion_limit_applied"))
    recursion_applied = recursion_applied or _is_truthy(
        packet.get("recursion_limit_applied")
    )

    trajectory: dict[str, Any] = {
        "run_status": packet.get("child_run_status") or packet.get("run_status"),
        "recursion_limit_applied": recursion_applied,
        "recursion_limit_empty_output": recursion_applied
        and _child_output_empty(packet),
    }

    automation = str(packet.get("automation_claim_status") or "").strip().lower()
    if automation:
        trajectory["child_attached"] = "attached" in automation or "invoked" in automation

    # Receipt-waiting is a specific status, not "any gate dict is present" — a
    # resolved gate also has a (different) status. Match runs.py: either
    # parent_loop_status == "receipt_waiting" or the gate dict's status field.
    if _is_receipt_waiting(packet):
        trajectory["receipt_waiting"] = True

    return {k: v for k, v in trajectory.items() if v is not None}


def coding_trajectory_from_run(
    run: dict[str, Any],
    *,
    run_events: list[dict[str, Any]] | None = None,
    failure_class: str | None = None,
    child_failures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the richer *post-run* trajectory view from a run record + events.

    Honest field provenance (verified against ``tinyassets/runs.py``):

    - ``run`` is the raw run record; only ``status`` is a raw run field
      (``_row_to_run`` ~480). ``get_run`` does NOT carry ``failure_class``,
      ``provider_calls``, ``recursion_limit_applied`` or a ``__system__`` blob.
    - ``failure_class`` is a ``_classify_failure`` enrichment (surfaced by
      ``list_recent_runs`` ~4006), so it is passed explicitly here; it falls
      back to ``run['failure_class']`` only when the caller handed an enriched
      API snapshot.
    - ``recursion_limit_applied`` and ``provider_calls`` are ``__system__``
      ``run_events`` rows (``status`` ``"recursion_limit_applied"`` ~2329 /
      ``"provider_calls"`` with ``detail['calls']`` ~2567); we parse them from
      ``run_events`` rather than reading a non-existent run field.
    - ``node_events`` are the non-``__system__`` ``run_events`` rows
      (``{node_id, status}``), so only real nodes count toward progression.
    - ``child_failures`` comes from ``RunOutcome.child_failures`` (~1953),
      passed explicitly.

    This is the higher-signal source for offline scoring; the gate-time path
    uses ``coding_trajectory_from_packet`` instead.
    """
    if not isinstance(run, dict):
        run = {}

    recursion_applied, provider_calls, node_events = _parse_run_events(run_events)

    resolved_failure = failure_class
    if resolved_failure is None:
        resolved_failure = run.get("failure_class")

    trajectory: dict[str, Any] = {
        "run_status": run.get("status"),
        "failure_class": resolved_failure,
        "recursion_limit_applied": recursion_applied,
    }
    if provider_calls is not None:
        trajectory["provider_calls"] = provider_calls
    if node_events is not None:
        trajectory["node_events"] = node_events
    if child_failures is not None:
        trajectory["child_failures"] = child_failures

    return {k: v for k, v in trajectory.items() if v is not None}


def _parse_run_events(
    run_events: list[dict[str, Any]] | None,
) -> tuple[bool, list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
    """Parse ``run_events`` rows into (recursion_applied, provider_calls, node_events).

    Each row is a serialized ``RunStepEvent`` (``{node_id, status, detail}``).
    ``__system__`` rows carry telemetry (recursion-limit, provider calls); all
    other rows are real node steps. Returns ``None`` for provider_calls /
    node_events when no such rows exist, so the corresponding checks stay
    non-applicable (fail-open) rather than scoring an empty list.
    """
    if not isinstance(run_events, list) or not run_events:
        return False, None, None

    recursion_applied = False
    provider_calls: list[dict[str, Any]] | None = None
    node_events: list[dict[str, Any]] = []

    for row in run_events:
        if not isinstance(row, dict):
            continue
        node_id = str(row.get("node_id") or "")
        status = str(row.get("status") or "")
        detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
        if node_id == "__system__":
            if status == "recursion_limit_applied":
                recursion_applied = True
            elif status == "provider_calls":
                calls = detail.get("calls")
                if isinstance(calls, list):
                    provider_calls = calls
            continue
        if node_id:
            node_events.append({"node_id": node_id, "status": status})

    return recursion_applied, provider_calls, (node_events or None)


# ── Helpers ─────────────────────────────────────────────────────────────────────


def _not_applicable(name: str, reason: str) -> CodingTrajectoryCheck:
    return CodingTrajectoryCheck(
        name=name,
        applicable=False,
        passed=True,
        score=0.0,
        details={"reason": reason},
        observation="",
    )


def _has_run_level_signal(trajectory: dict[str, Any]) -> bool:
    """True if the trajectory carries any run-level telemetry.

    Used to decide whether negative signals (e.g. recursion_limit_applied,
    whose *absence* is good) are applicable at all.
    """
    return any(
        key in trajectory
        for key in (
            "run_status",
            "failure_class",
            "recursion_limit_applied",
            "provider_calls",
            "node_events",
        )
    )


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _child_output_empty(packet: dict[str, Any]) -> bool:
    if "child_output" in packet:
        value = packet.get("child_output")
        return value in (None, "", {}, [])
    return False


def _is_receipt_waiting(packet: dict[str, Any]) -> bool:
    """True only on a genuine receipt-waiting signal (matches runs.py).

    The receipt gate is a dict whose ``status`` is ``"receipt_waiting"`` when
    unresolved (runs.py ~2418); a resolved/other gate carries a different
    status. So check the status field, not mere presence of the gate dict.
    """
    if str(packet.get("parent_loop_status") or "").strip().lower() == "receipt_waiting":
        return True
    gate = packet.get("child_invocation_receipt_gate")
    if isinstance(gate, dict):
        return str(gate.get("status") or "").strip().lower() == "receipt_waiting"
    return False
