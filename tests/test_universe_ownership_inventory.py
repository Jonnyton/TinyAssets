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
        assert "no at-risk directories" in capsys.readouterr().out

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
        _owned(base, "u-mine")

        import tinyassets.daemon_server as ds

        monkeypatch.setattr(
            ds, "owned_universe_id",
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("locked")),
        )

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
        before = {
            p.relative_to(base).as_posix(): p.stat().st_mtime_ns
            for p in sorted(base.rglob("*"))
            if p.is_file()
        }

        inventory(base)

        after = {
            p.relative_to(base).as_posix(): p.stat().st_mtime_ns
            for p in sorted(base.rglob("*"))
            if p.is_file()
        }
        assert after == before
