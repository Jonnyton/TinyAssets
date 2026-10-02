"""Owner-scoped rollout choices, maintainer writes, and account erasure."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tinyassets.storage import DB_FILENAME
from tinyassets.storage.account_agent_loop import account_agent_loop, set_account_agent_loop


def test_default_does_not_create_a_database(tmp_path):
    root = tmp_path / "absent"
    assert account_agent_loop(root, owner_user_id="owner") == "engine"
    assert not (root / DB_FILENAME).exists()
    assert not root.exists()


def test_set_get_and_owner_isolation(tmp_path):
    for value in ("thin", "engine"):
        assert set_account_agent_loop(
            tmp_path, owner_user_id="owner", agent_loop=value, updated_by="test",
        ) == value
        assert account_agent_loop(tmp_path, owner_user_id="owner") == value
        assert account_agent_loop(tmp_path, owner_user_id="other") == "engine"
    with sqlite3.connect(tmp_path / DB_FILENAME) as conn:
        rows = conn.execute(
            "SELECT agent_loop, updated_at, updated_by FROM account_agent_loop"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "engine" and rows[0][1] and rows[0][2] == "test"


@pytest.mark.parametrize("value", ["unknown", "THIN", " thin", "", None])
def test_refused_value_keeps_previous_choice(tmp_path, value):
    set_account_agent_loop(
        tmp_path, owner_user_id="owner", agent_loop="thin", updated_by="test",
    )
    with pytest.raises(ValueError, match="agent_loop"):
        set_account_agent_loop(
            tmp_path, owner_user_id="owner", agent_loop=value, updated_by="refused",
        )
    assert account_agent_loop(tmp_path, owner_user_id="owner") == "thin"
    with sqlite3.connect(tmp_path / DB_FILENAME) as conn:
        assert conn.execute("SELECT updated_by FROM account_agent_loop").fetchone() == ("test",)


@pytest.mark.parametrize("owner", ["", " \t", "x" * 401, "bad\nsubject"])
def test_invalid_subject_is_refused_without_creating_database(tmp_path, owner):
    with pytest.raises(ValueError, match="subject"):
        set_account_agent_loop(
            tmp_path, owner_user_id=owner, agent_loop="thin", updated_by="test",
        )
    assert not (tmp_path / DB_FILENAME).exists()


def test_maintainer_script_exit_codes_and_attribution(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "set_agent_loop.py"
    command = [sys.executable, str(script), "--owner", "owner", "--data-root", str(tmp_path)]
    for value in ("thin", "engine"):
        result = subprocess.run(command + ["--loop", value], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == value
        assert account_agent_loop(tmp_path, owner_user_id="owner") == value
    result = subprocess.run(command + ["--loop", "unknown"], capture_output=True, text=True)
    assert result.returncode != 0
    assert account_agent_loop(tmp_path, owner_user_id="owner") == "engine"
    with sqlite3.connect(tmp_path / DB_FILENAME) as conn:
        assert conn.execute("SELECT updated_by FROM account_agent_loop").fetchone() == (
            "maintainer-script",
        )


def test_account_deletion_sweeps_only_the_deleted_owners_setting(tmp_path):
    from tinyassets.account_deletion import delete_account

    for owner in ("owner", "other"):
        set_account_agent_loop(
            tmp_path, owner_user_id=owner, agent_loop="thin", updated_by="test",
        )
    receipt = delete_account(
        tmp_path, founder_sub="owner", delete_identity=lambda _: "not_applicable",
    )
    assert receipt["unfinished_phases"] == []
    assert receipt["rows_deleted"]["account_agent_loop"] == 1
    assert account_agent_loop(tmp_path, owner_user_id="owner") == "engine"
    assert account_agent_loop(tmp_path, owner_user_id="other") == "thin"
