"""Per-universe SQLite databases are never opened through a link, and never
trusted when something other than the daemon created them.

A workflow provider jail binds its universe read-write. Two things followed:

* ``.runs.db -> /data/<B>/.runs.db`` made ``sqlite3.connect`` read and write
  universe B's database in universe A's context.
* A hidden database absent until first use (``.effector_consents.db``) could be
  pre-seeded as a REGULAR SQLite file holding a forged active consent row; the
  daemon's ``CREATE TABLE IF NOT EXISTS`` kept the row and the external-call
  gate accepted it (concern 2026-10-01-platform-state-inside-the-universe-dir).

Also the credential vault's fixed ``.tmp`` name, which a pre-placed hardlink
could capture.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

import pytest

from tinyassets import universe_files
from tinyassets.storage import effector_consents
from tinyassets.universe_files import UniverseFileError, connect_db

pytestmark = pytest.mark.skipif(
    not getattr(universe_files.fs, "_POSIX", False),
    reason="descriptor walks and inode provenance are POSIX",
)


def _link(target: Path, link: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("this host cannot create a symlink")


@pytest.fixture
def data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / "data"
    (base / "u-alpha").mkdir(parents=True)
    (base / "u-bravo").mkdir(parents=True)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    return base


def _seed_bravo_db(data: Path, name: str) -> Path:
    path = data / "u-bravo" / name
    with connect_db(path) as conn:
        conn.execute("CREATE TABLE secret (v TEXT)")
        conn.execute("INSERT INTO secret VALUES ('B-SECRET')")
    return path


def _register(data: Path, uid: str) -> None:
    from tinyassets.daemon_server import ensure_universe_registered

    ensure_universe_registered(data, universe_id=uid, universe_path=data / uid)


def test_a_linked_database_file_is_refused(data):
    bravo = _seed_bravo_db(data, ".runs.db")
    _link(bravo, data / "u-alpha" / ".runs.db")
    with pytest.raises((OSError, sqlite3.Error)):
        with connect_db(data / "u-alpha" / ".runs.db") as conn:
            conn.execute("SELECT v FROM secret").fetchall()


def test_a_linked_parent_directory_is_refused(data):
    _seed_bravo_db(data, "story.db")
    _link(data / "u-bravo", data / "u-alpha" / "nested")
    with pytest.raises(OSError):
        connect_db(data / "u-alpha" / "nested" / "story.db")


def test_a_linked_wal_sidecar_is_refused(data):
    with connect_db(data / "u-alpha" / ".runs.db") as conn:
        conn.execute("CREATE TABLE t (v)")
    (data / "u-bravo" / "victim").write_text("B", encoding="utf-8")
    _link(data / "u-bravo" / "victim", data / "u-alpha" / ".runs.db-wal")
    with pytest.raises(UniverseFileError):
        connect_db(data / "u-alpha" / ".runs.db")
    assert (data / "u-bravo" / "victim").read_text(encoding="utf-8") == "B"


def test_a_daemon_created_database_reopens(data):
    path = data / "u-alpha" / ".conversation_memory.db"
    with connect_db(path) as conn:
        conn.execute("CREATE TABLE t (v)")
        conn.execute("INSERT INTO t VALUES (1)")
    with connect_db(path) as conn:
        assert conn.execute("SELECT v FROM t").fetchall() == [(1,)]
    uri = path.as_uri() + "?mode=ro"
    with connect_db(uri, uri=True) as conn:
        assert conn.execute("SELECT v FROM t").fetchall() == [(1,)]


def test_a_preseeded_consent_db_is_refused_on_a_new_universe(data):
    """The forge: a regular SQLite file at the not-yet-created consent DB name,
    carrying the real schema and an active consent row."""
    _register(data, "u-alpha")
    connect_db(data / "u-alpha" / ".runs.db").close()  # the daemon has seen it
    forged = data / "u-alpha" / ".effector_consents.db"
    raw = sqlite3.connect(forged)
    raw.executescript(effector_consents._SCHEMA)
    raw.execute(
        "INSERT INTO effector_consents VALUES ('http', 'https://evil.example', 1, 'owner', NULL)"
    )
    raw.commit()
    raw.close()
    with pytest.raises(UniverseFileError):
        effector_consents.is_consent_active(
            data / "u-alpha", sink="http", destination="https://evil.example",
        )


def test_a_preseeded_db_before_the_first_daemon_open_is_refused(data):
    """No grandfathering for a universe registered after provenance began."""
    universe_files._provenance_epoch(data)
    _register(data, "u-alpha")
    sqlite3.connect(data / "u-alpha" / ".effector_consents.db").close()
    with pytest.raises(UniverseFileError):
        connect_db(data / "u-alpha" / ".effector_consents.db")


def test_legacy_databases_are_grandfathered_once(data):
    """A universe from before provenance keeps its databases; a file that
    appears later is refused."""
    legacy = data / "u-alpha" / ".runs.db"
    sqlite3.connect(legacy).close()
    with connect_db(legacy):
        pass
    sqlite3.connect(data / "u-alpha" / ".late.db").close()
    with pytest.raises(UniverseFileError):
        connect_db(data / "u-alpha" / ".late.db")


def test_a_replaced_database_file_is_refused(data):
    path = data / "u-alpha" / ".automations.db"
    connect_db(path).close()
    swapped = data / "u-alpha" / "swap.db"
    sqlite3.connect(swapped).close()
    os.replace(swapped, path)
    with pytest.raises(UniverseFileError):
        connect_db(path)


def test_concurrent_first_opens_all_succeed(data):
    path = data / "u-alpha" / ".project_memory.db"
    errors: list[BaseException] = []

    def opener():
        try:
            connect_db(path, timeout=10).close()
        except BaseException as exc:  # noqa: BLE001 - collected for the assert
            errors.append(exc)

    threads = [threading.Thread(target=opener) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []


def test_outside_the_data_dir_is_plain_sqlite(tmp_path):
    path = tmp_path / "elsewhere" / "x.db"
    path.parent.mkdir()
    with connect_db(path) as conn:
        conn.execute("CREATE TABLE t (v)")
    assert connect_db(":memory:").execute("SELECT 1").fetchone() == (1,)


def test_sidecar_dir_constant_matches_the_jail():
    from tinyassets.providers.provider_jail import UNIVERSE_SIDECARS_DIR

    assert universe_files._SIDECARS_DIR == UNIVERSE_SIDECARS_DIR


def test_vault_temp_name_cannot_be_captured_by_a_hardlink(data):
    from tinyassets import credential_vault

    udir = data / "u-alpha"
    held = udir / "notes-held"
    held.write_text("", encoding="utf-8")
    vault = credential_vault.credential_vault_path(udir)
    planted = vault.with_name(f"{vault.name}.tmp")
    os.link(held, planted)
    credential_vault._persist_credential_vault_file(udir, [{"id": "c1", "secret": "S3CRET"}])
    assert held.read_text(encoding="utf-8") == ""
    assert "S3CRET" in vault.read_text(encoding="utf-8")
    leftovers = [p.name for p in udir.iterdir() if p.name.endswith(".tmp") and p != planted]
    assert leftovers == []
