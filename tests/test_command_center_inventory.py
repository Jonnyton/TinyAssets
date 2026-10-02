"""The cutover's read-only inventory and its layout table (design E1 / E6)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import command_center_inventory as inv
from tinyassets.command_center_layout import PLATFORM, USER, classify

HOME = "u-01kxm1vszd8hwp7em418asq8h9"
OTHER = "u-01ky3zh1arr8qth8jee7zx63pq"


@pytest.mark.parametrize("name,expected", [
    ("soul.md", USER), ("soul_versions", USER), ("config.yaml", USER),
    ("AGENTS.md", USER), ("skills", USER), ("notes.json", USER),
    ("selftest_note.md", USER), ("workspaces", USER),
    ("soul.edit.md", PLATFORM), ("dispatcher_config.yaml", PLATFORM),
    ("knowledge.db", PLATFORM), ("knowledge.db-wal", PLATFORM), (".runs.db-shm", PLATFORM),
    (".worker_supervisor.worker_assigned_abc.json", PLATFORM), (".soul.lock", PLATFORM),
    (".credentials", PLATFORM), ("lancedb", PLATFORM), ("ledger.json", PLATFORM),
    (".conversation_memory.db.bak-premigrate-1787982564-wal", PLATFORM),
    ("something-nobody-classified.bin", None), (".mystery", None),
])
def test_the_layout_table_puts_trust_in_platform_and_content_with_the_agent(name, expected):
    assert classify(name) == expected


def _fixture(root: Path) -> None:
    home = root / HOME
    home.mkdir(parents=True)
    (home / "soul.md").write_text("# Soul\n", encoding="utf-8")
    (home / "soul.edit.md").write_text("policy\n", encoding="utf-8")
    (home / "config.yaml").write_text(
        "allowed_providers: [codex]\nengine_assignment_state: ready\nstyle: terse\n",
        encoding="utf-8",
    )
    (home / "mystery.bin").write_bytes(b"\x00")
    (home / "status.json").write_text(json.dumps({"universe_id": HOME, "peer": OTHER}),
                                      encoding="utf-8")
    db = sqlite3.connect(root / ".tinyassets.db")
    db.executescript(f"""
        CREATE TABLE universes (universe_id TEXT PRIMARY KEY, display_name TEXT);
        CREATE TABLE runs (run_id TEXT, actor TEXT, payload BLOB,
            storage_class TEXT CHECK (storage_class IN ('scratch','universe')));
        CREATE INDEX runs_by_universe_actor ON runs(actor) WHERE actor LIKE 'universe:%';
        INSERT INTO universes VALUES ('{HOME}', 'Ada');
        INSERT INTO runs VALUES ('r1', 'universe:{HOME}',
            x'7b22757365223a22{HOME.encode().hex()}227d', 'scratch');
        INSERT INTO runs VALUES ('r2', 'someone', NULL, 'scratch');
    """)
    db.commit()
    db.close()


def _digest(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(str(path.relative_to(root)).encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def test_the_inventory_finds_what_the_cutover_must_change_and_writes_nothing(tmp_path):
    _fixture(tmp_path)
    before = _digest(tmp_path)

    report = inv.inventory(tmp_path)

    assert _digest(tmp_path) == before, "the inventory must never write"
    home = report["homes"][HOME]
    assert "soul.md" in home["user"] and "config.yaml" in home["user"]
    assert "soul.edit.md" in home["platform"] and "status.json" in home["platform"]
    assert home["unclassified"] == ["mystery.bin"]
    assert home["config_authority"] == ["engine_assignment_state", "allowed_providers"]

    db = report["sqlite"][".tinyassets.db"]
    assert db["tables"] == ["universes"]
    assert {"table": "universes", "column": "universe_id"} in db["columns"]
    kinds = {(o["type"], o["name"]) for o in db["schema_sql"]}
    assert ("index", "runs_by_universe_actor") in kinds and ("check", "runs") in kinds
    values = {(v["table"], v["column"]): v for v in db["values"]}
    assert values[("runs", "actor")]["actor_prefix"] == 1
    assert values[("runs", "payload")]["u_ids"] == 1, "a BLOB is scanned as bytes"
    assert values[("universes", "universe_id")]["u_ids"] == 1

    assert report["json"][f"{HOME}/status.json"] == {"keys": 1, "u_id_keys": 0, "u_id_values": 2}
    assert report["totals"]["unclassified_entries"] == 1
    assert report["totals"]["configs_with_authority"] == 1


def test_strict_mode_refuses_while_anything_is_unclassified(tmp_path, capsys):
    _fixture(tmp_path)
    assert inv.main([str(tmp_path), "--strict"]) == 2
    assert "mystery.bin" in capsys.readouterr().out
    (tmp_path / HOME / "mystery.bin").unlink()
    assert inv.main([str(tmp_path), "--strict"]) == 0
