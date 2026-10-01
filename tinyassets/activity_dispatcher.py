"""Dispatching activities: one live run each, durably, never only at boot
(harness D2; design D4).

Called on the assigned-queue consumer's tick and whenever an activity is
created or answered. For each activity that needs attention it:

* settles one whose run ENDED: a completed run completes the activity with the
  run's result; a failed run fails it; an interrupted run (its owner process
  provably died -- run recovery's rule) is resumed by a new run;
* claims a queued one (or one whose dispatcher died between claiming and
  binding), starts a run of the Activities branch and binds it.

A live run -- queued, running, or owned by a process that is alive or unknown --
is never replaced. Every step is a compare-and-set in the activity store, so
two dispatchers in one process, or a dispatcher racing the owner, cannot both
act on one activity.
"""

from __future__ import annotations

import logging
from pathlib import Path

from tinyassets import activity_runner as runner
from tinyassets import agent_activities as activities

logger = logging.getLogger(__name__)

#: Owner-authority refusals that end an activity, and the one that waits for
#: the owner (no model connected yet is something they fix, not a failure).
_WAITS = {"no_serving_assignment": "Connect a model so your agent can work on this."}


def _run_outcome(base_path: Path, run_id: str) -> tuple[str, str]:
    from tinyassets.runs import get_run

    record = get_run(base_path, run_id) or {}
    output = record.get("output") or {}
    if isinstance(output, str):
        import json

        try:
            output = json.loads(output)
        except ValueError:
            output = {}
    result = output.get("result") if isinstance(output, dict) else ""
    return str(record.get("status") or ""), str(result or "")


def _settle_ended(base_path: Path, universe_id: str, record: dict) -> bool:
    """A bound run ended: complete, fail, or leave for a resume. True if settled."""
    universe_dir = base_path / universe_id
    status, result = _run_outcome(base_path, record["runner_token"])
    generation = record["runner_generation"]
    try:
        if status == "completed":
            activities.transition(universe_dir, record["activity_id"], activities.COMPLETED,
                                  generation=generation, outcome="done",
                                  result_summary=result or record["result_summary"])
            return True
        if status in {"failed", "cancelled"}:
            activities.transition(universe_dir, record["activity_id"], activities.FAILED,
                                  generation=generation, outcome=f"failed:run_{status}")
            return True
    except activities.ActivityRefused as exc:
        if exc.kind not in {"superseded", "invalid_transition"}:
            raise
        return True
    return False  # interrupted: claim a new run below


def _start(base_path: Path, universe_id: str, activity_id: str) -> None:
    universe_dir = base_path / universe_id
    record = activities.get(universe_dir, activity_id)
    if record is None:
        return
    reason = runner.owner_unavailable(base_path, universe_id, record["owner_principal"])
    if reason and reason not in _WAITS:
        try:
            activities.transition(universe_dir, activity_id, activities.FAILED,
                                  outcome="failed:owner_lost")
        except activities.ActivityRefused:
            pass
        return
    if reason:
        activities.note_waiting_for_seat(universe_dir, activity_id)
        return
    generation = activities.claim(
        universe_dir, activity_id,
        replaceable=lambda run_id: runner.state(base_path, run_id) == runner.ENDED)
    if generation is None:
        return
    try:
        runner.start(base_path, universe_id, record, generation)
    except activities.ActivityRefused as exc:
        to = activities.FAILED if exc.kind != "run_refused" else activities.SCHEDULED
        try:
            activities.transition(universe_dir, activity_id, to, generation=generation,
                                  outcome=f"failed:{exc.kind}" if to == activities.FAILED
                                  else "")
        except activities.ActivityRefused:
            pass


def dispatch_universe(base_path: str | Path, universe_id: str) -> None:
    """Settle ended runs and start queued activities in one universe."""
    base_path = Path(base_path)
    universe_dir = base_path / universe_id

    def replaceable(run_id: str) -> bool:
        return runner.state(base_path, run_id) == runner.ENDED

    for activity_id in activities.needing_a_runner(universe_dir, replaceable=replaceable):
        try:
            record = activities.get(universe_dir, activity_id)
            if record is None:
                continue
            if record["status"] == activities.IN_PROGRESS and record["runner_token"]:
                if _settle_ended(base_path, universe_id, record):
                    continue
            _start(base_path, universe_id, activity_id)
        except Exception:  # noqa: BLE001 - one activity never stops the others
            logger.exception("activity dispatch failed universe=%s activity=%s",
                             universe_id, activity_id)


def dispatch_all(base_path: str | Path) -> None:
    """Every universe that has an activity store (the consumer tick)."""
    base_path = Path(base_path)
    records = base_path / ".agent-sessions"
    if not records.is_dir():
        return
    for store in sorted(records.glob("*/agent-activities.db")):
        universe_id = store.parent.name
        if universe_id.startswith(".") or not (base_path / universe_id).is_dir():
            continue
        dispatch_universe(base_path, universe_id)
