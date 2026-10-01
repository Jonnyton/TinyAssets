"""universe-runtime-state: one resolver for a universe's platform state, and a
one-time migration that loses nothing however it is interrupted."""

from __future__ import annotations

import os
import sys

import pytest

from tinyassets import universe_paths as up


@pytest.fixture(autouse=True)
def _fresh_cache():
    up._confirmed.clear()
    yield
    up._confirmed.clear()


def _universe(tmp_path, name="u-1"):
    root = tmp_path / name
    root.mkdir()
    return root


def test_a_platform_name_resolves_under_runtime_state(tmp_path):
    root = _universe(tmp_path)
    path = up.platform_path(root, ".effector_consents.db")
    assert path == root / ".runtime" / "state" / ".effector_consents.db"
    assert up.is_migrated(root)


def test_an_unknown_name_is_refused(tmp_path):
    root = _universe(tmp_path)
    for bad in ("soul.md", "../x", ".runtime", "a/b"):
        with pytest.raises(up.PlatformPathError):
            up.platform_path(root, bad)


def test_migration_moves_a_database_with_its_sidecars_and_reads_nothing_at_the_root(tmp_path):
    root = _universe(tmp_path)
    for name in (".effector_consents.db", ".effector_consents.db-wal", ".effector_consents.db-shm"):
        (root / name).write_bytes(name.encode())
    (root / "soul.md").write_text("mine")

    path = up.platform_path(root, ".effector_consents.db")

    assert path.read_bytes() == b".effector_consents.db"
    assert (path.parent / ".effector_consents.db-wal").read_bytes() == b".effector_consents.db-wal"
    assert up.is_tombstone(root / ".effector_consents.db")
    assert not (root / ".effector_consents.db-wal").exists()
    assert (root / "soul.md").read_text() == "mine"  # user files stay


def test_prefix_and_relocated_entries_move(tmp_path):
    root = _universe(tmp_path)
    (root / ".worker_supervisor.a.json").write_text("a")
    (root / ".worker_supervisor.b.json").write_text("b")
    (root / "wiki").mkdir()
    (root / "wiki" / ".wiki_write_back_destination_markers.db").write_text("m")
    (root / "wiki" / "page.md").write_text("page")

    state = up.ensure_migrated(root)

    assert sorted(p.name for p in state.glob(".worker_supervisor.*")) == [
        ".worker_supervisor.a.json", ".worker_supervisor.b.json",
    ]
    assert (state / ".wiki_write_back_destination_markers.db").read_text() == "m"
    assert (root / "wiki" / "page.md").read_text() == "page"


def test_a_crash_mid_move_leaves_no_marker_and_the_next_resolve_finishes(tmp_path, monkeypatch):
    root = _universe(tmp_path)
    names = (".runs.db", ".runs.db-wal", ".runs.db-shm", ".credential-vault.json", "ledger.json")
    for name in names:
        (root / name).write_text(name)

    real_rename = os.rename
    calls = {"n": 0}

    def dying_rename(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:  # after the database, before its -wal
            raise OSError("process killed")
        return real_rename(src, dst)

    monkeypatch.setattr(up.os, "rename", dying_rename)
    with pytest.raises(OSError, match="process killed"):
        up.platform_path(root, ".runs.db")
    assert not up.is_migrated(root)

    monkeypatch.setattr(up.os, "rename", real_rename)
    up.platform_path(root, ".runs.db")

    state = root / ".runtime" / "state"
    assert up.is_migrated(root)
    for name in names:
        assert (state / name).read_text() == name
        assert up.is_tombstone(root / name) if not name.endswith(("-wal", "-shm")) else not (root / name).exists()


def test_a_root_copy_beside_a_migrated_one_refuses_and_moves_nothing(tmp_path):
    root = _universe(tmp_path)
    state = root / ".runtime" / "state"
    state.mkdir(parents=True)
    (state / "ledger.json").write_text("migrated")
    (root / "ledger.json").write_text("stray")
    (root / "status.json").write_text("{}")

    with pytest.raises(up.MigrationRefused, match="conflict"):
        up.platform_path(root, "status.json")

    assert (state / "ledger.json").read_text() == "migrated"
    assert (root / "ledger.json").read_text() == "stray"
    assert (root / "status.json").read_text() == "{}"  # nothing moved at all
    assert not up.is_migrated(root)


def test_each_moved_name_leaves_a_tombstone_a_missed_reader_cannot_open(tmp_path):
    root = _universe(tmp_path)
    (root / "story.db").write_text("story")
    (root / "story.db-wal").write_text("wal")

    up.ensure_migrated(root)

    assert up.is_tombstone(root / "story.db")
    assert not (root / "story.db-wal").exists()  # sidecars leave no tombstone
    assert up.tombstones(root) == [root / "story.db"]
    with pytest.raises(OSError):
        (root / "story.db").read_bytes()


def test_a_lost_marker_retry_skips_tombstones(tmp_path):
    root = _universe(tmp_path)
    (root / "story.db").write_text("story")
    up.ensure_migrated(root)
    (root / ".runtime" / "state" / up.MARKER).unlink()
    up._confirmed.clear()

    up.ensure_migrated(root)

    assert (root / ".runtime" / "state" / "story.db").read_text() == "story"
    assert up.is_migrated(root)


def test_migration_runs_once(tmp_path):
    root = _universe(tmp_path)
    up.ensure_migrated(root)
    up._confirmed.clear()
    (root / "ledger.json").write_text("planted after migration")

    up.platform_path(root, "ledger.json")

    # A root file written after the marker is the user's: never moved, never read.
    assert (root / "ledger.json").read_text() == "planted after migration"
    assert not (root / ".runtime" / "state" / "ledger.json").exists()


def test_a_fresh_universe_resolves_to_an_empty_store_not_the_root(tmp_path):
    root = _universe(tmp_path)
    up.ensure_migrated(root)
    (root / ".effector_consents.db").write_text("forged grants")
    up._confirmed.clear()

    path = up.platform_path(root, ".effector_consents.db")

    assert not path.exists()


def test_migration_plan_is_a_dry_run(tmp_path):
    root = _universe(tmp_path)
    (root / "status.json").write_text("{}")
    plan = up.migration_plan(root)
    assert [(s.source.name, s.action) for s in plan] == [("status.json", "move")]
    assert (root / "status.json").exists()
    assert not (root / ".runtime").exists()


def _symlink_or_skip(target, link, *, directory=False):
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable here: {exc}")


def test_a_root_link_refuses_the_migration_and_is_never_followed(tmp_path):
    root = _universe(tmp_path)
    elsewhere = tmp_path / "other-user"
    elsewhere.mkdir()
    (elsewhere / ".effector_consents.db").write_text("someone else's")
    _symlink_or_skip(elsewhere / ".effector_consents.db", root / ".effector_consents.db")
    (root / "status.json").write_text("{}")

    with pytest.raises(up.MigrationRefused, match="link"):
        up.platform_path(root, ".effector_consents.db")

    assert (elsewhere / ".effector_consents.db").read_text() == "someone else's"
    assert os.path.islink(root / ".effector_consents.db")
    assert (root / "status.json").exists()
    assert not up.is_migrated(root)


def test_a_linked_state_directory_is_refused(tmp_path):
    root = _universe(tmp_path)
    elsewhere = tmp_path / "other-user-state"
    elsewhere.mkdir()
    (root / ".runtime").mkdir()
    _symlink_or_skip(elsewhere, root / ".runtime" / "state", directory=True)

    with pytest.raises(up.PlatformPathError):
        up.platform_path(root, ".effector_consents.db")
    assert list(elsewhere.iterdir()) == []


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks across processes")
def test_a_reader_waits_for_a_migration_in_another_process(tmp_path):
    import multiprocessing
    import time

    root = _universe(tmp_path)
    (root / ".runs.db").write_text("runs")
    state = root / ".runtime" / "state"
    state.mkdir(parents=True)

    ctx = multiprocessing.get_context("fork")
    held = ctx.Event()
    release = ctx.Event()

    def holder():
        with up._exclusive(state / up._LOCK_NAME):
            held.set()
            release.wait(10)

    proc = ctx.Process(target=holder)
    proc.start()
    try:
        assert held.wait(10)
        started = time.monotonic()
        import threading

        result = {}

        def reader():
            result["path"] = up.platform_path(root, ".runs.db")

        t = threading.Thread(target=reader)
        t.start()
        t.join(0.5)
        assert t.is_alive(), "a reader passed while another process held the migration lock"
        release.set()
        t.join(10)
        assert result["path"].read_text() == "runs"
        assert time.monotonic() - started >= 0.5
    finally:
        release.set()
        proc.join(10)


def test_record_layout_only_raises(tmp_path):
    up.record_layout(tmp_path)
    assert (tmp_path / up.LAYOUT_FILENAME).read_text().strip() == str(up.STATE_LAYOUT)
    (tmp_path / up.LAYOUT_FILENAME).write_text("9")
    up.record_layout(tmp_path)
    assert (tmp_path / up.LAYOUT_FILENAME).read_text().strip() == "9"


def test_every_registry_entry_has_a_known_reset_disposition():
    allowed = {up.RESET_CREDENTIAL, up.RESET_AUDIT, up.RESET_OPERATIONAL, up.RESET_RESETTABLE}
    assert {entry.reset for entry in up.PLATFORM_NAMES.values()} <= allowed
    for name in (".credential-vault.json", ".credentials"):
        assert up.PLATFORM_NAMES[name].reset == up.RESET_CREDENTIAL
    for name in (".external_write_receipts.db", ".idempotency.db", ".runs.db"):
        assert up.PLATFORM_NAMES[name].reset == up.RESET_AUDIT


@pytest.mark.parametrize("name", ["wiki", "scratch", "_backup_subject_migration_1", ".hidden"])
def test_a_directory_that_is_not_a_universe_is_never_migrated(tmp_path, name):
    root = tmp_path / name
    root.mkdir()
    (root / ".runs.db").write_text("a backup's runs")

    with pytest.raises(up.PlatformPathError):
        up.platform_path(root, ".runs.db")

    assert (root / ".runs.db").read_text() == "a backup's runs"
    assert not (root / ".runtime").exists()


def test_the_data_root_is_never_migrated(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / ".tinyassets.db").write_text("root db")
    (data / "outbound.db").write_text("the platform's ledger")

    with pytest.raises(up.PlatformPathError, match="data root"):
        up.ensure_migrated(data)

    assert (data / "outbound.db").read_text() == "the platform's ledger"


def test_an_enumerator_never_migrates(tmp_path):
    root = _universe(tmp_path)
    (root / "provider_definitions.json").write_text("[]")

    assert up.migrated_platform_path(root, "provider_definitions.json") is None
    assert (root / "provider_definitions.json").exists()
    assert not (root / ".runtime").exists()
