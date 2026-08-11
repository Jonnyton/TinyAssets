"""Worker-free daemon liveness and assigned-credential hold evidence."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from tinyassets.api.status import _compute_supervisor_liveness
from tinyassets.assigned_credential_execution import NoRequesterOwnedExecutor
from tinyassets.branch_tasks import BranchTask, append_task


def test_cloud_worker_supervisor_modules_are_absent() -> None:
    assert importlib.util.find_spec("tinyassets.cloud_worker") is None
    assert importlib.util.find_spec("tinyassets.cloud_worker_healthcheck") is None


def test_empty_queue_is_live_without_a_worker_fleet(
    tmp_path: Path,
    monkeypatch,
) -> None:
    universe = tmp_path / "universe"
    universe.mkdir()
    monkeypatch.setattr(
        "tinyassets.assigned_credential_execution.assigned_credential_availability",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            NoRequesterOwnedExecutor()
        ),
    )

    result = _compute_supervisor_liveness(universe)

    assert result["queue_state"]["depth"] == 0
    assert result["assigned_credential"]["status"] == "held"
    assert any("no_requester_owned_executor" in item for item in result["warnings"])


def test_pending_queue_remains_visible_while_credential_is_held(
    tmp_path: Path,
    monkeypatch,
) -> None:
    universe = tmp_path / "universe"
    universe.mkdir()
    append_task(
        universe,
        BranchTask(
            branch_task_id="task-a",
            branch_def_id="branch-a",
            universe_id=universe.name,
            hold_reason="no_requester_owned_executor",
        ),
    )
    monkeypatch.setattr(
        "tinyassets.assigned_credential_execution.assigned_credential_availability",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            NoRequesterOwnedExecutor()
        ),
    )

    result = _compute_supervisor_liveness(universe)

    assert result["queue_state"]["pending"] == 1
    assert result["queue_state"]["depth"] == 1
    assert result["assigned_credential"]["hold_reason"] == (
        "no_requester_owned_executor"
    )
