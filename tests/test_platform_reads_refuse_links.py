"""The daemon's platform-file reads never follow a link planted in a universe.

A workflow provider jail binds its universe read-write and allows ``symlink``
(codex's nested sandbox needs it), so universe A's provider can plant
``activity.log -> /data/<B>/founder.md``. Before this, ``inspect`` read it with
a plain ``read_text`` and returned B's lines to A's owner
(``docs/concerns/2026-10-01-provider-planted-link-reads-another-universe.md``).
These tests plant the links the jail allows and assert B's bytes never come back.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import tinyassets.api.universe as us
from tinyassets.api.helpers import _read_json, _read_text

FOREIGN = "B-SECRET founder line"


def _link(target: Path, link: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("this host cannot create a symlink")


@pytest.fixture
def data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / "data"
    (base / "u-alpha").mkdir(parents=True)
    bravo = base / "u-bravo"
    (bravo / "output").mkdir(parents=True)
    (bravo / "canon" / "sources").mkdir(parents=True)
    (bravo / "founder.md").write_text(FOREIGN + "\n", encoding="utf-8")
    (bravo / "work_targets.json").write_text(json.dumps({"secret": FOREIGN}), encoding="utf-8")
    (bravo / "output" / "draft.md").write_text(FOREIGN, encoding="utf-8")
    (bravo / "canon" / "lore.md").write_text(FOREIGN, encoding="utf-8")
    (bravo / "canon" / "sources" / "upload.md").write_text(FOREIGN, encoding="utf-8")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    return base


def _alpha(data: Path) -> Path:
    return (data / "u-alpha").resolve()


def test_a_linked_activity_log_reads_as_absent(data):
    _link(data / "u-bravo" / "founder.md", _alpha(data) / "activity.log")
    assert _read_text(_alpha(data) / "activity.log") == ""


def test_a_linked_directory_on_the_path_is_refused(data):
    _link(data / "u-bravo", _alpha(data) / "logs")
    assert _read_text(_alpha(data) / "logs" / "founder.md", "absent") == "absent"


def test_a_linked_json_record_reads_as_none(data):
    _link(data / "u-bravo" / "work_targets.json", _alpha(data) / "work_targets.json")
    assert _read_json(_alpha(data) / "work_targets.json") is None


def test_a_real_platform_file_still_reads(data):
    udir = _alpha(data)
    (udir / "activity.log").write_bytes(b"one\r\ntwo\n")
    (udir / "work_targets.json").write_text('{"ok": true}', encoding="utf-8")
    assert _read_text(udir / "activity.log") == "one\ntwo\n"
    assert _read_json(udir / "work_targets.json") == {"ok": True}
    assert _read_text(udir / "missing.log", "none") == "none"
    assert _read_json(udir / "missing.json") is None


def test_a_path_under_an_unresolved_data_dir_spelling_is_still_link_free(data, monkeypatch):
    """``_universe_dir`` resolves; the data dir env var may not be. Either
    spelling of the root must take the link-free route, never the plain one."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(data / "u-alpha" / ".."))
    _link(data / "u-bravo" / "founder.md", _alpha(data) / "activity.log")
    assert _read_text(_alpha(data) / "activity.log") == ""


def test_read_output_refuses_a_linked_output_dir(data, monkeypatch):
    monkeypatch.setattr(us, "_request_universe", lambda _uid: "u-alpha")
    _link(data / "u-bravo" / "output", _alpha(data) / "output")
    out = us._action_read_output(universe_id="u-alpha", path="draft.md")
    assert FOREIGN not in out
    assert "error" in json.loads(out)


def test_read_output_refuses_traversal_and_reads_a_real_file(data, monkeypatch):
    monkeypatch.setattr(us, "_request_universe", lambda _uid: "u-alpha")
    (_alpha(data) / "output").mkdir()
    (_alpha(data) / "output" / "note.md").write_text("hello", encoding="utf-8")
    ok = json.loads(us._action_read_output(universe_id="u-alpha", path="note.md"))
    assert ok["content"] == "hello"
    for bad in ("../u-bravo/founder.md", "/etc/passwd", "", "a//b"):
        out = json.loads(us._action_read_output(universe_id="u-alpha", path=bad))
        assert out == {"error": "Path traversal not allowed."}
    missing = json.loads(us._action_read_output(universe_id="u-alpha", path="nope.md"))
    assert missing["error"].startswith("File not found")


def test_read_canon_refuses_a_linked_canon_dir(data, monkeypatch):
    monkeypatch.setattr(us, "_request_universe", lambda _uid: "u-alpha")
    _link(data / "u-bravo" / "canon", _alpha(data) / "canon")
    canon = us._action_read_canon(universe_id="u-alpha", filename="lore.md")
    assert FOREIGN not in canon
    source = us._action_read_source(universe_id="u-alpha", filename="upload.md")
    assert FOREIGN not in source


def test_read_canon_still_reads_a_real_file(data, monkeypatch):
    monkeypatch.setattr(us, "_request_universe", lambda _uid: "u-alpha")
    (_alpha(data) / "canon").mkdir()
    (_alpha(data) / "canon" / "lore.md").write_bytes(b"alpha lore\r\n")
    out = json.loads(us._action_read_canon(universe_id="u-alpha", filename="lore.md"))
    assert out["content"] == "alpha lore\n"
