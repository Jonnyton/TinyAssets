"""The paths the final gpt-6-astra round on #4254 left open.

* ``work_targets.json`` (and the notes / hard-priority mirrors): the daemon's
  registry mirror wrote the JSON with a plain ``write_text``, and the bootstrap
  imported it with a plain ``read_text``. A planted
  ``work_targets.json -> /data/<B>/founder.md`` let a chapter-loop target update
  truncate B's file.
* ``soul_edit``'s own atomic writer created its temp with ``mkstemp`` in a
  directory reached by path, so ``soul_versions`` swapped for a link wrote the
  snapshot into another universe.
* ``write_universe_soul`` and the synthesis-priority sync read a refused file
  as absent and then rebuilt it.
* On the non-POSIX writer, exclusive mode reported an existing link as a
  refusal instead of ``FileExistsError``, so ``file_bug``'s retry missed it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tinyassets import universe_files, work_targets
from tinyassets.universe_files import write_data_path

FOREIGN = "B-SECRET founder line\n"


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
    (base / "u-bravo" / "founder.md").write_text(FOREIGN, encoding="utf-8")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    return base


def _alpha(data: Path) -> Path:
    return (data / "u-alpha").resolve()


def _bravo_founder(data: Path) -> str:
    return (data / "u-bravo" / "founder.md").read_text(encoding="utf-8")


def test_a_work_target_update_never_writes_through_a_planted_json_link(data):
    udir = _alpha(data)
    target = work_targets.WorkTarget(target_id="t1", title="first")
    work_targets.upsert_work_target(udir, target)
    (udir / "work_targets.json").unlink()
    _link(data / "u-bravo" / "founder.md", udir / "work_targets.json")
    work_targets.upsert_work_target(udir, work_targets.WorkTarget(target_id="t2", title="second"))
    assert _bravo_founder(data) == FOREIGN
    assert not (udir / "work_targets.json").is_symlink()
    ids = {item["target_id"] for item in json.loads((udir / "work_targets.json").read_text())}
    assert {"t1", "t2"} <= ids


def test_the_bootstrap_never_imports_a_linked_json(data):
    bravo_targets = data / "u-bravo" / "work_targets.json"
    bravo_targets.write_text(
        json.dumps([{"target_id": "b-secret", "title": FOREIGN}]), encoding="utf-8",
    )
    udir = _alpha(data)
    _link(bravo_targets, udir / "work_targets.json")
    loaded = work_targets.load_work_targets(udir)
    assert all(t.target_id != "b-secret" for t in loaded)


def test_soul_edit_writer_refuses_a_linked_versions_dir(data):
    from tinyassets.soul_edit import _atomic_write_text

    (data / "u-bravo" / "soul_versions").mkdir()
    _link(data / "u-bravo" / "soul_versions", _alpha(data) / "soul_versions")
    with pytest.raises(OSError):
        _atomic_write_text(_alpha(data) / "soul_versions" / "0002.md", "x", mode="exclusive")
    assert list((data / "u-bravo" / "soul_versions").iterdir()) == []


def test_soul_edit_snapshot_is_exclusive(data):
    from tinyassets.soul_edit import _atomic_write_text

    path = _alpha(data) / "soul_versions" / "0001.md"
    _atomic_write_text(path, "first", mode="exclusive")
    with pytest.raises(FileExistsError):
        _atomic_write_text(path, "second", mode="exclusive")
    assert path.read_text(encoding="utf-8") == "first"


def test_write_universe_soul_refuses_rather_than_rebuilding_over_a_refused_read(data):
    from tinyassets.universe_soul import read_universe_soul, write_universe_soul

    (data / "u-bravo" / "soul.md").write_text(FOREIGN, encoding="utf-8")
    _link(data / "u-bravo" / "soul.md", _alpha(data) / "soul.md")
    assert read_universe_soul(_alpha(data)) is None  # display reads still degrade
    with pytest.raises(OSError):
        write_universe_soul(_alpha(data), purpose="alpha purpose")
    assert (data / "u-bravo" / "soul.md").read_text(encoding="utf-8") == FOREIGN


def test_priority_review_reports_a_refused_signal_queue(data):
    from domains.fantasy_daemon.phases.foundation_priority_review import (
        foundation_priority_review,
    )
    from tinyassets.enrichment_signals import enrichment_signals_path

    bravo_signals = enrichment_signals_path(data / "u-bravo")
    bravo_signals.write_text(json.dumps([{"secret": FOREIGN}]), encoding="utf-8")
    _link(bravo_signals, enrichment_signals_path(_alpha(data)))
    out = foundation_priority_review({"universe_path": str(_alpha(data))})
    assert out["quality_trace"][0]["action"] == "foundation_review_signals_unreadable"
    assert json.loads(bravo_signals.read_text(encoding="utf-8")) == [{"secret": FOREIGN}]


def test_a_dangling_link_at_the_signal_name_is_read_not_skipped(data):
    from tinyassets.enrichment_signals import enrichment_signals_path, load_enrichment_signals

    _link(data / "u-bravo" / "nowhere.json", enrichment_signals_path(_alpha(data)))
    with pytest.raises(RuntimeError):
        load_enrichment_signals(_alpha(data), strict=True)


def test_non_posix_exclusive_reports_an_existing_entry_as_file_exists(data, monkeypatch):
    monkeypatch.setattr(universe_files.fs, "_POSIX", False)
    path = _alpha(data) / "bug-001.md"
    path.write_text("taken", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_data_path(path, "mine", mode="exclusive")
    link = _alpha(data) / "bug-002.md"
    _link(data / "u-bravo" / "founder.md", link)
    with pytest.raises(FileExistsError):
        write_data_path(link, "mine", mode="exclusive")
    assert _bravo_founder(data) == FOREIGN
