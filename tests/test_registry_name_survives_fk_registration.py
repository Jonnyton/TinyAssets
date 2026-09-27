"""A universe's name survives every caller that registers it for an FK.

`ensure_universe_registered` is an UPSERT whose conflict clause is
`display_name=excluded.display_name, metadata_json=excluded.metadata_json`, and
both parameters are optional. Every caller that registers only to satisfy a
foreign key — and so passes neither — silently renamed the universe to its raw id
and emptied its registry metadata, reporting success.

Eight helpers in `tinyassets.daemon_server` did exactly that, **three of them on
reads**: listing a universe's notes, work targets, or hard priorities renamed it.
The same shape in the visibility backfill (fixed in #4019) ran on every boot, so a
universe its owner had named lost that name at the next restart.

This is a data-loss guard, so each half is mutation-checked: removing the absence
check in `register_universe_if_absent` turns these red.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tinyassets.daemon_server import (
    ensure_universe_registered,
    get_universe,
    register_universe_if_absent,
)

OWNER_NAME = "My learned name"
OWNER_META = {"keep": "valuable", "nested": {"still": "here"}}


@pytest.fixture
def named_universe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A registered universe whose owner has given it a name and metadata."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    uid = "u-named"
    udir = tmp_path / uid
    udir.mkdir(parents=True)
    ensure_universe_registered(
        tmp_path,
        universe_id=uid,
        universe_path=udir,
        display_name=OWNER_NAME,
        metadata=dict(OWNER_META),
    )
    return tmp_path, udir


def _assert_name_intact(base: Path, uid: str = "u-named") -> None:
    row = get_universe(base, universe_id=uid)
    assert row["display_name"] == OWNER_NAME, row
    assert row["metadata"] == OWNER_META, row


# Every helper that registers only to satisfy the notes/work-target/hard-priority
# foreign key. `list_*` are READS, which is what made this bug reachable by simply
# looking at a universe.
_FK_ONLY_HELPERS = (
    "list_note_dicts",
    "list_work_target_dicts",
    "list_hard_priority_dicts",
)


@pytest.mark.parametrize("helper_name", _FK_ONLY_HELPERS)
def test_reading_does_not_rename_the_universe(named_universe, helper_name):
    """A read must not write. These three are the reachable half of the defect."""
    import tinyassets.daemon_server as ds

    base, udir = named_universe
    getattr(ds, helper_name)(udir)
    _assert_name_intact(base)


def test_adding_a_note_does_not_rename_the_universe(named_universe):
    from tinyassets.daemon_server import add_note_dict

    base, udir = named_universe
    add_note_dict(udir, {"id": "n1", "text": "hello", "source": "user"})
    _assert_name_intact(base)


def test_upserting_a_work_target_does_not_rename_the_universe(named_universe):
    from tinyassets.daemon_server import upsert_work_target_dict

    base, udir = named_universe
    upsert_work_target_dict(udir, {"target_id": "t1", "title": "a target"})
    _assert_name_intact(base)


def test_upserting_a_hard_priority_does_not_rename_the_universe(named_universe):
    from tinyassets.daemon_server import upsert_hard_priority_dict

    base, udir = named_universe
    upsert_hard_priority_dict(udir, {"priority_id": "p1", "text": "a priority"})
    _assert_name_intact(base)


def test_repeated_calls_still_do_not_rename_it(named_universe):
    """The boot-path shape: the damage was once per call, so once is not enough."""
    import tinyassets.daemon_server as ds

    base, udir = named_universe
    for _ in range(3):
        for helper_name in _FK_ONLY_HELPERS:
            getattr(ds, helper_name)(udir)
    _assert_name_intact(base)


class TestThePredicateItself:
    def test_it_registers_a_universe_that_has_no_row(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
        (tmp_path / "u-fresh").mkdir()

        assert register_universe_if_absent(tmp_path, universe_id="u-fresh") is True
        assert get_universe(tmp_path, universe_id="u-fresh")["universe_id"] == "u-fresh"

    def test_it_does_nothing_when_a_row_exists(self, named_universe):
        base, _udir = named_universe
        assert register_universe_if_absent(base, universe_id="u-named") is False
        _assert_name_intact(base)

    def test_a_blank_id_writes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
        assert register_universe_if_absent(tmp_path, universe_id="   ") is False

    def test_it_honours_a_caller_supplied_path(self, tmp_path, monkeypatch):
        """The helpers hold the real path already; re-deriving one is how a second
        answer to "where does this universe live" gets introduced."""
        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
        elsewhere = tmp_path / "nested" / "u-odd"
        elsewhere.mkdir(parents=True)

        register_universe_if_absent(
            tmp_path, universe_id="u-odd", universe_path=elsewhere,
        )
        row = get_universe(tmp_path, universe_id="u-odd")
        assert Path(row["host_path"]) == elsewhere.resolve()

    def test_it_defaults_the_path_under_the_base(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
        (tmp_path / "u-default-path").mkdir()

        register_universe_if_absent(tmp_path, universe_id="u-default-path")
        row = get_universe(tmp_path, universe_id="u-default-path")
        assert Path(row["host_path"]) == (tmp_path / "u-default-path").resolve()


def test_the_dedicated_renamer_still_renames(named_universe):
    """"Only if absent" is only safe because renaming has its own caller."""
    from tinyassets.daemon_server import set_universe_display_name

    base, _udir = named_universe
    set_universe_display_name(base, universe_id="u-named", display_name="Renamed")
    assert get_universe(base, universe_id="u-named")["display_name"] == "Renamed"
