"""The pre-deploy gate for the universe-ownership predicate.

A universe exists because an ownership row names it. That makes an unowned
directory invisible -- correct for a prune's archive or an operational bucket,
and a REGRESSION for a real universe that never got a row (a pre-migration
universe, or one restored from a backup under a different case, since ownership
is matched exactly).

`scripts/universe_ownership_inventory.py` is how that case is found BEFORE the
deploy rather than by a founder noticing their universe is gone. It is read-only
and it is NOT the prune: it never suggests removing anything, because deciding to
cut needs a positive reason to believe a directory was a universe.

The contract these tests pin:
  * exit 0 when every universe-looking directory is owned;
  * exit 1 naming each at-risk directory -- one that carries `soul.md`, a
    `PROGRAM.md`, or a platform-generated serial id, and has no ownership row;
  * exit 2 when the root or the store cannot be read (unknown is not safe);
  * an archive or operational bucket with NO universe signal is reported as
    expected-unowned, not as at-risk -- otherwise the gate cries wolf on every
    root and stops being read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.universe_ownership_inventory import inventory, main
from tinyassets.daemon_server import (
    ensure_universe_registered,
    grant_universe_access,
    set_founder_home,
)

ARCHIVE = "_removed_universes_20260829"


@pytest.fixture
def base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    return root


def _owned(base: Path, uid: str, owner: str = "workos|founder") -> Path:
    udir = base / uid
    udir.mkdir(parents=True, exist_ok=True)
    (udir / "soul.md").write_text(f"# {uid}\n", encoding="utf-8")
    ensure_universe_registered(base, universe_id=uid, universe_path=udir)
    grant_universe_access(
        base, universe_id=uid, actor_id=owner, permission="admin", granted_by=owner,
    )
    return udir


def _row(report: dict, name: str) -> dict:
    return next(r for r in report["directories"] if r["directory"] == name)


class TestTheGateAnswersTheDeployQuestion:
    def test_an_all_owned_root_is_clear(self, base, capsys):
        _owned(base, "u-mine")
        _owned(base, "u-second", owner="workos|second")

        assert main(["--data-dir", str(base)]) == 0
        out = capsys.readouterr().out
        assert "no directory carrying a universe signal is unowned" in out
        # Even a wholly clean root must not be told it is safe to deploy.
        assert "never that the deploy is safe" in out

    def test_an_unowned_universe_looking_directory_blocks(self, base, capsys):
        _owned(base, "u-mine")
        stray = base / "u-forgotten"
        stray.mkdir()
        (stray / "soul.md").write_text("# forgotten\n", encoding="utf-8")

        assert main(["--data-dir", str(base)]) == 1
        out = capsys.readouterr().out
        assert "AT RISK" in out
        assert "u-forgotten" in out
        # The instruction has to be "write the row", never "delete it".
        assert "BEFORE deploying" in out
        assert "delete" not in out.lower() or "not removed" in out.lower()

    def test_an_archive_with_no_universe_signal_does_not_block(self, base, capsys):
        """The gate must not cry wolf on every root, or it stops being read."""
        _owned(base, "u-mine")
        (base / ARCHIVE).mkdir()
        (base / "lancedb").mkdir()

        assert main(["--data-dir", str(base)]) == 0
        out = capsys.readouterr().out
        assert ARCHIVE in out
        assert "AT RISK" not in out

    def test_a_case_mismatched_row_is_at_risk(self, base):
        """The cost of matching ownership exactly, made visible rather than
        silent: a directory restored as `U-Mine` whose row reads `u-mine`."""
        udir = base / "U-Mine"
        udir.mkdir()
        (udir / "soul.md").write_text("# restored\n", encoding="utf-8")
        grant_universe_access(
            base, universe_id="u-mine", actor_id="workos|founder",
            permission="admin", granted_by="workos|founder",
        )

        report = inventory(base)
        assert report["at_risk"] == ["U-Mine"]
        assert _row(report, "U-Mine")["owned_as"] == ""

    def test_a_missing_root_is_unknown_not_clear(self, base, capsys):
        assert main(["--data-dir", str(base / "nope")]) == 2

    def test_an_unreadable_store_is_unknown_not_clear(self, base, monkeypatch, capsys):
        """Driven through the REAL read path. Patching a `daemon_server` helper
        proves nothing now: the inventory deliberately calls none of them, so a
        test that mocked one would pass while the store was never consulted."""
        _owned(base, "u-mine")

        import scripts.universe_ownership_inventory as inv

        def _boom(*_a, **_k):
            raise inv.OwnershipStoreUnreadable("database is locked")

        monkeypatch.setattr(inv, "_read_ownership", _boom)

        assert main(["--data-dir", str(base)]) == 2
        assert "could not read the ownership store" in capsys.readouterr().err

    def test_a_corrupt_store_is_unknown_not_clear(self, base, capsys):
        """No mock at all: a real unreadable file on disk."""
        from tinyassets.storage import db_path

        _owned(base, "u-mine")
        db_path(base).write_bytes(b"this is not a sqlite database" * 20)

        assert main(["--data-dir", str(base)]) == 2


class TestWhatTheReportSays:
    def test_it_names_both_ownership_stores(self, base):
        _owned(base, "u-acl")
        home = base / "u-home"
        home.mkdir()
        (home / "soul.md").write_text("# home\n", encoding="utf-8")
        ensure_universe_registered(base, universe_id="u-home", universe_path=home)
        set_founder_home(base, founder_sub="workos|homer", universe_id="u-home")

        report = inventory(base)
        assert _row(report, "u-acl")["acl_grants"] == ["workos|founder:admin"]
        assert _row(report, "u-home")["home_bindings"] == ["workos|homer"]
        assert report["owned"] == 2
        assert report["at_risk"] == []

    def test_it_labels_the_universe_signal_it_found(self, base):
        _owned(base, "u-mine")
        legacy = base / "u-legacy"
        legacy.mkdir()
        (legacy / "PROGRAM.md").write_text("a premise", encoding="utf-8")
        (base / ARCHIVE).mkdir()

        report = inventory(base)
        assert _row(report, "u-mine")["universe_signal"] == "carries soul.md"
        assert "PROGRAM.md" in _row(report, "u-legacy")["universe_signal"]
        assert _row(report, ARCHIVE)["universe_signal"] == ""

    def test_a_serial_id_alone_is_a_universe_signal(self, base):
        """A platform-generated id means the platform made it, whatever it
        contains -- an interrupted first contact leaves a bare serial directory,
        and that is exactly the universe a founder would miss."""
        from tinyassets.ids import new_universe_id

        uid = new_universe_id()
        (base / uid).mkdir()

        report = inventory(base)
        assert report["at_risk"] == [uid]
        assert _row(report, uid)["universe_signal"] == "platform-generated serial id"

    def test_dotted_directories_are_not_inventoried(self, base):
        _owned(base, "u-mine")
        (base / ".deleting").mkdir()

        report = inventory(base)
        assert [r["directory"] for r in report["directories"]] == ["u-mine"]

    def test_json_mode_is_the_same_report(self, base, capsys):
        _owned(base, "u-mine")

        assert main(["--data-dir", str(base), "--json"]) == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["owned"] == 1
        assert parsed["at_risk"] == []

    def test_it_writes_nothing(self, base):
        """Read-only, asserted rather than asserted-in-prose: the whole point of
        running this against a live root before a deploy."""
        _owned(base, "u-mine")
        (base / ARCHIVE).mkdir()
        def snapshot() -> dict[str, int]:
            # The `-wal` / `-shm` sidecars are EXCLUDED, and that exclusion is
            # the honest limit of this assertion: SQLite materializes the shared
            # -shm segment to read a WAL database at all, so any reader creates
            # them and no read-only mode avoids it (`immutable=1` would, and is
            # unsafe against a live daemon writing concurrently). They carry no
            # data of their own. Everything else must be untouched.
            return {
                p.relative_to(base).as_posix(): p.stat().st_mtime_ns
                for p in sorted(base.rglob("*"))
                if p.is_file() and not p.name.endswith(("-wal", "-shm"))
            }

        before = snapshot()
        inventory(base)
        assert snapshot() == before

    def test_it_does_not_CREATE_the_store_on_a_root_that_has_none(self, base):
        """The case the mtime snapshot above cannot see, because it snapshots a
        root where `_owned` has already initialized the store -- which also
        populates the process-local init cache, hiding the write (Codex review
        round 2, P1).

        `storage._connect` creates the database file and sets `journal_mode=WAL`,
        and `owned_universe_id` -> `initialize_author_server` runs MIGRATIONS. A
        command whose whole purpose is to be safe to point at a live production
        root must do neither.
        """
        from tinyassets.storage import db_path

        (base / "u-unknown").mkdir()
        assert not db_path(base).is_file()  # premise: nothing has run here

        report = inventory(base)

        assert not db_path(base).is_file(), (
            "the inventory created the ownership store it was asked to read"
        )
        assert sorted(p.name for p in base.iterdir()) == ["u-unknown"]
        assert report["owned"] == 0

    def test_it_does_not_migrate_an_existing_store(self, base, monkeypatch):
        """`initialize_author_server` is never reached, so a store that predates
        a column is not silently migrated by an inspection."""
        _owned(base, "u-mine")

        import tinyassets.daemon_server as ds

        def _boom(*_a, **_k):
            raise AssertionError("the inventory must not initialize the store")

        monkeypatch.setattr(ds, "initialize_author_server", _boom)
        monkeypatch.setattr(ds, "owned_universe_id", _boom)
        monkeypatch.setattr(ds, "owned_universe_ids", _boom)
        monkeypatch.setattr(ds, "list_universe_acl", _boom)

        report = inventory(base)
        assert report["owned"] == 1
        assert _row(report, "u-mine")["acl_grants"] == ["workos|founder:admin"]

    def test_an_unowned_unrecognised_directory_is_not_called_safe(self, base, capsys):
        """The absence of a universe signal is no evidence. A legacy universe may
        hold a shape nobody thought to list, so an unrecognised directory is
        reported as needing a human look -- never as disposable, and never as
        making the deploy safe."""
        _owned(base, "u-mine")
        (base / "who-knows").mkdir()
        (base / "who-knows" / "mystery.bin").write_bytes(b"x")

        assert main(["--data-dir", str(base)]) == 0
        out = capsys.readouterr().out
        assert "UNOWNED AND UNRECOGNISED" in out
        assert "who-knows" in out
        assert "NOT evidence they are disposable" in out
        assert "never that the deploy is safe" in out
        assert "expected" not in out.lower()

    @pytest.mark.parametrize(
        "marker", ["notes.json", "status.json", "identity.md", "activity.log"],
    )
    def test_a_legacy_universe_without_soul_md_still_blocks(self, base, marker):
        """A universe predating `soul.md` still holds its notes, status or log.
        Requiring the modern seed marker is how a real universe goes dark."""
        _owned(base, "u-mine")
        legacy = base / "u-legacy"
        legacy.mkdir()
        (legacy / marker).write_text("{}", encoding="utf-8")

        report = inventory(base)
        assert report["at_risk"] == ["u-legacy"], report

    @pytest.mark.parametrize("subtree", ["wiki", "output", "canon"])
    def test_a_universe_known_only_by_its_subtree_still_blocks(self, base, subtree):
        _owned(base, "u-mine")
        legacy = base / "u-legacy"
        (legacy / subtree).mkdir(parents=True)

        report = inventory(base)
        assert report["at_risk"] == ["u-legacy"], report
