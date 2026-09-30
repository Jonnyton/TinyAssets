"""Test helper: make a run's owning process provably dead.

Recovery interrupts a run only when its owner's liveness lock file exists and
nobody holds it (``tinyassets.process_liveness``). A run created in the test
process is owned by the test process, which is alive, so a test of recovery
hands the run to an owner that has a lock file and no holder -- exactly what a
killed process leaves behind.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from tinyassets import process_liveness, runs


def mark_owner_dead(base: str | Path, *run_ids: str) -> str:
    """Point ``run_ids`` at a fresh owner token whose process is dead."""
    token = f"proc_dead_{secrets.token_hex(6)}"
    path = process_liveness.liveness_path(base, token)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    assert process_liveness.owner_state(base, token) == process_liveness.DEAD
    with runs._connect(base) as conn:
        for run_id in run_ids:
            conn.execute("UPDATE runs SET owner_token = ? WHERE run_id = ?", (token, run_id))
    return token
