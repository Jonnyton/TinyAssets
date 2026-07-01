"""Tests for the clean-slate universe reset (tinyassets/reset.py).

Confirmed reset clears every universe (dirs + index/ACL/rules/snapshots) and all
hosted-daemon state, while PRESERVING the branch commons (branch_definitions,
goals) and the wiki. Dry-run deletes nothing.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_UA = "u-01aaaaaaaaaaaaaaaaaaaaaaaa"
_UB = "u-01bbbbbbbbbbbbbbbbbbbbbbbb"


def _count(base: Path, table: str) -> int:
    conn = sqlite3.connect(str(base / ".tinyassets.db"))
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0])
    finally:
        conn.close()


def _seed(base: Path) -> None:
    from tinyassets.daemon_registry import create_daemon
    from tinyassets.daemon_server import (
        ensure_universe_registered,
        grant_universe_access,
        initialize_author_server,
        save_branch_definition,
        save_goal,
    )

    initialize_author_server(base)
    for uid in (_UA, _UB):
        udir = base / uid
        udir.mkdir(parents=True)
        (udir / "soul.md").write_text("---\ntype: Universe Soul\n---\n", encoding="utf-8")
        ensure_universe_registered(base, universe_id=uid, universe_path=udir)
        grant_universe_access(
            base, universe_id=uid, actor_id="founder-sub",
            permission="admin", granted_by="founder-sub",
        )
    (base / ".active_universe").write_text(_UA, encoding="utf-8")
    (base / "wiki").mkdir()  # commons dir — must survive
    # A hosted daemon identity (global) + branch/goal commons.
    create_daemon(base, display_name="Scout", created_by="founder-sub")
    save_branch_definition(base, branch_def={"branch_def_id": "b-commons", "name": "c"})
    save_goal(base, goal={"goal_id": "g-commons", "name": "commons goal"})


def test_dry_run_reports_but_deletes_nothing(tmp_path, monkeypatch):
    from tinyassets.reset import reset

    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    _seed(base)

    plan = reset(base, confirm=False)
    assert set(plan["universe_dirs"]) == {_UA, _UB}
    assert plan["active_universe_marker"] is True
    assert "universe_acl" in plan["db_rows_to_clear"]
    assert "author_definitions" in plan["db_rows_to_clear"]
    assert plan.get("done") is not True
    # Nothing actually deleted.
    assert (base / _UA).is_dir()
    assert (base / ".active_universe").is_file()
    assert _count(base, "universe_acl") == 2
    assert _count(base, "author_definitions") >= 1


def test_confirm_clears_universes_daemons_preserves_commons(tmp_path, monkeypatch):
    from tinyassets.reset import reset

    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    _seed(base)

    # Commons + universe/daemon state present before reset.
    assert _count(base, "branch_definitions") >= 1
    assert _count(base, "goals") >= 1

    plan = reset(base, confirm=True)
    assert plan.get("done") is True

    # Universes gone (dirs + marker + index/acl).
    assert not (base / _UA).exists()
    assert not (base / _UB).exists()
    assert not (base / ".active_universe").exists()
    assert _count(base, "universes") == 0
    assert _count(base, "universe_acl") == 0
    # Daemons gone.
    assert _count(base, "author_definitions") == 0
    assert _count(base, "author_runtime_instances") == 0
    # Branch commons + wiki preserved.
    assert (base / "wiki").is_dir()
    assert _count(base, "branch_definitions") >= 1
    assert _count(base, "goals") >= 1


def test_reset_is_idempotent(tmp_path, monkeypatch):
    from tinyassets.reset import reset

    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    _seed(base)

    reset(base, confirm=True)
    plan2 = reset(base, confirm=True)
    assert plan2["universe_dirs"] == []
    assert plan2["db_rows_to_clear"] == {}
    assert plan2["active_universe_marker"] is False
