"""A universe's run list is its OWN newest runs, not its share of everyone's.

``list_runs`` used to take the newest ``limit`` runs of the whole deployment and
only then keep the ones in the named universe. On a shared host that is usually
none of them, although the universe has runs -- so a custom UI asking for its
agents' runs, or a person asking for theirs, was told there were none.
"""

from __future__ import annotations

import json
import sqlite3

from tinyassets import runs
from tinyassets.api import runs as api_runs

MINE = "u-mine"
THEIRS = "u-theirs"


def _run(base, *, actor: str, queue: str | None, started: str) -> str:
    run_id = runs.create_run(
        base, branch_def_id="b1", thread_id="t", inputs={}, run_name="r",
        actor=actor, queue_universe_id=queue, owner_user_id="",
    )
    with sqlite3.connect(runs.runs_db_path(base)) as conn:
        conn.execute("UPDATE runs SET started_at = ? WHERE run_id = ?", (started, run_id))
    return run_id


def _seed(base):
    # Mine are the OLDEST rows; a crowd of another universe's runs is newer.
    by_actor = _run(base, actor=f"universe:{MINE}", queue=None, started="2026-09-01T00:00:01")
    by_queue = _run(base, actor="owner-a", queue=MINE, started="2026-09-01T00:00:02")
    for i in range(12):
        _run(base, actor=f"universe:{THEIRS}", queue=None, started=f"2026-09-02T00:00:{i:02d}")
    return by_actor, by_queue


def test_the_limit_applies_after_the_universe_not_before(tmp_path):
    by_actor, by_queue = _seed(tmp_path)
    got = runs.list_runs(tmp_path, universe_id=MINE, limit=5)
    assert {r["run_id"] for r in got} == {by_actor, by_queue}
    # Unscoped listing is unchanged: the newest rows of the deployment.
    assert len(runs.list_runs(tmp_path, limit=5)) == 5


def test_the_connector_read_returns_this_universes_runs(tmp_path, monkeypatch):
    by_actor, by_queue = _seed(tmp_path)
    monkeypatch.setattr(api_runs, "_base_path", lambda: str(tmp_path))
    monkeypatch.setattr(api_runs, "_run_read_allowed", lambda record: True)
    payload = json.loads(api_runs._action_list_runs({"universe_id": MINE, "limit": 5}))
    assert {r["run_id"] for r in payload["runs"]} == {by_actor, by_queue}
    # And the other universe's rows never appear under this one's name.
    theirs = json.loads(api_runs._action_list_runs({"universe_id": THEIRS, "limit": 50}))
    assert theirs["count"] == 12
    assert not {by_actor, by_queue} & {r["run_id"] for r in theirs["runs"]}
